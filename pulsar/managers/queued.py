import os
import multiprocessing
from six.moves import queue
import threading
import traceback

from pulsar.managers.unqueued import Manager

from logging import getLogger
log = getLogger(__name__)

STOP_SIGNAL = object()
RUN = object()
# Number of concurrent jobs used by default for
# QueueManager.
DEFAULT_NUM_CONCURRENT_JOBS = 1

JOB_FILE_COMMAND_LINE = "command_line"


class QueueManager(Manager):
    """
    A job manager that queues up jobs directly (i.e. does not use an
    external queuing software such PBS, SGE, etc...).
    """
    manager_type = "queued_python"

    def __init__(self, name, app, **kwds):
        super(QueueManager, self).__init__(name, app, **kwds)

        num_concurrent_jobs = kwds.get('num_concurrent_jobs', DEFAULT_NUM_CONCURRENT_JOBS)
        if num_concurrent_jobs == '*':
            num_concurrent_jobs = multiprocessing.cpu_count()
        else:
            num_concurrent_jobs = int(num_concurrent_jobs)

        self._init_worker_threads(num_concurrent_jobs)

    def _init_worker_threads(self, num_concurrent_jobs):
        self.work_queue = queue.Queue()
        self.work_threads = []
        for i in range(num_concurrent_jobs):
            worker = threading.Thread(target=self.run_next)
            worker.daemon = True
            worker.start()
            self.work_threads.append(worker)

    def launch(self, job_id, command_line, submit_params={}, dependencies_description=None, env=[], setup_params=None):
        command_line = self._prepare_run(
            job_id,
            command_line,
            dependencies_description=dependencies_description,
            env=env,
            setup_params=setup_params
        )
        try:
            self._write_command_line(job_id, command_line)
        except Exception:
            log.info("Failed to persist command line for job %s, will not be able to recover." % job_id)
        self.work_queue.put((RUN, (job_id, command_line)))

    def _recover_active_job(self, job_id):
        command_line = self.read_command_line(job_id)
        if command_line:
            self.work_queue.put((RUN, (job_id, command_line)))
        else:
            raise Exception("Cannot recover job with id %s" % job_id)

    def shutdown(self, timeout=None):
        for i in range(len(self.work_threads)):
            self.work_queue.put((STOP_SIGNAL, None))
        for worker in self.work_threads:
            worker.join(timeout)
            if worker.isAlive():
                log.warn("Failed to stop worker thread [%s]" % worker)

    def run_next(self):
        """
        Run the next item in the queue (a job waiting to run).
        """
        while 1:
            (op, obj) = self.work_queue.get()
            if op is STOP_SIGNAL:
                return
            try:
                (job_id, command_line) = obj
                try:
                    os.remove(self._job_file(job_id, JOB_FILE_COMMAND_LINE))
                except Exception:
                    log.exception("Running command but failed to delete - command may rerun on Pulsar boot.")
                # _run will not do anything if job has been cancelled.
                self._run(job_id, command_line, background=False)
            except Exception:
                log.warn("Uncaught exception running job with job_id %s" % job_id)
                traceback.print_exc()
