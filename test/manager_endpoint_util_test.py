"""Tests for the manager_endpoint_util submit-message idempotency guard.

When an AMQP setup message is redelivered (after a Pulsar SIGKILL between
setup_job and message.ack(), for example), submit_job must NOT re-run the
job. Once ``launch_config`` metadata is present on disk, the redelivered
message is a no-op.
"""
from pulsar import manager_endpoint_util
from pulsar.client.job_directory import RemoteJobDirectory


class _FakeJobDirectory:
    def __init__(self, exists=True, metadata=None):
        self._exists = exists
        self._metadata = dict(metadata or {})

    def exists(self):
        return self._exists

    def has_metadata(self, name):
        return name in self._metadata


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

    def job_directory(self, job_id):
        return self._jd

    def touch_outputs(self, job_id, names):
        pass

    def preprocess_and_launch(self, job_id, launch_config):
        self.preprocess_and_launch_calls += 1

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


class _StagingJobDirectory(RemoteJobDirectory):
    """Real path arithmetic, plus the two methods the duplicate-setup guard uses."""

    def exists(self):
        return False

    def has_metadata(self, name):
        return False


class _RecordingManager(_FakeManager):
    """Captures the launch_config so command-line rewriting can be asserted."""

    def __init__(self, job_directory, staging_directory="/staging"):
        super().__init__(job_directory)
        self._staging_directory = staging_directory
        self.launch_config = None

    def job_directory(self, job_id):
        return _StagingJobDirectory(self._staging_directory, job_id or "j1", "/")

    def preprocess_and_launch(self, job_id, launch_config):
        super().preprocess_and_launch(job_id, launch_config)
        self.launch_config = launch_config


def _submit_with_setup(command_line, staging_directory="/staging"):
    mgr = _RecordingManager(_FakeJobDirectory(exists=False), staging_directory)
    cfg = _job_config(command_line=command_line, setup_params={"job_id": "j1"})
    manager_endpoint_util.submit_job(mgr, cfg)
    return mgr.launch_config["command_line"]


def test_command_line_jobs_directory_token_is_substituted():
    rewritten = _submit_with_setup("cat __PULSAR_JOBS_DIRECTORY__/j1/configs/x")
    assert "__PULSAR_JOBS_DIRECTORY__" not in rewritten
    assert rewritten.endswith("/staging/j1/configs/x")


def test_command_line_job_directory_token_is_substituted():
    rewritten = _submit_with_setup("cat __PULSAR_JOB_DIRECTORY__/working/x")
    assert "__PULSAR_JOB_DIRECTORY__" not in rewritten
    assert rewritten.endswith("/staging/j1/working/x")


def test_both_command_line_tokens_resolve_independently():
    """The plural token must not eat the singular one (or vice versa)."""
    rewritten = _submit_with_setup(
        "__PULSAR_JOBS_DIRECTORY__ then __PULSAR_JOB_DIRECTORY__"
    )
    assert rewritten.endswith("/staging then /staging/j1")


def test_no_substitution_without_setup_params():
    """job_config is None when the client did a remote setup - the paths in
    the command line are already real and must be left alone."""
    mgr = _RecordingManager(_FakeJobDirectory(exists=False))
    manager_endpoint_util.submit_job(
        mgr, _job_config(command_line="cat __PULSAR_JOBS_DIRECTORY__/j1")
    )
    assert mgr.launch_config["command_line"] == "cat __PULSAR_JOBS_DIRECTORY__/j1"
