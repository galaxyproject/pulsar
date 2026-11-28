"""Tests for how Pulsar's postprocessing treats an output file that does not exist."""
import os
import time
from unittest import mock

import pytest

from pulsar.client import util as client_util
from pulsar.client.action_mapper import RemoteCopyAction
from pulsar.client.transport.transient import is_transient_http_error
from pulsar.managers.staging.post import (
    postprocess,
    PulsarServerOutputCollector,
)
from pulsar.managers.util import retry as retry_module
from pulsar.managers.util.retry import RetryActionExecutor
from .test_utils import (
    temp_directory,
    temp_job_directory,
)

WORK_DIR_OUTPUT = "Log.final.out"


class _RecordingExecutor(RetryActionExecutor):
    """The postprocess executor as production configures it, recording its backoff retries."""

    def __init__(self):
        self.retried = []
        super().__init__(
            max_retries=10,
            interval_start=2,
            interval_step=2,
            interval_max=60,
            should_retry=is_transient_http_error,
            errback=lambda exc, interval, description=None: self.retried.append(exc),
        )


@pytest.fixture
def sleeps():
    """Patch both sleeps: the NFS revalidation's and the backoff executor's."""
    with mock.patch.object(time, "sleep") as nfs_sleep, \
            mock.patch.object(retry_module, "sleep") as backoff_sleep:
        yield nfs_sleep, backoff_sleep


def _store_launch_config(job_directory, client_directory, work_dir_outputs=(WORK_DIR_OUTPUT,)):
    """Stage outputs back with remote_copy; Galaxy expects from_work_dir outputs."""
    galaxy_working_directory = os.path.join(client_directory, "working")
    galaxy_outputs = [
        os.path.join(client_directory, f"dataset_{i}.dat") for i in range(1, len(work_dir_outputs) + 1)
    ]
    job_directory.store_metadata(
        "launch_config",
        {
            "remote_staging": {
                "action_mapper": {"default_action": "remote_copy"},
                "client_outputs": {
                    "working_directory": galaxy_working_directory,
                    "job_directory": client_directory,
                    "output_files": list(galaxy_outputs),
                    "work_dir_outputs": [
                        [os.path.join(galaxy_working_directory, name), galaxy_output]
                        for name, galaxy_output in zip(work_dir_outputs, galaxy_outputs)
                    ],
                },
            }
        },
    )
    return galaxy_outputs[0]


def test_missing_work_dir_output_is_not_retried_by_the_backoff_executor(sleeps):
    """A tool that failed before writing a from_work_dir output (STAR's Log.final.out,
    or a job killed by the DRM) must not hold the job - and its postprocess slot - for
    the whole backoff schedule. Only the short NFS revalidation retries run, then the
    missing output is an allowed failure as before."""
    nfs_sleep, backoff_sleep = sleeps
    with temp_directory() as client_directory, temp_job_directory() as job_directory:
        job_directory.setup()
        galaxy_output = _store_launch_config(job_directory, client_directory)
        executor = _RecordingExecutor()

        assert postprocess(job_directory, executor, lambda: False)

        assert executor.retried == []
        backoff_sleep.assert_not_called()
        assert nfs_sleep.call_args_list == (
            [mock.call(client_util.OUTPUT_COLLECTION_RETRY_SLEEP)]
            * client_util.DEFAULT_OUTPUT_COLLECTION_RETRIES
        )
        assert not os.path.exists(galaxy_output)


def test_work_dir_output_visible_after_nfs_revalidation_is_collected(sleeps):
    """A file the compute node wrote moments ago may only become visible once the
    Pulsar host's NFS client revalidates the directory; it is then collected."""
    nfs_sleep, backoff_sleep = sleeps
    with temp_directory() as client_directory, temp_job_directory() as job_directory:
        job_directory.setup()
        galaxy_output = _store_launch_config(job_directory, client_directory)
        pulsar_path = job_directory.calculate_path(WORK_DIR_OUTPUT, "output_workdir")

        def appears_while_sleeping(seconds):
            with open(pulsar_path, "w") as fh:
                fh.write("Uniquely mapped reads %")

        nfs_sleep.side_effect = appears_while_sleeping
        executor = _RecordingExecutor()

        assert postprocess(job_directory, executor, lambda: False)

        nfs_sleep.assert_called_once_with(client_util.OUTPUT_COLLECTION_RETRY_SLEEP)
        assert executor.retried == []
        with open(galaxy_output) as fh:
            assert fh.read() == "Uniquely mapped reads %"


def test_several_missing_outputs_in_one_directory_wait_once(sleeps):
    """Revalidating a directory once is enough: a job killed before writing its 4
    from_work_dir outputs waits for the first, then the others fail at once."""
    nfs_sleep, backoff_sleep = sleeps
    with temp_directory() as client_directory, temp_job_directory() as job_directory:
        job_directory.setup()
        names = [f"output_{i}.qza" for i in range(4)]
        _store_launch_config(job_directory, client_directory, names)
        executor = _RecordingExecutor()

        assert postprocess(job_directory, executor, lambda: False)

        assert nfs_sleep.call_count == client_util.DEFAULT_OUTPUT_COLLECTION_RETRIES
        assert executor.retried == []
        backoff_sleep.assert_not_called()


def test_missing_output_in_another_directory_still_waits(sleeps):
    """The wait is paid once per directory: revalidating the working directory says
    nothing about the outputs directory, so a miss there gets its own checks."""
    nfs_sleep, _ = sleeps
    with temp_directory() as client_directory, temp_job_directory() as job_directory:
        job_directory.setup()
        collector = PulsarServerOutputCollector(job_directory, _RecordingExecutor(), lambda: False)
        work_dir_action = RemoteCopyAction({"path": os.path.join(client_directory, WORK_DIR_OUTPUT)})
        output_action = RemoteCopyAction({"path": os.path.join(client_directory, "dataset_1.dat")})

        with pytest.raises(FileNotFoundError):
            collector.collect_output(None, "output_workdir", work_dir_action, WORK_DIR_OUTPUT)
        with pytest.raises(FileNotFoundError):
            collector.collect_output(None, "output", output_action, "dataset_1.dat")

        assert nfs_sleep.call_count == 2 * client_util.DEFAULT_OUTPUT_COLLECTION_RETRIES


@pytest.mark.parametrize("retries", [0, 2])
def test_missing_output_retries_are_configurable(sleeps, retries):
    """``output_collection_retries`` bounds the NFS revalidation, ``0`` disables it."""
    nfs_sleep, _ = sleeps
    with temp_directory() as client_directory, temp_job_directory() as job_directory:
        job_directory.setup()
        _store_launch_config(job_directory, client_directory)

        assert postprocess(
            job_directory, _RecordingExecutor(), lambda: False, output_collection_retries=retries
        )

        assert nfs_sleep.call_count == retries


def test_missing_regular_output_still_fails_collection(sleeps):
    """Only from_work_dir outputs may be missing: for any other output the
    FileNotFoundError still propagates, without the backoff retries."""
    nfs_sleep, backoff_sleep = sleeps
    with temp_directory() as client_directory, temp_job_directory() as job_directory:
        job_directory.setup()
        action = RemoteCopyAction({"path": os.path.join(client_directory, "dataset_1.dat")})
        executor = _RecordingExecutor()
        collector = PulsarServerOutputCollector(job_directory, executor, lambda: False)

        with pytest.raises(FileNotFoundError, match=r"dataset_1\.dat"):
            collector.collect_output(None, "output", action, "dataset_1.dat")

        assert executor.retried == []
        backoff_sleep.assert_not_called()
        assert nfs_sleep.call_count == client_util.DEFAULT_OUTPUT_COLLECTION_RETRIES


def test_cancelled_job_does_not_wait_for_missing_output(sleeps):
    nfs_sleep, _ = sleeps
    with temp_directory() as client_directory, temp_job_directory() as job_directory:
        job_directory.setup()
        action = RemoteCopyAction({"path": os.path.join(client_directory, "dataset_1.dat")})
        collector = PulsarServerOutputCollector(job_directory, _RecordingExecutor(), lambda: True)

        collector.collect_output(None, "output", action, "dataset_1.dat")

        nfs_sleep.assert_not_called()


def test_job_cancelled_during_the_wait_skips_the_missing_output(sleeps):
    """Cancelling while the NFS checks wait skips the output, as the executor does,
    rather than turning it into a collection failure."""
    nfs_sleep, _ = sleeps
    with temp_directory() as client_directory, temp_job_directory() as job_directory:
        job_directory.setup()
        action = RemoteCopyAction({"path": os.path.join(client_directory, "dataset_1.dat")})
        cancelled = []
        nfs_sleep.side_effect = lambda _seconds: cancelled.append(True)
        collector = PulsarServerOutputCollector(job_directory, _RecordingExecutor(), lambda: bool(cancelled))

        collector.collect_output(None, "output", action, "dataset_1.dat")

        assert nfs_sleep.call_count == 1


def test_transient_transfer_errors_are_still_retried(sleeps):
    """An output that exists but fails to transfer keeps the backoff retries."""
    _, backoff_sleep = sleeps
    with temp_directory() as client_directory, temp_job_directory() as job_directory:
        job_directory.setup()
        with open(job_directory.calculate_path("dataset_1.dat", "output"), "w") as fh:
            fh.write("contents")
        destination = os.path.join(client_directory, "dataset_1.dat")
        action = RemoteCopyAction({"path": destination})
        real_write_from_path = action.write_from_path
        attempts = []

        def fails_once(pulsar_path):
            attempts.append(pulsar_path)
            if len(attempts) == 1:
                raise ConnectionError("Galaxy restarting")
            real_write_from_path(pulsar_path)

        executor = _RecordingExecutor()
        collector = PulsarServerOutputCollector(job_directory, executor, lambda: False)
        with mock.patch.object(action, "write_from_path", side_effect=fails_once):
            collector.collect_output(None, "output", action, "dataset_1.dat")

        assert len(executor.retried) == 1
        backoff_sleep.assert_called_once_with(2.0)
        with open(destination) as fh:
            assert fh.read() == "contents"
