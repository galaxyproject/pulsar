""" This module contains the server-side only code for interfacing with
message queues. Code shared between client and server can be found in
submodules of ``pulsar.client``.
"""

import logging

from six import itervalues

from ..messaging import bind_amqp

log = logging.getLogger(__name__)


def bind_app(app, queue_id, connect_ssl=None):
    connection_string = __id_to_connection_string(app, queue_id)
    queue_state = QueueState()
    for manager in itervalues(app.managers):
        bind_amqp.bind_manager_to_queue(manager, queue_state, connection_string, connect_ssl)
    return queue_state


class QueueState(object):
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
            if t.isAlive():
                log.warn("Failed to join thread [%s]." % t)


def __id_to_connection_string(app, queue_id):
    return queue_id
