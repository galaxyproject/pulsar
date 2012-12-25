import shelve
from threading import Lock
import traceback
import sys


class PersistedJobStore:
    """

    >>> import tempfile
    >>> import os
    >>> tf = tempfile.NamedTemporaryFile(delete=False)
    >>> os.remove(tf.name)
    >>> store = PersistedJobStore(shelf_filename=tf.name)
    >>> store.enqueue("moo", "1234", "/bin/ls")
    >>> jobs = store.persisted_jobs("moo")
    >>> jobs[0][0]
    '1234'
    >>> jobs[0][1]
    '/bin/ls'
    >>> tf.close()
    """

    def __init__(self, **conf):
        self.shelf_filename = conf.get('shelf_filename', None)
        self._open_shelf()
        self.shelf_lock = Lock()

    def _open_shelf(self):
        self.shelf = shelve.open(self.shelf_filename) if self.shelf_filename else None

    def close(self):
        self.shelf.close()

    def __with_lock(self, func):
        if self.shelf is not None:
            with self.shelf_lock:
                try:
                    func()
                except:
                    traceback.print_exc(file=sys.stdout)
                    pass

    def enqueue(self, manager_name, job_id, command_line):
        shelf_id = self._shelf_id(manager_name, job_id)

        def set_command_line():
            self.shelf[shelf_id] = command_line

        self.__with_lock(set_command_line)

    def dequeue(self, manager_name, job_id):
        shelf_id = self._shelf_id(manager_name, job_id)

        def delete():
            del self.shelf[shelf_id]

        self.__with_lock(delete)

    def persisted_jobs(self, manager_name):
        prefix = '%s:' % manager_name
        jobs = []

        def set_jobs():
            shelf_keys = self.shelf.keys()
            persisted_shelf_ids = [shelf_key for shelf_key in shelf_keys if shelf_key.startswith(prefix)]
            jobs.extend([(shelf_id[len(prefix):], self.shelf[shelf_id]) for shelf_id in persisted_shelf_ids])

        self.__with_lock(set_jobs)

        return jobs

    def _shelf_id(self, manager_name, job_id):
        return '%s:%s' % (manager_name, str(job_id))
