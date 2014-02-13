import shelve
from threading import Lock
import traceback


class PersistenceStore(object):

    def __init__(self, filename, require_sync=True):
        self.shelf_filename = filename
        self.__require_sync = require_sync
        self.__open_shelf()
        self.__shelf_lock = Lock()

    def __open_shelf(self):
        self.shelf = shelve.open(self.shelf_filename, writeback=self.__require_sync) if self.shelf_filename else None

    def close(self):
        self.shelf.close()

    def _sync_if_needed(self):
        if self.__require_sync:
            self.shelf.sync()

    def _lock(self):
        return self.__shelf_lock

    def _with_lock(self, func, suppress_exception=True):
        if self.shelf is not None:
            with self._lock():
                try:
                    return func()
                except:
                    traceback.print_exc()
                    if not suppress_exception:
                        raise


class JobMetadataStore(PersistenceStore):
    """

    """

    def __init__(self, path):
        super(JobMetadataStore, self).__init__(path)

    def _store(self, job_id, metadata):
        shelf_id = self.__shelf_id(job_id)

        def store():
            self.shelf[shelf_id] = metadata
            self._sync_if_needed()

        self._with_lock(store)

    def _delete(self, job_id):
        shelf_id = self.__shelf_id(job_id)

        def delete():
            del self.shelf[shelf_id]
            self._sync_if_needed()

        self._with_lock(delete)

    def _get(self, job_id, default):
        shelf_id = self.__shelf_id(job_id)
        return self.shelf.get(shelf_id, default)

    def _load(self):
        metadata = []

        def load():
            shelf_keys = self.shelf.keys()
            metadata.extend([(shelf_id, self.shelf[shelf_id]) for shelf_id in shelf_keys])

        self._with_lock(load)
        return dict(metadata)

    def __shelf_id(self, job_id):
        return str(job_id)
