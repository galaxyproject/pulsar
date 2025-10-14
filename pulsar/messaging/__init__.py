""" This module contains the server-side only code for interfacing with
message queues. Code shared between client and server can be found in
submodules of ``pulsar.client``.
"""

import logging

from ..messaging import (
    bind_amqp,
    bind_proxy,
)
from ..messaging.proxy_state import ProxyState

log = logging.getLogger(__name__)


def bind_app(app, queue_id, conf=None):
    connection_string = __id_to_connection_string(app, queue_id)

    # Check if this is a proxy connection
    if connection_string and connection_string.startswith('http://') or connection_string.startswith('https://'):
        proxy_url = connection_string
        log.info("Detected proxy connection string, binding to pulsar-proxy at %s", proxy_url)

        proxy_state = ProxyState()
        for manager in app.managers.values():
            bind_proxy.bind_manager_to_proxy(manager, proxy_state, proxy_url, conf or {})
        return proxy_state
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
