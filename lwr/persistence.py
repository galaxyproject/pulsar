import shelve
from threading import Lock
import traceback
import sys


class PersistenceStore(object):

    def __init__(self, filename):
        self.shelf_filename = filename
        self.__open_shelf()
        self.__shelf_lock = Lock()

    def __open_shelf(self):
        self.shelf = shelve.open(self.shelf_filename) if self.shelf_filename else None

    def close(self):
        self.shelf.close()

    def _lock(self):
        return self.__shelf_lock

    def _with_lock(self, func, suppress_exception=True):
        if self.shelf is not None:
            with self._lock():
                try:
                    return func()
                except:
                    traceback.print_exc(file=sys.stdout)
                    if not suppress_exception:
                        raise


class PersistedJobStore(PersistenceStore):
    """

    >>> import tempfile
    >>> import os
    >>> tf = tempfile.NamedTemporaryFile()
    >>> os.remove(tf.name)
    >>> store = PersistedJobStore(shelf_filename=tf.name)
    >>> store.enqueue("moo", "1234", "/bin/ls")
    >>> jobs = store.persisted_jobs("moo")
    >>> jobs[0][0]
    '1234'
    >>> jobs[0][1]
    '/bin/ls'
    >>> store = PersistedJobStore(shelf_filename=tf.name)
    >>> try:
    ...     tf.close()
    ... except:
    ...     pass
    >>>
    """

    def __init__(self, **conf):
        super(PersistedJobStore, self).__init__(conf.get('shelf_filename', None))

    def enqueue(self, manager_name, job_id, command_line):
        shelf_id = self.__shelf_id(manager_name, job_id)

        def set_command_line():
            self.shelf[shelf_id] = command_line

        self._with_lock(set_command_line)

    def dequeue(self, manager_name, job_id):
        shelf_id = self.__shelf_id(manager_name, job_id)

        def delete():
            del self.shelf[shelf_id]

        self._with_lock(delete)

    def persisted_jobs(self, manager_name):
        prefix = '%s:' % manager_name
        jobs = []

        def set_jobs():
            shelf_keys = self.shelf.keys()
            persisted_shelf_ids = [shelf_key for shelf_key in shelf_keys if shelf_key.startswith(prefix)]
            jobs.extend([(shelf_id[len(prefix):], self.shelf[shelf_id]) for shelf_id in persisted_shelf_ids])

        self._with_lock(set_jobs)
        return jobs

    def __shelf_id(self, manager_name, job_id):
        return '%s:%s' % (manager_name, str(job_id))
