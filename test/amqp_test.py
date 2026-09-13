"""Tests for ``pulsar.client.amqp_exchange``."""

import threading
import time

import pytest

from pulsar.client import (
    amqp_exchange,
    amqp_exchange_factory,
)
from .test_utils import (
    skip_unless_module,
)

TEST_CONNECTION = "memory://test_amqp"


@skip_unless_module("kombu")
@pytest.mark.timeout(15)
def test_amqp():
    """Test the client PulsarExchange abstraction with an in-memory connection."""
    manager1_exchange = amqp_exchange.PulsarExchange(TEST_CONNECTION, "manager_test")
    manager3_exchange = amqp_exchange.PulsarExchange(TEST_CONNECTION, "manager3_test")
    manager2_exchange = amqp_exchange.PulsarExchange(TEST_CONNECTION, "manager2_test")
    manager4_exchange = amqp_exchange.PulsarExchange(TEST_CONNECTION, "manager4_test", amqp_key_prefix="foobar_")
    thread1 = TestThread("manager_test", manager1_exchange)
    thread2 = TestThread("manager2_test", manager2_exchange)
    thread3 = TestThread("manager3_test", manager3_exchange)
    thread4 = TestThread("manager4_test", manager4_exchange)
    thread1.start()
    thread2.start()
    thread3.start()
    thread4.start()
    time.sleep(0.5)
    manager1_exchange.publish("manager_test", "cow1")
    manager2_exchange.publish("manager2_test", "cow2")
    manager3_exchange.publish("manager3_test", "cow3")
    manager4_exchange.publish("manager4_test", "cow4")
    time.sleep(0.1)
    thread1.wait_for_message("cow1")
    thread2.wait_for_message("cow2")
    thread3.wait_for_message("cow3")
    thread4.wait_for_message("cow4")


class TestThread(threading.Thread):

    def __init__(self, queue_name, exchange):
        super().__init__(target=self.run)
        self.queue_name = queue_name
        self.daemon = True
        self.exchange = exchange
        self.message = None

    def __nonzero__(self):
        return self.message is None

    __bool__ = __nonzero__  # Both needed Py2 v 3

    def run(self):
        def callback(body, message):
            self.message = body
            message.ack()

        self.exchange.consume(self.queue_name, callback=callback, check=self)

    def wait_for_message(self, expected_message):
        while self:
            time.sleep(0.05)
        if self.message != expected_message:
            msg = "Expected [{}], got [{}].".format(expected_message, self.message)
            raise AssertionError(msg)

        self.join(2)


@skip_unless_module("kombu")
def test_durable_queue_and_exchange_default():
    """Default is durable. That matches kombu's own default (which Pulsar relied
    on before opt-in durability was added) and is required by RabbitMQ 4.x,
    which refuses transient non-exclusive queues outright. Operators can opt out
    on a legacy broker via ``amqp_durable: false``.
    """
    exchange = amqp_exchange.PulsarExchange(TEST_CONNECTION, "manager_durable_default")
    queue = exchange._PulsarExchange__queue("status_update")
    assert queue.durable is True
    assert queue.exchange.durable is True


@skip_unless_module("kombu")
def test_durable_can_be_disabled():
    """Explicit opt-out for legacy brokers that still allow transient queues."""
    exchange = amqp_exchange.PulsarExchange(TEST_CONNECTION, "manager_durable_off", durable=False)
    queue = exchange._PulsarExchange__queue("status_update")
    assert queue.durable is False
    assert queue.exchange.durable is False


@skip_unless_module("kombu")
def test_durable_publishes_use_persistent_delivery_mode():
    """Persistent delivery (delivery_mode=2) is required for messages to survive
    broker restart even when the queue itself is durable.
    """
    exchange = amqp_exchange.PulsarExchange(TEST_CONNECTION, "manager_dm", durable=True)
    publish_kwds = exchange._PulsarExchange__prepare_publish_kwds("test")
    assert publish_kwds.get("delivery_mode") == 2


@skip_unless_module("kombu")
def test_non_durable_publishes_do_not_force_persistent_mode():
    exchange = amqp_exchange.PulsarExchange(TEST_CONNECTION, "manager_dm_off", durable=False)
    publish_kwds = exchange._PulsarExchange__prepare_publish_kwds("test")
    assert "delivery_mode" not in publish_kwds


@skip_unless_module("kombu")
def test_factory_defaults_durable_true():
    exchange = amqp_exchange_factory.get_exchange(TEST_CONNECTION, "factory_durable_default", {})
    queue = exchange._PulsarExchange__queue("status_update")
    assert queue.durable is True


@skip_unless_module("kombu")
def test_factory_respects_amqp_durable_false():
    exchange = amqp_exchange_factory.get_exchange(
        TEST_CONNECTION, "factory_durable_off", {"amqp_durable": False},
    )
    queue = exchange._PulsarExchange__queue("status_update")
    assert queue.durable is False


@skip_unless_module("kombu")
def test_factory_respects_amqp_durable_true():
    exchange = amqp_exchange_factory.get_exchange(
        TEST_CONNECTION, "factory_durable_on", {"amqp_durable": True},
    )
    queue = exchange._PulsarExchange__queue("status_update")
    assert queue.durable is True


@skip_unless_module("kombu")
def test_factory_respects_amqp_durable_string_true():
    exchange = amqp_exchange_factory.get_exchange(
        TEST_CONNECTION, "factory_durable_on_str", {"amqp_durable": "true"},
    )
    queue = exchange._PulsarExchange__queue("status_update")
    assert queue.durable is True


class ConsumeOnce:
    """``check`` object letting ``consume()`` run exactly one iteration."""

    def __init__(self):
        self.checks = 0

    def __bool__(self):
        self.checks += 1
        return self.checks <= 1


def spy_on_consume(monkeypatch):
    """Record connection kwargs and heartbeat-thread starts across consume()."""
    connection_kwargs = []
    heartbeat_queues = []
    original_connection = amqp_exchange.PulsarExchange.connection

    def connection(self, connection_string, **kwargs):
        connection_kwargs.append(kwargs)
        return original_connection(self, connection_string, **kwargs)

    def start_heartbeat(self, queue_name, connection):
        heartbeat_queues.append(queue_name)
        return None

    monkeypatch.setattr(amqp_exchange.PulsarExchange, "connection", connection)
    monkeypatch.setattr(
        amqp_exchange.PulsarExchange, "_PulsarExchange__start_heartbeat", start_heartbeat
    )
    return connection_kwargs, heartbeat_queues


@skip_unless_module("kombu")
def test_factory_defaults_heartbeat():
    exchange = amqp_exchange_factory.get_exchange(TEST_CONNECTION, "factory_hb_default", {})
    assert exchange._PulsarExchange__heartbeat == amqp_exchange.DEFAULT_HEARTBEAT


@skip_unless_module("kombu")
@pytest.mark.parametrize("value", [False, 0, "false", "0", "off", ""])
def test_factory_disables_heartbeat(value):
    """``false`` and ``0`` are the documented opt-outs; py-amqp treats a falsy
    client heartbeat as a hard disable and ignores the broker's proposal."""
    exchange = amqp_exchange_factory.get_exchange(
        TEST_CONNECTION, "factory_hb_off", {"amqp_heartbeat": value},
    )
    assert exchange._PulsarExchange__heartbeat == 0


@skip_unless_module("kombu")
@pytest.mark.parametrize("value,expected", [
    (60, 60),
    ("580", 580),
    (" 60 ", 60),
    (True, amqp_exchange.DEFAULT_HEARTBEAT),
])
def test_factory_coerces_heartbeat(value, expected):
    """Galaxy destination params and Pulsar's ini config hand over strings. A
    non-numeric heartbeat raises TypeError inside py-amqp's tune handshake, and
    TypeError is not in recoverable_exceptions - it kills the consumer thread.
    """
    exchange = amqp_exchange_factory.get_exchange(
        TEST_CONNECTION, "factory_hb_coerce", {"amqp_heartbeat": value},
    )
    heartbeat = exchange._PulsarExchange__heartbeat
    assert heartbeat == expected
    assert isinstance(heartbeat, int)


@skip_unless_module("kombu")
@pytest.mark.timeout(15)
def test_consume_passes_configured_heartbeat(monkeypatch):
    connection_kwargs, heartbeat_queues = spy_on_consume(monkeypatch)
    exchange = amqp_exchange.PulsarExchange(TEST_CONNECTION, "hb_consume", heartbeat=42)
    exchange.consume("setup", callback=None, check=ConsumeOnce())
    assert [kwargs["heartbeat"] for kwargs in connection_kwargs] == [42]
    assert heartbeat_queues == ["setup"]


@skip_unless_module("kombu")
@pytest.mark.timeout(15)
def test_consume_with_heartbeat_disabled_starts_no_thread(monkeypatch):
    connection_kwargs, heartbeat_queues = spy_on_consume(monkeypatch)
    exchange = amqp_exchange.PulsarExchange(TEST_CONNECTION, "hb_consume_off", heartbeat=0)
    exchange.consume("setup", callback=None, check=ConsumeOnce())
    assert [kwargs["heartbeat"] for kwargs in connection_kwargs] == [0]
    assert heartbeat_queues == []


@skip_unless_module("kombu")
@pytest.mark.timeout(15)
def test_heartbeat_does_not_leak_between_exchanges(monkeypatch):
    """consume() must not stash the heartbeat in its own default argument: that
    dict is shared process-wide, so an exchange with heartbeats disabled would
    negotiate one with the broker while starting no thread to send it, and the
    broker would drop the connection every couple of intervals forever.
    """
    connection_kwargs, _ = spy_on_consume(monkeypatch)
    default_exchange = amqp_exchange.PulsarExchange(TEST_CONNECTION, "hb_leak_default")
    default_exchange.consume("setup", callback=None, check=ConsumeOnce())
    disabled_exchange = amqp_exchange.PulsarExchange(TEST_CONNECTION, "hb_leak_off", heartbeat=0)
    disabled_exchange.consume("setup", callback=None, check=ConsumeOnce())
    assert [kwargs["heartbeat"] for kwargs in connection_kwargs] == [
        amqp_exchange.DEFAULT_HEARTBEAT, 0,
    ]


def test_publish_kwds_no_retry_by_default():
    """Without an explicit opt-in we leave kombu's defaults alone, so existing
    deployments don't get surprise retry behavior; the persistent outbox is
    the primary durability layer."""
    publish_kwds = amqp_exchange_factory.parse_amqp_publish_kwds({})
    assert "retry" not in publish_kwds
    assert "retry_policy" not in publish_kwds


def test_publish_kwds_retry_true_populates_default_policy():
    """When the operator opts into retries we fill in bounded defaults so a
    single hiccup doesn't drop a message before the outbox sees it."""
    publish_kwds = amqp_exchange_factory.parse_amqp_publish_kwds({"amqp_publish_retry": True})
    assert publish_kwds["retry"] is True
    assert publish_kwds["retry_policy"] == amqp_exchange_factory.DEFAULT_PUBLISH_RETRY_POLICY


def test_publish_kwds_explicit_retry_policy_wins_over_defaults():
    publish_kwds = amqp_exchange_factory.parse_amqp_publish_kwds({
        "amqp_publish_retry": True,
        "amqp_publish_retry_max_retries": 99,
        "amqp_publish_retry_interval_start": 7,
    })
    assert publish_kwds["retry"] is True
    assert publish_kwds["retry_policy"]["max_retries"] == 99
    assert publish_kwds["retry_policy"]["interval_start"] == 7
    # Non-overridden defaults are still filled in.
    assert publish_kwds["retry_policy"]["interval_max"] == amqp_exchange_factory.DEFAULT_PUBLISH_RETRY_POLICY["interval_max"]


__all__ = ["test_amqp"]
