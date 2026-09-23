"""Tests for the transfer metrics Pulsar records for Galaxy's ``pulsar_transfer`` plugin."""
import json
import os

from pulsar.client.action_mapper import (
    NoneAction,
    RemoteCopyAction,
)
from pulsar.managers.staging.metrics import (
    POSTPROCESS,
    PREPROCESS,
    record_transfer,
    transfer_metrics_file_name,
)
from pulsar.managers.staging.post import (
    postprocess,
    PulsarServerOutputCollector,
)
from pulsar.managers.staging.pre import preprocess
from pulsar.managers.util.retry import RetryActionExecutor
from .test_utils import (
    temp_directory,
    temp_job_directory,
)

CONTENTS = "0123456789"


def _recorded(job_directory, phase):
    path = os.path.join(
        job_directory.metadata_directory(), transfer_metrics_file_name(phase)
    )
    with open(path) as fh:
        return json.load(fh)


def test_file_name_matches_the_galaxy_plugin():
    assert transfer_metrics_file_name(PREPROCESS) == "__instrument_pulsar_transfer_preprocess"
    assert transfer_metrics_file_name(POSTPROCESS) == "__instrument_pulsar_transfer_postprocess"


def test_records_files_and_bytes():
    with temp_job_directory() as job_directory:
        job_directory.setup()
        staged = os.path.join(job_directory.job_directory, "staged.dat")
        with open(staged, "w") as fh:
            fh.write(CONTENTS)
        with record_transfer(job_directory, PREPROCESS) as metrics:
            metrics.record_file(staged)
            metrics.record_file(staged)
        recorded = _recorded(job_directory, PREPROCESS)
        assert recorded["files"] == 2
        assert recorded["bytes"] == 2 * len(CONTENTS)
        assert recorded["seconds"] >= 0


def test_records_a_file_that_cannot_be_sized():
    with temp_job_directory() as job_directory:
        job_directory.setup()
        with record_transfer(job_directory, PREPROCESS) as metrics:
            metrics.record_file(os.path.join(job_directory.job_directory, "gone.dat"))
        recorded = _recorded(job_directory, PREPROCESS)
        assert recorded["files"] == 1
        assert recorded["bytes"] == 0


def test_records_what_a_failed_phase_managed():
    with temp_job_directory() as job_directory:
        job_directory.setup()
        try:
            with record_transfer(job_directory, PREPROCESS) as metrics:
                metrics.record_file(os.path.join(job_directory.job_directory, "gone.dat"))
                raise Exception("staging blew up")
        except Exception:
            pass
        assert _recorded(job_directory, PREPROCESS)["files"] == 1


def test_preprocess_records_staged_inputs():
    with temp_directory() as client_directory, temp_job_directory() as job_directory:
        job_directory.setup()
        source = os.path.join(client_directory, "input.dat")
        with open(source, "w") as fh:
            fh.write(CONTENTS)
        setup_actions = [
            {
                "name": "input.dat",
                "type": "input",
                "action": {"path": source, "action_type": "remote_copy", "source": {"path": source}},
            }
        ]
        preprocess(job_directory, setup_actions, RetryActionExecutor(), lambda: False)
        recorded = _recorded(job_directory, PREPROCESS)
        assert recorded["files"] == 1
        assert recorded["bytes"] == len(CONTENTS)


def test_postprocess_records_and_stages_out_its_own_metrics():
    with temp_directory() as client_directory, temp_job_directory() as job_directory:
        job_directory.setup()
        client_metadata_directory = os.path.join(client_directory, "metadata")
        os.makedirs(client_metadata_directory)
        output_name = "output.dat"
        pulsar_output = job_directory.calculate_path(output_name, "output")
        with open(pulsar_output, "w") as fh:
            fh.write(CONTENTS)
        job_directory.store_metadata(
            "launch_config",
            {
                "remote_staging": {
                    "action_mapper": {"default_action": "remote_copy"},
                    "client_outputs": {
                        "working_directory": os.path.join(client_directory, "working"),
                        "metadata_directory": client_metadata_directory,
                        "job_directory": client_directory,
                        "output_files": [os.path.join(client_directory, output_name)],
                    },
                }
            },
        )
        assert postprocess(job_directory, RetryActionExecutor(), lambda: False)

        recorded = _recorded(job_directory, POSTPROCESS)
        assert recorded["files"] == 1
        assert recorded["bytes"] == len(CONTENTS)
        staged_back = os.path.join(
            client_metadata_directory, transfer_metrics_file_name(POSTPROCESS)
        )
        assert os.path.exists(staged_back)
        with open(staged_back) as fh:
            assert json.load(fh) == recorded


def test_postprocess_does_not_count_shared_filesystem_output():
    with temp_job_directory() as job_directory:
        job_directory.setup()
        output_name = "output.dat"
        pulsar_output = job_directory.calculate_path(output_name, "output")
        with open(pulsar_output, "w") as fh:
            fh.write(CONTENTS)
        action = NoneAction({"path": pulsar_output})
        with record_transfer(job_directory, POSTPROCESS) as metrics:
            collector = PulsarServerOutputCollector(
                job_directory, RetryActionExecutor(), lambda: False, metrics
            )
            collector.collect_output(None, "output", action, output_name)
        recorded = _recorded(job_directory, POSTPROCESS)
        assert recorded["files"] == 0
        assert recorded["bytes"] == 0


def test_postprocess_does_not_count_cancelled_output():
    with temp_directory() as client_directory, temp_job_directory() as job_directory:
        job_directory.setup()
        output_name = "output.dat"
        pulsar_output = job_directory.calculate_path(output_name, "output")
        with open(pulsar_output, "w") as fh:
            fh.write(CONTENTS)
        destination = os.path.join(client_directory, output_name)
        action = RemoteCopyAction({"path": destination})
        with record_transfer(job_directory, POSTPROCESS) as metrics:
            collector = PulsarServerOutputCollector(
                job_directory, RetryActionExecutor(), lambda: True, metrics
            )
            collector.collect_output(None, "output", action, output_name)
        recorded = _recorded(job_directory, POSTPROCESS)
        assert recorded["files"] == 0
        assert recorded["bytes"] == 0
        assert not os.path.exists(destination)
