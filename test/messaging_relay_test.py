from pulsar.messaging.bind_relay import (
    _relay_long_poll_timeout,
    DEFAULT_RELAY_LONG_POLL_TIMEOUT,
    start_consumer,
)
from pulsar.messaging.relay_state import RelayState


class RecordingLongPollTransport:
    def __init__(self, relay_state):
        self.relay_state = relay_state
        self.calls = []

    def long_poll(self, topics, timeout):
        self.calls.append((topics, timeout))
        self.relay_state.active = False
        return []


def test_relay_long_poll_timeout_defaults_to_30_seconds():
    assert _relay_long_poll_timeout({}) == DEFAULT_RELAY_LONG_POLL_TIMEOUT


def test_relay_long_poll_timeout_accepts_configured_value():
    assert _relay_long_poll_timeout({"relay_long_poll_timeout": "2"}) == 2.0


def test_start_consumer_uses_configured_long_poll_timeout():
    relay_state = RelayState()
    transport = RecordingLongPollTransport(relay_state)

    thread = start_consumer(
        transport,
        relay_state,
        ["job_setup"],
        {},
        long_poll_timeout=1.5,
    )
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert transport.calls == [(["job_setup"], 1.5)]
