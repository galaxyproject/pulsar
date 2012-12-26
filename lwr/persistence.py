import shelve
from threading import Lock
import traceback
import sys


class PersistedJobStore:
    """

    >>> import tempfile
    >>> import os
    >>> tf = tempfile.NamedTemporaryFile()
    >>> os.remove(tf.name)
    >>> store = PersistedJobStore(shelf_filename=tf.name)
    >>> store.next_id()
    1
    >>> store.enqueue("moo", "1234", "/bin/ls")
    >>> jobs = store.persisted_jobs("moo")
    >>> jobs[0][0]
    '1234'
    >>> jobs[0][1]
    '/bin/ls'
    >>> store.next_id()
    2
    >>> store = PersistedJobStore(shelf_filename=tf.name)
    >>> store.next_id()
    3
    >>> tf.close()
    """

    def __init__(self, **conf):
        self.shelf_filename = conf.get('shelf_filename', None)
        self.__open_shelf()
        self.id = 0
        self.shelf_lock = Lock()

    def __open_shelf(self):
        self.shelf = shelve.open(self.shelf_filename) if self.shelf_filename else None

    def close(self):
        self.shelf.close()

    def __with_lock(self, func, suppress_exception=True):
        if self.shelf is not None:
            with self.shelf_lock:
                try:
                    return func()
                except:
                    traceback.print_exc(file=sys.stdout)
                    if not suppress_exception:
                        raise

    def enqueue(self, manager_name, job_id, command_line):
        shelf_id = self.__shelf_id(manager_name, job_id)

        def set_command_line():
            self.shelf[shelf_id] = command_line

        self.__with_lock(set_command_line)

    def dequeue(self, manager_name, job_id):
        shelf_id = self.__shelf_id(manager_name, job_id)

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

    def next_id(self):
        with self.shelf_lock:
            if self.id == 0 and self.shelf is not None:
                self.id = self.shelf.get("*id*", 0)
            self.id += 1
            if self.shelf is not None:
                self.shelf["*id*"] = self.id
            id = self.id
        return id

    def __shelf_id(self, manager_name, job_id):
        return '%s:%s' % (manager_name, str(job_id))
