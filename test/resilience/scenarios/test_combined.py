"""D. Combined failure scenarios.

The hard cases: every layer fails at once. If A/B/C pass independently but
combined cases fail, the system has implicit dependencies between recovery
mechanisms.
"""
import time

import pytest
import requests

from harness.assertions import (
    assert_exactly_once_terminal,
    await_any_terminal,
    await_terminal,
)
from harness.job_factory import make_setup_message

GALAXY_BASE = "http://localhost:8088"


@pytest.mark.resilience
def test_d1_pulsar_restart_with_broker_and_galaxy_outage(
    pulsar, rabbitmq_proxy, relay_proxy, galaxy_proxy,
):
    """All three layers fault at once: the running queued_python subprocess
    dies with pulsar (so terminal is ``lost``, not ``complete``), but the
    non-loss guarantee still holds — exactly one terminal is delivered."""
    proxy = relay_proxy if pulsar.mode == "relay" else rabbitmq_proxy
    body = make_setup_message(command_line="echo d1 && sleep 1")
    requests.post(f"{GALAXY_BASE}/_publish_setup", json=body, timeout=5).raise_for_status()
    time.sleep(0.5)
    proxy.add_latency(500)
    galaxy_proxy.disable()
    pulsar.kill()
    time.sleep(1.5)
    galaxy_proxy.enable()
    pulsar.start(wait_ready=True)
    proxy.remove_all_toxics()
    await_any_terminal(body["job_id"], timeout=120)
    assert_exactly_once_terminal(body["job_id"], expected=None)


@pytest.mark.resilience
def test_d2_two_concurrent_jobs_under_faults(pulsar, rabbitmq_proxy, relay_proxy):
    proxy = relay_proxy if pulsar.mode == "relay" else rabbitmq_proxy
    body_a = make_setup_message(job_id="d2-a", command_line="echo d2-a && sleep 1")
    body_b = make_setup_message(job_id="d2-b", command_line="echo d2-b && sleep 2")
    requests.post(f"{GALAXY_BASE}/_publish_setup", json=body_a, timeout=5).raise_for_status()
    requests.post(f"{GALAXY_BASE}/_publish_setup", json=body_b, timeout=5).raise_for_status()
    time.sleep(0.3)
    proxy.add_blackhole()
    time.sleep(4.0)
    proxy.remove_all_toxics()
    await_terminal("d2-a", timeout=120, expected="complete")
    await_terminal("d2-b", timeout=120, expected="complete")
    assert_exactly_once_terminal("d2-a", expected="complete")
    assert_exactly_once_terminal("d2-b", expected="complete")
