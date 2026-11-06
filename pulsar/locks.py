from types import ModuleType
from typing import (
    Dict,
    Optional,
    TYPE_CHECKING,
    Union,
)

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


import errno
import logging
import os
import threading
import time
from contextlib import contextmanager

log = logging.getLogger(__name__)

NO_PYLOCKFILE_MESSAGE = "pylockfile module not found, skipping experimental lockfile handling."


@contextmanager
def interprocess_lock(path):
    """Lock a stable file outside directories protected by the lock.

    Unlike the optional legacy lock manager, this also coordinates independent
    server processes when pylockfile is not installed.
    """
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.name == "nt":
            import msvcrt

            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
            while True:
                try:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    time.sleep(0.05)
            try:
                yield
            finally:
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


class LockManager:

    def __init__(self, lockfile: Optional[ModuleType] = lockfile):
        if not lockfile:
            log.info(NO_PYLOCKFILE_MESSAGE)
            self.job_locks: Dict[str, Lock] = {}
            self.job_locks_lock: Lock = threading.Lock()
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
