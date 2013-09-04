JOB_FILE_RETURN_CODE = "return_code"
JOB_FILE_STANDARD_OUTPUT = "stdout"
JOB_FILE_STANDARD_ERROR = "stderr"
JOB_FILE_TOOL_ID = "tool_id"
JOB_FILE_TOOL_VERSION = "tool_version"

from lwr.managers.base import BaseManager
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
