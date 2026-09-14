"""Tests for terminal status handling in :class:`StatefulManagerProxy`."""
import threading
import time
from contextlib import contextmanager
from shutil import rmtree
from unittest import mock

from pulsar.managers import (
    stateful,
    status,
)
from pulsar.managers.queued import QueueManager
from pulsar.managers.stateful import StatefulManagerProxy
from .test_utils import minimal_app_for_managers

TEST_JOB_ID = "4"
# An empty staging config exercises postprocessing without external transfers.
TEST_LAUNCH_CONFIG = {"command_line": "true", "remote_staging": {}}


class _ScriptedStatusManager(QueueManager):
    """Runs nothing, reports whatever status the test scripts."""

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.scripted_status = status.QUEUED
        self.deactivated = []

    def get_status(self, job_id):
        return self.scripted_status

    def _deactivate_job(self, job_id):
        self.deactivated.append(job_id)


class _FailingLaunchManager(_ScriptedStatusManager):
    """Raises during launch."""

    def launch(self, *args, **kwds):
        raise Exception("Test failure launching job")


class _RecordingStatefulManagerProxy(StatefulManagerProxy):
    """Records state changes without starting a monitor thread.

    ``set_state_change_callback`` would also build a ``ManagerMonitor``, whose
    polling would race the explicit ``get_status`` calls these tests make.
    """

    def __init__(self, manager, **kwds):
        super().__init__(manager, **kwds)
        self.callbacks = []

    def _default_status_change_callback(self, job_status, job_id):
        self.callbacks.append((job_status, job_id))


def test_failed_status_deactivates_and_notifies():
    with _launched_job() as (proxy, manager, job_id):
        manager.scripted_status = status.FAILED
        # Outputs are staged before the terminal callback.
        with _postprocessing_held() as release:
            assert proxy.get_status(job_id) == status.POSTPROCESSING
            release.set()
        _wait_for_callback(proxy)
        assert proxy.callbacks == [(status.FAILED, job_id)]
        assert proxy.active_jobs.active_job_ids() == []
        assert manager.deactivated == [job_id]
        assert proxy.get_status(job_id) == status.FAILED


def test_lost_status_is_not_terminal():
    with _launched_job() as (proxy, manager, job_id):
        manager.scripted_status = status.LOST
        assert proxy.get_status(job_id) == status.LOST
        # LOST can be transient while an external job ID is being recovered.
        assert proxy.active_jobs.active_job_ids() == [job_id]
        assert manager.deactivated == []
        time.sleep(.1)
        assert proxy.callbacks == []

        manager.scripted_status = status.COMPLETE
        with _postprocessing_held() as release:
            assert proxy.get_status(job_id) == status.POSTPROCESSING
            release.set()
        _wait_for_callback(proxy)
        assert proxy.callbacks == [(status.COMPLETE, job_id)]


def test_complete_status_postprocesses_and_notifies():
    with _launched_job() as (proxy, manager, job_id):
        manager.scripted_status = status.COMPLETE
        with _postprocessing_held() as release:
            assert proxy.get_status(job_id) == status.POSTPROCESSING
            release.set()
        _wait_for_callback(proxy)
        assert proxy.callbacks == [(status.COMPLETE, job_id)]
        assert proxy.active_jobs.active_job_ids() == []
        assert proxy.get_status(job_id) == status.COMPLETE


def test_cancelled_status_deactivates_without_notification():
    with _launched_job() as (proxy, manager, job_id):
        manager.scripted_status = status.CANCELLED
        assert proxy.get_status(job_id) == status.CANCELLED
        assert proxy.active_jobs.active_job_ids() == []
        assert manager.deactivated == [job_id]
        # Cancellation is client-initiated and requires no callback.
        time.sleep(.1)
        assert proxy.callbacks == []


def test_terminal_status_is_reported_once():
    with _launched_job() as (proxy, manager, job_id):
        manager.scripted_status = status.FAILED
        proxy.get_status(job_id)
        _wait_for_callback(proxy)
        # Persisted terminal status takes precedence over later manager results.
        manager.scripted_status = status.RUNNING
        for _ in range(3):
            assert proxy.get_status(job_id) == status.FAILED
        assert proxy.callbacks == [(status.FAILED, job_id)]


def test_preprocessing_failure_is_reported_once():
    with _proxy(_FailingLaunchManager) as (proxy, manager):
        job_id = proxy.setup_job(TEST_JOB_ID, "tool1", "1.0.0")
        proxy.preprocess_and_launch(job_id, TEST_LAUNCH_CONFIG)
        assert proxy.callbacks == [(status.FAILED, job_id)]
        for _ in range(3):
            assert proxy.get_status(job_id) == status.FAILED
        # No postprocessing or second callback is needed before launch.
        time.sleep(.1)
        assert proxy.callbacks == [(status.FAILED, job_id)]


@contextmanager
def _proxy(manager_class=_ScriptedStatusManager):
    app = minimal_app_for_managers()
    manager = manager_class("test", app, num_concurrent_jobs=0)
    proxy = _RecordingStatefulManagerProxy(manager)
    try:
        yield proxy, manager
    finally:
        try:
            proxy.shutdown()
        except Exception:
            pass
        rmtree(app.staging_directory, ignore_errors=True)


@contextmanager
def _launched_job():
    with _proxy() as (proxy, manager):
        job_id = proxy.setup_job(TEST_JOB_ID, "tool1", "1.0.0")
        proxy.preprocess_and_launch(job_id, TEST_LAUNCH_CONFIG)
        assert proxy.active_jobs.active_job_ids() == [job_id]
        yield proxy, manager, job_id


@contextmanager
def _postprocessing_held(timeout=5):
    """Hold postprocessing until the test releases it.

    ``get_status`` starts postprocessing on its own thread and then reports
    POSTPROCESSING only while that thread has not finished.  These jobs have
    nothing to stage, so the thread can finish first and ``get_status`` returns
    the terminal status instead - correct behaviour, but it makes any assertion
    on POSTPROCESSING a race.
    """
    release = threading.Event()
    real_postprocess = stateful.postprocess

    def held_postprocess(*args, **kwds):
        if not release.wait(timeout):
            raise AssertionError("Timed out waiting for postprocessing to be released.")
        return real_postprocess(*args, **kwds)

    with mock.patch.object(stateful, "postprocess", held_postprocess):
        yield release


def _wait_for_callback(proxy, timeout=5):
    time_end = time.time() + timeout
    while time.time() < time_end:
        if proxy.callbacks:
            return
        time.sleep(.01)
    raise AssertionError("Timed out waiting for a state change callback.")
