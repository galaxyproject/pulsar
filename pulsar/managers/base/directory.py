import logging
import os
import stat

from galaxy.util import asbool

from pulsar.managers import PULSAR_UNKNOWN_RETURN_CODE
from pulsar.managers.base import BaseManager
from ..util.env import env_to_statement
from ..util.job_script import job_script

log = logging.getLogger(__name__)

# TODO: Rename these to abstract out the fact they are files - pulsar
# should be able to replace metadata backing with non-file stuff now that
# the abstractions are fairly well utilized.
JOB_FILE_RETURN_CODE = "return_code"
TOOL_FILE_STANDARD_OUTPUT = os.path.join("metadata", "tool_stdout")
TOOL_FILE_STANDARD_ERROR = os.path.join("metadata", "tool_stderr")
JOB_FILE_STANDARD_OUTPUT = os.path.join("metadata", "job_stdout")
JOB_FILE_STANDARD_ERROR = os.path.join("metadata", "job_stderr")
JOB_FILE_TOOL_ID = "tool_id"
JOB_FILE_TOOL_VERSION = "tool_version"
JOB_FILE_CANCELLED = "cancelled"
JOB_FILE_COMMAND_LINE = "command_line"
CREATE_TMP_PATTERN = '''$([ ! -e '{0}/tmp' ] || mv '{0}/tmp' '{0}'/tmp.$(date +%Y%m%d-%H%M%S) ; mkdir '{0}/tmp'; echo '{0}/tmp')'''
PREPARE_DIRS_TEMPLATE = """for dir in {working_directory} {outputs_directory} {configs_directory}; do
    if [ -d "${{dir}}.orig" ]; then
        rm -rf "$dir"; cp -R "${{dir}}.orig" "$dir"
    else
        cp -R "$dir" "${{dir}}.orig"
    fi
done
"""


class DirectoryBaseManager(BaseManager):

    def _job_file(self, job_id, name):
        return self._job_directory(job_id)._job_file(name)

    def return_code(self, job_id):
        return_code_str = self._read_job_file(job_id, JOB_FILE_RETURN_CODE, default=PULSAR_UNKNOWN_RETURN_CODE)
        return int(return_code_str) if return_code_str and return_code_str != PULSAR_UNKNOWN_RETURN_CODE else return_code_str

    def stdout_contents(self, job_id):
        try:
            return self._read_job_file(job_id, TOOL_FILE_STANDARD_OUTPUT, size=self.maximum_stream_size)
        except FileNotFoundError:
            # Could be old job finishing up, drop in 2024?
            return self._read_job_file(job_id, "tool_stdout", size=self.maximum_stream_size, default=b"")

    def stderr_contents(self, job_id):
        try:
            return self._read_job_file(job_id, TOOL_FILE_STANDARD_ERROR, size=self.maximum_stream_size)
        except FileNotFoundError:
            # Could be old job finishing up, drop in 2024?
            return self._read_job_file(job_id, "tool_stderr", size=self.maximum_stream_size, default=b"")

    def job_stdout_contents(self, job_id):
        return self._read_job_file(job_id, JOB_FILE_STANDARD_OUTPUT, size=self.maximum_stream_size, default=b"")

    def job_stderr_contents(self, job_id):
        return self._read_job_file(job_id, JOB_FILE_STANDARD_ERROR, size=self.maximum_stream_size, default=b"")

    def read_command_line(self, job_id):
        command_line = self._read_job_file(job_id, JOB_FILE_COMMAND_LINE)
        if command_line.startswith(b'"'):
            # legacy JSON...
            import json
            command_line = json.loads(command_line)
        return command_line

    def _tool_stdout_path(self, job_id):
        return self._job_file(job_id, TOOL_FILE_STANDARD_OUTPUT)

    def _tool_stderr_path(self, job_id):
        return self._job_file(job_id, TOOL_FILE_STANDARD_ERROR)

    def _job_stdout_path(self, job_id):
        return self._job_file(job_id, JOB_FILE_STANDARD_OUTPUT)

    def _job_stderr_path(self, job_id):
        return self._job_file(job_id, JOB_FILE_STANDARD_ERROR)

    def _return_code_path(self, job_id):
        return self._job_file(job_id, JOB_FILE_RETURN_CODE)

    def _setup_job_for_job_id(self, job_id, tool_id, tool_version):
        self._setup_job_directory(job_id)

        tool_id = str(tool_id) if tool_id else ""
        tool_version = str(tool_version) if tool_version else ""

        authorization = self._get_authorization(job_id, tool_id)
        authorization.authorize_setup()

        self._write_tool_info(job_id, tool_id, tool_version)
        return job_id

    def _read_job_file(self, job_id, name, **kwds):
        return self._job_directory(job_id).read_file(name, **kwds)

    def _write_job_file(self, job_id, name, contents):
        return self._job_directory(job_id).write_file(name, contents)

    def _write_return_code_if_unset(self, job_id, return_code):
        return_code_str = self._read_job_file(job_id, JOB_FILE_RETURN_CODE, default=PULSAR_UNKNOWN_RETURN_CODE)
        if return_code_str == PULSAR_UNKNOWN_RETURN_CODE:
            self._write_job_file(job_id, JOB_FILE_RETURN_CODE, str(return_code))

    def _write_tool_info(self, job_id, tool_id, tool_version):
        job_directory = self._job_directory(job_id)
        job_directory.store_metadata(JOB_FILE_TOOL_ID, tool_id)
        job_directory.store_metadata(JOB_FILE_TOOL_VERSION, tool_version)

    def _write_command_line(self, job_id, command_line):
        self._write_job_file(job_id, JOB_FILE_COMMAND_LINE, command_line)

    def _record_cancel(self, job_id):
        try:
            self._job_directory(job_id).store_metadata(JOB_FILE_CANCELLED, True)
        except Exception:
            log.info("Failed to record job with id %s was cancelled." % job_id)

    def _was_cancelled(self, job_id):
        try:
            return self._job_directory(job_id).load_metadata(JOB_FILE_CANCELLED, None)
        except Exception:
            log.info("Failed to determine if job with id %s was cancelled, assuming no." % job_id)
            return False

    def _open_job_standard_output(self, job_id):
        return self._job_directory(job_id).open_file(JOB_FILE_STANDARD_OUTPUT, 'w')

    def _open_job_standard_error(self, job_id):
        return self._job_directory(job_id).open_file(JOB_FILE_STANDARD_ERROR, 'w')

    def _check_execution_with_tool_file(self, job_id, command_line):
        tool_id = self._tool_id(job_id)
        self._check_execution(job_id, tool_id, command_line)

    def _tool_id(self, job_id):
        tool_id = None
        job_directory = self._job_directory(job_id)
        if job_directory.has_metadata(JOB_FILE_TOOL_ID):
            tool_id = job_directory.load_metadata(JOB_FILE_TOOL_ID)
        return tool_id

    def _expand_command_line(self, job_id, command_line: str, dependencies_description, job_directory=None) -> str:
        command_line = super()._expand_command_line(
            job_id, command_line, dependencies_description, job_directory=job_directory
        )
        if not self._is_windows:
            rc_path = self._return_code_path(job_id)
            CAPTURE_RETURN_CODE = "return_code=$?"
            command_line = f"{command_line}; {CAPTURE_RETURN_CODE}; echo $return_code > {rc_path};"
        return command_line

    # Helpers methods related to setting up job script files.
    def _setup_job_file(self, job_id, command_line, dependencies_description=None, env=[], setup_params=None):
        command_line = self._expand_command_line(
            job_id, command_line, dependencies_description, job_directory=self.job_directory(job_id).job_directory
        )
        script_env = self._job_template_env(job_id, command_line=command_line, env=env, setup_params=setup_params)
        script = job_script(**script_env)
        return self._write_job_script(job_id, script)

    def _tmp_dir(self, job_id: str):
        # Code stolen from Galaxy's job wrapper.
        tmp_dir = self.tmp_dir
        try:
            if not tmp_dir or asbool(tmp_dir):
                working_directory = self.job_directory(job_id).job_directory
                return CREATE_TMP_PATTERN.format(working_directory)
            else:
                return tmp_dir
        except ValueError:
            # Catch case where tmp_dir is a complex expression and not a boolean value
            return tmp_dir

    def _prepare_dirs(self, job_id: str):
        return PREPARE_DIRS_TEMPLATE.format(
            working_directory=self.job_directory(job_id).working_directory(),
            outputs_directory=self.job_directory(job_id).outputs_directory(),
            configs_directory=self.job_directory(job_id).configs_directory(),
        )

    def _job_template_env(self, job_id, command_line=None, env=[], setup_params=None):
        # TODO: Add option to ignore remote env.
        env = env + self.env_vars
        setup_params = setup_params or {}
        env_setup_commands = map(env_to_statement, env)
        job_template_env = {
            'job_instrumenter': self.job_metrics.default_job_instrumenter,
            'galaxy_virtual_env': self._galaxy_virtual_env(),
            'galaxy_lib': self._galaxy_lib(),
            'preserve_python_environment': setup_params.get('preserve_galaxy_python_environment', False),
            'env_setup_commands': env_setup_commands,
            # job_diredctory not used by job_script and it calls the job directory working directory
            'working_directory': self.job_directory(job_id).working_directory(),
            'metadata_directory': self.job_directory(job_id).metadata_directory(),
            'home_directory': self.job_directory(job_id).home_directory(),
            'job_id': job_id,
            'tmp_dir_creation_statement': self._tmp_dir(job_id),
            'prepare_dirs_statement': self._prepare_dirs(job_id),
        }
        if command_line:
            job_template_env['command'] = command_line
        return job_template_env

    def _write_job_script(self, job_id, contents):
        self._write_job_file(job_id, "command.sh", contents)
        script_path = self._job_file(job_id, "command.sh")
        os.chmod(script_path, stat.S_IEXEC | stat.S_IWRITE | stat.S_IREAD)
        return script_path
