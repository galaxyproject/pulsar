"""The arguments a coexecution client gives the pulsar-submit and pulsar-finish containers.

Container runtimes exec these scripts with the launch message as one argument,
and Linux refuses an argument longer than 131071 bytes (MAX_ARG_STRLEN less
the terminating NUL). Every staged input adds about 1.2 KB to the plain
base64 message, so a job with about 110 inputs could not start.
"""
import uuid
from types import SimpleNamespace

import pytest

from pulsar.client.coexecution import (
    BaseMessageCoexecutionJobClient,
    CoexecutionLaunchMixin,
    ExecutionType,
)
from pulsar.scripts import (
    finish,
    submit,
)
from pulsar.scripts.submit_util import _load_job_config

LONGEST_ARGUMENT = 131071
JOB_ID = "45"
FILES_ENDPOINT = "http://galaxy.example.org/api/jobs/f2db41e1fa331b3e/files?job_key=0123456789abcdef"
SCRIPTS = {
    "pulsar-submit": (submit, "run_server_for_job"),
    "pulsar-finish": (finish, "run_server_for_job_finish"),
}


class RecordingCoexecutionClient(BaseMessageCoexecutionJobClient, CoexecutionLaunchMixin):
    execution_type = ExecutionType.SEQUENTIAL

    def _launch_containers(self, pulsar_submit_container, tool_container, pulsar_finish_container):
        self.containers = (pulsar_submit_container, tool_container, pulsar_finish_container)


def _launch(n_inputs):
    client = RecordingCoexecutionClient({}, JOB_ID, SimpleNamespace(manager_name="_default_"))
    remote_staging = _remote_staging(n_inputs)
    client.launch(
        "cat inputs/* > outputs/out.dat",
        remote_staging=remote_staging,
        container_info={"container_id": "busybox:1.36"},
    )
    return client.containers, remote_staging


def _remote_staging(n_inputs):
    """Staging setup shaped like Galaxy's: one remote_transfer action per input dataset."""
    setup = []
    for i in range(n_inputs):
        dataset_uuid = str(uuid.uuid4())
        path = "/galaxy/database/objects/%s/%s/%s/dataset_%s.dat" % (
            dataset_uuid[0], dataset_uuid[1], dataset_uuid[2], dataset_uuid
        )
        setup.append({
            "name": "dataset_%s.dat" % dataset_uuid,
            "type": "input",
            "action": {
                "path": path,
                "source": {"path": path, "object_store_ref": {
                    "dataset_id": 1000 + i, "dataset_uuid": dataset_uuid, "object_store_id": None,
                }},
                "action_type": "remote_transfer",
                "url": "%s&path=%s&file_type=input" % (FILES_ENDPOINT, path.replace("/", "%2F")),
            },
        })
    return {
        "setup": setup,
        "action_mapper": {"default_action": "remote_transfer", "files_endpoint": FILES_ENDPOINT},
        "client_outputs": {"working_directory": "/galaxy/jobs/45/working", "output_files": []},
    }


def _job_config(monkeypatch, container):
    """Parse the container's arguments with its script's own parser and read the job message."""
    script, runner = SCRIPTS[container.command]
    parsed_args = []
    monkeypatch.setattr(script, runner, parsed_args.append)
    script.main(container.args)
    return _load_job_config(parsed_args[0])


def _staged_inputs(job_config):
    return [entry["name"] for entry in job_config["remote_staging"]["setup"]]


def test_small_launch_message_stays_plain_base64(monkeypatch):
    # Staging images without the compressed form keep working for every job that fits.
    (submit_container, _, _), remote_staging = _launch(3)
    assert "--base64" in submit_container.args
    assert "--base64_zlib" not in submit_container.args
    assert _staged_inputs(_job_config(monkeypatch, submit_container)) == [entry["name"] for entry in remote_staging["setup"]]


@pytest.mark.parametrize("n_inputs", [300, 1000])
def test_large_launch_message_fits_in_one_argument(monkeypatch, n_inputs):
    (submit_container, _, finish_container), remote_staging = _launch(n_inputs)
    assert max(len(arg) for arg in submit_container.args) <= LONGEST_ARGUMENT
    assert max(len(arg) for arg in finish_container.args) <= LONGEST_ARGUMENT
    assert _staged_inputs(_job_config(monkeypatch, submit_container)) == [entry["name"] for entry in remote_staging["setup"]]


def test_compressed_launch_message_survives_path_normalization():
    # Some TES servers (tesp-api) parse executor arguments as paths, which
    # collapses "//" and drops a trailing "/". Standard base64 of compressed
    # data contains both; the URL-safe alphabet has no "/".
    (submit_container, _, _), _ = _launch(1000)
    message = submit_container.args[submit_container.args.index("--base64_zlib") + 1]
    assert "/" not in message


def test_finish_container_gets_only_the_job_id(monkeypatch):
    # pulsar-finish reads the job id; pulsar-submit persisted the rest in the job directory.
    (_, _, finish_container), _ = _launch(300)
    assert _job_config(monkeypatch, finish_container) == {"job_id": JOB_ID}


def test_launch_message_too_large_even_compressed_fails_at_launch():
    # A clear error in Galaxy instead of a TES task that can't start its first container.
    with pytest.raises(Exception, match="too large"):
        _launch(3000)
