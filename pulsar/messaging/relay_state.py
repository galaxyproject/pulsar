"""State management for pulsar-relay message consumers.

Similar to QueueState for AMQP, this manages the lifecycle of relay
consumer threads on the Pulsar server side.
"""
import logging
import threading
from typing import (
    List,
    Optional,
)

log = logging.getLogger(__name__)


class RelayState:
    """Manages state for pulsar-relay message consumers.

    This object is passed to consumer loops and used to signal when
    they should stop processing messages.
    """

    def __init__(self) -> None:
        """Initialize relay state."""
        self.active: bool = True
        self.threads: List[threading.Thread] = []
        self.outboxes: list = []

    def deactivate(self) -> None:
        """Mark the relay state as inactive, signaling consumers to stop."""
        self.active = False
        for outbox in self.outboxes:
            try:
                outbox.stop(timeout=2.0)
            except OSError:
                log.exception("Failed to stop relay status update outbox")

    def join(self, timeout: Optional[float] = None) -> None:
        """Join all consumer threads."""
        for t in self.threads:
            t.join(timeout)
            if t.is_alive():
                log.warning("Failed to join relay consumer thread [%s].", t)
