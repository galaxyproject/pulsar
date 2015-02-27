""" This module contains the server-side only code for interfacing with
message queues. Code shared between client and server can be found in
submodules of ``pulsar.client``.
"""

from ..messaging import bind_amqp
from six import itervalues


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

    def deactivate(self):
        self.active = False

    def __nonzero__(self):
        return self.active


def __id_to_connection_string(app, queue_id):
    return queue_id
