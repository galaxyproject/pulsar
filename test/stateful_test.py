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


class _RecordingRecoveryManager(_ScriptedStatusManager):
    """Records which jobs the runner was asked to recover."""

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.recovered = []

    def _recover_active_job(self, job_id):
        self.recovered.append(job_id)


class _RecoveringStatusManager(_ScriptedStatusManager):
    """Requires recovery to finish before the first status check."""

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.recovered = False
        self.status_checked = threading.Event()

    def _recover_active_job(self, job_id):
        self.recovered = True

    def get_status(self, job_id):
        assert self.recovered
        self.status_checked.set()
        return super().get_status(job_id)


class _FailingRecoveryManager(_ScriptedStatusManager):
    def _recover_active_job(self, job_id):
        raise Exception("Test recovery failure")


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


def test_monitor_can_start_after_external_job_recovery():
    with _proxy(_RecoveringStatusManager) as (proxy, manager):
        job_id = proxy.setup_job(TEST_JOB_ID, "tool1", "1.0.0")
        manager.job_directory(job_id).store_metadata(
            stateful.JOB_FILE_PREPROCESSED,
            True,
        )
        proxy.active_jobs.activate_job(job_id)
        callback = mock.Mock()
        proxy.set_state_change_callback(callback, start_monitor=False)

        assert not manager.status_checked.wait(.1)
        proxy.recover_active_jobs()
        proxy.start_monitor()

        assert manager.status_checked.wait(1)


def test_recovery_failure_notifies_bound_callback_before_monitor_starts():
    with _proxy(_FailingRecoveryManager) as (proxy, manager):
        proxy.active_jobs.activate_job(TEST_JOB_ID)
        callback = mock.Mock()
        proxy.set_state_change_callback(callback, start_monitor=False)

        proxy.recover_active_jobs()

        callback.assert_called_once_with(status.LOST, TEST_JOB_ID)
        assert proxy.active_jobs.active_job_ids() == []


def test_postprocessing_job_is_tracked_as_active():
    with _launched_job() as (proxy, manager, job_id):
        manager.scripted_status = status.COMPLETE
        with _postprocessing_held() as release:
            assert proxy.get_status(job_id) == status.POSTPROCESSING
            # A restart at this instant must still find the job - postprocessing
            # is the only index it is in.
            assert _postprocessing_job_ids(proxy) == [job_id]
            assert proxy.active_jobs.active_job_ids() == []
            release.set()
        _wait_for_callback(proxy)
        _wait_for_postprocessing_index_cleared(proxy)


def test_recover_active_jobs_redrives_interrupted_postprocessing():
    app = minimal_app_for_managers()
    try:
        with _proxy(app=app) as (proxy, manager):
            job_id = proxy.setup_job(TEST_JOB_ID, "tool1", "1.0.0")
            proxy.preprocess_and_launch(job_id, TEST_LAUNCH_CONFIG)
            _interrupt_postprocessing(proxy, manager, job_id)

        with _proxy(app=app) as (proxy, manager):
            proxy.recover_active_jobs()
            _wait_for_callback(proxy)
            assert proxy.callbacks == [(status.COMPLETE, job_id)]
            assert manager.job_directory(job_id).has_metadata(
                stateful.JOB_FILE_POSTPROCESSED
            )
            _wait_for_postprocessing_index_cleared(proxy)
    finally:
        rmtree(app.staging_directory, ignore_errors=True)


def test_job_killed_between_indexes_is_not_rerun():
    """A job in both indexes is postprocessed, never handed to the runner.

    ``__handle_terminal_status`` indexes the job for postprocessing before it
    removes it from the launched index, so a kill lands in a window where it is
    in both. Recovering it as a launched job would re-run the tool.
    """
    app = minimal_app_for_managers()
    try:
        with _proxy(_RecordingRecoveryManager, app=app) as (proxy, manager):
            job_id = proxy.setup_job(TEST_JOB_ID, "tool1", "1.0.0")
            proxy.preprocess_and_launch(job_id, TEST_LAUNCH_CONFIG)
            _interrupt_postprocessing(proxy, manager, job_id, leave_launched=True)

        with _proxy(_RecordingRecoveryManager, app=app) as (proxy, manager):
            proxy.recover_active_jobs()
            _wait_for_callback(proxy)
            assert proxy.callbacks == [(status.COMPLETE, job_id)]
            assert manager.recovered == []
            assert proxy.active_jobs.active_job_ids() == []
            _wait_for_postprocessing_index_cleared(proxy)
    finally:
        rmtree(app.staging_directory, ignore_errors=True)


def test_terminal_job_left_in_launched_index_is_postprocessed():
    """Killed after the terminal status was recorded, before it was indexed.

    The job is only in the launched index, but its outputs still need staging -
    and the runner's recovery would re-run it.
    """
    app = minimal_app_for_managers()
    try:
        with _proxy(_RecordingRecoveryManager, app=app) as (proxy, manager):
            job_id = proxy.setup_job(TEST_JOB_ID, "tool1", "1.0.0")
            proxy.preprocess_and_launch(job_id, TEST_LAUNCH_CONFIG)
            with manager.job_directory(job_id).lock("status"):
                manager.job_directory(job_id).store_metadata(
                    stateful.JOB_FILE_FINAL_STATUS, status.COMPLETE
                )

        with _proxy(_RecordingRecoveryManager, app=app) as (proxy, manager):
            proxy.recover_active_jobs()
            _wait_for_callback(proxy)
            assert proxy.callbacks == [(status.COMPLETE, job_id)]
            assert manager.recovered == []
            assert proxy.active_jobs.active_job_ids() == []
    finally:
        rmtree(app.staging_directory, ignore_errors=True)


def test_interrupted_postprocessing_is_not_reported_lost():
    app = minimal_app_for_managers()
    try:
        with _proxy(app=app) as (proxy, manager):
            job_id = proxy.setup_job(TEST_JOB_ID, "tool1", "1.0.0")
            proxy.preprocess_and_launch(job_id, TEST_LAUNCH_CONFIG)
            _interrupt_postprocessing(proxy, manager, job_id)

        with _proxy(app=app) as (proxy, manager):
            proxy.recover_active_jobs()
            _wait_for_callback(proxy)
            assert (status.LOST, job_id) not in proxy.callbacks
            assert proxy.get_status(job_id) == status.COMPLETE
    finally:
        rmtree(app.staging_directory, ignore_errors=True)


@contextmanager
def _proxy(manager_class=_ScriptedStatusManager, app=None):
    """Yield a proxy, owning the app whose staging directory it uses.

    Pass ``app`` to build a second proxy over state a first one left behind -
    what a restarted Pulsar sees. The caller then owns the cleanup.
    """
    owns_app = app is None
    if owns_app:
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
        if owns_app:
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


def _wait_for(condition, description, timeout=5):
    time_end = time.time() + timeout
    while time.time() < time_end:
        if condition():
            return
        time.sleep(.01)
    raise AssertionError("Timed out waiting for %s." % description)


def _wait_for_callback(proxy, timeout=5):
    _wait_for(lambda: proxy.callbacks, "a state change callback", timeout=timeout)


def _wait_for_postprocessing_index_cleared(proxy, timeout=5):
    _wait_for(
        lambda: _postprocessing_job_ids(proxy) == [],
        "the postprocessing index to be cleared",
        timeout=timeout,
    )


def _postprocessing_job_ids(proxy):
    return proxy.active_jobs.active_job_ids(
        active_status=stateful.ACTIVE_STATUS_POSTPROCESSING
    )


def _interrupt_postprocessing(proxy, manager, job_id, leave_launched=False):
    """Leave behind what a Pulsar killed mid-postprocessing leaves behind.

    A terminal status on disk, an entry in the postprocessing index, and no
    outputs staged. ``leave_launched`` models the narrower kill window between
    the two index writes, where the job is in both.
    """
    job_directory = manager.job_directory(job_id)
    with job_directory.lock("status"):
        job_directory.store_metadata(stateful.JOB_FILE_FINAL_STATUS, status.COMPLETE)
    proxy.active_jobs.activate_job(
        job_id, active_status=stateful.ACTIVE_STATUS_POSTPROCESSING
    )
    if not leave_launched:
        proxy.active_jobs.deactivate_job(job_id)
    assert not job_directory.has_metadata(stateful.JOB_FILE_POSTPROCESSED)
