"""
LWR job manager that uses a CLI interface to a job queue (e.g. Torque's qsub,
qstat, etc...).

"""

from .base.external import ExternalBaseManager
from .util.external import parse_external_id
from .util.cli import CliInterface, split_params

from logging import getLogger
log = getLogger(__name__)


class CliQueueManager(ExternalBaseManager):
    manager_type = "queued_cli"

    def __init__(self, name, app, **kwds):
        super(CliQueueManager, self).__init__(name, app, **kwds)
        self.cli_interface = CliInterface(code_dir='.')
        self.shell_params, self.job_params = split_params(kwds)

    def launch(self, job_id, command_line, submit_params={}, requirements=[], env=[]):
        self._check_execution_with_tool_file(job_id, command_line)
        shell, job_interface = self.__get_cli_plugins()
        return_code_path = self._return_code_path(job_id)
        stdout_path = self._stdout_path(job_id)
        stderr_path = self._stderr_path(job_id)
        job_name = self._job_name(job_id)
        working_directory = self.job_directory(job_id).working_directory()
        command_line = self._expand_command_line(command_line, requirements)
        script = job_interface.get_job_template(stdout_path, stderr_path, job_name, working_directory, command_line, return_code_path, env=env)
        script_path = self._write_job_script(job_id, script)
        submission_command = job_interface.submit(script_path)
        cmd_out = shell.execute(submission_command)
        if cmd_out.returncode != 0:
            log.warn("Failed to submit job - command was %s" % submission_command)
            raise Exception("Failed to submit job")
        external_id = parse_external_id(cmd_out.stdout.strip())
        if not external_id:
            message_template = "Failed to obtain externl id for job_id %s and submission_command %s"
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
        return state
