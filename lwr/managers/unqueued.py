try:
    import thread
except ImportError:
    import _thread as thread  # Py3K changed it.
from .util import kill_pid
from lwr.managers.base.directory import DirectoryBaseManager
from galaxy.util import execute

from logging import getLogger
log = getLogger(__name__)

JOB_FILE_SUBMITTED = "submitted"
JOB_FILE_CANCELLED = "cancelled"
JOB_FILE_PID = "pid"


## Job Locks (for status updates). Following methods are locked.
##    _finish_execution(self, job_id)
##    _get_status(self, job_id)
##    _is_cancelled(self, job_id)
##    _record_pid(self, job_id, pid)
##    _get_pid_for_killing_or_cancel(self, job_id)
##
class Manager(DirectoryBaseManager):
    """
    A simple job manager that just directly runs jobs as given (no
    queueing). Preserved for compatibilty with older versions of LWR
    client code where Galaxy is used to maintain queue (like Galaxy's
    local job runner).

    """
    manager_type = "unqueued"

    def __init__(self, name, app, **kwds):
        super(Manager, self).__init__(name, app, **kwds)

    def _record_cancel(self, job_id):
        self._write_job_file(job_id, JOB_FILE_CANCELLED, 'true')

    def _record_submission(self, job_id):
        self._write_job_file(job_id, JOB_FILE_SUBMITTED, 'true')

    def __get_pid(self, job_id):
        pid = None
        try:
            pid = self._read_job_file(job_id, JOB_FILE_PID)
            if pid is not None:
                pid = int(pid)
        except:
            pass
        return pid

    def setup_job(self, input_job_id, tool_id, tool_version):
        job_id = self._get_job_id(input_job_id)
        return self._setup_job_for_job_id(job_id, tool_id, tool_version)

    def _get_job_id(self, galaxy_job_id):
        return str(self.id_assigner(galaxy_job_id))

    def _get_job_lock(self, job_id):
        return self._job_directory(job_id).lock()

    def get_status(self, job_id):
        with self._get_job_lock(job_id):
            return self._get_status(job_id)

    def kill(self, job_id):
        log.info("Attempting to kill job with job_id %s" % job_id)
        job_lock = self._get_job_lock(job_id)
        with job_lock:
            pid = self._get_pid_for_killing_or_cancel(job_id)
        if pid:
            log.info("Attempting to kill pid %s" % pid)
            kill_pid(pid)

    def _monitor_execution(self, job_id, proc, stdout, stderr):
        try:
            proc.wait()
            stdout.close()
            stderr.close()
            return_code = proc.returncode
            self._write_return_code(job_id, str(return_code))
        finally:
            with self._get_job_lock(job_id):
                self._finish_execution(job_id)

    # with job lock
    def _finish_execution(self, job_id):
        self._job_directory(job_id).remove_file(JOB_FILE_SUBMITTED)
        self._job_directory(job_id).remove_file(JOB_FILE_PID)

    # with job lock
    def _get_status(self, job_id):
        job_directory = self._job_directory(job_id)
        if self._is_cancelled(job_id):
            return 'cancelled'
        elif job_directory.contains_file(JOB_FILE_PID):
            return 'running'
        elif job_directory.contains_file(JOB_FILE_SUBMITTED):
            return 'queued'
        else:
            return 'complete'

    # with job lock
    def _is_cancelled(self, job_id):
        return self._job_directory(job_id).contains_file(JOB_FILE_CANCELLED)

    # with job lock
    def _record_pid(self, job_id, pid):
        self._write_job_file(job_id, JOB_FILE_PID, str(pid))

    # with job lock
    def _get_pid_for_killing_or_cancel(self, job_id):
        status = self._get_status(job_id)
        if status not in ['running', 'queued']:
            return

        pid = self.__get_pid(job_id)
        if pid is None:
            self._record_cancel(job_id)
            self._job_directory(job_id).remove_file(JOB_FILE_SUBMITTED)
        return pid

    def _run(self, job_id, command_line, async=True):
        with self._get_job_lock(job_id):
            if self._is_cancelled(job_id):
                return
        job_directory = self.job_directory(job_id)
        working_directory = job_directory.working_directory()
        stdout = self._open_standard_output(job_id)
        stderr = self._open_standard_error(job_id)
        proc = execute(command_line=command_line,
                       working_directory=working_directory,
                       stdout=stdout,
                       stderr=stderr)
        with self._get_job_lock(job_id):
            self._record_pid(job_id, proc.pid)
        if async:
            thread.start_new_thread(self._monitor_execution, (job_id, proc, stdout, stderr))
        else:
            self._monitor_execution(job_id, proc, stdout, stderr)

    def launch(self, job_id, command_line, submit_params={}, requirements=[]):
        command_line = self._prepare_run(job_id, command_line, requirements=requirements)
        self._run(job_id, command_line)

    def _prepare_run(self, job_id, command_line, requirements):
        self._check_execution_with_tool_file(job_id, command_line)
        self._record_submission(job_id)
        command_line = self._expand_command_line(command_line, requirements)
        return command_line

__all__ = [Manager]
