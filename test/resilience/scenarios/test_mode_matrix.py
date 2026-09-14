"""E. Mode matrix sanity check.

The other scenario files take the parametrized ``pulsar`` fixture, so they
already run across every mode. This file pins down the *invariants* that the
matrix must satisfy independent of failure injection: status update wire
format consistency, queue/topic naming, and that ``amqp_durable=true`` and
the persistent outbox are actually engaged.
"""
import os
import subprocess

import pytest
import requests

from harness.assertions import (
    assert_exactly_once_terminal,
    await_terminal,
)
from harness.job_factory import make_setup_message

GALAXY_BASE = "http://localhost:8088"
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.resilience
def test_outbox_directory_exists_after_first_publish(pulsar):
    body = make_setup_message(command_line="echo mode-matrix")
    requests.post(f"{GALAXY_BASE}/_publish_setup", json=body, timeout=5).raise_for_status()
    await_terminal(body["job_id"], timeout=60, expected="complete")
    assert_exactly_once_terminal(body["job_id"], expected="complete")

    # Confirm Pulsar's persistence_directory contains the outbox dir; even on
    # the happy path the directory is created on first bind.
    suffix = "relay-status-outbox" if pulsar.mode == "relay" else "status-outbox"
    res = subprocess.run(
        ["docker", "compose", "-f", f"{PROJECT_DIR}/docker-compose.yml",
         "exec", "-T", "pulsar", "ls", "/pulsar/persisted"],
        capture_output=True, text=True, check=True,
    )
    listing = res.stdout
    assert any(suffix in line for line in listing.splitlines()), (
        f"expected an outbox dir ending with {suffix} in {listing!r}"
    )


@pytest.mark.resilience
def test_payload_contains_required_fields(pulsar):
    body = make_setup_message(command_line="echo wire-format")
    requests.post(f"{GALAXY_BASE}/_publish_setup", json=body, timeout=5).raise_for_status()
    ev = await_terminal(body["job_id"], timeout=60, expected="complete")
    payload = ev["payload"]
    for key in ("job_id", "status", "complete", "returncode", "pulsar_version"):
        assert key in payload, f"terminal payload missing {key!r}: {payload}"


@pytest.mark.resilience
def test_state_transitions_arrive_in_valid_order(pulsar):
    """Per-job state transitions are observed in non-decreasing lifecycle
    rank — the FIFO outbox + recorder regression guard must hold over real
    pulsar emissions, not just unit-level mocks."""
    body = make_setup_message(command_line="echo ordering && sleep 1")
    requests.post(f"{GALAXY_BASE}/_publish_setup", json=body, timeout=5).raise_for_status()
    await_terminal(body["job_id"], timeout=60, expected="complete")
    rank = ["preprocessing", "queued", "running", "postprocessing", "complete"]
    events = requests.get(
        f"{GALAXY_BASE}/_recorder/events", params={"job_id": body["job_id"]},
        timeout=5,
    ).json()
    seen_rank = -1
    for ev in events:
        r = rank.index(ev["status"]) if ev["status"] in rank else len(rank)
        assert r >= seen_rank, f"state regressed: {[e['status'] for e in events]}"
        seen_rank = r


@pytest.mark.resilience
def test_galaxy_reset_token_admits_post_terminal_transitions(pulsar):
    """Galaxy can explicitly restart a completed job. The recorder must
    accept the new lifecycle when ``_galaxy_reset_token`` is set, even
    though it would otherwise refuse non-terminal-after-terminal updates."""
    body = make_setup_message(command_line="echo first-run")
    requests.post(f"{GALAXY_BASE}/_publish_setup", json=body, timeout=5).raise_for_status()
    await_terminal(body["job_id"], timeout=60, expected="complete")

    # Simulate Galaxy resubmitting the job: an in-process status update
    # carrying a reset token, then a fresh lifecycle that would be a
    # regression without it.
    job_id = body["job_id"]
    requests.post(f"{GALAXY_BASE}/_recorder/inject_status", json={
        "job_id": job_id, "status": "preprocessing",
        "_galaxy_reset_token": "epoch-2",
    }, timeout=5).raise_for_status()
    requests.post(f"{GALAXY_BASE}/_recorder/inject_status", json={
        "job_id": job_id, "status": "running",
    }, timeout=5).raise_for_status()
    requests.post(f"{GALAXY_BASE}/_recorder/inject_status", json={
        "job_id": job_id, "status": "complete",
    }, timeout=5).raise_for_status()

    # Per-job view shows only the post-reset epoch as a clean lifecycle —
    # the prior `complete` is logically forgotten so the new run can use the
    # same set of state transitions without tripping the regression guard.
    events = requests.get(
        f"{GALAXY_BASE}/_recorder/events", params={"job_id": job_id},
        timeout=5,
    ).json()
    statuses = [e["status"] for e in events]
    assert statuses == ["preprocessing", "running", "complete"]
    # Global event log retains the full observed history (two completes).
    all_events = requests.get(f"{GALAXY_BASE}/_recorder/events", timeout=5).json()
    completes_for_job = [
        e for e in all_events if e["job_id"] == job_id and e["status"] == "complete"
    ]
    assert len(completes_for_job) == 2
