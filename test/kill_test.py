import os
import signal
import subprocess
import time
from contextlib import contextmanager

import psutil
import pytest

from pulsar.managers.util.kill import kill_pid

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Requires POSIX signals and bash")


@contextmanager
def running_job(tmp_path, script):
    ready = tmp_path / "ready"
    process = subprocess.Popen(["bash", "-c", script, "job", str(tmp_path)], start_new_session=True)
    try:
        deadline = time.monotonic() + 10
        while not ready.exists():
            assert process.poll() is None, "Job exited before becoming ready"
            assert time.monotonic() < deadline, "Job did not become ready"
            time.sleep(0.01)
        yield process
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        process.wait(timeout=10)


@pytest.mark.parametrize("use_psutil", [True, False])
def test_cancel_runs_exit_cleanup(tmp_path, use_psutil):
    # The fake Docker client reports readiness before becoming a foreground job.
    docker = tmp_path / "docker"
    docker.write_text('#!/bin/bash\ntouch "$1/ready"\nexec sleep 60\n')
    docker.chmod(0o755)
    script = """
trap 'sleep 0.1; echo cleaned > "$1/cleanup"' EXIT
"$1/docker" "$1"
"""
    with running_job(tmp_path, script) as process:
        if use_psutil:
            kill_pid(process.pid)
        else:
            kill_pid(process.pid, use_psutil=False, grace_period=0.5)
        assert (tmp_path / "cleanup").read_text().strip() == "cleaned"


@pytest.mark.parametrize("use_psutil", [True, False])
def test_cancel_escalates_for_term_ignoring_tree(tmp_path, use_psutil):
    script = """
trap '' TERM
sleep 60 &
echo $! > "$1/child"
touch "$1/ready"
wait
"""
    with running_job(tmp_path, script) as process:
        child = psutil.Process(int((tmp_path / "child").read_text()))
        started = time.monotonic()
        kill_pid(process.pid, use_psutil=use_psutil, grace_period=0.1)
        assert time.monotonic() - started < 5
        process.wait(timeout=5)
        assert_stopped(child.pid)


def test_cancel_missing_process():
    process = subprocess.Popen(["true"])
    process.wait(timeout=10)
    kill_pid(process.pid)


def test_cancel_kills_process_started_by_cleanup(tmp_path):
    script = """
cleanup() {
    trap '' TERM
    sleep 60 &
    echo $! > "$1/cleanup_child"
    wait
}
trap 'cleanup "$1"' EXIT
sleep 60 &
touch "$1/ready"
wait
"""
    with running_job(tmp_path, script) as process:
        kill_pid(process.pid, grace_period=0.5)
        child_pid = int((tmp_path / "cleanup_child").read_text())
        process.wait(timeout=5)
        assert_stopped(child_pid)


def assert_stopped(pid):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                return
        except psutil.NoSuchProcess:
            return
        time.sleep(0.01)
    pytest.fail(f"Process {pid} survived cancellation")


@pytest.mark.parametrize("grace_period", [-1, float("inf"), float("nan")])
def test_invalid_grace_period_does_not_signal(tmp_path, grace_period):
    script = 'touch "$1/ready"; exec sleep 60'
    with running_job(tmp_path, script) as process:
        with pytest.raises(ValueError, match="finite and nonnegative"):
            kill_pid(process.pid, grace_period=grace_period)
        assert process.poll() is None
