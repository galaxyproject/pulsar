"""Unit tests for the StatusRecorder ordering rules.

The recorder is the test framework's stand-in for Galaxy's job-state
processor. Run from this directory: ``pytest mock_galaxy/recorder_test.py``.
"""
import os
import sys

import pytest

# Make sibling import work when invoked from the resilience root or via
# `pytest test/resilience/mock_galaxy/recorder_test.py`.
sys.path.insert(0, os.path.dirname(__file__))
from recorder import StatusRecorder  # type: ignore  # noqa: E402


def _statuses(rec, job_id):
    return [e["status"] for e in rec.events(job_id)]


def test_dedupes_repeated_status():
    rec = StatusRecorder()
    rec.record({"job_id": "j1", "status": "running"})
    rec.record({"job_id": "j1", "status": "running"})
    rec.record({"job_id": "j1", "status": "complete"})
    rec.record({"job_id": "j1", "status": "complete"})
    assert _statuses(rec, "j1") == ["running", "complete"]


def test_drops_non_terminal_after_terminal():
    rec = StatusRecorder()
    rec.record({"job_id": "j1", "status": "running"})
    rec.record({"job_id": "j1", "status": "complete"})
    rec.record({"job_id": "j1", "status": "running"})  # stale buffered update
    rec.record({"job_id": "j1", "status": "queued"})    # ditto
    assert _statuses(rec, "j1") == ["running", "complete"]


def test_terminal_after_terminal_is_just_a_dupe():
    """Two different terminals (e.g. complete then failed) shouldn't both
    land — but the dedupe rule is by (job_id, status), so the second is
    distinct from the first. We treat the second as a regression: terminal
    states are sinks and a different terminal arriving later is suspect."""
    rec = StatusRecorder()
    rec.record({"job_id": "j1", "status": "complete"})
    rec.record({"job_id": "j1", "status": "failed"})
    # Either result is defensible; we just want exactly-one terminal.
    terminals = [s for s in _statuses(rec, "j1") if s in StatusRecorder.TERMINAL]
    assert len(terminals) == 1


def test_galaxy_reset_token_starts_fresh_epoch():
    rec = StatusRecorder()
    rec.record({"job_id": "j1", "status": "running"})
    rec.record({"job_id": "j1", "status": "complete"})
    # Galaxy restarts the job; the new lifecycle should be admitted fully.
    rec.record({
        "job_id": "j1",
        "status": "preprocessing",
        "_galaxy_reset_token": "epoch-2",
    })
    rec.record({"job_id": "j1", "status": "running"})
    rec.record({"job_id": "j1", "status": "complete"})
    assert _statuses(rec, "j1") == ["preprocessing", "running", "complete"]


def test_reset_token_does_not_leak_across_jobs():
    rec = StatusRecorder()
    rec.record({"job_id": "j1", "status": "complete"})
    rec.record({
        "job_id": "j2",
        "status": "preprocessing",
        "_galaxy_reset_token": "x",
    })
    # j1's history must not be affected by j2's reset.
    assert _statuses(rec, "j1") == ["complete"]
    assert _statuses(rec, "j2") == ["preprocessing"]


@pytest.mark.parametrize("terminal", ["complete", "failed", "cancelled", "lost"])
def test_each_terminal_blocks_subsequent_non_terminals(terminal):
    rec = StatusRecorder()
    rec.record({"job_id": "j1", "status": terminal})
    rec.record({"job_id": "j1", "status": "running"})
    assert _statuses(rec, "j1") == [terminal]
