"""Tests for live stdout/stderr streaming in :class:`StatefulManagerProxy`.

Covers the incremental read that feeds Galaxy's append-on-POST files endpoint,
and the rule that the completion status may only drop the streams once a live
update for that job was actually accepted.
"""
import io

from pulsar import manager_endpoint_util
from pulsar.managers import status
from pulsar.managers.base.directory import (
    TOOL_FILE_STANDARD_ERROR,
    TOOL_FILE_STANDARD_OUTPUT,
)
from pulsar.managers.stateful import StatefulManagerProxy

TEST_JOB_ID = "7"


class _FakeJobDirectory:
    """Serves job files from memory and remembers every handle it opened."""

    def __init__(self, contents=None):
        self.contents = dict(contents or {})
        self.handles = []

    def open_file(self, name, mode="rb"):
        handle = io.BytesIO(self.contents.get(name, b""))
        self.handles.append(handle)
        return handle


class _FakeManager:
    manager_type = "fake"

    def __init__(self, job_directory):
        self._job_directory = job_directory

    def job_directory(self, job_id):
        return self._job_directory

    def get_status(self, job_id):
        return status.RUNNING


def _proxy(job_directory, **kwds):
    """Build the proxy without running ``__init__``'s manager/monitor setup."""
    proxy = StatefulManagerProxy.__new__(StatefulManagerProxy)
    proxy._proxied_manager = _FakeManager(job_directory)
    proxy.send_stdout = kwds.get("send_stdout", True)
    name = "_StatefulManagerProxy__"
    setattr(proxy, name + "stdout_file_pointer_map", {})
    setattr(proxy, name + "stderr_file_pointer_map", {})
    setattr(proxy, name + "live_update_delivered", {})
    return proxy


def _pointers(proxy):
    return getattr(proxy, "_StatefulManagerProxy__stdout_file_pointer_map")


def test_prepare_file_output_returns_only_new_bytes():
    job_directory = _FakeJobDirectory({TOOL_FILE_STANDARD_OUTPUT: b"hello"})
    proxy = _proxy(job_directory)

    first = proxy._prepare_file_output(TEST_JOB_ID, job_directory, TOOL_FILE_STANDARD_OUTPUT)
    assert first == b"hello"

    # Nothing new written yet -> empty delta, so no POST is made.
    second = proxy._prepare_file_output(TEST_JOB_ID, job_directory, TOOL_FILE_STANDARD_OUTPUT)
    assert second == b""

    job_directory.contents[TOOL_FILE_STANDARD_OUTPUT] = b"hello world"
    third = proxy._prepare_file_output(TEST_JOB_ID, job_directory, TOOL_FILE_STANDARD_OUTPUT)
    assert third == b" world"


def test_prepare_file_output_closes_handles():
    job_directory = _FakeJobDirectory({TOOL_FILE_STANDARD_OUTPUT: b"data"})
    proxy = _proxy(job_directory)
    proxy._prepare_file_output(TEST_JOB_ID, job_directory, TOOL_FILE_STANDARD_OUTPUT)
    assert job_directory.handles, "expected the job file to be opened"
    assert all(h.closed for h in job_directory.handles)


def test_chunk_may_split_a_multibyte_character():
    """A delta boundary inside a UTF-8 sequence must not raise or lose data."""
    text = "ünïcödé output".encode("utf-8")
    # Cut inside the two-byte "ü" so the first chunk ends mid-character.
    job_directory = _FakeJobDirectory({TOOL_FILE_STANDARD_OUTPUT: text[:1]})
    proxy = _proxy(job_directory)

    first = proxy._prepare_file_output(TEST_JOB_ID, job_directory, TOOL_FILE_STANDARD_OUTPUT)
    job_directory.contents[TOOL_FILE_STANDARD_OUTPUT] = text
    second = proxy._prepare_file_output(TEST_JOB_ID, job_directory, TOOL_FILE_STANDARD_OUTPUT)

    # Galaxy appends the chunks verbatim, so they must reassemble exactly.
    assert first + second == text
    assert (first + second).decode("utf-8") == "ünïcödé output"


def test_unknown_job_id_does_not_raise():
    """A job recovered after a Pulsar restart has no pointer entry yet."""
    job_directory = _FakeJobDirectory({TOOL_FILE_STANDARD_ERROR: b"late"})
    proxy = _proxy(job_directory)
    assert _pointers(proxy) == {}
    delta = proxy._prepare_file_output("never-seen", job_directory, TOOL_FILE_STANDARD_ERROR)
    assert delta == b"late"


def test_stdout_and_stderr_pointers_are_independent():
    job_directory = _FakeJobDirectory(
        {TOOL_FILE_STANDARD_OUTPUT: b"out", TOOL_FILE_STANDARD_ERROR: b"err!"}
    )
    proxy = _proxy(job_directory)
    assert proxy._prepare_file_output(TEST_JOB_ID, job_directory, TOOL_FILE_STANDARD_OUTPUT) == b"out"
    assert proxy._prepare_file_output(TEST_JOB_ID, job_directory, TOOL_FILE_STANDARD_ERROR) == b"err!"
    assert proxy._prepare_file_output(TEST_JOB_ID, job_directory, TOOL_FILE_STANDARD_OUTPUT) == b""


def test_live_update_flag_requires_a_confirmed_delivery():
    proxy = _proxy(_FakeJobDirectory())
    # Enabled, but nothing has been delivered for this job yet.
    assert proxy.is_live_stdout_update(TEST_JOB_ID) is False

    getattr(proxy, "_StatefulManagerProxy__live_update_delivered")[TEST_JOB_ID] = True
    assert proxy.is_live_stdout_update(TEST_JOB_ID) is True


def test_live_update_flag_false_when_disabled():
    proxy = _proxy(_FakeJobDirectory(), send_stdout=False)
    getattr(proxy, "_StatefulManagerProxy__live_update_delivered")[TEST_JOB_ID] = True
    assert proxy.is_live_stdout_update(TEST_JOB_ID) is False


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
