"""Smoke test: a job submitted to Pulsar reaches `complete` with no faults.

If this test fails the harness is broken; nothing else in this suite is meaningful.
"""
import pytest
import requests

from harness.assertions import (
    assert_exactly_once_terminal,
    await_terminal,
)
from harness.job_factory import make_setup_message

GALAXY_BASE = "http://localhost:8088"


@pytest.mark.resilience
def test_happy_path(pulsar):
    body = make_setup_message(command_line="echo resilience-smoke")
    requests.post(f"{GALAXY_BASE}/_publish_setup", json=body, timeout=5).raise_for_status()
    await_terminal(body["job_id"], timeout=60, expected="complete")
    assert_exactly_once_terminal(body["job_id"], expected="complete")
