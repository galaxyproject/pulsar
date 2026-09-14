import shelve
import sqlite3
import traceback
from threading import Lock


class PersistenceStore:

    def __init__(self, filename, require_sync=True):
        self.shelf_filename = filename
        self.__require_sync = require_sync
        self.__open_shelf()
        self.__shelf_lock = Lock()

    def __open_shelf(self):
        if not self.shelf_filename:
            self.shelf = None
            return
        self.shelf = shelve.open(self.shelf_filename, writeback=self.__require_sync)
        self.__make_shelf_thread_safe()

    def __make_shelf_thread_safe(self):
        # Python 3.13 added dbm.sqlite3 as a default backend candidate; its
        # sqlite3 connection rejects cross-thread use. We serialise all
        # shelf access via __shelf_lock, so it is safe to drop that check.
        db = self.shelf.dict
        if type(db).__module__ != "dbm.sqlite3":
            return
        path_row = db._cx.execute("PRAGMA database_list").fetchone()
        path = path_row[2]
        db._cx.close()
        db._cx = sqlite3.connect(path, autocommit=True, check_same_thread=False)

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
