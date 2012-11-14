from shelve import Shelf
from threading import Lock


class PersistedJobStore:

    def __init__(self, **conf):
        shelf_filename = conf.get('shelf_filename', None)
        shelf_flag = conf.get('shelf_flag', 'c')
        shelf_protocol = conf.get('shelf_protocol', None)
        self.shelf = Shelf(shelf_filename, shelf_flag, shelf_protocol) if shelf_filename else None
        self.shelf_lock = Lock()

    def queue(self, manager_name, job_id, command_line):
        shelf_id = self._shelf_id(manager_name, job_id)
        if self.shelf:
            with self.shelf_lock:
                try:
                    self.shelf[shelf_id] = command_line
                except:
                    pass

    def dequeue(self, manager_name, job_id):
        shelf_id = self._shelf_id(manager_name, job_id)
        if self.shelf:
            with self.shelf_lock:
                try:
                    del self.shelf[shelf_id]
                except:
                    pass

    def persisted_jobs(self, manager_name):
        prefix = '%s:' % manager_name
        jobs = []
        if self.shelf:
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
