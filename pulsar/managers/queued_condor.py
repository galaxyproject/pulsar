from os.path import exists
from os import stat

from .util.condor import build_submit_description
from .util.condor import condor_submit, condor_stop, summarize_condor_log, submission_params
from .base.external import ExternalBaseManager
from ..managers import status

from logging import getLogger
log = getLogger(__name__)


# TODO:
#  - user_log_sizes and state_cache never expire
#    elements never expire. This is a small memory
#    leak that should be fixed.
class CondorQueueManager(ExternalBaseManager):
    """
    Job manager backend that plugs into Condor.
    """
    manager_type = "queued_condor"

    def __init__(self, name, app, **kwds):
        super(CondorQueueManager, self).__init__(name, app, **kwds)
        self.submission_params = submission_params(**kwds)
        self.user_log_sizes = {}
        self.state_cache = {}

    def launch(self, job_id, command_line, submit_params={}, dependencies_description=None, env=[], setup_params=None):
        self._check_execution_with_tool_file(job_id, command_line)
        job_file_path = self._setup_job_file(
            job_id,
            command_line,
            dependencies_description=dependencies_description,
            env=env,
            setup_params=setup_params
        )
        log_path = self.__condor_user_log(job_id)
        open(log_path, 'w')  # Touch log file
        build_submit_params = dict(
            executable=job_file_path,
            output=self._stdout_path(job_id),
            error=self._stderr_path(job_id),
            user_log=log_path,
            query_params=self.submission_params,
        )
        submit_file_contents = build_submit_description(**build_submit_params)
        submit_file = self._write_job_file(job_id, "job.condor.submit", submit_file_contents)
        external_id, message = condor_submit(submit_file)
        if not external_id:
            raise Exception(message)
        self._register_external_id(job_id, external_id)

    def __condor_user_log(self, job_id):
        return self._job_file(job_id, 'job_condor.log')

    def _kill_external(self, external_id):
        failure_message = condor_stop(external_id)
        if failure_message:
            log.warn("Failed to stop condor job with id %s - %s" % (external_id, failure_message))

    def get_status(self, job_id):
        external_id = self._external_id(job_id)
        if not external_id:
            raise Exception("Failed to obtain external_id for job_id %s, cannot determine status." % job_id)
        log_path = self.__condor_user_log(job_id)
        if not exists(log_path):
            return status.COMPLETE
        if external_id not in self.user_log_sizes:
            self.user_log_sizes[external_id] = -1
            self.state_cache[external_id] = status.QUEUED
        log_size = stat(log_path).st_size
        if log_size == self.user_log_sizes[external_id]:
            return self.state_cache[external_id]
        return self.__get_state_from_log(external_id, log_path)

    def __get_state_from_log(self, external_id, log_file):
        s1, s4, s7, s5, s9, log_size = summarize_condor_log(log_file, external_id)
        if s5 or s9:
            state = status.COMPLETE
        elif s1 or s4 or s7:
            state = status.RUNNING
        else:
            state = status.QUEUED
        self.user_log_sizes[external_id] = log_size
        self.state_cache[external_id] = state
        return state
