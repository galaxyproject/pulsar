from types import SimpleNamespace
from unittest import mock

from galaxy.util import commands

from pulsar import manager_endpoint_util
from pulsar.managers import (
    queued_slurm,
    status,
)
from pulsar.managers.base import base_drmaa
from pulsar.managers.queued_slurm import SlurmQueueManager
from pulsar.managers.util import runner_states
from pulsar.managers.util.slurm import (
    check_memory_limit,
    MEMORY_LIMIT_EXCEEDED,
    MEMORY_LIMIT_PROBABLY_EXCEEDED,
    NOT_FOUND,
    slurm_job_state,
)
from .test_utils import BaseManagerTestCase

FAKE_DRMAA_JOB_STATES = SimpleNamespace(
    UNDETERMINED="undetermined",
    QUEUED_ACTIVE="queued_active",
    SYSTEM_ON_HOLD="system_on_hold",
    USER_ON_HOLD="user_on_hold",
    USER_SYSTEM_ON_HOLD="user_system_on_hold",
    RUNNING="running",
    SYSTEM_SUSPENDED="system_suspended",
    USER_SUSPENDED="user_suspended",
    USER_SYSTEM_SUSPENDED="user_system_suspended",
    DONE="done",
    FAILED="failed",
)
EXTERNAL_ID = "4321"
SLURMSTEPD_OOM = b"slurmstepd: error: Exceeded job memory limit\n"


class _StubDrmaaSession:
    state = FAKE_DRMAA_JOB_STATES.FAILED

    def job_status(self, external_id):
        return self.state

    def close(self):
        pass


class _StubDrmaaSessionFactory:
    def get(self):
        return _StubDrmaaSession()


class SlurmManagerTest(BaseManagerTestCase):

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(base_drmaa, "JobState", FAKE_DRMAA_JOB_STATES)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.manager = self._new_manager()
        self.addCleanup(self.manager.shutdown)
        self.job_id = self.manager.setup_job("123", "tool1", "1.0.0")
        self.manager._register_external_id(self.job_id, EXTERNAL_ID)

    def _new_manager(self):
        return SlurmQueueManager("_default_", self.app, drmaa_session_factory_class=_StubDrmaaSessionFactory)

    def _status_for_slurm_state(self, slurm_state):
        with mock.patch.object(queued_slurm, "slurm_job_state", return_value=slurm_state) as slurm_job_state_mock:
            job_status = self.manager.get_status(self.job_id)
        slurm_job_state_mock.assert_called_once_with(EXTERNAL_ID)
        return job_status

    def _write_job_stderr(self, contents):
        with open(self.manager._job_stderr_path(self.job_id), "wb") as stderr:
            stderr.write(contents)

    def test_out_of_memory_is_reported_as_memory_limit(self):
        assert self._status_for_slurm_state("OUT_OF_MEMORY") == status.FAILED
        assert self.manager.runner_state(self.job_id) == runner_states.MEMORY_LIMIT_REACHED

    def test_timeout_is_reported_as_walltime(self):
        assert self._status_for_slurm_state("TIMEOUT") == status.FAILED
        assert self.manager.runner_state(self.job_id) == runner_states.WALLTIME_REACHED

    def test_cancelled_with_slurmstepd_message_is_memory_limit(self):
        self._write_job_stderr(b"tool noise\n" + SLURMSTEPD_OOM)
        assert self._status_for_slurm_state("CANCELLED") == status.FAILED
        assert self.manager.runner_state(self.job_id) == runner_states.MEMORY_LIMIT_REACHED

    def test_cancelled_without_message_has_no_reason(self):
        self._write_job_stderr(b"tool noise\n")
        assert self._status_for_slurm_state("CANCELLED") == status.FAILED
        assert self.manager.runner_state(self.job_id) is None

    def test_other_failures_have_no_reason(self):
        for slurm_state in ("FAILED", "NODE_FAIL"):
            assert self._status_for_slurm_state(slurm_state) == status.FAILED
            assert self.manager.runner_state(self.job_id) is None

    def test_jobs_slurm_says_finished_are_complete(self):
        for slurm_state in ("COMPLETED", NOT_FOUND):
            assert self._status_for_slurm_state(slurm_state) == status.COMPLETE

    def test_jobs_slurm_says_active_stay_running(self):
        for slurm_state in ("PENDING", "RUNNING", "COMPLETING"):
            assert self._status_for_slurm_state(slurm_state) == status.RUNNING
        assert self.manager.runner_state(self.job_id) is None

    def test_job_stuck_completing_eventually_fails(self):
        assert self._status_for_slurm_state("COMPLETING") == status.RUNNING
        with mock.patch.object(queued_slurm.time, "monotonic", return_value=float("inf")):
            assert self._status_for_slurm_state("COMPLETING") == status.FAILED

    def test_failure_to_query_slurm_still_fails_job(self):
        with mock.patch.object(queued_slurm, "slurm_job_state", side_effect=OSError("no scontrol")):
            assert self.manager.get_status(self.job_id) == status.FAILED
        assert self.manager.runner_state(self.job_id) is None

    def test_cancelled_through_pulsar_does_not_consult_slurm(self):
        self.manager._record_cancel(self.job_id)
        with mock.patch.object(queued_slurm, "slurm_job_state") as slurm_job_state_mock:
            assert self.manager.get_status(self.job_id) == status.CANCELLED
        slurm_job_state_mock.assert_not_called()

    def test_runner_state_survives_restart_and_reaches_status_response(self):
        assert self._status_for_slurm_state("OUT_OF_MEMORY") == status.FAILED
        restarted_manager = self._new_manager()
        self.addCleanup(restarted_manager.shutdown)
        response = _full_status(restarted_manager, self.job_id)
        assert response["status"] == status.FAILED
        assert response["runner_state"] == runner_states.MEMORY_LIMIT_REACHED

    def test_status_response_omits_unknown_runner_state(self):
        response = _full_status(self.manager, self.job_id)
        assert "runner_state" not in response


def _full_status(manager, job_id):
    # Only the stateful proxy Pulsar wraps managers in tracks live output.
    with mock.patch.object(manager, "is_live_stdout_update", create=True, return_value=False):
        return manager_endpoint_util.full_status(manager, status.FAILED, job_id)


def _execute_returning(*outputs):
    return mock.Mock(side_effect=list(outputs))


def test_slurm_job_state_parses_values_with_spaces():
    execute = _execute_returning("JobId=7 Comment=** time_limit (60m) min_nodes (1) ** JobState=OUT_OF_MEMORY StdIn=StdIn=/dev/null\n")
    assert slurm_job_state("7", execute=execute) == "OUT_OF_MEMORY"
    execute.assert_called_once_with(["scontrol", "-o", "show", "job", "7"])


def test_slurm_job_state_passes_cluster():
    execute = _execute_returning("JobState=TIMEOUT\n")
    assert slurm_job_state("7.mycluster", execute=execute) == "TIMEOUT"
    execute.assert_called_once_with(["scontrol", "-o", "-M", "mycluster", "show", "job", "7"])


def _scontrol_error(stderr):
    return commands.CommandLineException("scontrol", "", stderr, 1)


def test_slurm_job_state_falls_back_to_sacct():
    execute = _execute_returning(_scontrol_error("slurm_load_jobs error: Invalid job id specified\n"), "OUT_OF_MEMORY+\nOUT_OF_MEMORY\n")
    assert slurm_job_state("7", execute=execute) == "OUT_OF_MEMORY"


def test_slurm_job_state_not_found_without_accounting():
    execute = _execute_returning(
        _scontrol_error("slurm_load_jobs error: Invalid job id specified\n"),
        _scontrol_error("SLURM accounting storage is disabled\n"),
    )
    assert slurm_job_state("7", execute=execute) == NOT_FOUND


def test_check_memory_limit(tmp_path):
    efile = tmp_path / "stderr"
    assert check_memory_limit(str(efile)) is None
    efile.write_bytes(b"x" * 4096 + b"\n" + SLURMSTEPD_OOM)
    assert check_memory_limit(str(efile)) == MEMORY_LIMIT_EXCEEDED
    efile.write_bytes(b"slurmstepd: error: task/cgroup: Exceeded step memory limit at some point.\n")
    assert check_memory_limit(str(efile)) == MEMORY_LIMIT_PROBABLY_EXCEEDED
    efile.write_bytes(b"nothing to see\n")
    assert check_memory_limit(str(efile)) is None
