"""Unit tests for the relay capabilities publisher.

The publisher is intentionally simple — one POST per startup, errors
swallowed — so these tests pin down the small set of guarantees that
the rest of the design relies on:

* ``message_queue_publish_capabilities=False`` skips the publish.
* A collection failure is logged and swallowed (does not block bind).
* ``RelayTransportError`` from ``post_message`` is swallowed.
* The topic name reflects the manager and prefix.
* ``published_at`` is stamped at publish time, not at collection time.

The publisher and collector are exercised against a real
``minimal_app_for_managers()`` + ``StatefulManagerProxy(QueueManager(...))``
so contract drift in the manager interface breaks these tests.
"""
import datetime
import importlib.util
from contextlib import contextmanager
from shutil import rmtree
from unittest import mock

import pytest

# ``pulsar-relay-client`` requires Python >=3.10 (PEP 508 marker on the
# requirements pin). Skip the entire module on older interpreters where
# the relay code path is unreachable but pulsar itself still installs.
pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("pulsar_relay_client") is None,
    reason="pulsar-relay-client requires Python >=3.10",
)

if importlib.util.find_spec("pulsar_relay_client") is not None:
    from pulsar_relay_client import RelayTransportError
else:
    # Module-level skip above means tests never reference this fallback;
    # the assignment exists purely so the import line doesn't crash on
    # py3.7. mypy sees both branches statically and rejects rebinding a
    # type — silenced because the runtime path is provably unreachable.
    RelayTransportError = Exception  # type: ignore[misc, assignment]

from pulsar.managers.queued import QueueManager  # noqa: E402 — guarded above
from pulsar.managers.stateful import StatefulManagerProxy  # noqa: E402 — guarded above
from pulsar.messaging import bind_relay  # noqa: E402 — guarded above

from .test_utils import (  # noqa: E402 — guarded above
    RecordingRelayTransport,
    minimal_app_for_managers,
)


@contextmanager
def _publish_ctx(name="_default_", num_concurrent_jobs=1, raise_on_post=None):
    """Real app + real ``StatefulManagerProxy(QueueManager(...))`` + recording transport.

    Yields ``(app, proxy, transport)`` and tears down both the proxy
    (worker threads) and the staging directory.
    """
    app = minimal_app_for_managers()
    proxy = StatefulManagerProxy(QueueManager(name, app, num_concurrent_jobs=num_concurrent_jobs))
    transport = RecordingRelayTransport(raise_on_post=raise_on_post)
    try:
        yield app, proxy, transport
    finally:
        try:
            proxy.shutdown()
        except Exception:
            pass
        try:
            rmtree(app.staging_directory)
        except Exception:
            pass


def test_publishes_once_with_expected_topic_and_payload():
    with _publish_ctx() as (app, proxy, transport):
        bind_relay.publish_manager_capabilities_to_relay(app, proxy, transport, conf={})
        assert len(transport.calls) == 1
        topic, payload = transport.calls[0]
        assert topic == "pulsar_capabilities"
        assert payload["schema_version"] == 1
        assert payload["manager_name"] == "_default_"
        assert "published_at" in payload  # stamped at publish time


def test_topic_prefix_is_applied():
    with _publish_ctx() as (app, proxy, transport):
        bind_relay.publish_manager_capabilities_to_relay(
            app, proxy, transport, conf={"relay_topic_prefix": "prod"},
        )
        assert transport.calls[0][0] == "prod_pulsar_capabilities"


def test_non_default_manager_suffix():
    with _publish_ctx(name="cluster_a") as (app, proxy, transport):
        bind_relay.publish_manager_capabilities_to_relay(app, proxy, transport, conf={})
        assert transport.calls[0][0] == "pulsar_capabilities_cluster_a"


def test_off_switch_skips_publish():
    with _publish_ctx() as (app, proxy, transport):
        bind_relay.publish_manager_capabilities_to_relay(
            app, proxy, transport,
            conf={"message_queue_publish_capabilities": False},
        )
        assert transport.calls == []


def test_collect_failure_logged_and_swallowed(caplog):
    # A correctly-built real ``StatefulManagerProxy(QueueManager(...))`` cannot
    # make ``collect_capabilities`` raise, so this test patches the collector
    # seam to inject the fault. The SUT here is the publisher's error
    # isolation (collection failure must not block bind), not the collector.
    with _publish_ctx() as (app, proxy, transport):
        with mock.patch(
            "pulsar.messaging.bind_relay.collect_capabilities",
            side_effect=RuntimeError("boom"),
        ):
            # Must not raise.
            bind_relay.publish_manager_capabilities_to_relay(app, proxy, transport, conf={})
        assert transport.calls == []
        assert any(
            "Failed to collect capabilities" in r.message
            for r in caplog.records
        )


def test_relay_transport_error_swallowed(caplog):
    # post_message can raise RelayTransportError or any underlying HTTP/TLS
    # error; the publisher swallows ``Exception`` to keep manager bind
    # advisory. Pinning RelayTransportError covers the realistic case.
    with _publish_ctx(raise_on_post=RelayTransportError("network down")) as (app, proxy, transport):
        # Must not raise.
        bind_relay.publish_manager_capabilities_to_relay(app, proxy, transport, conf={})
        assert any(
            "Failed to publish capabilities" in r.message
            for r in caplog.records
        )


def test_published_at_is_iso8601_utc():
    with _publish_ctx() as (app, proxy, transport):
        bind_relay.publish_manager_capabilities_to_relay(app, proxy, transport, conf={})
        payload = transport.calls[0][1]
        # Must round-trip through fromisoformat with timezone info.
        parsed = datetime.datetime.fromisoformat(payload["published_at"])
        assert parsed.tzinfo is not None


def test_make_capabilities_topic_name_examples():
    # Module-level dunder names aren't mangled, so reach in via __dict__.
    fn = bind_relay.__dict__["__make_capabilities_topic_name"]
    assert fn("", "_default_") == "pulsar_capabilities"
    assert fn("", "cluster_a") == "pulsar_capabilities_cluster_a"
    assert fn("prod", "_default_") == "prod_pulsar_capabilities"
    assert fn("prod", "cluster_a") == "prod_pulsar_capabilities_cluster_a"
