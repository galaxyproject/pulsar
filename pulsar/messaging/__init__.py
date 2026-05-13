""" This module contains the server-side only code for interfacing with
message queues. Code shared between client and server can be found in
submodules of ``pulsar.client``.
"""

import logging

from ..messaging import (
    bind_amqp,
    bind_relay,
)
from .relay_state import RelayState

log = logging.getLogger(__name__)


def bind_app(app, queue_id, conf=None):
    connection_string = __id_to_connection_string(app, queue_id)

    # Check if this is a relay connection
    if connection_string and connection_string.startswith('http://') or connection_string.startswith('https://'):
        relay_url = connection_string
        log.info("Detected relay connection string, binding to pulsar-relay at %s", relay_url)

        relay_state = RelayState()
        merged_conf = conf or {}
        for manager in app.managers.values():
            # Build the transport once per manager and reuse for both the
            # control-message bind and the capabilities publish, so the
            # initial token fetch + cursor file open happen exactly once.
            relay_transport = bind_relay.build_relay_transport(manager, relay_url, merged_conf)
            bind_relay.bind_manager_to_relay(
                manager, relay_state, relay_url, merged_conf,
                relay_transport=relay_transport,
            )
            bind_relay.publish_manager_capabilities_to_relay(
                app, manager, relay_transport, merged_conf,
            )
        return relay_state
    else:
        # Use AMQP binding
        queue_state = QueueState()
        for manager in app.managers.values():
            bind_amqp.bind_manager_to_queue(manager, queue_state, connection_string, conf)
        return queue_state


class QueueState:
    """ Passed through to event loops, should be "non-zero" while queues should
    be active.
    """
    def __init__(self):
        self.active = True
        self.threads = []
        self.outboxes = []

    def deactivate(self):
        self.active = False
        for outbox in self.outboxes:
            try:
                outbox.stop(timeout=2.0)
            except OSError:
                log.exception("Failed to stop status update outbox")

    def __nonzero__(self):
        return self.active

    __bool__ = __nonzero__  # Both needed Py2 v 3

    def join(self, timeout=None):
        for t in self.threads:
            t.join(timeout)
            if t.is_alive():
                log.warning("Failed to join thread [%s]." % t)


def __id_to_connection_string(app, queue_id):
    return queue_id
