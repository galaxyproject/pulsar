import multiprocessing
try:
    from Queue import Queue
except ImportError:
    from queue import Queue
import sys
import threading
import traceback

from lwr.managers.unqueued import Manager

from logging import getLogger
log = getLogger(__name__)

STOP_SIGNAL = object()
RUN = object()
# Number of concurrent jobs used by default for
# QueueManager.
DEFAULT_NUM_CONCURRENT_JOBS = 1


class QueueManager(Manager):
    """
    A job manager that queues up jobs directly (i.e. does not use an
    external queuing software such PBS, SGE, etc...).
    """
    manager_type = "queued_python"

    def __init__(self, name, app, **kwds):
        super(QueueManager, self).__init__(name, app, **kwds)
        self.persisted_job_store = app.persisted_job_store

        num_concurrent_jobs = kwds.get('num_concurrent_jobs', DEFAULT_NUM_CONCURRENT_JOBS)
        if num_concurrent_jobs == '*':
            num_concurrent_jobs = multiprocessing.cpu_count()
        else:
            num_concurrent_jobs = int(num_concurrent_jobs)

        self._init_worker_threads(num_concurrent_jobs)
        self._recover()

    def _init_worker_threads(self, num_concurrent_jobs):
        self.work_queue = Queue()
        self.work_threads = []
        for i in range(num_concurrent_jobs):
            worker = threading.Thread(target=self.run_next)
            worker.start()
            self.work_threads.append(worker)

    def launch(self, job_id, command_line):
        self._prepare_run(job_id, command_line)
        self.work_queue.put((RUN, (job_id, command_line)))
        self.persisted_job_store.enqueue(self.name, job_id, command_line)

    def _recover(self):
        for (job_id, command_line) in self.persisted_job_store.persisted_jobs(self.name):
            self._register_job(job_id, new=False)
            self.work_queue.put((RUN, (job_id, command_line)))

    def shutdown(self):
        self.work_queue.put((STOP_SIGNAL, None))

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
                self.persisted_job_store.dequeue(self.name, job_id)
                self._run(job_id, command_line, async=False)
            except:
                log.warn("Uncaught exception running job with job_id %s" % job_id)
                traceback.print_exc(file=sys.stdout)
