
import shelve
import traceback

from threading import Lock


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
                except Exception:
                    traceback.print_exc()
                    if not suppress_exception:
                        raise
