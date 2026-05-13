"""Resilience scenario: pulsar publishes its capability snapshot to the relay.

The publisher fires once at ``messaging.bind_app`` time. After the relay
fixture is healthy and pulsar has bound its consumers, the snapshot must
be retrievable through the relay's REST topic-messages endpoint.

Only the relay messaging mode is exercised — there's nothing to publish
in AMQP mode, and the publisher path is gated on the connection-string
prefix in ``pulsar.messaging.bind_app``.
"""
import time

import pytest
import requests

from harness.pulsar_control import (
    RELAY_HTTP,
    _relay_admin_token,
)


def _fetch_latest_capabilities(topic="pulsar_capabilities", timeout=5.0):
    """Hit ``GET /api/v1/topics/{topic}/messages?limit=1&order=desc``.

    Returns the message payload dict, or ``None`` if the topic is empty
    / not found / the relay is unreachable. Bounded by ``timeout``.
    """
    deadline = time.time() + timeout
    last_status = None
    last_body = None
    while time.time() < deadline:
        try:
            token = _relay_admin_token()
        except Exception:
            time.sleep(0.2)
            continue
        try:
            r = requests.get(
                f"{RELAY_HTTP}/api/v1/topics/{topic}/messages",
                params={"limit": 1, "order": "desc"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=2,
            )
        except Exception:
            time.sleep(0.2)
            continue
        last_status = r.status_code
        last_body = r.text
        if r.status_code == 200:
            messages = (r.json() or {}).get("messages") or []
            if messages:
                return messages[0].get("payload")
        # 404 = topic not yet created (publish in flight); keep polling.
        time.sleep(0.2)
    pytest.fail(
        f"capabilities topic empty after {timeout}s "
        f"(last status={last_status}, body={last_body})"
    )


@pytest.mark.parametrize("mq_mode", ["relay"], indirect=True)
def test_pulsar_publishes_capabilities_on_bind(pulsar):
    """After ``pulsar.start(wait_ready=True)`` the snapshot is on the relay."""
    payload = _fetch_latest_capabilities()
    assert payload is not None
    assert payload["schema_version"] == 1
    assert payload["manager_name"] == "_default_"
    assert payload["staging_directory"]
    # Pulsar is booted with at least one dependency resolver from the
    # default conf — the field must be present even if the list is short.
    assert "dependency_resolvers" in payload
    assert "container_runtime" in payload
    assert payload["container_runtime"]["docker_available"] in (True, False)
    assert payload["manager"]["type"]  # whatever manager_type the test stack uses
    # Stamped at publish time, not collection time.
    assert payload["published_at"]


@pytest.mark.parametrize("mq_mode", ["relay"], indirect=True)
def test_capabilities_resnapshot_after_pulsar_restart(pulsar):
    """A restart re-publishes; the latest pointer advances."""
    first = _fetch_latest_capabilities()
    first_ts = first["published_at"]

    pulsar.restart(wait_ready=True)

    # Poll until the new snapshot is visible — restart re-binds and
    # re-publishes, but the relay-side stream takes a tick to expose it.
    deadline = time.time() + 10
    while time.time() < deadline:
        latest = _fetch_latest_capabilities()
        if latest["published_at"] != first_ts:
            assert latest["schema_version"] == 1
            assert latest["manager_name"] == "_default_"
            return
        time.sleep(0.3)
    pytest.fail("capabilities published_at did not advance after pulsar restart")
