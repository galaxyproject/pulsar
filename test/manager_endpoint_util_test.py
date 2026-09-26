"""Tests for manager_endpoint_util.

The submit-message idempotency guard: when an AMQP setup message is redelivered
(after a Pulsar SIGKILL between setup_job and message.ack(), for example),
submit_job must NOT re-run the job. Once ``launch_config`` metadata is present
on disk, the redelivered message is a no-op.
"""
from unittest.mock import Mock

import pytest

from pulsar import manager_endpoint_util


class _FakeJobDirectory:
    def __init__(self, exists=True, metadata=None, path="/staging/j1"):
        self._exists = exists
        self._metadata = dict(metadata or {})
        self.path = path

    def exists(self):
        return self._exists

    def has_metadata(self, name):
        return name in self._metadata

    def _sub(self, name):
        return "%s/%s" % (self.path, name)

    def inputs_directory(self):
        return self._sub("inputs")

    def working_directory(self):
        return self._sub("working")

    def metadata_directory(self):
        return self._sub("metadata")

    def outputs_directory(self):
        return self._sub("outputs")

    def configs_directory(self):
        return self._sub("configs")

    def tool_files_directory(self):
        return self._sub("tool_files")

    def unstructured_files_directory(self):
        return self._sub("unstructured")


class _FakeActiveJobs:
    def __init__(self, active=()):
        self._active = set(active)

    def active_job_ids(self, active_status=None):
        return list(self._active)


class _FakeManager:
    def __init__(self, job_directory, active_jobs=None):
        self._jd = job_directory
        self.handle_failure_calls = 0
        self.preprocess_and_launch_calls = 0
        self.setup_job_calls = 0
        self.active_jobs = active_jobs or _FakeActiveJobs()
        self.launch_config = None

    def job_directory(self, job_id):
        return self._jd

    def touch_outputs(self, job_id, names):
        pass

    def preprocess_and_launch(self, job_id, launch_config):
        self.preprocess_and_launch_calls += 1
        self.launch_config = launch_config

    def handle_failure_before_launch(self, job_id):
        self.handle_failure_calls += 1

    def setup_job(self, *args, **kwargs):
        self.setup_job_calls += 1
        return "j1"

    def system_properties(self):
        return {}


def _job_config(job_id="j1", **overrides):
    cfg = {
        "job_id": job_id,
        "command_line": "echo ok",
        "remote_staging": {},
    }
    cfg.update(overrides)
    return cfg


def _completed_manager(stdout=b"tool stdout", stderr=b"tool stderr", live_stdout_update=False):
    job_directory = Mock(job_directory="/jobs/j1")
    job_directory.working_directory.return_value = "/jobs/j1/working"
    job_directory.metadata_directory.return_value = "/jobs/j1/metadata"
    job_directory.working_directory_contents.return_value = ["working.txt"]
    job_directory.metadata_directory_contents.return_value = ["metadata.txt"]
    job_directory.outputs_directory_contents.return_value = ["output.txt"]
    job_directory.job_directory_contents.return_value = ["working", "metadata", "outputs"]
    job_directory.load_metadata.return_value = None

    manager = Mock()
    manager.return_code.return_value = 0
    manager.stdout_contents.return_value = stdout
    manager.stderr_contents.return_value = stderr
    manager.job_stdout_contents.return_value = b"job stdout"
    manager.job_stderr_contents.return_value = b"job stderr"
    manager.job_directory.return_value = job_directory
    manager.system_properties.return_value = {"separator": "/"}
    manager.is_live_stdout_update.return_value = live_stdout_update
    return manager


def test_completed_status_preserves_short_tool_streams_and_metadata():
    result = manager_endpoint_util.full_status(_completed_manager(), "complete", "j1")

    assert result["stdout"] == "tool stdout"
    assert result["stderr"] == "tool stderr"
    assert result["job_stdout"] == "job stdout"
    assert result["job_stderr"] == "job stderr"
    assert result["returncode"] == 0
    assert result["working_directory_contents"] == ["working.txt"]
    assert result["metadata_directory_contents"] == ["metadata.txt"]
    assert result["outputs_directory_contents"] == ["output.txt"]
    assert result["job_directory_contents"] == ["working", "metadata", "outputs"]


def test_completed_status_caps_tool_streams_at_64_kib():
    stream_limit = manager_endpoint_util.MAXIMUM_STATUS_STREAM_SIZE
    manager = _completed_manager(
        stdout=b"o" * (stream_limit + 1),
        stderr=b"e" * (stream_limit + 1),
    )

    result = manager_endpoint_util.full_status(manager, "complete", "j1")

    assert result["stdout"] == "o" * stream_limit
    assert result["stderr"] == "e" * stream_limit


def test_completed_status_omits_tool_streams_already_delivered_live():
    result = manager_endpoint_util.full_status(
        _completed_manager(live_stdout_update=True), "complete", "j1"
    )

    assert result["stdout"] is None
    assert result["stderr"] is None
    assert result["job_stdout"] == "job stdout"
    assert result["job_stderr"] == "job stderr"


def test_first_setup_proceeds_to_preprocess_and_launch():
    jd = _FakeJobDirectory(exists=True, metadata={})  # launch_config not yet stored
    mgr = _FakeManager(jd)
    manager_endpoint_util.submit_job(mgr, _job_config())
    assert mgr.preprocess_and_launch_calls == 1
    assert mgr.handle_failure_calls == 0


def test_redelivered_setup_with_terminal_status_is_noop():
    """Job already completed: redelivery must not re-run anything."""
    jd = _FakeJobDirectory(
        exists=True,
        metadata={"launch_config": True, "final_status": "complete"},
    )
    mgr = _FakeManager(jd)
    manager_endpoint_util.submit_job(mgr, _job_config())
    assert mgr.preprocess_and_launch_calls == 0


def test_redelivered_setup_for_active_job_is_noop():
    """Job is in active_jobs (recover_active_jobs will resume it)."""
    jd = _FakeJobDirectory(exists=True, metadata={"launch_config": True})
    mgr = _FakeManager(jd, active_jobs=_FakeActiveJobs(active={"j1"}))
    manager_endpoint_util.submit_job(mgr, _job_config())
    assert mgr.preprocess_and_launch_calls == 0


def test_redelivered_setup_after_crash_between_launch_config_and_activate_replays():
    """The narrow loss window: launch_config exists but no active_jobs entry
    and no terminal status. Recovery cannot resume the job, so the
    redelivered setup must drive a fresh preprocess_and_launch."""
    jd = _FakeJobDirectory(exists=True, metadata={"launch_config": True})
    mgr = _FakeManager(jd, active_jobs=_FakeActiveJobs(active=set()))
    manager_endpoint_util.submit_job(mgr, _job_config())
    assert mgr.preprocess_and_launch_calls == 1


def test_setup_when_directory_does_not_exist_proceeds_normally():
    jd = _FakeJobDirectory(exists=False, metadata={})
    mgr = _FakeManager(jd)
    manager_endpoint_util.submit_job(mgr, _job_config())
    assert mgr.preprocess_and_launch_calls == 1


def test_missing_job_id_does_not_short_circuit():
    jd = _FakeJobDirectory(exists=True, metadata={"launch_config": True})
    mgr = _FakeManager(jd)
    cfg = _job_config()
    cfg.pop("job_id")
    # Without a job_id the duplicate check is skipped; preprocess_and_launch
    # is invoked with job_id=None and may fail downstream, but the guard
    # itself must not raise.
    try:
        manager_endpoint_util.submit_job(mgr, cfg)
    except Exception:
        pass
    assert mgr.preprocess_and_launch_calls + mgr.handle_failure_calls >= 1


def _submit_with_setup(command_line, job_directory="/staging/j1"):
    """Drive submit_job down the branch that used to run token substitution.

    Substitution only ran when ``setup_params`` was present, so these tests
    have to send them.
    """
    jd = _FakeJobDirectory(exists=True, metadata={}, path=job_directory)
    mgr = _FakeManager(jd)
    manager_endpoint_util.submit_job(
        mgr, _job_config(command_line=command_line, setup_params={"job_id": "j1"})
    )
    return mgr.launch_config["command_line"]


def test_job_directory_token_is_still_substituted():
    """The singular, per-job token survives the removal of the plural one."""
    assert _submit_with_setup("cat __PULSAR_JOB_DIRECTORY__/configs/x") == (
        "cat /staging/j1/configs/x"
    )


def test_removed_jobs_directory_token_is_rejected():
    """__PULSAR_JOBS_DIRECTORY__ was removed; a destination still using it fails
    loudly rather than staging into a directory named for the token."""
    with pytest.raises(Exception) as exc_info:
        _submit_with_setup("cat __PULSAR_JOBS_DIRECTORY__/j1/configs/x")
    message = str(exc_info.value)
    assert "__PULSAR_JOBS_DIRECTORY__" in message
    assert "jobs_directory" in message
