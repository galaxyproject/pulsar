"""Tests for sending live stdout/stderr to Galaxy while jobs run.

Covers the incremental reads that feed Galaxy's append-on-POST files endpoint,
the limits that keep the cost bounded (chunk size, ``maximum_stream_size``,
no work for idle jobs, endpoint backoff), offsets surviving a Pulsar restart,
the completion flush, and the rule that the completion status may only drop
the streams once Galaxy holds them.
"""
import os
import threading
import time
from contextlib import contextmanager
from shutil import rmtree
from unittest import mock
from urllib.parse import (
    parse_qs,
    urlsplit,
)

import pytest
import requests

from pulsar import manager_endpoint_util
from pulsar.managers import (
    live_output,
    stateful,
    status,
)
from pulsar.managers.base import JobDirectory
from pulsar.managers.base.directory import (
    TOOL_FILE_STANDARD_ERROR,
    TOOL_FILE_STANDARD_OUTPUT,
)
from pulsar.managers.live_output import (
    JOB_FILE_LIVE_OUTPUT_STATE,
    LiveOutputReporter,
)
from pulsar.managers.queued import QueueManager
from pulsar.managers.stateful import StatefulManagerProxy
from .test_utils import minimal_app_for_managers

TEST_JOB_ID = "7"
FILES_ENDPOINT = "http://galaxy.example.org/api/jobs/1/files?job_key=abc"
REMOTE_STAGING = {
    "action_mapper": {"files_endpoint": FILES_ENDPOINT},
    "client_outputs": {"working_directory": "/galaxy/jobs/1/working"},
}


class _Poster:
    """Stands in for ``post_bytes``: records uploads, or raises ``error``."""

    def __init__(self):
        self.posts = []
        self.error = None
        self.lock = threading.Lock()
        # Set ``gate`` to hold POSTs until the test sets it; ``entered`` fires
        # once a POST is waiting on the gate.
        self.gate = None
        self.entered = threading.Event()

    def __call__(self, url, name, data, session=None, timeout=None):
        assert timeout is not None, "live output POSTs must have a timeout"
        if self.gate is not None:
            self.entered.set()
            assert self.gate.wait(5), "test never released the POST"
        if self.error is not None:
            raise self.error
        with self.lock:
            self.posts.append((parse_qs(urlsplit(url).query)["path"][0], data))

    def sent(self, stream_name):
        with self.lock:
            return b"".join(data for path, data in self.posts if path.endswith(stream_name))


class _FakeManager:
    def __init__(self, staging_directory):
        self.staging_directory = staging_directory

    def job_directory(self, job_id):
        return JobDirectory(self.staging_directory, job_id)


@pytest.fixture
def poster(monkeypatch):
    poster = _Poster()
    monkeypatch.setattr(live_output, "post_bytes", poster)
    return poster


@pytest.fixture
def manager(tmp_path):
    return _FakeManager(str(tmp_path))


def _job_directory(manager, job_id=TEST_JOB_ID, remote_staging=REMOTE_STAGING):
    job_directory = manager.job_directory(job_id)
    os.makedirs(os.path.join(job_directory.path, "metadata"), exist_ok=True)
    job_directory.store_metadata("launch_config", {"remote_staging": remote_staging})
    return job_directory


def _write(job_directory, stream, data):
    with open(os.path.join(job_directory.path, stream), "ab") as f:
        f.write(data)


def _reporter(manager, **kwds):
    kwds.setdefault("interval", 60)
    return LiveOutputReporter(manager, **kwds)


def _watched(reporter, job_id=TEST_JOB_ID):
    """Watch a job without starting the background thread; return its state."""
    with mock.patch.object(reporter, "_ensure_started"):
        assert reporter.watch(job_id)
    return reporter._jobs[job_id]


def _http_error(status_code):
    response = requests.Response()
    response.status_code = status_code
    return requests.HTTPError("HTTP %d" % status_code, response=response)


def test_update_sends_only_new_bytes(manager, poster):
    job_directory = _job_directory(manager)
    reporter = _reporter(manager)
    job = _watched(reporter)

    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"hello")
    reporter._update(job)
    reporter._update(job)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b" world")
    reporter._update(job)

    assert [data for _, data in poster.posts] == [b"hello", b" world"]
    assert poster.posts[0][0] == "/galaxy/jobs/1/outputs/tool_stdout"


def test_idle_job_is_not_opened_or_stored(manager, poster):
    job_directory = _job_directory(manager)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"hello")
    reporter = _reporter(manager)
    job = _watched(reporter)
    reporter._update(job)

    with mock.patch.object(job.job_directory, "open_file") as open_file, \
            mock.patch.object(job.job_directory, "store_metadata") as store_metadata:
        for _ in range(3):
            reporter._update(job)
    open_file.assert_not_called()
    store_metadata.assert_not_called()
    assert len(poster.posts) == 1


def test_missing_stream_files_are_not_an_error(manager, poster):
    """Before the tool starts, there is simply nothing to send."""
    _job_directory(manager)
    reporter = _reporter(manager)
    job = _watched(reporter)
    reporter._update(job)
    assert poster.posts == []
    assert job.failures == 0
    assert TEST_JOB_ID in reporter._jobs


def test_chunk_may_split_a_multibyte_character(manager, poster):
    """A chunk boundary inside a UTF-8 sequence must not raise or lose data."""
    text = "ünïcödé output".encode()
    job_directory = _job_directory(manager)
    reporter = _reporter(manager)
    job = _watched(reporter)

    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, text[:1])
    reporter._update(job)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, text[1:])
    reporter._update(job)

    assert poster.sent("tool_stdout") == text


def test_offsets_survive_a_restart(manager, poster):
    """A new reporter resumes from the persisted offset instead of resending.

    Galaxy appends every POST, so resending from zero duplicates the output.
    """
    job_directory = _job_directory(manager)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"first chunk")
    reporter = _reporter(manager)
    reporter._update(_watched(reporter))

    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b" and more")
    restarted = _reporter(manager)
    restarted._update(_watched(restarted))

    assert poster.sent("tool_stdout") == b"first chunk and more"


def test_stdout_and_stderr_offsets_are_independent(manager, poster):
    job_directory = _job_directory(manager)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"out")
    _write(job_directory, TOOL_FILE_STANDARD_ERROR, b"err!")
    reporter = _reporter(manager)
    job = _watched(reporter)
    reporter._update(job)
    _write(job_directory, TOOL_FILE_STANDARD_ERROR, b"?")
    reporter._update(job)

    assert poster.sent("tool_stdout") == b"out"
    assert poster.sent("tool_stderr") == b"err!?"


def test_large_output_is_sent_in_bounded_chunks(manager, poster):
    job_directory = _job_directory(manager)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"0123456789")
    reporter = _reporter(manager, chunk_size=4)
    job = _watched(reporter)

    reporter._update(job)
    # More is waiting, so the job is due again straight away.
    assert job.next_due <= time.monotonic()
    reporter._update(job)
    reporter._update(job)
    assert job.next_due > time.monotonic()

    assert [data for _, data in poster.posts] == [b"0123", b"4567", b"89"]


def test_streams_respect_maximum_stream_size(manager, poster):
    job_directory = _job_directory(manager)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"0123456789")
    reporter = _reporter(manager, chunk_size=4, maximum_stream_size=6)
    job = _watched(reporter)
    for _ in range(4):
        reporter._update(job)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"more")
    reporter._update(job)
    assert poster.sent("tool_stdout") == b"012345"


def test_job_without_files_endpoint_is_not_watched(manager, poster):
    """Shared file system setups have nowhere to send output: skip, don't retry."""
    _job_directory(manager, remote_staging={})
    reporter = _reporter(manager)
    assert reporter.watch(TEST_JOB_ID) is False
    assert reporter._jobs == {}
    assert reporter._thread is None


@pytest.mark.parametrize(
    "error", [requests.ConnectionError("refused"), requests.Timeout("slow"), _http_error(503)]
)
def test_transient_failure_backs_off_the_whole_endpoint(manager, poster, error):
    job_directory = _job_directory(manager)
    other_directory = _job_directory(manager, job_id="8")
    _job_directory(manager, job_id="9")
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"a")
    _write(other_directory, TOOL_FILE_STANDARD_OUTPUT, b"b")
    reporter = _reporter(manager, interval=10)
    job, other, idle = _watched(reporter), _watched(reporter, "8"), _watched(reporter, "9")

    poster.error = error
    reporter._update(job)
    retry_at, delay = reporter._backoff[job.endpoint]
    assert delay == 10
    assert job.next_due == retry_at
    assert job.offsets[TOOL_FILE_STANDARD_OUTPUT] == 0

    # Other jobs on the same Galaxy wait too instead of each timing out.
    poster.error = None
    reporter._update(other)
    assert poster.posts == []
    assert other.next_due == retry_at

    # A job with nothing to send once the pause ends proves nothing about
    # Galaxy, so it must not reset the backoff...
    reporter._backoff[job.endpoint] = (0.0, delay)
    reporter._update(idle)
    assert reporter._backoff[job.endpoint] == (0.0, delay)

    # ...which grows while Galaxy keeps failing, and resets once it recovers.
    poster.error = error
    reporter._update(job)
    assert reporter._backoff[job.endpoint][1] == 20
    poster.error = None
    reporter._backoff[job.endpoint] = (0.0, 20)
    reporter._update(job)
    reporter._update(other)
    assert job.endpoint not in reporter._backoff
    assert poster.sent("tool_stdout") == b"ab"


def test_permanent_http_error_stops_updates_for_the_job(manager, poster):
    job_directory = _job_directory(manager)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"a")
    reporter = _reporter(manager)
    job = _watched(reporter)
    poster.error = _http_error(403)
    reporter._update(job)
    assert TEST_JOB_ID not in reporter._jobs
    assert reporter._backoff == {}


def test_local_failure_backs_off_only_that_job(manager, poster):
    job_directory = _job_directory(manager)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"a")
    reporter = _reporter(manager, interval=10)
    job = _watched(reporter)
    with mock.patch.object(job.job_directory, "open_file", side_effect=PermissionError("denied")):
        reporter._update(job)
    assert job.failures == 1
    assert job.next_due > time.monotonic() + 10
    assert reporter._backoff == {}
    assert TEST_JOB_ID in reporter._jobs


def test_deleted_job_directory_is_dropped(manager, poster):
    job_directory = _job_directory(manager)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"a")
    reporter = _reporter(manager)
    job = _watched(reporter)
    rmtree(job_directory.path)
    reporter._update(job)
    assert TEST_JOB_ID not in reporter._jobs


def test_finish_without_delivery_makes_no_requests(manager, poster):
    """Short or silent jobs cost no extra POSTs: the status carries the streams."""
    job_directory = _job_directory(manager)
    reporter = _reporter(manager)
    _watched(reporter)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"all at the end")
    assert reporter.finish(TEST_JOB_ID) is False
    assert poster.posts == []
    assert TEST_JOB_ID not in reporter._jobs


def test_finish_sends_the_tail_and_creates_missing_streams(manager, poster):
    job_directory = _job_directory(manager)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"early")
    reporter = _reporter(manager, chunk_size=4)
    job = _watched(reporter)
    reporter._update(job)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b" and late")

    assert reporter.finish(TEST_JOB_ID) is True
    assert poster.sent("tool_stdout") == b"early and late"
    # Galaxy reads outputs/tool_stderr when the status omits it, so it must exist.
    assert ("/galaxy/jobs/1/outputs/tool_stderr", b"") in poster.posts
    assert live_output.load_state(job_directory)["delivered"] is True

    # The reporter no longer touches a finished job.
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"!")
    posts = len(poster.posts)
    reporter._update(job)
    assert len(poster.posts) == posts


def test_finish_after_a_restart_uses_persisted_offsets(manager, poster):
    job_directory = _job_directory(manager)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"early")
    reporter = _reporter(manager)
    reporter._update(_watched(reporter))
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b" late")

    assert _reporter(manager).finish(TEST_JOB_ID) is True
    assert poster.sent("tool_stdout") == b"early late"


def test_failed_finish_falls_back_to_the_completion_status(manager, poster):
    job_directory = _job_directory(manager)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"early")
    reporter = _reporter(manager)
    reporter._update(_watched(reporter))
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b" late")

    poster.error = requests.ConnectionError("Galaxy went away")
    assert reporter.finish(TEST_JOB_ID) is False
    assert live_output.load_state(job_directory)["delivered"] is False


def test_finish_does_not_wait_on_a_backed_off_endpoint(manager, poster):
    job_directory = _job_directory(manager)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"early")
    reporter = _reporter(manager)
    job = _watched(reporter)
    reporter._update(job)
    reporter._backoff[job.endpoint] = (time.monotonic() + 60, 60)
    posts = len(poster.posts)

    assert reporter.finish(TEST_JOB_ID) is False
    assert len(poster.posts) == posts
    assert live_output.load_state(job_directory)["delivered"] is False


def test_finish_hands_a_large_backlog_to_the_completion_status(manager, poster):
    """The flush is bounded so a huge backlog cannot hold up output staging."""
    job_directory = _job_directory(manager)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"x")
    reporter = _reporter(manager, chunk_size=1)
    reporter._update(_watched(reporter))
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"y" * (live_output.MAX_FINISH_CHUNKS + 5))

    assert reporter.finish(TEST_JOB_ID) is False
    assert len(poster.posts) == 1 + live_output.MAX_FINISH_CHUNKS
    assert live_output.load_state(job_directory)["delivered"] is False


def test_forget_stops_updates_and_hands_streams_to_the_status(manager, poster):
    """Cancelled jobs are not flushed, so the status must carry their streams."""
    job_directory = _job_directory(manager)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"a")
    reporter = _reporter(manager)
    job = _watched(reporter)
    reporter._update(job)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"b")

    reporter.forget(TEST_JOB_ID)
    reporter._update(job)
    assert poster.sent("tool_stdout") == b"a"
    assert reporter._jobs == {}
    assert live_output.load_state(job_directory)["delivered"] is False


def test_forget_during_an_update_does_not_block_and_wins(manager, poster):
    job_directory = _job_directory(manager)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"a")
    reporter = _reporter(manager)
    job = _watched(reporter)
    poster.gate = threading.Event()
    update = threading.Thread(target=reporter._update, args=(job,))
    update.start()
    assert poster.entered.wait(5)

    started = time.monotonic()
    reporter.forget(TEST_JOB_ID)
    assert time.monotonic() - started < 1, "forget() waited on an in-flight POST"
    poster.gate.set()
    update.join(5)

    # The in-flight POST landed and set delivered, but forget() still wins.
    _wait_for(lambda: live_output.load_state(job_directory)["delivered"] is False)


def test_finish_during_an_update_sends_every_byte_once(manager, poster):
    job_directory = _job_directory(manager)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"early")
    reporter = _reporter(manager)
    job = _watched(reporter)
    poster.gate = threading.Event()
    update = threading.Thread(target=reporter._update, args=(job,))
    update.start()
    assert poster.entered.wait(5)

    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b" late")
    finished = []
    finish = threading.Thread(target=lambda: finished.append(reporter.finish(TEST_JOB_ID)))
    finish.start()
    time.sleep(0.1)
    poster.gate.set()
    update.join(5)
    finish.join(5)

    assert finished == [True]
    assert poster.sent("tool_stdout") == b"early late"


def test_state_is_written_atomically(manager, poster):
    job_directory = _job_directory(manager)
    _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"a")
    reporter = _reporter(manager)
    with mock.patch("os.replace", wraps=os.replace) as replace:
        reporter._update(_watched(reporter))
    assert replace.called
    assert [name for name in os.listdir(job_directory.path) if ".tmp." in name] == []


def test_one_daemon_thread_serves_all_jobs(manager, poster):
    reporter = _reporter(manager, interval=0.05)
    for job_id in ["1", "2", "3"]:
        _write(_job_directory(manager, job_id), TOOL_FILE_STANDARD_OUTPUT, job_id.encode())
        assert reporter.watch(job_id)
    try:
        _wait_for(lambda: len(poster.posts) == 3)
        threads = [t for t in threading.enumerate() if "live_output" in t.name]
        assert threads == [reporter._thread]
        assert reporter._thread.daemon
    finally:
        reporter.shutdown(timeout=5)
    assert not reporter._thread.is_alive()


# StatefulManagerProxy integration.


class _ScriptedStatusManager(QueueManager):
    """Runs nothing, reports whatever status the test scripts, counts polls."""

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.scripted_status = status.QUEUED
        self.status_calls = 0

    def get_status(self, job_id):
        self.status_calls += 1
        return self.scripted_status


class _RecordingStatefulManagerProxy(StatefulManagerProxy):
    """Records state changes without starting a monitor thread."""

    def __init__(self, manager, **kwds):
        super().__init__(manager, **kwds)
        self.callbacks = []

    def _default_status_change_callback(self, job_status, job_id):
        self.callbacks.append((job_status, job_id))


@contextmanager
def _proxy(app=None, **options):
    app = app or minimal_app_for_managers()
    manager = _ScriptedStatusManager("test", app, num_concurrent_jobs=0)
    options.setdefault("send_stdout_update", True)
    options.setdefault("stdout_update_interval", 0.05)
    proxy = _RecordingStatefulManagerProxy(manager, **options)
    try:
        yield proxy, manager
    finally:
        proxy.shutdown(timeout=5)


def _launch(proxy):
    job_id = proxy.setup_job(TEST_JOB_ID, "tool1", "1.0.0")
    proxy.preprocess_and_launch(
        job_id, {"command_line": "true", "remote_staging": REMOTE_STAGING}
    )
    job_directory = proxy._proxied_manager.job_directory(job_id)
    os.makedirs(os.path.join(job_directory.path, "metadata"), exist_ok=True)
    return job_id, job_directory


def _wait_for(condition, timeout=5):
    time_end = time.time() + timeout
    while time.time() < time_end:
        if condition():
            return
        time.sleep(.01)
    raise AssertionError("Timed out waiting for condition.")


def test_running_job_streams_output_without_polling_the_scheduler(poster):
    app = minimal_app_for_managers()
    try:
        with _proxy(app) as (proxy, manager):
            job_id, job_directory = _launch(proxy)
            _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"live ")
            manager.scripted_status = status.RUNNING
            assert proxy.get_status(job_id) == status.RUNNING
            polls = manager.status_calls

            _wait_for(lambda: poster.sent("tool_stdout") == b"live ")
            time.sleep(0.2)  # several update intervals
            assert manager.status_calls == polls

            _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"tail")
            manager.scripted_status = status.COMPLETE
            with mock.patch.object(stateful, "postprocess", return_value=True):
                proxy.get_status(job_id)
                _wait_for(lambda: proxy.callbacks[-1:] == [(status.COMPLETE, job_id)])

            assert poster.sent("tool_stdout") == b"live tail"
            assert proxy.is_live_stdout_update(job_id) is True
            assert proxy._live_output._jobs == {}
    finally:
        rmtree(app.staging_directory, ignore_errors=True)


def test_cancelled_job_stops_streaming(poster):
    app = minimal_app_for_managers()
    try:
        with _proxy(app) as (proxy, manager):
            job_id, job_directory = _launch(proxy)
            manager.scripted_status = status.RUNNING
            proxy.get_status(job_id)
            assert job_id in proxy._live_output._jobs
            _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"a")
            _wait_for(lambda: proxy.is_live_stdout_update(job_id))
            manager.scripted_status = status.CANCELLED
            proxy.get_status(job_id)
            assert proxy._live_output._jobs == {}
            # Galaxy gets the cancelled job's streams with its status instead.
            assert proxy.is_live_stdout_update(job_id) is False
    finally:
        rmtree(app.staging_directory, ignore_errors=True)


def test_running_jobs_resume_streaming_after_a_restart(poster):
    app = minimal_app_for_managers()
    try:
        with _proxy(app) as (proxy, manager):
            job_id, job_directory = _launch(proxy)
            _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"before ")
            manager.scripted_status = status.RUNNING
            proxy.get_status(job_id)
            _wait_for(lambda: poster.sent("tool_stdout") == b"before ")

        _write(job_directory, TOOL_FILE_STANDARD_OUTPUT, b"after")
        with _proxy(app) as (restarted, manager):
            restarted.recover_active_jobs()
            _wait_for(lambda: poster.sent("tool_stdout") == b"before after")
    finally:
        rmtree(app.staging_directory, ignore_errors=True)


def test_disabled_proxy_has_no_reporter(poster):
    with _proxy(send_stdout_update=False) as (proxy, manager):
        job_id, job_directory = _launch(proxy)
        job_directory.store_metadata(JOB_FILE_LIVE_OUTPUT_STATE, {"delivered": True})
        manager.scripted_status = status.RUNNING
        proxy.get_status(job_id)
        assert proxy._live_output is None
        assert proxy.is_live_stdout_update(job_id) is False


def test_live_update_flag_requires_a_confirmed_delivery(poster):
    with _proxy() as (proxy, manager):
        job_id, job_directory = _launch(proxy)
        assert proxy.is_live_stdout_update(job_id) is False
        job_directory.store_metadata(JOB_FILE_LIVE_OUTPUT_STATE, {"delivered": True})
        assert proxy.is_live_stdout_update(job_id) is True


class _StatusJobDirectory:
    """Enough of a job directory for ``__job_complete_dict`` to build a status."""

    job_directory = "/tmp/pulsar-test-job"

    def working_directory(self):
        return self.job_directory + "/working"

    def metadata_directory(self):
        return self.job_directory + "/metadata"

    def working_directory_contents(self):
        return []

    def metadata_directory_contents(self):
        return []

    def outputs_directory_contents(self):
        return []

    def job_directory_contents(self):
        return []

    def has_metadata(self, name):
        return False

    def load_metadata(self, name, default=None):
        return default


class _StatusManager:
    """Minimal manager for exercising ``full_status``."""

    def __init__(self, live):
        self._live = live
        self._job_directory = _StatusJobDirectory()

    def is_live_stdout_update(self, job_id):
        return self._live

    def return_code(self, job_id):
        return 0

    def stdout_contents(self, job_id):
        return b"tool stdout"

    def stderr_contents(self, job_id):
        return b"tool stderr"

    def job_stdout_contents(self, job_id):
        return b""

    def job_stderr_contents(self, job_id):
        return b""

    def job_directory(self, job_id):
        return self._job_directory

    def system_properties(self):
        return {}


def test_full_status_keeps_streams_when_nothing_was_delivered():
    """If no live update landed, the completion status must still carry them."""
    result = manager_endpoint_util.full_status(
        _StatusManager(live=False), status.COMPLETE, TEST_JOB_ID
    )
    assert result["stdout"] == "tool stdout"
    assert result["stderr"] == "tool stderr"


def test_full_status_drops_streams_once_delivered():
    result = manager_endpoint_util.full_status(
        _StatusManager(live=True), status.COMPLETE, TEST_JOB_ID
    )
    assert result["stdout"] is None
    assert result["stderr"] is None
