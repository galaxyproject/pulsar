"""Tests for the manager_endpoint_util submit-message idempotency guard.

When an AMQP setup message is redelivered (after a Pulsar SIGKILL between
setup_job and message.ack(), for example), submit_job must NOT re-run the
job. Once ``launch_config`` metadata is present on disk, the redelivered
message is a no-op.
"""
from pulsar import manager_endpoint_util


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
