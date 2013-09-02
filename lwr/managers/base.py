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
        self._job_directory(job_id).write_file(name, contents)

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
