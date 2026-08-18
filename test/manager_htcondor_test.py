import os
import sys
from os.path import (
    dirname,
    join,
)

from pulsar.managers import status

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
        return self.manager_class('_default_', self.app, **kwds)

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

    def test_missing_event_log_escalates_to_lost(self):
        job_id = self._launch()
        os.unlink(self._user_log(job_id))
        for _ in range(4):
            assert self.manager.get_status(job_id) == status.QUEUED
        assert self.manager.get_status(job_id) == status.LOST

    def test_missing_event_log_recovers_if_log_reappears(self):
        job_id = self._launch()
        user_log = self._user_log(job_id)
        os.unlink(user_log)
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
