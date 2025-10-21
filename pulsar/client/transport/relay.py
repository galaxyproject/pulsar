"""
HTTP transport for communicating with pulsar-relay.

Provides methods for posting messages, long-polling, and managing
authentication with the relay server.
"""
import logging
from typing import Any, Dict, List, Optional

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

    def post_message(
        self,
        topic: str,
        payload: Dict[str, Any],
        ttl: Optional[int] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Post a single message to the relay.

        Args:
            topic: Topic name to publish to
            payload: Message payload (must be JSON-serializable)
            ttl: Time-to-live in seconds (optional)
            metadata: Optional metadata dictionary

        Returns:
            Response dictionary with message_id, topic, and timestamp

        Raises:
            RelayTransportError: If the request fails
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

        try:
            response = self.session.post(
                url,
                json=message_data,
                headers=self._get_headers(),
                timeout=self.timeout
            )

            if response.status_code == 401:
                # Token might have expired, invalidate and retry once
                log.debug("Received 401, invalidating token and retrying")
                self.auth_manager.invalidate()
                response = self.session.post(
                    url,
                    json=message_data,
                    headers=self._get_headers(),
                    timeout=self.timeout
                )

            response.raise_for_status()
            result = response.json()

            log.debug("Posted message to topic '%s': message_id=%s", topic, result.get('message_id'))
            return result

        except requests.RequestException as e:
            log.error("Failed to post message to topic '%s': %s", topic, e)
            raise RelayTransportError(f"Failed to post message: {e}")

    def post_bulk_messages(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Post multiple messages in a single request.

        Args:
            messages: List of message dictionaries, each containing 'topic' and 'payload'

        Returns:
            Response dictionary with results and summary

        Raises:
            RelayTransportError: If the request fails
        """
        url = f"{self.relay_url}/api/v1/messages/bulk"

        request_data = {'messages': messages}

        try:
            response = self.session.post(
                url,
                json=request_data,
                headers=self._get_headers(),
                timeout=self.timeout
            )

            if response.status_code == 401:
                self.auth_manager.invalidate()
                response = self.session.post(
                    url,
                    json=request_data,
                    headers=self._get_headers(),
                    timeout=self.timeout
                )

            response.raise_for_status()
            result = response.json()

            log.debug("Posted %d messages in bulk", len(messages))
            return result

        except requests.RequestException as e:
            log.error("Failed to post bulk messages: %s", e)
            raise RelayTransportError(f"Failed to post bulk messages: {e}")

    def long_poll(
        self,
        topics: List[str],
        since: Optional[Dict[str, str]] = None,
        timeout: int = 30
    ) -> List[Dict[str, Any]]:
        """Poll for messages from specified topics.

        This is a blocking call that waits up to 'timeout' seconds for new messages.

        Args:
            topics: List of topic names to subscribe to
            since: Optional dict mapping topic names to last seen message IDs
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

        if since is not None:
            poll_data['since'] = since

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

            messages = result.get('messages', [])
            if messages:
                log.debug("Received %d messages from long poll", len(messages))

            return messages

        except requests.Timeout:
            # Timeout is expected in long polling when no messages arrive
            log.debug("Long poll timeout (no messages)")
            return []

        except requests.RequestException as e:
            log.error("Failed to long poll: %s", e)
            raise RelayTransportError(f"Failed to long poll: {e}")

    def close(self):
        """Close the transport and cleanup resources."""
        self.session.close()
