from types import SimpleNamespace

from pulsar.managers import status
from pulsar.managers.queued_cli import CliQueueManager
from pulsar.managers.util import runner_states
from pulsar.managers.util.cli.job.lsf import LSF
from pulsar.managers.util.cli.job.slurm import Slurm
from .test_utils import BaseManagerTestCase

EXTERNAL_ID = "4321"
BJOBS_EXIT = "EXIT\n"
BJOBS_MEMLIMIT = "Job <4321>\n TERM_MEMLIMIT: job killed after reaching LSF memory usage limit.\n"


class _StubShell:
    def __init__(self, responses):
        self.responses = responses
        self.commands = []

    def execute(self, command):
        self.commands.append(command)
        return SimpleNamespace(stdout=self.responses[command], stderr="", returncode=0)


class _SlurmWithoutFailureReason(Slurm):
    def get_failure_reason(self, job_id):
        return None


class CliManagerTest(BaseManagerTestCase):

    def setUp(self):
        super().setUp()
        self.manager = CliQueueManager("_default_", self.app)
        self.addCleanup(self.manager.shutdown)
        self.job_id = self.manager.setup_job("123", "tool1", "1.0.0")
        self.manager._register_external_id(self.job_id, EXTERNAL_ID)

    def _use_plugins(self, shell, job_interface):
        self.manager.cli_interface = SimpleNamespace(get_plugins=lambda *args: (shell, job_interface))

    def _lsf_shell(self, failure_reason):
        job_interface = LSF()
        return _StubShell(
            {
                job_interface.get_single_status(EXTERNAL_ID): BJOBS_EXIT,
                job_interface.get_failure_reason(EXTERNAL_ID): failure_reason,
            }
        ), job_interface

    def test_lsf_memory_limit_is_reported(self):
        self._use_plugins(*self._lsf_shell(BJOBS_MEMLIMIT))
        assert self.manager.get_status(self.job_id) == status.FAILED
        assert self.manager.runner_state(self.job_id) == runner_states.MEMORY_LIMIT_REACHED

    def test_lsf_other_failure_has_no_reason(self):
        self._use_plugins(*self._lsf_shell("Job <4321>\nExited with exit code 1.\n"))
        assert self.manager.get_status(self.job_id) == status.FAILED
        assert self.manager.runner_state(self.job_id) is None

    def test_plugin_without_failure_reason_runs_no_extra_command(self):
        job_interface = _SlurmWithoutFailureReason()
        status_command = job_interface.get_single_status(EXTERNAL_ID)
        shell = _StubShell({status_command: "JOBID ST\n4321 F\n"})
        self._use_plugins(shell, job_interface)
        assert self.manager.get_status(self.job_id) == status.FAILED
        assert shell.commands == [status_command]
        assert self.manager.runner_state(self.job_id) is None

    def test_failure_to_get_reason_still_fails_job(self):
        shell, job_interface = self._lsf_shell(BJOBS_MEMLIMIT)
        del shell.responses[job_interface.get_failure_reason(EXTERNAL_ID)]
        self._use_plugins(shell, job_interface)
        assert self.manager.get_status(self.job_id) == status.FAILED
        assert self.manager.runner_state(self.job_id) is None

    def _slurm_shell(self, short_state, failure_reason):
        job_interface = Slurm()
        return _StubShell(
            {
                job_interface.get_single_status(EXTERNAL_ID): f"JOBID ST\n{EXTERNAL_ID} {short_state}\n",
                job_interface.get_failure_reason(EXTERNAL_ID): failure_reason,
            }
        ), job_interface

    def test_slurm_timeout_is_reported(self):
        self._use_plugins(*self._slurm_shell("TO", f"JobId={EXTERNAL_ID} JobState=TIMEOUT Reason=TimeLimit\n"))
        assert self.manager.get_status(self.job_id) == status.FAILED
        assert self.manager.runner_state(self.job_id) == runner_states.WALLTIME_REACHED

    def test_slurm_out_of_memory_is_reported(self):
        self._use_plugins(*self._slurm_shell("OOM", f"JobId={EXTERNAL_ID} JobState=OUT_OF_MEMORY Reason=OutOfMemory\n"))
        assert self.manager.get_status(self.job_id) == status.FAILED
        assert self.manager.runner_state(self.job_id) == runner_states.MEMORY_LIMIT_REACHED

    def test_slurm_reason_falls_back_to_sacct_output(self):
        self._use_plugins(*self._slurm_shell("OOM", f"{EXTERNAL_ID}|OUT_OF_MEMORY\n{EXTERNAL_ID}.batch|OUT_OF_MEMORY\n"))
        assert self.manager.get_status(self.job_id) == status.FAILED
        assert self.manager.runner_state(self.job_id) == runner_states.MEMORY_LIMIT_REACHED

    def test_slurm_ordinary_failure_has_no_reason(self):
        self._use_plugins(*self._slurm_shell("F", f"JobId={EXTERNAL_ID} JobState=FAILED Reason=NonZeroExitCode\n"))
        assert self.manager.get_status(self.job_id) == status.FAILED
        assert self.manager.runner_state(self.job_id) is None

    def test_slurm_job_gone_from_squeue_uses_sacct(self):
        job_interface = Slurm()
        shell = _StubShell(
            {
                job_interface.get_single_status(EXTERNAL_ID): "JOBID ST\n",
                f"sacct -o JobIDRaw,State -P -n -j {EXTERNAL_ID}": f"{EXTERNAL_ID}|TIMEOUT\n{EXTERNAL_ID}.batch|CANCELLED\n",
                job_interface.get_failure_reason(EXTERNAL_ID): f"{EXTERNAL_ID}|TIMEOUT\n",
            }
        )
        self._use_plugins(shell, job_interface)
        assert self.manager.get_status(self.job_id) == status.FAILED
        assert self.manager.runner_state(self.job_id) == runner_states.WALLTIME_REACHED

    def test_slurm_without_accounting_completes_aged_out_job(self):
        job_interface = Slurm()
        command = f"sacct -o JobIDRaw,State -P -n -j {EXTERNAL_ID}"
        shell = _StubShell({job_interface.get_single_status(EXTERNAL_ID): "JOBID ST\n", command: ""})
        shell.execute = lambda c: SimpleNamespace(
            stdout=shell.responses[c],
            stderr="Slurm accounting storage is disabled\n" if c == command else "",
            returncode=1 if c == command else 0,
        )
        self._use_plugins(shell, job_interface)
        assert self.manager.get_status(self.job_id) == status.COMPLETE
        assert job_interface.sacct_available is False
