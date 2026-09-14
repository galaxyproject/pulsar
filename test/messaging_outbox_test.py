"""Tests for pulsar.messaging.outbox.

These tests pin the behavior that makes the outbox the cornerstone of the
"jobs are never lost" guarantee: enqueue must never raise, failures must stay
on disk, the drain thread must retry until publish succeeds, and surviving
on-disk entries must be replayed when a fresh outbox is constructed against
the same directory (the restart case).
"""
import os
import threading
import time

import pytest

from pulsar.messaging.outbox import StatusUpdateOutbox


class _Recorder:
    def __init__(self, fail_until_attempt=0, raise_exc=None):
        self.calls = []
        self.fail_until_attempt = fail_until_attempt
        self.raise_exc = raise_exc or RuntimeError("simulated broker down")
        self._lock = threading.Lock()

    def __call__(self, payload):
        with self._lock:
            self.calls.append(payload)
            attempt = len(self.calls)
        if attempt <= self.fail_until_attempt:
            raise self.raise_exc

    @property
    def call_count(self):
        with self._lock:
            return len(self.calls)


def _wait_for(predicate, timeout=5.0, interval=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_enqueue_persists_and_publishes_on_happy_path(tmp_path):
    recorder = _Recorder()
    outbox = StatusUpdateOutbox(str(tmp_path), recorder, drain_interval=0.1)
    outbox.start()
    try:
        outbox.enqueue({"job_id": "j1", "status": "complete"})
        assert _wait_for(lambda: recorder.call_count == 1)
        assert _wait_for(lambda: outbox.pending_count() == 0)
    finally:
        outbox.stop()


def test_enqueue_does_not_raise_when_publish_fails(tmp_path):
    recorder = _Recorder(fail_until_attempt=10**6)
    outbox = StatusUpdateOutbox(str(tmp_path), recorder, drain_interval=0.05)
    outbox.start()
    try:
        outbox.enqueue({"job_id": "j1", "status": "complete"})
        assert _wait_for(lambda: outbox.pending_count() == 1)
        assert any(f.endswith(".json") for f in os.listdir(str(tmp_path)))
    finally:
        outbox.stop()


def test_drain_retries_until_publish_succeeds(tmp_path):
    recorder = _Recorder(fail_until_attempt=3)
    outbox = StatusUpdateOutbox(str(tmp_path), recorder, drain_interval=0.05)
    outbox.start()
    try:
        outbox.enqueue({"job_id": "j1", "status": "complete"})
        assert _wait_for(lambda: outbox.pending_count() == 0, timeout=10)
        assert recorder.call_count >= 4
    finally:
        outbox.stop()


def test_restart_replays_pending_entries(tmp_path):
    recorder1 = _Recorder(fail_until_attempt=10**6)
    outbox1 = StatusUpdateOutbox(str(tmp_path), recorder1, drain_interval=0.05)
    outbox1.start()
    try:
        outbox1.enqueue({"job_id": "j1", "status": "complete"})
        outbox1.enqueue({"job_id": "j2", "status": "failed"})
        assert _wait_for(lambda: outbox1.pending_count() == 2)
    finally:
        outbox1.stop()

    recorder2 = _Recorder()
    outbox2 = StatusUpdateOutbox(str(tmp_path), recorder2, drain_interval=0.05)
    outbox2.start()
    try:
        assert _wait_for(lambda: outbox2.pending_count() == 0, timeout=10)
        assert recorder2.call_count == 2
        delivered_ids = {p["job_id"] for p in recorder2.calls}
        assert delivered_ids == {"j1", "j2"}
    finally:
        outbox2.stop()


def test_corrupt_entry_is_removed_and_does_not_block_drain(tmp_path):
    recorder = _Recorder()
    bad_path = os.path.join(str(tmp_path), "bad.json")
    with open(bad_path, "w") as fh:
        fh.write("not-valid-json{")
    outbox = StatusUpdateOutbox(str(tmp_path), recorder, drain_interval=0.05)
    outbox.start()
    try:
        outbox.enqueue({"job_id": "j1", "status": "complete"})
        assert _wait_for(lambda: outbox.pending_count() == 0, timeout=5)
        assert recorder.call_count == 1
        assert not os.path.exists(bad_path)
    finally:
        outbox.stop()


def test_drain_once_returns_remaining_count(tmp_path):
    recorder = _Recorder(fail_until_attempt=10**6)
    outbox = StatusUpdateOutbox(str(tmp_path), recorder, drain_interval=3600)
    try:
        outbox.enqueue({"job_id": "j1", "status": "complete"})
        outbox.enqueue({"job_id": "j2", "status": "failed"})
        # Background thread is not started; call drain_once directly.
        remaining = outbox.drain_once()
        assert remaining == 2
        assert recorder.call_count == 2
    finally:
        outbox.stop()


def test_build_status_outbox_returns_none_without_persistence_directory():
    from pulsar.messaging.outbox import build_status_outbox

    class _StubManager:
        name = "test"
        persistence_directory = None

    result = build_status_outbox(_StubManager(), {}, publish_fn=lambda payload: None)
    assert result is None


def test_build_status_outbox_creates_outbox_under_persistence_dir(tmp_path):
    from pulsar.messaging.outbox import build_status_outbox

    class _StubManager:
        name = "test"
        persistence_directory = str(tmp_path)

    recorder = _Recorder()
    outbox = build_status_outbox(_StubManager(), {"status_outbox_drain_interval": 0.05}, publish_fn=recorder)
    assert outbox is not None
    try:
        expected_dir = os.path.join(str(tmp_path), "test-status-outbox")
        assert os.path.isdir(expected_dir)
        outbox.enqueue({"job_id": "j1", "status": "complete"})
        assert _wait_for(lambda: recorder.call_count == 1)
    finally:
        outbox.stop()


@pytest.mark.parametrize("payload", [
    {"job_id": "j1", "status": "complete", "stdout": "hello\nworld"},
    {"job_id": "j2", "status": "failed", "returncode": 1, "metadata_directory_contents": []},
    {"job_id": "j3", "status": "running", "system_properties": {"hostname": "x"}},
])
def test_payload_round_trips_through_disk(tmp_path, payload):
    seen = []
    outbox = StatusUpdateOutbox(str(tmp_path), seen.append, drain_interval=0.05)
    outbox.start()
    try:
        outbox.enqueue(payload)
        assert _wait_for(lambda: len(seen) == 1)
        assert seen[0] == payload
    finally:
        outbox.stop()


def test_drain_is_fifo(tmp_path):
    """Successive enqueues must drain in enqueue order — never preprocessing
    after running, never running after complete."""
    seen = []
    outbox = StatusUpdateOutbox(str(tmp_path), seen.append, drain_interval=3600)
    statuses = ["preprocessing", "queued", "running", "complete"]
    for s in statuses:
        outbox.enqueue({"job_id": "j1", "status": s})
    outbox.drain_once()
    assert [p["status"] for p in seen] == statuses


def test_drain_is_fifo_across_restart(tmp_path):
    """Sequence numbers persist across processes: a restart that finds entries
    on disk drains them in the order they were originally enqueued before
    any new entries piled on by the new process."""
    o1 = StatusUpdateOutbox(str(tmp_path), lambda p: (_ for _ in ()).throw(RuntimeError()), drain_interval=3600)
    for s in ["preprocessing", "running"]:
        o1.enqueue({"job_id": "j1", "status": s})

    seen = []
    o2 = StatusUpdateOutbox(str(tmp_path), seen.append, drain_interval=3600)
    o2.enqueue({"job_id": "j1", "status": "complete"})
    o2.drain_once()
    assert [p["status"] for p in seen] == ["preprocessing", "running", "complete"]
