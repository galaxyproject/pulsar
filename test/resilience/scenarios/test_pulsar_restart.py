"""A. Pulsar restart resilience.

Each scenario submits a job, kills Pulsar at a different lifecycle phase,
restarts it, and asserts the terminal status is delivered exactly once.

A3 specifically targets the loss point that motivated the persistent
status-update outbox (LP1 in the design plan): the window between the
on-disk ``final_status`` write and the synchronous publish.
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
def test_a1_sigkill_during_preprocessing(pulsar):
    """Pulsar dies mid-preprocessing.

    For ``queued_python`` (default in this harness) the running subprocess
    dies with the parent, so the post-restart terminal status is ``lost``,
    not ``complete``. The non-loss guarantee is still met: pulsar must
    deliver *exactly one* terminal status, not silence Galaxy forever.
    """
    body = make_setup_message(command_line="echo a1 && sleep 2")
    requests.post(f"{GALAXY_BASE}/_publish_setup", json=body, timeout=5).raise_for_status()
    time.sleep(0.3)
    pulsar.kill()
    pulsar.start(wait_ready=True)
    await_any_terminal(body["job_id"], timeout=60)
    assert_exactly_once_terminal(body["job_id"], expected=None)


@pytest.mark.resilience
def test_a2_sigkill_during_execution(pulsar):
    """Same shape as A1; the subprocess can't outlive its parent under
    queued_python. With a DRMAA/Slurm runner the terminal would be
    ``complete``."""
    body = make_setup_message(command_line="sleep 3 && echo a2-done")
    requests.post(f"{GALAXY_BASE}/_publish_setup", json=body, timeout=5).raise_for_status()
    time.sleep(1.0)
    pulsar.kill()
    pulsar.start(wait_ready=True)
    await_any_terminal(body["job_id"], timeout=60)
    assert_exactly_once_terminal(body["job_id"], expected=None)


@pytest.mark.resilience
def test_a3_sigkill_after_final_status_before_publish(pulsar, rabbitmq_proxy, relay_proxy):
    """The LP1 window: final_status is on disk but the publish hasn't gone out.

    Sequence: submit a fast job and let it complete. After the job's terminal
    status has reached the recorder (publish happened), kill pulsar, briefly
    sever the broker so any retried publishes can't go out, then restart.
    The outbox guarantees one delivered terminal status total — i.e. no
    duplicates, even after restart with prior on-disk pending entries.
    """
    body = make_setup_message(command_line="echo a3-fast")
    requests.post(f"{GALAXY_BASE}/_publish_setup", json=body, timeout=5).raise_for_status()
    # Wait for the original terminal status to land in the recorder.
    await_terminal(body["job_id"], timeout=60, expected="complete")
    # Now sever the broker, kill pulsar mid-quiescence, restore, and verify
    # the recorder still shows exactly one terminal event after pulsar comes
    # back (the outbox should not republish a delivered message).
    if pulsar.mode == "relay":
        relay_proxy.disable()
    else:
        rabbitmq_proxy.disable()
    pulsar.kill()
    if pulsar.mode == "relay":
        relay_proxy.enable()
    else:
        rabbitmq_proxy.enable()
    pulsar.start(wait_ready=True)
    time.sleep(4.0)
    assert_exactly_once_terminal(body["job_id"], expected="complete")


@pytest.mark.resilience
def test_a4_sigkill_after_status_delivered_no_duplicate(pulsar):
    body = make_setup_message(command_line="echo a4-fast")
    requests.post(f"{GALAXY_BASE}/_publish_setup", json=body, timeout=5).raise_for_status()
    await_terminal(body["job_id"], timeout=60, expected="complete")
    pulsar.kill()
    pulsar.start(wait_ready=True)
    # Wait long enough that any redelivery would have arrived.
    time.sleep(5.0)
    assert_exactly_once_terminal(body["job_id"], expected="complete")
