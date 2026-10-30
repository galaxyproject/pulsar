import os
import signal
import subprocess
from math import isfinite
from platform import system
from time import sleep
from typing import TYPE_CHECKING

try:
    from psutil import (
        NoSuchProcess,
        Process,
        wait_procs,
    )
except ImportError:
    """Don't make psutil a strict requirement, but use if available."""
    if not TYPE_CHECKING:
        Process = None


def kill_pid(pid: int, use_psutil: bool = True, grace_period: float = 5):
    """Terminate a job tree, allowing POSIX cleanup before killing survivors.

    ``grace_period`` bounds the SIGTERM wait in seconds. On Windows psutil
    terminate, like taskkill /F, stops processes without a grace period.
    """
    if not isfinite(grace_period) or grace_period < 0:
        raise ValueError("grace_period must be finite and nonnegative")
    if use_psutil and Process is not None:
        _psutil_kill_pid(pid, grace_period)
    else:
        _stock_kill_pid(pid, grace_period)


def _psutil_kill_pid(pid: int, grace_period: float = 5):
    try:
        parent = Process(pid)
        processes = [parent, *parent.children(recursive=True)]
    except NoSuchProcess:
        return

    # Signal waiting shells first: terminating a child can start its shell's
    # EXIT trap, which a later TERM to that shell would interrupt.
    for process in processes:
        try:
            process.terminate()
        except NoSuchProcess:
            pass
    _, alive = wait_procs(processes, timeout=grace_period)
    # EXIT handlers may start cleanup commands during the grace period.
    survivors = set(alive)
    for process in alive:
        try:
            survivors.update(process.children(recursive=True))
        except NoSuchProcess:
            pass
    for process in survivors:
        try:
            process.kill()
        except NoSuchProcess:
            pass


def _stock_kill_pid(pid: int, grace_period: float = 5):
    is_windows = system() == "Windows"

    if is_windows:
        __kill_windows(pid)
    else:
        __kill_posix(pid, grace_period)


def __kill_windows(pid):
    try:
        subprocess.check_call(["taskkill", "/F", "/T", "/PID", str(pid)])
    except subprocess.CalledProcessError:
        pass


def __kill_posix(pid: int, grace_period: float = 5):
    def __check_pid():
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    if __check_pid():
        for sig in [signal.SIGTERM, signal.SIGKILL]:
            try:
                os.killpg(pid, sig)
            except OSError:
                return
            if sig == signal.SIGTERM:
                sleep(grace_period)
            if not __check_pid():
                return
