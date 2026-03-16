from types import ModuleType
from typing import Dict, Optional, Union, TYPE_CHECKING
try:
    import lockfile
except ImportError:
    lockfile = None

if TYPE_CHECKING:
    from threading import Lock
    try:
        from lockfile import LockFile
    except ImportError:
        LockFile = object


import logging
import threading

log = logging.getLogger(__name__)

NO_PYLOCKFILE_MESSAGE = "pylockfile module not found, skipping experimental lockfile handling."


class LockManager():

    def __init__(self, lockfile: Optional[ModuleType] = lockfile):
        if not lockfile:
            log.info(NO_PYLOCKFILE_MESSAGE)
            self.job_locks: Dict[str, "Lock"] = dict()
            self.job_locks_lock: "Lock" = threading.Lock()
        self.lockfile: Optional[ModuleType] = lockfile

    def get_lock(self, path: str) -> Union["Lock", "LockFile"]:
        """ Get a job lock corresponding to the path - assumes parent
        directory exists but the file itself does not.
        """
        if self.lockfile:
            return self.lockfile.LockFile(path)
        else:
            with self.job_locks_lock:
                if path not in self.job_locks:
                    lock = threading.Lock()
                    self.job_locks[path] = lock
                else:
                    lock = self.job_locks[path]
            return lock

    def free_lock(self, path: str) -> None:
        # Not needed with pylockfile
        # Not currently be called, will result in tiny memory leak if
        # pylockfile is unavailable - so if you process millions of jobs
        # install pylockfile.
        if not self.lockfile:
            with self.job_locks_lock:
                if path in self.job_locks:
                    del self.job_locks[path]
