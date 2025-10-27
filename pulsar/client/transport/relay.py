"""
HTTP transport for communicating with pulsar-relay.

Provides methods for posting messages, long-polling, and managing
authentication with the relay server.
"""
import logging
import time
from typing import Any, Callable, Dict, List, Optional

import requests

from ..relay_auth import RelayAuthManager

log = logging.getLogger(__name__)


class RelayTransportError(Exception):
    """Raised when communication with pulsar-relay fails."""
    pass


class RelayTransport:
    """HTTP transport for pulsar-relay communication.

    Handles:
    - Message publishing (single and bulk)
    - Long-polling for message consumption
    - Automatic authentication and retry
    """

    def __init__(self, relay_url: str, username: str, password: str, timeout: int = 30):
        """Initialize the relay transport.

        Args:
            relay_url: Base URL of the pulsar-relay server
            username: Username for authentication
            password: Password for authentication
            timeout: Default request timeout in seconds
        """
        self.relay_url = relay_url.rstrip('/')
        self.auth_manager = RelayAuthManager(relay_url, username, password)
        self.timeout = timeout
        self.session = requests.Session()
        self._last_message_ids: Dict[str, str] = {}  # Track last message ID per topic

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers including authentication token.

        Returns:
            Dictionary of HTTP headers
        """
        token = self.auth_manager.get_token()
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

    def _retry_with_backoff(
        self,
        operation: Callable[[], requests.Response],
        operation_name: str,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0
    ) -> requests.Response:
        """Retry an operation with exponential backoff.

        Retries indefinitely for communication errors and 5xx errors,
        but not for 4xx errors (client errors).

        Args:
            operation: Function that performs the HTTP request
            operation_name: Name of the operation for logging
            initial_delay: Initial delay in seconds before first retry
            max_delay: Maximum delay in seconds between retries
            backoff_factor: Multiplier for exponential backoff

        Returns:
            requests.Response object from successful request

        Raises:
            RelayTransportError: For 4xx client errors (non-retryable)
        """
        attempt = 0
        delay = initial_delay

        while True:
            attempt += 1
            try:
                response = operation()

                # Check for client errors (4xx) - don't retry these
                if 400 <= response.status_code < 500:
                    # Let caller handle 401 separately
                    if response.status_code == 401:
                        return response
                    # Other 4xx errors are client errors, don't retry
                    response.raise_for_status()
                    return response

                # Check for server errors (5xx) - retry these
                if response.status_code >= 500:
                    log.warning(
                        "%s failed with status %d (attempt %d), retrying in %.1f seconds",
                        operation_name, response.status_code, attempt, delay
                    )
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)
                    continue

                # Success
                return response

            except requests.ConnectionError as e:
                log.warning(
                    "%s connection error (attempt %d): %s, retrying in %.1f seconds",
                    operation_name, attempt, e, delay
                )
                time.sleep(delay)
                delay = min(delay * backoff_factor, max_delay)

            except requests.Timeout as e:
                log.warning(
                    "%s timeout (attempt %d): %s, retrying in %.1f seconds",
                    operation_name, attempt, e, delay
                )
                time.sleep(delay)
                delay = min(delay * backoff_factor, max_delay)

            except requests.RequestException as e:
                # For other request exceptions, check if it's a client error
                if hasattr(e, 'response') and e.response is not None:
                    if 400 <= e.response.status_code < 500:
                        # Client error, don't retry
                        raise RelayTransportError(f"{operation_name} failed: {e}")
                # Otherwise retry
                log.warning(
                    "%s error (attempt %d): %s, retrying in %.1f seconds",
                    operation_name, attempt, e, delay
                )
                time.sleep(delay)
                delay = min(delay * backoff_factor, max_delay)

    def post_message(
        self,
        topic: str,
        payload: Dict[str, Any],
        ttl: Optional[int] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Post a single message to the relay.

        Automatically retries on communication errors and server errors (5xx)
        with exponential backoff. Does not retry on client errors (4xx).

        Args:
            topic: Topic name to publish to
            payload: Message payload (must be JSON-serializable)
            ttl: Time-to-live in seconds (optional)
            metadata: Optional metadata dictionary

        Returns:
            Response dictionary with message_id, topic, and timestamp

        Raises:
            RelayTransportError: If the request fails with a client error (4xx)
        """
        url = f"{self.relay_url}/api/v1/messages"

        message_data: Dict[str, Any] = {
            'topic': topic,
            'payload': payload
        }

        if ttl is not None:
            message_data['ttl'] = ttl

        if metadata is not None:
            message_data['metadata'] = metadata

        def _post() -> requests.Response:
            return self.session.post(
                url,
                json=message_data,
                headers=self._get_headers(),
                timeout=self.timeout
            )

        # Use retry logic with exponential backoff
        response = self._retry_with_backoff(_post, "post_message")

        if response.status_code == 401:
            # Token might have expired, invalidate and retry
            log.debug("Received 401, invalidating token and retrying")
            self.auth_manager.invalidate()
            response = self._retry_with_backoff(_post, "post_message")

        response.raise_for_status()
        result = response.json()

        log.debug("Posted message to topic '%s': message_id=%s", topic, result.get('message_id'))
        return result

    def post_bulk_messages(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Post multiple messages in a single request.

        Automatically retries on communication errors and server errors (5xx)
        with exponential backoff. Does not retry on client errors (4xx).

        Args:
            messages: List of message dictionaries, each containing 'topic' and 'payload'

        Returns:
            Response dictionary with results and summary

        Raises:
            RelayTransportError: If the request fails with a client error (4xx)
        """
        url = f"{self.relay_url}/api/v1/messages/bulk"

        request_data = {'messages': messages}

        def _post() -> requests.Response:
            return self.session.post(
                url,
                json=request_data,
                headers=self._get_headers(),
                timeout=self.timeout
            )

        # Use retry logic with exponential backoff
        response = self._retry_with_backoff(_post, "post_bulk_messages")

        if response.status_code == 401:
            self.auth_manager.invalidate()
            response = self._retry_with_backoff(_post, "post_bulk_messages")

        response.raise_for_status()
        result = response.json()

        log.debug("Posted %d messages in bulk", len(messages))
        return result

    def long_poll(
        self,
        topics: List[str],
        timeout: int = 30,
    ) -> List[Dict[str, Any]]:
        """Poll for messages from specified topics.

        This is a blocking call that waits up to 'timeout' seconds for new messages.
        Automatically tracks the last message ID per topic and includes it in
        subsequent poll requests to ensure no messages are missed.

        Args:
            topics: List of topic names to subscribe to
            timeout: Maximum seconds to wait for messages (1-60)

        Returns:
            List of message dictionaries

        Raises:
            RelayTransportError: If the request fails
        """
        url = f"{self.relay_url}/messages/poll"

        poll_data = {
            'topics': topics,
            'timeout': min(max(timeout, 1), 60)  # Clamp to 1-60 range
        }

        # Build since dict from tracked message IDs for requested topics
        tracked_since = {}
        for topic in topics:
            msg_id = self.get_last_message_id(topic)
            if msg_id is not None:
                tracked_since[topic] = msg_id
        if tracked_since:
            poll_data['since'] = tracked_since
            log.debug("Using tracked message IDs for poll: %s", tracked_since)

        try:
            response = self.session.post(
                url,
                json=poll_data,
                headers=self._get_headers(),
                timeout=timeout + 5  # Add buffer to request timeout
            )

            if response.status_code == 401:
                self.auth_manager.invalidate()
                response = self.session.post(
                    url,
                    json=poll_data,
                    headers=self._get_headers(),
                    timeout=timeout + 5
                )

            response.raise_for_status()
            result = response.json()

            messages = result.get('messages') or []

            # Track the last message ID per topic
            for message in messages:
                topic = message.get('topic')
                message_id = message.get('message_id')
                if topic and message_id:
                    self.set_last_message_id(topic, message_id)

            # Build dict of tracked IDs for the requested topics
            tracked_ids = {}
            for topic in topics:
                msg_id = self.get_last_message_id(topic)
                if msg_id is not None:
                    tracked_ids[topic] = msg_id
            log.debug(
                "Received %d messages from long poll, tracked IDs: %s",
                len(messages),
                tracked_ids
            )

            return messages

        except requests.Timeout:
            # Timeout is expected in long polling when no messages arrive
            log.debug("Long poll timeout (no messages)")
            return []

        except requests.RequestException as e:
            log.error("Failed to long poll: %s", e)
            raise RelayTransportError(f"Failed to long poll: {e}")

    def get_last_message_id(self, topic: str) -> Optional[str]:
        """Get the last tracked message ID for a topic.

        Args:
            topic: Topic name

        Returns:
            Last message ID for the topic, or None if not tracked
        """
        return self._last_message_ids.get(topic)

    def get_all_tracked_message_ids(self) -> Dict[str, str]:
        """Get all tracked message IDs.

        Returns:
            Dictionary mapping topic names to last message IDs
        """
        return self._last_message_ids.copy()

    def set_last_message_id(self, topic: str, message_id: str) -> None:
        """Manually set the last message ID for a topic.

        This can be useful for resuming from a specific message ID
        after a restart.

        Args:
            topic: Topic name
            message_id: Message ID to set as the last seen message
        """
        self._last_message_ids[topic] = message_id

    def clear_tracked_message_ids(self, topic: Optional[str] = None) -> None:
        """Clear tracked message IDs.

        Args:
            topic: If provided, clears only the specified topic.
                  If None, clears all tracked message IDs.
        """
        if topic is not None:
            if topic in self._last_message_ids:
                del self._last_message_ids[topic]
                log.debug("Cleared tracked message ID for topic '%s'", topic)
        else:
            self._last_message_ids.clear()
            log.debug("Cleared all tracked message IDs")

    def close(self):
        """Close the transport and cleanup resources."""
        self.session.close()
