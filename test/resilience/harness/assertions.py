"""Assertions over the StatusRecorder events recorded by mock-galaxy.

The single guarantee these tests pin down is: every submitted job's terminal
status is delivered exactly once and is preceded only by valid intermediate
states. Helpers here let scenarios state that intent declaratively.
"""
import time

import requests

VALID_ORDER = [
    "preprocessing",
    "queued",
    "running",
    "postprocessing",
    "complete",
    "failed",
    "cancelled",
    "lost",
]
TERMINAL = {"complete", "failed", "cancelled", "lost"}

GALAXY_BASE = "http://localhost:8088"


def fetch_events(galaxy_base=GALAXY_BASE, job_id=None):
    params = {}
    if job_id:
        params["job_id"] = job_id
    r = requests.get(f"{galaxy_base}/_recorder/events", params=params, timeout=5)
    r.raise_for_status()
    return r.json()


def clear_events(galaxy_base=GALAXY_BASE):
    requests.post(f"{galaxy_base}/_recorder/clear", timeout=5).raise_for_status()


def await_terminal(job_id, timeout=60.0, expected="complete", galaxy_base=GALAXY_BASE):
    """Poll the recorder until ``job_id`` has a terminal status, then assert
    it matches ``expected``.
    """
    deadline = time.time() + timeout
    last_events = []
    while time.time() < deadline:
        events = fetch_events(galaxy_base=galaxy_base, job_id=job_id)
        for ev in events:
            if ev["status"] in TERMINAL:
                assert ev["status"] == expected, (
                    f"job {job_id} terminal {ev['status']!r}, expected {expected!r}; "
                    f"all events: {events}"
                )
                return ev
        last_events = events
        time.sleep(0.25)
    raise AssertionError(
        f"job {job_id} did not reach terminal status within {timeout}s; "
        f"last events: {last_events}"
    )


def assert_exactly_once_terminal(job_id, expected="complete", galaxy_base=GALAXY_BASE):
    events = fetch_events(galaxy_base=galaxy_base, job_id=job_id)
    terminal = [ev for ev in events if ev["status"] in TERMINAL]
    assert len(terminal) == 1, (
        f"job {job_id} got {len(terminal)} terminal events, expected 1; "
        f"terminals: {terminal}"
    )
    if expected is not None:
        assert terminal[0]["status"] == expected, (
            f"job {job_id} terminal {terminal[0]['status']!r}, expected {expected!r}"
        )


def await_any_terminal(job_id, timeout=60.0, galaxy_base=GALAXY_BASE):
    """Wait until a terminal status of any kind is delivered.

    Use this in scenarios where the runner cannot reasonably resume the
    underlying job (e.g. queued_python loses the subprocess on SIGKILL).
    The non-loss guarantee is still 'a terminal status is delivered exactly
    once'; *which* terminal it is depends on whether the runner can recover.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        events = fetch_events(galaxy_base=galaxy_base, job_id=job_id)
        for ev in events:
            if ev["status"] in TERMINAL:
                return ev
        time.sleep(0.25)
    raise AssertionError(
        f"job {job_id} did not reach any terminal status within {timeout}s"
    )


def assert_states_in_order(job_id, galaxy_base=GALAXY_BASE):
    """No state regressions (e.g. 'complete' followed by 'running')."""
    events = fetch_events(galaxy_base=galaxy_base, job_id=job_id)
    seen = []
    for ev in events:
        s = ev["status"]
        if s in seen and s in TERMINAL:
            raise AssertionError(
                f"duplicate terminal {s} for job {job_id}: events {events}"
            )
        seen.append(s)
    # Cheap order check: every adjacent pair must be a non-decreasing index in
    # VALID_ORDER, except that running/postprocessing transitions can repeat.
    rank = {s: i for i, s in enumerate(VALID_ORDER)}
    last_rank = -1
    for ev in events:
        r = rank.get(ev["status"], 0)
        if r < last_rank and ev["status"] in TERMINAL:
            raise AssertionError(
                f"state regression for job {job_id}: events {events}"
            )
        last_rank = max(last_rank, r)
