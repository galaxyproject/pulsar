from os.path import exists, isdir, join, basename
from os import listdir
from os import makedirs
from uuid import uuid4

from lwr.util import JobDirectory
from lwr.managers import ManagerInterface

JOB_DIRECTORY_INPUTS = "inputs"
JOB_DIRECTORY_OUTPUTS = "outputs"
JOB_DIRECTORY_WORKING = "working"
JOB_DIRECTORY_CONFIGS = "configs"
JOB_DIRECTORY_TOOL_FILES = "tool_files"

DEFAULT_ID_ASSIGNER = "galaxy"

ID_ASSIGNER = {
    # Generate a random id, needed if multiple
    # Galaxy instances submitting to same LWR.
    'uuid': lambda galaxy_job_id: uuid4().hex,
    # Pass galaxy id through, default for single
    # Galaxy LWR instance.
    'galaxy': lambda galaxy_job_id: galaxy_job_id
}

from logging import getLogger
log = getLogger(__name__)


def get_id_assigner(assign_ids):
    default_id_assigner = ID_ASSIGNER[DEFAULT_ID_ASSIGNER]
    return ID_ASSIGNER.get(assign_ids, default_id_assigner)


class BaseManager(ManagerInterface):

    def __init__(self, name, app, **kwds):
        self.name = name
        self._setup_staging_directory(app.staging_directory)
        self.id_assigner = get_id_assigner(kwds.get("assign_ids", None))
        self.authorizer = app.authorizer

    def clean_job_directory(self, job_id):
        job_directory = self._job_directory(job_id)
        if job_directory.exists():
            try:
                job_directory.delete()
            except:
                pass

    def working_directory(self, job_id):
        return self._job_directory(job_id).working_directory()

    def inputs_directory(self, job_id):
        return self._job_directory(job_id).inputs_directory()

    def outputs_directory(self, job_id):
        return self._job_directory(job_id).outputs_directory()

    def configs_directory(self, job_id):
        return self._job_directory(job_id).configs_directory()

    def tool_files_directory(self, job_id):
        return self._job_directory(job_id).tool_files_directory()

    def _setup_staging_directory(self, staging_directory):
        assert not staging_directory == None
        if not exists(staging_directory):
            makedirs(staging_directory)
        assert isdir(staging_directory)
        self.staging_directory = staging_directory

    def _job_directory(self, job_id):
        return JobDirectory(self.staging_directory, job_id)

    def _setup_job_directory(self, job_id):
        job_directory = self._job_directory(job_id)
        job_directory.setup()
        for directory in [JOB_DIRECTORY_INPUTS,
                          JOB_DIRECTORY_WORKING,
                          JOB_DIRECTORY_OUTPUTS,
                          JOB_DIRECTORY_CONFIGS,
                          JOB_DIRECTORY_TOOL_FILES]:
            job_directory.make_directory(directory)
        return job_directory

    def _get_authorization(self, job_id, tool_id):
        return self.authorizer.get_authorization(tool_id)

    def _check_execution(self, job_id, tool_id, command_line):
        log.debug("job_id: %s - Checking authorization of command_line [%s]" % (job_id, command_line))
        authorization = self._get_authorization(job_id, tool_id)
        job_directory = self._job_directory(job_id)
        tool_files_dir = self.tool_files_directory(job_id)
        for file in listdir(tool_files_dir):
            contents = open(join(tool_files_dir, file), 'r').read()
            log.debug("job_id: %s - checking tool file %s" % (job_id, file))
            authorization.authorize_tool_file(basename(file), contents)
        config_files_dir = self.configs_directory(job_id)
        for file in listdir(config_files_dir):
            path = join(config_files_dir, file)
            authorization.authorize_config_file(job_directory, file, path)
        authorization.authorize_execution(job_directory, command_line)


JOB_FILE_RETURN_CODE = "return_code"
JOB_FILE_STANDARD_OUTPUT = "stdout"
JOB_FILE_STANDARD_ERROR = "stderr"
JOB_FILE_TOOL_ID = "tool_id"
JOB_FILE_TOOL_VERSION = "tool_version"

from lwr.managers import LWR_UNKNOWN_RETURN_CODE


class DirectoryBaseManager(BaseManager):

    def _job_file(self, job_id, name):
        return self._job_directory(job_id)._job_file(name)

    def return_code(self, job_id):
        return_code_str = self._read_job_file(job_id, JOB_FILE_RETURN_CODE, default=LWR_UNKNOWN_RETURN_CODE)
        return int(return_code_str) if return_code_str and return_code_str != LWR_UNKNOWN_RETURN_CODE else return_code_str

    def stdout_contents(self, job_id):
        return self._read_job_file(job_id, JOB_FILE_STANDARD_OUTPUT, default="")

    def stderr_contents(self, job_id):
        return self._read_job_file(job_id, JOB_FILE_STANDARD_ERROR, default="")

    def _stdout_path(self, job_id):
        return self._job_file(job_id, JOB_FILE_STANDARD_OUTPUT)

    def _stderr_path(self, job_id):
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

    def _write_return_code(self, job_id, return_code):
        self._write_job_file(job_id, JOB_FILE_RETURN_CODE, str(return_code))

    def _write_tool_info(self, job_id, tool_id, tool_version):
        job_directory = self._job_directory(job_id)
        job_directory.write_file(JOB_FILE_TOOL_ID, tool_id)
        job_directory.write_file(JOB_FILE_TOOL_VERSION, tool_version)

    def _open_standard_output(self, job_id):
        return self._job_directory(job_id).open_file(JOB_FILE_STANDARD_OUTPUT, 'w')

    def _open_standard_error(self, job_id):
        return self._job_directory(job_id).open_file(JOB_FILE_STANDARD_ERROR, 'w')

    def _check_execution_with_tool_file(self, job_id, command_line):
        tool_id = self._tool_id(job_id)
        self._check_execution(job_id, tool_id, command_line)

    def _tool_id(self, job_id):
        tool_id = None
        job_directory = self._job_directory(job_id)
        if job_directory.contains_file(JOB_FILE_TOOL_ID):
            tool_id = job_directory.read_file(JOB_FILE_TOOL_ID)
        return tool_id

from os import chmod
from stat import S_IEXEC, S_IWRITE, S_IREAD
from string import Template

DEFAULT_JOB_NAME_TEMPLATE = "lwr_$job_id"

DEFAULT_JOB_FILE_TEMPLATE = """#!/bin/sh
cd $working_directory
$command_line
echo $? > $return_code_path
"""


class ExternalBaseManager(DirectoryBaseManager):

    def __init__(self, name, app, **kwds):
        super(ExternalBaseManager, self).__init__(name, app, **kwds)
        self.external_ids = {}
        self.job_name_template = kwds.get('job_name_template', DEFAULT_JOB_NAME_TEMPLATE)

    def setup_job(self, input_job_id, tool_id, tool_version):
        job_id = self._get_job_id(input_job_id)
        return self._setup_job_for_job_id(job_id, tool_id, tool_version)

    def kill(self, job_id):
        external_id = self._external_id(job_id)
        if external_id:
            self._kill_external(external_id)

    def get_status(self, job_id):
        external_id = self._external_id(job_id)
        if not external_id:
            raise KeyError
        return self._get_status_external(external_id)

    def _setup_job_file(self, job_id, command_line, file_template=DEFAULT_JOB_FILE_TEMPLATE):
        script_env = self._job_template_env(job_id, command_line=command_line)
        template = Template(file_template)
        script_contents = template.safe_substitute(**script_env)
        return self._write_job_script(job_id, script_contents)

    def _get_job_id(self, input_job_id):
        return str(self.id_assigner(input_job_id))

    def _register_external_id(self, job_id, external_id):
        self.external_ids[job_id] = external_id
        return external_id

    def _external_id(self, job_id):
        return self.external_ids.get(job_id, None)

    def _job_template_env(self, job_id, command_line=None):
        return_code_path = self._return_code_path(job_id)
        job_template_env = {
            'return_code_path': return_code_path,
            'working_directory': self.working_directory(job_id),
            'job_id': job_id,
        }
        if command_line:
            job_template_env['command_line'] = command_line

        return job_template_env

    def _write_job_script(self, job_id, contents):
        self._write_job_file(job_id, "command.sh", contents)
        script_path = self._job_file(job_id, "command.sh")
        chmod(script_path, S_IEXEC | S_IWRITE | S_IREAD)
        return script_path

    def _job_name(self, job_id):
        env = self._job_template_env(job_id)
        return Template(self.job_name_template).safe_substitute(env)
