"""
JWT authentication manager for pulsar-relay.

Handles token acquisition, caching, and automatic refresh.
"""
import logging
import threading
from typing import cast, Optional
from datetime import datetime, timedelta

import requests

log = logging.getLogger(__name__)


class RelayAuthManager:
    """Manages JWT authentication tokens for pulsar-relay communication.

    Features:
    - Thread-safe token caching
    - Automatic token refresh before expiry
    - Lazy authentication (only authenticates when needed)
    """

    def __init__(self, relay_url: str, username: str, password: str):
        """Initialize the authentication manager.

        Args:
            relay_url: Base URL of the pulsar-relay server
            username: Username for authentication
            password: Password for authentication
        """
        self.relay_url = relay_url.rstrip('/')
        self.username = username
        self.password = password

        self._token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._lock = threading.Lock()

        # Refresh token 5 minutes before expiry
        self._refresh_buffer_seconds = 300

    def get_token(self) -> str:
        """Get a valid JWT token, refreshing if necessary.

        Returns:
            Valid JWT access token

        Raises:
            Exception: If authentication fails
        """
        with self._lock:
            if self._is_token_valid():
                return cast(str, self._token)

            # Need to authenticate or refresh
            log.debug("Authenticating with pulsar-relay at %s", self.relay_url)
            self._authenticate()
            return cast(str, self._token)

    def _is_token_valid(self) -> bool:
        """Check if current token is valid and not expiring soon.

        Returns:
            True if token exists and won't expire soon, False otherwise
        """
        if self._token is None or self._token_expiry is None:
            return False

        # Check if token will expire within refresh buffer
        time_until_expiry = (self._token_expiry - datetime.now()).total_seconds()
        return time_until_expiry > self._refresh_buffer_seconds

    def _authenticate(self) -> None:
        """Perform authentication and cache the token.

        Raises:
            Exception: If authentication fails
        """

        auth_url = f"{self.relay_url}/auth/login"

        try:
            response = requests.post(
                auth_url,
                data={
                    'username': self.username,
                    'password': self.password,
                    'grant_type': 'password'
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=10
            )
            response.raise_for_status()

            data = response.json()
            self._token = data['access_token']
            expires_in = data['expires_in']

            # Calculate expiry time
            self._token_expiry = datetime.now() + timedelta(seconds=expires_in)

            log.info("Successfully authenticated with pulsar-relay, token expires in %d seconds", expires_in)

        except requests.RequestException as e:
            log.error("Failed to authenticate with pulsar-relay: %s", e)
            raise Exception(f"pulsar-relay authentication failed: {e}")

    def invalidate(self) -> None:
        """Invalidate the current token, forcing re-authentication on next request."""
        with self._lock:
            self._token = None
            self._token_expiry = None
            log.debug("Invalidated pulsar-relay authentication token")
