"""Tests for live stdout/stderr streaming in :class:`StatefulManagerProxy`.

Covers the incremental read that feeds Galaxy's append-on-POST files endpoint,
the fact that the read offsets survive a Pulsar restart, and the rule that the
completion status may only drop the streams once a live update for that job was
actually accepted.
"""
import contextlib
import io

from pulsar import manager_endpoint_util
from pulsar.managers import status
from pulsar.managers.base.directory import (
    TOOL_FILE_STANDARD_ERROR,
    TOOL_FILE_STANDARD_OUTPUT,
)
from pulsar.managers.stateful import (
    JOB_FILE_LIVE_OUTPUT_STATE,
    StatefulManagerProxy,
)

TEST_JOB_ID = "7"


class _FakeJobDirectory:
    """Serves job files from memory and persists metadata like a real one."""

    def __init__(self, contents=None, metadata=None):
        self.contents = dict(contents or {})
        self.metadata = dict(metadata or {})
        self.handles = []

    def open_file(self, name, mode="rb"):
        handle = io.BytesIO(self.contents.get(name, b""))
        self.handles.append(handle)
        return handle

    def store_metadata(self, name, value):
        self.metadata[name] = value

    def load_metadata(self, name, default=None):
        return self.metadata.get(name, default)

    @contextlib.contextmanager
    def lock(self, name=".state"):
        yield


class _FakeManager:
    manager_type = "fake"

    def __init__(self, job_directory):
        self._job_directory = job_directory

    def job_directory(self, job_id):
        return self._job_directory

    def get_status(self, job_id):
        return status.RUNNING


def _proxy(job_directory, send_stdout=True):
    """Build the proxy without running __init__'s manager/monitor setup."""
    proxy = StatefulManagerProxy.__new__(StatefulManagerProxy)
    proxy._proxied_manager = _FakeManager(job_directory)
    proxy.send_stdout = send_stdout
    return proxy


def test_prepare_file_output_returns_only_new_bytes():
    job_directory = _FakeJobDirectory({TOOL_FILE_STANDARD_OUTPUT: b"hello"})
    proxy = _proxy(job_directory)
    state = proxy._load_live_output_state(job_directory)

    assert proxy._prepare_file_output(job_directory, TOOL_FILE_STANDARD_OUTPUT, state) == b"hello"
    # Nothing new written yet -> empty delta, so no POST is made.
    assert proxy._prepare_file_output(job_directory, TOOL_FILE_STANDARD_OUTPUT, state) == b""

    job_directory.contents[TOOL_FILE_STANDARD_OUTPUT] = b"hello world"
    assert proxy._prepare_file_output(job_directory, TOOL_FILE_STANDARD_OUTPUT, state) == b" world"


def test_prepare_file_output_closes_handles():
    job_directory = _FakeJobDirectory({TOOL_FILE_STANDARD_OUTPUT: b"data"})
    proxy = _proxy(job_directory)
    state = proxy._load_live_output_state(job_directory)
    proxy._prepare_file_output(job_directory, TOOL_FILE_STANDARD_OUTPUT, state)
    assert job_directory.handles, "expected the job file to be opened"
    assert all(h.closed for h in job_directory.handles)


def test_chunk_may_split_a_multibyte_character():
    """A delta boundary inside a UTF-8 sequence must not raise or lose data."""
    text = "\u00fcn\u00efc\u00f6d\u00e9 output".encode("utf-8")
    # Cut inside the two-byte first character so chunk one ends mid-character.
    job_directory = _FakeJobDirectory({TOOL_FILE_STANDARD_OUTPUT: text[:1]})
    proxy = _proxy(job_directory)
    state = proxy._load_live_output_state(job_directory)

    first = proxy._prepare_file_output(job_directory, TOOL_FILE_STANDARD_OUTPUT, state)
    job_directory.contents[TOOL_FILE_STANDARD_OUTPUT] = text
    second = proxy._prepare_file_output(job_directory, TOOL_FILE_STANDARD_OUTPUT, state)

    # Galaxy appends the chunks verbatim, so they must reassemble exactly.
    assert first + second == text
    assert (first + second).decode("utf-8") == "\u00fcn\u00efc\u00f6d\u00e9 output"


def test_offsets_survive_a_restart():
    """A new proxy must resume from the persisted offset, not resend from zero.

    Galaxy appends every POST, so resending from zero duplicates the output.
    """
    job_directory = _FakeJobDirectory({TOOL_FILE_STANDARD_OUTPUT: b"first chunk"})
    proxy = _proxy(job_directory)

    state = proxy._load_live_output_state(job_directory)
    assert proxy._prepare_file_output(job_directory, TOOL_FILE_STANDARD_OUTPUT, state) == b"first chunk"
    proxy._store_live_output_state(job_directory, state)
    assert JOB_FILE_LIVE_OUTPUT_STATE in job_directory.metadata

    # Pulsar restarts: brand new proxy, same job directory on disk.
    job_directory.contents[TOOL_FILE_STANDARD_OUTPUT] = b"first chunk and more"
    restarted = _proxy(job_directory)
    resumed = restarted._load_live_output_state(job_directory)
    assert resumed[TOOL_FILE_STANDARD_OUTPUT] == len(b"first chunk")
    assert restarted._prepare_file_output(job_directory, TOOL_FILE_STANDARD_OUTPUT, resumed) == b" and more"


def test_delivered_flag_survives_a_restart():
    job_directory = _FakeJobDirectory(
        metadata={JOB_FILE_LIVE_OUTPUT_STATE: {"delivered": True}}
    )
    assert _proxy(job_directory).is_live_stdout_update(TEST_JOB_ID) is True


def test_unknown_job_directory_starts_at_zero():
    """A job with no persisted state yet reads from the beginning."""
    job_directory = _FakeJobDirectory({TOOL_FILE_STANDARD_ERROR: b"late"})
    proxy = _proxy(job_directory)
    state = proxy._load_live_output_state(job_directory)
    assert state[TOOL_FILE_STANDARD_ERROR] == 0
    assert proxy._prepare_file_output(job_directory, TOOL_FILE_STANDARD_ERROR, state) == b"late"


def test_stdout_and_stderr_offsets_are_independent():
    job_directory = _FakeJobDirectory(
        {TOOL_FILE_STANDARD_OUTPUT: b"out", TOOL_FILE_STANDARD_ERROR: b"err!"}
    )
    proxy = _proxy(job_directory)
    state = proxy._load_live_output_state(job_directory)
    assert proxy._prepare_file_output(job_directory, TOOL_FILE_STANDARD_OUTPUT, state) == b"out"
    assert proxy._prepare_file_output(job_directory, TOOL_FILE_STANDARD_ERROR, state) == b"err!"
    assert proxy._prepare_file_output(job_directory, TOOL_FILE_STANDARD_OUTPUT, state) == b""


def test_live_update_flag_requires_a_confirmed_delivery():
    job_directory = _FakeJobDirectory()
    proxy = _proxy(job_directory)
    # Enabled, but nothing has been delivered for this job yet.
    assert proxy.is_live_stdout_update(TEST_JOB_ID) is False

    proxy._store_live_output_state(job_directory, {"delivered": True})
    assert proxy.is_live_stdout_update(TEST_JOB_ID) is True


def test_live_update_flag_false_when_disabled():
    job_directory = _FakeJobDirectory(
        metadata={JOB_FILE_LIVE_OUTPUT_STATE: {"delivered": True}}
    )
    assert _proxy(job_directory, send_stdout=False).is_live_stdout_update(TEST_JOB_ID) is False


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
