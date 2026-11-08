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
        job_interface = Slurm()
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
