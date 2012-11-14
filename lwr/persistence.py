import shelve
from threading import Lock
import traceback
import sys


class PersistedJobStore:

    def __init__(self, **conf):
        self.shelf_filename = conf.get('shelf_filename', None)
        self._open_shelf()
        self.shelf_lock = Lock()

    def _open_shelf(self):
        self.shelf = shelve.open(self.shelf_filename) if self.shelf_filename else None

    def close(self):
        self.shelf.close()

    def queue(self, manager_name, job_id, command_line):
        shelf_id = self._shelf_id(manager_name, job_id)
        if self.shelf is not None:
            shelf = self.shelf
            with self.shelf_lock:
                try:
                    shelf[shelf_id] = command_line
                except:
                    traceback.print_exc(file=sys.stdout)
                    pass

    def dequeue(self, manager_name, job_id):
        shelf_id = self._shelf_id(manager_name, job_id)
        if self.shelf is not None:
            with self.shelf_lock:
                try:
                    del self.shelf[shelf_id]
                except:
                    pass

    def persisted_jobs(self, manager_name):
        prefix = '%s:' % manager_name
        jobs = []
        if self.shelf is not None:
            with self.shelf_lock:
                try:
                    shelf_keys = self.shelf.keys()
                    persisted_shelf_ids = [shelf_key for shelf_key in shelf_keys if shelf_key.startswith(prefix)]
                    jobs = [(shelf_id[len(prefix):], self.shelf[shelf_id]) for shelf_id in persisted_shelf_ids]
                except:
                    pass
        return jobs

    def _shelf_id(self, manager_name, job_id):
        return '%s:%s' % (manager_name, str(job_id))
