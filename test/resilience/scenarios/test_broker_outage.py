"""B. Broker outage scenarios.

For AMQP and relay modes, verify that an outage of the message bus does not
lose a job's terminal status. The outbox + durable queues + persisted relay
cursor are the production-side guarantees being exercised here.
"""
import time

import pytest
import requests

from harness.assertions import (
    assert_exactly_once_terminal,
    assert_states_in_order,
    await_terminal,
)
from harness.job_factory import make_setup_message

GALAXY_BASE = "http://localhost:8088"


def _broker_proxy_for_mode(mode, rabbitmq_proxy, relay_proxy):
    return relay_proxy if mode == "relay" else rabbitmq_proxy


@pytest.mark.resilience
def test_b1_outage_during_preprocessing(pulsar, rabbitmq_proxy, relay_proxy):
    proxy = _broker_proxy_for_mode(pulsar.mode, rabbitmq_proxy, relay_proxy)
    body = make_setup_message(command_line="echo b1 && sleep 1")
    requests.post(f"{GALAXY_BASE}/_publish_setup", json=body, timeout=5).raise_for_status()
    time.sleep(0.3)
    proxy.disable()
    time.sleep(3.0)
    proxy.enable()
    await_terminal(body["job_id"], timeout=180, expected="complete")
    assert_exactly_once_terminal(body["job_id"], expected="complete")
    assert_states_in_order(body["job_id"])


@pytest.mark.resilience
def test_b2_outage_during_execution(pulsar, rabbitmq_proxy, relay_proxy):
    proxy = _broker_proxy_for_mode(pulsar.mode, rabbitmq_proxy, relay_proxy)
    body = make_setup_message(command_line="sleep 2 && echo b2-done")
    requests.post(f"{GALAXY_BASE}/_publish_setup", json=body, timeout=5).raise_for_status()
    time.sleep(0.8)
    proxy.disable()
    time.sleep(4.0)
    proxy.enable()
    await_terminal(body["job_id"], timeout=180, expected="complete")
    assert_exactly_once_terminal(body["job_id"], expected="complete")


@pytest.mark.resilience
def test_b3_long_outage_with_running_pulsar(pulsar, rabbitmq_proxy, relay_proxy):
    """Pulsar stays up the whole time; the broker is gone for a long stretch.

    No exceptions in the postprocess thread should kill it: with the outbox,
    the terminal status sits on disk and is published as soon as the broker
    returns.
    """
    proxy = _broker_proxy_for_mode(pulsar.mode, rabbitmq_proxy, relay_proxy)
    body = make_setup_message(command_line="echo b3-fast && sleep 1")
    requests.post(f"{GALAXY_BASE}/_publish_setup", json=body, timeout=5).raise_for_status()
    # Let the setup be consumed and the job start before severing the broker;
    # mock-galaxy can only publish to a backend that's actually reachable.
    time.sleep(0.6)
    proxy.disable()
    time.sleep(8.0)  # long outage while Pulsar holds the terminal status
    proxy.enable()
    await_terminal(body["job_id"], timeout=120, expected="complete")
    assert_exactly_once_terminal(body["job_id"], expected="complete")


@pytest.mark.resilience
def test_b4_broker_dies_and_pulsar_sigkill(pulsar, rabbitmq_proxy, relay_proxy):
    proxy = _broker_proxy_for_mode(pulsar.mode, rabbitmq_proxy, relay_proxy)
    body = make_setup_message(command_line="echo b4-fast")
    requests.post(f"{GALAXY_BASE}/_publish_setup", json=body, timeout=5).raise_for_status()
    time.sleep(0.5)
    proxy.disable()
    pulsar.kill()
    time.sleep(1.5)
    proxy.enable()
    pulsar.start(wait_ready=True)
    await_terminal(body["job_id"], timeout=180, expected="complete")
    assert_exactly_once_terminal(body["job_id"], expected="complete")


@pytest.mark.resilience
def test_b5_blackhole_partition(pulsar, rabbitmq_proxy, relay_proxy):
    proxy = _broker_proxy_for_mode(pulsar.mode, rabbitmq_proxy, relay_proxy)
    body = make_setup_message(command_line="echo b5 && sleep 1")
    requests.post(f"{GALAXY_BASE}/_publish_setup", json=body, timeout=5).raise_for_status()
    # Let the setup land before partitioning; mock-galaxy can't reach a
    # blackholed broker (the same as B3).
    time.sleep(0.8)
    proxy.add_blackhole()
    time.sleep(6.0)
    proxy.remove_all_toxics()
    await_terminal(body["job_id"], timeout=180, expected="complete")
    assert_exactly_once_terminal(body["job_id"], expected="complete")
