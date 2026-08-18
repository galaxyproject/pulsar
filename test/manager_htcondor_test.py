import os
import sys
import time
from os.path import (
    dirname,
    join,
)

from pulsar.managers import status
from pulsar.managers.stateful import StatefulManagerProxy
from pulsar.managers.util.condor.htcondor import (
    MISSING_LOG_GRACE_SECONDS,
    STATUS_ERROR_GRACE_SECONDS,
)

from .test_utils import BaseManagerTestCase

FAKE_MODULE_PATH = join(dirname(__file__), "htcondor_fake")


def _install_fake_htcondor():
    """Make ``import htcondor2`` resolve to the fake module in htcondor_fake/."""
    if FAKE_MODULE_PATH not in sys.path:
        sys.path.insert(0, FAKE_MODULE_PATH)
    sys.modules.pop("htcondor2", None)
    import htcondor2

    htcondor2.reset()
    return htcondor2


def _uninstall_fake_htcondor():
    sys.modules.pop("htcondor2", None)
    if FAKE_MODULE_PATH in sys.path:
        sys.path.remove(FAKE_MODULE_PATH)


class HTCondorManagerTest(BaseManagerTestCase):

    def setUp(self):
        super().setUp()
        # Drives the wall-clock escalation grace periods without sleeping.
        self.now = 0.0
        self.htcondor2 = _install_fake_htcondor()
        # Imported after the fake is installed so import_htcondor() finds it.
        from pulsar.managers.queued_htcondor import HTCondorQueueManager

        self.manager_class = HTCondorQueueManager
        self.manager = self._manager()

    def tearDown(self):
        self.manager.shutdown()
        _uninstall_fake_htcondor()
        super().tearDown()

    def _manager(self, **kwds):
        manager = self.manager_class('_default_', self.app, **kwds)
        manager.clock = lambda: self.now
        return manager

    def _launch(self, manager=None, external_job_id="123", command_line="true", **launch_kwds):
        manager = manager or self.manager
        job_id = manager.setup_job(external_job_id, "tool1", "1.0.0")
        manager.launch(job_id, command_line, **launch_kwds)
        return job_id

    def _user_log(self, job_id, manager=None):
        manager = manager or self.manager
        return manager._job_file(job_id, "job_condor.log")

    def _push_events(self, job_id, *events, manager=None):
        cluster_id = int((manager or self.manager)._external_id(job_id))
        self.htcondor2.JobEventLog.set_events(
            self._user_log(job_id, manager=manager),
            [self.htcondor2.FakeJobEvent(cluster_id, 0, event_type, **attrs) for event_type, attrs in events],
        )

    def _event(self, name, **attrs):
        return (getattr(self.htcondor2.JobEventType, name), attrs)

    # -- end to end -------------------------------------------------------

    def test_simple_execution(self):
        self.htcondor2.AUTO_COMPLETE = True
        self._test_simple_execution(self.manager)

    def test_cancel(self):
        self._test_cancelling(self.manager)

    # -- submission -------------------------------------------------------

    def test_submit_description_includes_job_paths(self):
        job_id = self._launch()
        submission = self.htcondor2.SUBMISSIONS[-1]
        description = submission["submit_description"]
        assert f"log = {self._user_log(job_id)}" in description, description
        assert "executable = " in description
        assert "universe = vanilla" in description
        assert self.manager._external_id(job_id) == str(submission["cluster_id"])

    def test_manager_submit_params_reach_submit_description(self):
        manager = self._manager(submit_request_cpus="4", submit_universe="docker")
        self._launch(manager=manager)
        description = self.htcondor2.SUBMISSIONS[-1]["submit_description"]
        assert "request_cpus = 4" in description, description
        assert "universe = docker" in description, description

    def test_request_walltime_becomes_periodic_hold(self):
        manager = self._manager(request_walltime="1:00:00")
        self._launch(manager=manager)
        description = self.htcondor2.SUBMISSIONS[-1]["submit_description"]
        assert "periodic_hold = (JobDurationSeconds >= 3600)" in description, description

    def test_manager_params_are_not_submitted_to_condor(self):
        manager = self._manager(request_walltime="1:00:00", max_held_count=5)
        self._launch(manager=manager)
        description = self.htcondor2.SUBMISSIONS[-1]["submit_description"]
        assert "request_walltime" not in description, description
        assert "max_held_count" not in description, description

    def test_unparseable_walltime_is_ignored(self):
        manager = self._manager(request_walltime="forever")
        self._launch(manager=manager)
        description = self.htcondor2.SUBMISSIONS[-1]["submit_description"]
        assert "periodic_hold" not in description, description

    def test_collector_and_schedd_are_passed_through(self):
        manager = self._manager(htcondor_collector="collector:9618", htcondor_schedd="schedd@host")
        self._launch(manager=manager)
        submission = self.htcondor2.SUBMISSIONS[-1]
        assert submission["collector"] == "collector:9618"
        assert submission["schedd_name"] == "schedd@host"

    # -- status mapping ---------------------------------------------------

    def test_queued_until_execute_event(self):
        job_id = self._launch()
        assert self.manager.get_status(job_id) == status.QUEUED
        self._push_events(job_id, self._event("EXECUTE"))
        assert self.manager.get_status(job_id) == status.RUNNING
        # No new events - the job is still believed to be running.
        assert self.manager.get_status(job_id) == status.RUNNING

    def test_terminated_event_completes_job(self):
        job_id = self._launch()
        self._push_events(job_id, self._event("EXECUTE"), self._event("JOB_TERMINATED"))
        assert self.manager.get_status(job_id) == status.COMPLETE

    def test_aborted_event_fails_job(self):
        job_id = self._launch()
        self._push_events(job_id, self._event("JOB_ABORTED"))
        assert self.manager.get_status(job_id) == status.FAILED

    def test_shadow_exception_fails_job(self):
        job_id = self._launch()
        self._push_events(job_id, self._event("SHADOW_EXCEPTION"))
        assert self.manager.get_status(job_id) == status.FAILED

    def test_memory_hold_fails_job_immediately(self):
        job_id = self._launch()
        self._push_events(job_id, self._event("JOB_HELD", HoldReasonCode=34))
        assert self.manager.get_status(job_id) == status.FAILED

    def test_walltime_hold_fails_job_immediately(self):
        job_id = self._launch()
        self._push_events(job_id, self._event("JOB_HELD", HoldReasonCode=16))
        assert self.manager.get_status(job_id) == status.FAILED

    def test_generic_hold_escalates_after_max_held_count(self):
        manager = self._manager(max_held_count=3)
        job_id = self._launch(manager=manager)
        for _ in range(2):
            self._push_events(job_id, self._event("JOB_HELD", HoldReasonCode=1), manager=manager)
            assert manager.get_status(job_id) == status.QUEUED
        self._push_events(job_id, self._event("JOB_HELD", HoldReasonCode=1), manager=manager)
        assert manager.get_status(job_id) == status.FAILED

    def test_release_resets_held_count(self):
        manager = self._manager(max_held_count=2)
        job_id = self._launch(manager=manager)
        self._push_events(job_id, self._event("JOB_HELD", HoldReasonCode=1), manager=manager)
        assert manager.get_status(job_id) == status.QUEUED
        self._push_events(job_id, self._event("JOB_RELEASED"), manager=manager)
        assert manager.get_status(job_id) == status.QUEUED
        # Held count was reset, so this hold is the first one again.
        self._push_events(job_id, self._event("JOB_HELD", HoldReasonCode=1), manager=manager)
        assert manager.get_status(job_id) == status.QUEUED

    def test_per_job_max_held_count_overrides_manager_default(self):
        job_id = self._launch(submit_params=dict(max_held_count=2))
        self._push_events(job_id, self._event("JOB_HELD", HoldReasonCode=1))
        assert self.manager.get_status(job_id) == status.QUEUED
        self._push_events(job_id, self._event("JOB_HELD", HoldReasonCode=1))
        assert self.manager.get_status(job_id) == status.FAILED

    def test_per_job_walltime_becomes_periodic_hold(self):
        self._launch(submit_params=dict(request_walltime="90:00"))
        description = self.htcondor2.SUBMISSIONS[-1]["submit_description"]
        assert "periodic_hold = (JobDurationSeconds >= 5400)" in description, description

    def test_max_held_count_zero_disables_escalation(self):
        manager = self._manager(max_held_count=0)
        job_id = self._launch(manager=manager)
        for _ in range(5):
            self._push_events(job_id, self._event("JOB_HELD", HoldReasonCode=1), manager=manager)
            assert manager.get_status(job_id) == status.QUEUED

    def test_missing_event_log_escalates_to_failed(self):
        job_id = self._launch()
        os.unlink(self._user_log(job_id))
        # Polling faster than the grace period must not escalate, however many
        # times it happens - that is the point of tracking wall-clock time.
        for _ in range(20):
            self.now += MISSING_LOG_GRACE_SECONDS / 40
            assert self.manager.get_status(job_id) == status.QUEUED
        self.now += MISSING_LOG_GRACE_SECONDS
        # FAILED, not LOST - LOST is not terminal for the stateful proxy, so the
        # job would never be deactivated and its event log never closed.
        assert self.manager.get_status(job_id) == status.FAILED

    def test_missing_event_log_preserves_running_state(self):
        job_id = self._launch()
        self._push_events(job_id, self._event("EXECUTE"))
        assert self.manager.get_status(job_id) == status.RUNNING
        os.unlink(self._user_log(job_id))
        assert self.manager.get_status(job_id) == status.RUNNING

    def test_status_errors_escalate_to_failed(self):
        job_id = self._launch()
        self.htcondor2.JobEventLog.error = OSError("Test event log failure")
        for _ in range(20):
            self.now += STATUS_ERROR_GRACE_SECONDS / 40
            assert self.manager.get_status(job_id) == status.QUEUED
        self.now += STATUS_ERROR_GRACE_SECONDS
        assert self.manager.get_status(job_id) == status.FAILED

    def test_status_errors_recover_before_escalating(self):
        job_id = self._launch()
        self._push_events(job_id, self._event("EXECUTE"))
        assert self.manager.get_status(job_id) == status.RUNNING
        self.htcondor2.JobEventLog.error = OSError("Test event log failure")
        # A transient error keeps the last known state rather than resetting it.
        assert self.manager.get_status(job_id) == status.RUNNING
        self.htcondor2.JobEventLog.error = None
        self._push_events(job_id, self._event("JOB_TERMINATED"))
        assert self.manager.get_status(job_id) == status.COMPLETE

    def test_status_error_grace_period_restarts_after_recovery(self):
        job_id = self._launch()
        self.htcondor2.JobEventLog.error = OSError("Test event log failure")
        self.now += STATUS_ERROR_GRACE_SECONDS / 2
        assert self.manager.get_status(job_id) == status.QUEUED
        self.htcondor2.JobEventLog.error = None
        assert self.manager.get_status(job_id) == status.QUEUED
        # The clock restarts on recovery, so the earlier errors are not counted.
        self.htcondor2.JobEventLog.error = OSError("Test event log failure")
        self.now += STATUS_ERROR_GRACE_SECONDS * 0.75
        assert self.manager.get_status(job_id) == status.QUEUED

    def test_missing_external_id_is_lost(self):
        # Never launched, so the external id is genuinely unknown rather than
        # exhausted - LOST lets the proxy keep the job and recover it.
        job_id = self.manager.setup_job("456", "tool1", "1.0.0")
        assert self.manager.get_status(job_id) == status.LOST

    def test_missing_event_log_recovers_if_log_reappears(self):
        job_id = self._launch()
        user_log = self._user_log(job_id)
        os.unlink(user_log)
        self.now += MISSING_LOG_GRACE_SECONDS / 2
        assert self.manager.get_status(job_id) == status.QUEUED
        open(user_log, "w").close()
        self._push_events(job_id, self._event("EXECUTE"))
        assert self.manager.get_status(job_id) == status.RUNNING

    # -- kill -------------------------------------------------------------

    def test_kill_removes_job_from_schedd(self):
        job_id = self._launch()
        external_id = self.manager._external_id(job_id)
        self.manager.kill(job_id)
        removal = self.htcondor2.REMOVALS[-1]
        assert removal["action"] == "Remove"
        assert removal["job_spec"] == int(external_id)
        assert removal["reason"] == "Pulsar job stop request"
        assert self.manager.get_status(job_id) == status.CANCELLED

    # -- behind the stateful proxy ----------------------------------------

    def test_escalated_failure_finishes_job_behind_stateful_proxy(self):
        # The escalation is only useful if the layer every manager runs behind
        # acts on it - LOST here would leave the job active and unreported.
        proxy, callbacks = self._stateful_proxy()
        job_id = proxy.setup_job("789", "tool1", "1.0.0")
        proxy.preprocess_and_launch(job_id, {"command_line": "true", "remote_staging": {}})
        os.unlink(self._user_log(job_id))
        proxy.get_status(job_id)
        self.now += MISSING_LOG_GRACE_SECONDS
        proxy.get_status(job_id)
        self._wait_for_callback(callbacks)
        assert callbacks == [(status.FAILED, job_id)], callbacks
        assert proxy.active_jobs.active_job_ids() == []
        # Deactivation is what closes the event log handle.
        assert self.manager._job_states == {}

    def _stateful_proxy(self):
        callbacks = []

        class _RecordingStatefulManagerProxy(StatefulManagerProxy):
            """Records state changes without starting a monitor thread."""

            def _default_status_change_callback(self, job_status, job_id):
                callbacks.append((job_status, job_id))

        return _RecordingStatefulManagerProxy(self.manager), callbacks

    def _wait_for_callback(self, callbacks, timeout=5):
        time_end = time.time() + timeout
        while time.time() < time_end:
            if callbacks:
                return
            time.sleep(.01)
        raise AssertionError("Timed out waiting for a state change callback.")
