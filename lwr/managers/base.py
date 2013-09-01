from abc import ABCMeta, abstractmethod

LWR_UNKNOWN_RETURN_CODE = None


class ManagerInterface(object):
    """
    Defines the interface to various job managers.
    """
    __metaclass__ = ABCMeta

    @abstractmethod
    def setup_job(self, input_job_id, tool_id, tool_version):
        """
        Setup a job directory for specified input (galaxy) job id, tool id,
        and tool version.
        """

    @abstractmethod
    def tool_files_directory(self, job_id):
        """
        Directory where job with id `job_id` tool files (wrapper scripts)
        will be stored.
        """

    @abstractmethod
    def inputs_directory(self, job_id):
        """
        Directory where job with id `job_id` input files will be stored.
        """

    @abstractmethod
    def working_directory(self, job_id):
        """
        Working directory for execution of job with id `job_id`.
        """

    @abstractmethod
    def outputs_directory(self, job_id):
        """
        Directory where job with id `job_id` outputs will be stored.
        """

    @abstractmethod
    def configs_directory(self, job_id):
        """
        Directory where job with id `job_id` tool config files will be stored.
        """

    @abstractmethod
    def clean_job_directory(self, job_id):
        """
        Delete job directory and clean up resources associated with job with
        id `job_id`.
        """

    @abstractmethod
    def launch(self, job_id, command_line):
        """
        Called to indicate that the client is ready for this job with specified
        job id and command line to be executed (i.e. run or queue this job
        depending on implementation).
        """

    @abstractmethod
    def get_status(self, job_id):
        """
        Return status of job as string, currently supported statuses include
        'cancelled', 'running', 'queued', and 'complete'.
        """

    @abstractmethod
    def return_code(self, job_id):
        """
        Return integer indicating return code of specified execution or
        LWR_UNKNOWN_RETURN_CODE.
        """

    @abstractmethod
    def stdout_contents(self, job_id):
        """
        After completion, return contents of stdout associated with specified
        job.
        """

    @abstractmethod
    def stderr_contents(self, job_id):
        """
        After completion, return contents of stderr associated with specified
        job.
        """

    @abstractmethod
    def kill(self, job_id):
        """
        End or cancel execution of the specified job.
        """
