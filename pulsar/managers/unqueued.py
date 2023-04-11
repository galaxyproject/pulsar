import _thread as thread
import os
import platform
import tempfile
import time
from logging import getLogger
from subprocess import Popen

from pulsar.managers import status
from pulsar.managers.base.directory import DirectoryBaseManager
from pulsar.client.util import MonitorStyle
from .util import kill_pid

log = getLogger(__name__)

JOB_FILE_SUBMITTED = "submitted"
JOB_FILE_PID = "pid"

try:
    from galaxy.util.commands import new_clean_env
except ImportError:
    # We can drop this once we require galaxy-util >=21.01
    def new_clean_env():
        """
        Returns a minimal environment to use when invoking a subprocess
        """
        env = {}
        for k in ("HOME", "PATH", "TMPDIR"):
            if k in os.environ:
                env[k] = os.environ[k]
        if "TMPDIR" not in env:
            env["TMPDIR"] = os.path.abspath(tempfile.gettempdir())
        # Set LC_CTYPE environment variable to enforce UTF-8 file encoding.
        # This is needed e.g. for Python < 3.7 where
        # `locale.getpreferredencoding()` (also used by open() to determine the
        # default file encoding) would return `ANSI_X3.4-1968` without this.
        env["LC_CTYPE"] = "C.UTF-8"
        return env


class BaseUnqueuedManager(DirectoryBaseManager):

    def _record_submission(self, job_id):
        self._job_directory(job_id).store_metadata(JOB_FILE_SUBMITTED, 'true')

    def _get_status(self, job_id):
        job_directory = self._job_directory(job_id)
        if self._was_cancelled(job_id):
            job_status = status.CANCELLED
        elif job_directory.has_metadata(JOB_FILE_PID):
            job_status = status.RUNNING
        elif job_directory.has_metadata(JOB_FILE_SUBMITTED):
            job_status = status.QUEUED
        else:
            job_status = status.COMPLETE
        return job_status

    def _finish_execution(self, job_id):
        self._job_directory(job_id).remove_metadata(JOB_FILE_SUBMITTED)

    def _prepare_run(self, job_id, command_line, dependencies_description, env, setup_params=None):
        self._check_execution_with_tool_file(job_id, command_line)
        self._record_submission(job_id)
        if self._is_windows:
            # TODO: Don't ignore requirements and env without warning. Ideally
            # process them or at least warn about them being ignored.
            command_line = self._expand_command_line(
                job_id, command_line, dependencies_description, job_directory=self.job_directory(job_id).job_directory
            )
        else:
            command_line = self._setup_job_file(
                job_id,
                command_line,
                dependencies_description=dependencies_description,
                env=env,
                setup_params=setup_params
            )
        return command_line

    def _start_monitor(self, *args, **kwd):
        monitor = kwd.get("monitor", MonitorStyle.BACKGROUND)
        if monitor == MonitorStyle.BACKGROUND:
            thread.start_new_thread(self._monitor_execution, args)
        elif monitor == MonitorStyle.FOREGROUND:
            self._monitor_execution(*args)
        else:
            log.info("No monitoring job")


# Job Locks (for status updates). Following methods are locked.
#    _finish_execution(self, job_id)
#    _get_status(self, job_id)
#    _is_cancelled(self, job_id)
#    _record_pid(self, job_id, pid)
#    _get_pid_for_killing_or_cancel(self, job_id)
#
class Manager(BaseUnqueuedManager):
    """
    A simple job manager that just directly runs jobs as given (no
    queueing). Preserved for compatibilty with older versions of Pulsar
    client code where Galaxy is used to maintain queue (like Galaxy's
    local job runner).

    """
    manager_type = "unqueued"

    def __init__(self, name, app, **kwds):
        super().__init__(name, app, **kwds)

    def __get_pid(self, job_id):
        pid = None
        try:
            pid = self._job_directory(job_id).load_metadata(JOB_FILE_PID)
            if pid is not None:
                pid = int(pid)
        except Exception:
            pass
        return pid

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
            # job_script might have set return code so use that if set, otherwise use this one.
            # Should there be someway to signal failure if this is non-0 in that case?
            self._write_return_code_if_unset(job_id, str(return_code))
        finally:
            with self._get_job_lock(job_id):
                self._finish_execution(job_id)

    # with job lock
    def _finish_execution(self, job_id):
        super()._finish_execution(job_id)
        self._job_directory(job_id).remove_metadata(JOB_FILE_PID)

    # with job lock
    def _get_status(self, job_id):
        return super()._get_status(job_id)

    # with job lock
    def _was_cancelled(self, job_id):
        return super()._was_cancelled(job_id)

    # with job lock
    def _record_pid(self, job_id, pid):
        self._job_directory(job_id).store_metadata(JOB_FILE_PID, str(pid))

    # with job lock
    def _get_pid_for_killing_or_cancel(self, job_id):
        job_status = self._get_status(job_id)
        if job_status not in [status.RUNNING, status.QUEUED]:
            return

        pid = self.__get_pid(job_id)
        self._record_cancel(job_id)
        if pid is None:
            self._job_directory(job_id).remove_metadata(JOB_FILE_SUBMITTED)
        return pid

    def _run(self, job_id, command_line, montior: MonitorStyle = MonitorStyle.BACKGROUND):
        with self._get_job_lock(job_id):
            if self._was_cancelled(job_id):
                return

        proc, stdout, stderr = self._proc_for_job_id(job_id, command_line)
        with self._get_job_lock(job_id):
            self._record_pid(job_id, proc.pid)
        self._start_monitor(job_id, proc, stdout, stderr, montior=montior)

    def _proc_for_job_id(self, job_id, command_line):
        job_directory = self.job_directory(job_id)
        working_directory = job_directory.working_directory()
        stdout = self._open_job_standard_output(job_id)
        stderr = self._open_job_standard_error(job_id)
        proc = execute(command_line=command_line,
                       working_directory=working_directory,
                       stdout=stdout,
                       stderr=stderr)
        return proc, stdout, stderr

    def launch(self, job_id, command_line, submit_params={}, dependencies_description=None, env=[], setup_params=None):
        command_line = self._prepare_run(job_id, command_line, dependencies_description=dependencies_description, env=env, setup_params=setup_params)
        self._run(job_id, command_line)


class CoexecutionManager(BaseUnqueuedManager):
    """Manager that managers one job in a pod-like environment.

    Assume some process in another container will execute the command.
    """
    manager_type = "coexecution"

    def __init__(self, name, app, **kwds):
        super().__init__(name, app, **kwds)
        self.monitor = MonitorStyle(kwds.get("monitor", "background"))

    def get_status(self, job_id):
        return self._get_status(job_id)

    def kill(self, job_id):
        log.info("Attempting to kill job with job_id %s - unimplemented in CoexecutionManager..." % job_id)

    def _monitor_execution(self, job_id):
        return_code_path = self._return_code_path(job_id)
        try:
            while not os.path.exists(return_code_path):
                time.sleep(0.1)
                print("monitoring for %s" % return_code_path)
                continue
            print("found return code path...")
            self._job_directory(job_id).remove_metadata(JOB_FILE_PID)
            time.sleep(1)
        finally:
            self._finish_execution(job_id)

    def finish_execution(self, job_id):
        # expose this publicly for post-processing containers
        self._job_directory(job_id).remove_metadata(JOB_FILE_PID)
        self._finish_execution(job_id)

    def launch(self, job_id, command_line, submit_params={}, dependencies_description=None, env=[], setup_params=None):
        command_line = self._prepare_run(job_id, command_line, dependencies_description=dependencies_description, env=env, setup_params=setup_params)
        job_directory = self.job_directory(job_id)
        working_directory = job_directory.working_directory()
        command_line = "cd '{}'; sh {}".format(working_directory, command_line)
        log.info("writing command line [%s] for co-execution" % command_line)
        self._write_command_line(job_id, command_line)
        # Write dummy JOB_FILE_PID so get_status thinks this job is running.
        self._job_directory(job_id).store_metadata(JOB_FILE_PID, "1")
        monitor = self.monitor
        self._start_monitor(job_id, monitor=monitor)


def execute(command_line, working_directory, stdout, stderr):
    preexec_fn = None
    if platform.system() != 'Windows':
        preexec_fn = os.setpgrp
    proc = Popen(
        args=command_line,
        shell=True,
        cwd=working_directory,
        stdout=stdout,
        stderr=stderr,
        preexec_fn=preexec_fn,
        env=new_clean_env(),
    )
    return proc


__all__ = ['Manager']
