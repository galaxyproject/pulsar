"""State management for pulsar-relay message consumers.

Similar to QueueState for AMQP, this manages the lifecycle of relay
consumer threads on the Pulsar server side.
"""


class RelayState:
    """Manages state for pulsar-relay message consumers.

    This object is passed to consumer loops and used to signal when
    they should stop processing messages.
    """

    def __init__(self):
        """Initialize relay state."""
        self.active = True
        self.threads = []

    def deactivate(self):
        """Mark the relay state as inactive, signaling consumers to stop."""
        self.active = False

    def join(self, timeout=None):
        """Join all consumer threads.

        Args:
            timeout: Optional timeout in seconds for joining threads
        """
        import logging
        log = logging.getLogger(__name__)

        for t in self.threads:
            t.join(timeout)
            if t.is_alive():
                log.warning("Failed to join relay consumer thread [%s].", t)
