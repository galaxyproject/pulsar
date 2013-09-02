"""
LWR job manager that uses a CLI interface to a job queue (e.g. Torque's qsub,
qstat, etc...).

"""
from os import getcwd
from os.path import join, basename
from glob import glob

from lwr.managers.base import ExternalBaseManager

from logging import getLogger
log = getLogger(__name__)


class CliQueueManager(ExternalBaseManager):
    manager_type = "queued_cli"

    def __init__(self, name, app, **kwds):
        super(CliQueueManager, self).__init__(name, app, **kwds)
        self.shell_params = dict((k.replace('shell_', '', 1), v) for k, v in kwds.iteritems() if k.startswith('shell_'))
        self.job_params = dict((k.replace('job_', '', 1), v) for k, v in kwds.iteritems() if k.startswith('job_'))

    def __load_cli_plugins(self):
        def __load(module_path, d):
            for file in glob(join(join(getcwd(), *module_path.split('.')), '*.py')):
                if basename(file).startswith('_'):
                    continue
                module_name = '%s.%s' % (module_path, basename(file).rsplit('.py', 1)[0])
                module = __import__(module_name)
                for comp in module_name.split( "." )[1:]:
                    module = getattr(module, comp)
                for name in module.__all__:
                    d[name] = getattr(module, name)
        self.cli_shells = {}
        self.cli_job_interfaces = {}
        __load('lwr.cli.shell', self.cli_shells)
        __load('lwr.cli.job', self.cli_job_interfaces)

    def launch(self, job_id, command_line):
        self._check_execution_with_tool_file(job_id, command_line)
        shell, job_interface = self.get_cli_plugins()
        return_code_path = self._return_code_path(job_id)
        stdout_path = self._stdout_path(job_id)
        stderr_path = self._stderr_path(job_id)
        job_name = self._job_name(job_id)
        working_directory = self.working_directory(job_id)
        script = job_interface.get_job_template(stdout_path, stderr_path, job_name, working_directory, command_line, return_code_path)
        script_path = self._write_job_script(job_id, script)
        submission_command = job_interface.submit(script_path)
        cmd_out = shell.execute(submission_command)
        if cmd_out.return_code != 0:
            log.warn("Failed to submit job - command was %s" % submission_command)
            raise Exception("Failed to submit job")
        external_id = cmd_out.stdout.strip()
        if not external_id:
            message_template = "Failed to obtain externl id for job_id %s and submission_command %s"
            message = message_template % (job_id, submission_command)
            log.warn(message)
            raise Exception("Failed to obtain external id")

    def __get_cli_plugins(self):
        # load shell plugin
        shell_params = self.shell_params
        job_params = self.job_params
        shell = self.cli_shells[shell_params['plugin']](**shell_params)
        job_interface = self.cli_job_interfaces[self.job_params['plugin']](**job_params)
        return shell, job_interface

    def _kill_external(self, external_id):
        shell, job_interface = self.get_cli_plugins()
        kill_command = job_interface.delete(external_id)
        shell.execute(kill_command)

    def _get_status_external(self, external_id):
        shell, job_interface = self.get_cli_plugins()
        status_command = job_interface.get_single_status(external_id)
        cmd_out = shell.execute(status_command)
        state = job_interface.parse_single_status(cmd_out.stdout, external_id)
        return state
