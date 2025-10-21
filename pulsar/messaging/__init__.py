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
        for manager in app.managers.values():
            bind_relay.bind_manager_to_relay(manager, relay_state, relay_url, conf or {})
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

    def deactivate(self):
        self.active = False

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
