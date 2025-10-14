"""State management for pulsar-proxy message consumers.

Similar to QueueState for AMQP, this manages the lifecycle of proxy
consumer threads on the Pulsar server side.
"""


class ProxyState:
    """Manages state for pulsar-proxy message consumers.

    This object is passed to consumer loops and used to signal when
    they should stop processing messages.
    """

    def __init__(self):
        """Initialize proxy state."""
        self.active = True
        self.threads = []

    def deactivate(self):
        """Mark the proxy state as inactive, signaling consumers to stop."""
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
                log.warning("Failed to join proxy consumer thread [%s].", t)
