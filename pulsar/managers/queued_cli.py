"""
Pulsar job manager that uses a CLI interface to a job queue (e.g. Torque's qsub,
qstat, etc...).
"""

from logging import getLogger

from pulsar.managers import status
from .base.external import ExternalBaseManager
from .util.cli import (
    CliInterface,
    split_params,
)
from .util.cli.job import job_states
from .util.external import parse_external_id
from .util.job_script import job_script

log = getLogger(__name__)

# Translate the CLI plugins' job states into the Pulsar status vocabulary the
# stateful manager understands. The CLI plugins are shared with Galaxy, so
# job_states resolves to galaxy.model.Job.states when Galaxy is importable
# (OK == 'ok', ERROR == 'error') and to Pulsar's local fallback enum otherwise
# (OK == 'complete', ERROR == 'failed'). Keying on the enum member rather than
# its string value keeps this correct under both bindings. Mirrors the
# JobState -> status mapping in base/base_drmaa.py.
_CLI_STATE_TO_STATUS = {
    job_states.OK: status.COMPLETE,
    job_states.RUNNING: status.RUNNING,
    job_states.QUEUED: status.QUEUED,
    job_states.ERROR: status.FAILED,
}


class CliQueueManager(ExternalBaseManager):
    manager_type = "queued_cli"

    def __init__(self, name, app, **kwds):
        super().__init__(name, app, **kwds)
        self.cli_interface = CliInterface()
        self.shell_params, self.job_params = split_params(kwds)

    def launch(self, job_id, command_line, submit_params={}, dependencies_description=None, env=[], setup_params=None):
        self._check_execution_with_tool_file(job_id, command_line)
        shell, job_interface = self.__get_cli_plugins()
        stdout_path = self._job_stdout_path(job_id)
        stderr_path = self._job_stderr_path(job_id)
        job_name = self._job_name(job_id)
        command_line = self._expand_command_line(
            job_id, command_line, dependencies_description, job_directory=self.job_directory(job_id).job_directory
        )
        job_script_kwargs = self._job_template_env(
            job_id,
            command_line=command_line,
            env=env,
            setup_params=setup_params
        )
        extra_kwargs = job_interface.job_script_kwargs(stdout_path, stderr_path, job_name)
        job_script_kwargs.update(extra_kwargs)
        script = job_script(**job_script_kwargs)
        script_path = self._write_job_script(job_id, script)
        submission_command = job_interface.submit(script_path)
        cmd_out = shell.execute(submission_command)
        if cmd_out.returncode != 0:
            log.warn("Failed to submit job - command was:\n%s" % submission_command)
            raise Exception("Failed to submit job, error was:\n%s" % cmd_out.stderr)
        external_id = parse_external_id(cmd_out.stdout.strip())
        if not external_id:
            message_template = "Failed to obtain external id for job_id %s and submission_command %s"
            message = message_template % (job_id, submission_command)
            log.warn(message)
            raise Exception("Failed to obtain external id")
        self._register_external_id(job_id, external_id)

    def __get_cli_plugins(self):
        return self.cli_interface.get_plugins(self.shell_params, self.job_params)

    def _kill_external(self, external_id):
        shell, job_interface = self.__get_cli_plugins()
        kill_command = job_interface.delete(external_id)
        shell.execute(kill_command)

    def _get_status_external(self, external_id):
        shell, job_interface = self.__get_cli_plugins()
        status_command = job_interface.get_single_status(external_id)
        cmd_out = shell.execute(status_command)
        state = job_interface.parse_single_status(cmd_out.stdout, external_id)
        return _CLI_STATE_TO_STATUS.get(state, state)
