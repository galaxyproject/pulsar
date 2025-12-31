"""
Tests for the relay transport implementation.

Tests retry logic and message ID tracking functionality.
"""
from unittest import TestCase
from unittest.mock import Mock, patch

import requests

from pulsar.client.transport.relay import RelayTransport, RelayTransportError


class TestRetryLogic(TestCase):
    """Test retry logic with exponential backoff."""

    @patch('pulsar.client.transport.relay.time.sleep')
    def test_post_message_retries_on_connection_error(self, mock_sleep):
        """Test that post_message retries indefinitely on connection errors."""
        transport = RelayTransport('http://localhost:8000', 'user', 'pass')

        # Mock the auth manager to return a token
        transport.auth_manager.get_token = Mock(return_value='test-token')

        # Mock session.post to fail twice with ConnectionError, then succeed
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'message_id': 'msg_123',
            'topic': 'test-topic',
            'timestamp': '2025-10-27T10:00:00Z'
        }

        transport.session.post = Mock(
            side_effect=[
                requests.ConnectionError("Connection refused"),
                requests.ConnectionError("Connection refused"),
                mock_response
            ]
        )

        result = transport.post_message('test-topic', {'data': 'test'})

        # Verify it succeeded after retries
        assert result['message_id'] == 'msg_123'
        assert transport.session.post.call_count == 3
        # Verify exponential backoff was used
        assert mock_sleep.call_count == 2
        # First delay should be 1.0, second should be 2.0
        assert mock_sleep.call_args_list[0][0][0] == 1.0
        assert mock_sleep.call_args_list[1][0][0] == 2.0

    @patch('pulsar.client.transport.relay.time.sleep')
    def test_post_message_retries_on_500_error(self, mock_sleep):
        """Test that post_message retries on 5xx server errors."""
        transport = RelayTransport('http://localhost:8000', 'user', 'pass')
        transport.auth_manager.get_token = Mock(return_value='test-token')

        # Mock responses: 500, 503, then 200
        mock_500 = Mock()
        mock_500.status_code = 500

        mock_503 = Mock()
        mock_503.status_code = 503

        mock_200 = Mock()
        mock_200.status_code = 200
        mock_200.json.return_value = {
            'message_id': 'msg_456',
            'topic': 'test-topic',
            'timestamp': '2025-10-27T10:00:00Z'
        }

        transport.session.post = Mock(side_effect=[mock_500, mock_503, mock_200])

        result = transport.post_message('test-topic', {'data': 'test'})

        assert result['message_id'] == 'msg_456'
        assert transport.session.post.call_count == 3
        assert mock_sleep.call_count == 2

    def test_post_message_does_not_retry_on_400_error(self):
        """Test that post_message does NOT retry on 4xx client errors."""
        transport = RelayTransport('http://localhost:8000', 'user', 'pass')
        transport.auth_manager.get_token = Mock(return_value='test-token')

        # Mock response with 400 error
        mock_400 = Mock()
        mock_400.status_code = 400

        # Create HTTPError with response attached
        error = requests.HTTPError("400 Bad Request")
        error.response = mock_400
        mock_400.raise_for_status.side_effect = error

        transport.session.post = Mock(return_value=mock_400)

        with self.assertRaises(RelayTransportError):
            transport.post_message('test-topic', {'data': 'test'})

        # Should only be called once (no retries for 4xx)
        assert transport.session.post.call_count == 1

    @patch('pulsar.client.transport.relay.time.sleep')
    def test_post_message_retries_on_timeout(self, mock_sleep):
        """Test that post_message retries on timeout."""
        transport = RelayTransport('http://localhost:8000', 'user', 'pass')
        transport.auth_manager.get_token = Mock(return_value='test-token')

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'message_id': 'msg_789',
            'topic': 'test-topic',
            'timestamp': '2025-10-27T10:00:00Z'
        }

        transport.session.post = Mock(
            side_effect=[
                requests.Timeout("Request timed out"),
                mock_response
            ]
        )

        result = transport.post_message('test-topic', {'data': 'test'})

        assert result['message_id'] == 'msg_789'
        assert transport.session.post.call_count == 2
        assert mock_sleep.call_count == 1

    @patch('pulsar.client.transport.relay.time.sleep')
    def test_retry_backoff_caps_at_max_delay(self, mock_sleep):
        """Test that exponential backoff caps at max_delay."""
        transport = RelayTransport('http://localhost:8000', 'user', 'pass')
        transport.auth_manager.get_token = Mock(return_value='test-token')

        # Create many connection errors to test max delay
        errors = [requests.ConnectionError("Connection refused")] * 10

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'message_id': 'msg_999',
            'topic': 'test-topic',
            'timestamp': '2025-10-27T10:00:00Z'
        }

        transport.session.post = Mock(side_effect=errors + [mock_response])

        result = transport.post_message('test-topic', {'data': 'test'})

        assert result['message_id'] == 'msg_999'
        assert mock_sleep.call_count == 10

        # Check that delay caps at 60 seconds
        delays = [call[0][0] for call in mock_sleep.call_args_list]
        # Expected: 1, 2, 4, 8, 16, 32, 60, 60, 60, 60
        assert delays[0] == 1.0
        assert delays[1] == 2.0
        assert delays[2] == 4.0
        assert delays[3] == 8.0
        assert delays[4] == 16.0
        assert delays[5] == 32.0
        # After this, should cap at 60
        assert all(d == 60.0 for d in delays[6:])


class TestMessageIDTracking:
    """Test message ID tracking functionality."""

    def test_long_poll_tracks_message_ids(self):
        """Test that long_poll tracks message IDs per topic."""
        transport = RelayTransport('http://localhost:8000', 'user', 'pass')
        transport.auth_manager.get_token = Mock(return_value='test-token')

        # Mock response with messages from different topics
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'messages': [
                {'topic': 'topic1', 'message_id': 'msg_001', 'payload': {'data': 'a'}},
                {'topic': 'topic2', 'message_id': 'msg_002', 'payload': {'data': 'b'}},
                {'topic': 'topic1', 'message_id': 'msg_003', 'payload': {'data': 'c'}},
            ],
            'has_more': False
        }

        transport.session.post = Mock(return_value=mock_response)

        messages = transport.long_poll(['topic1', 'topic2'])

        # Verify message IDs are tracked (last message ID per topic)
        assert transport.get_last_message_id('topic1') == 'msg_003'
        assert transport.get_last_message_id('topic2') == 'msg_002'
        assert len(messages) == 3

    def test_long_poll_uses_tracked_message_ids_in_since(self):
        """Test that long_poll includes tracked message IDs in the since parameter."""
        transport = RelayTransport('http://localhost:8000', 'user', 'pass')
        transport.auth_manager.get_token = Mock(return_value='test-token')

        # Set some tracked message IDs
        transport.set_last_message_id('topic1', 'msg_100')
        transport.set_last_message_id('topic2', 'msg_200')

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'messages': [],
            'has_more': False
        }

        transport.session.post = Mock(return_value=mock_response)

        # Call long_poll
        transport.long_poll(['topic1', 'topic2'])

        # Verify the 'since' parameter was included in the request
        call_args = transport.session.post.call_args
        request_json = call_args[1]['json']

        assert 'since' in request_json
        assert request_json['since']['topic1'] == 'msg_100'
        assert request_json['since']['topic2'] == 'msg_200'

    def test_long_poll_only_includes_since_for_requested_topics(self):
        """Test that since only includes tracked IDs for topics in the request."""
        transport = RelayTransport('http://localhost:8000', 'user', 'pass')
        transport.auth_manager.get_token = Mock(return_value='test-token')

        # Set tracked message IDs for multiple topics
        transport.set_last_message_id('topic1', 'msg_100')
        transport.set_last_message_id('topic2', 'msg_200')
        transport.set_last_message_id('topic3', 'msg_300')

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'messages': [], 'has_more': False}

        transport.session.post = Mock(return_value=mock_response)

        # Only poll for topic1 and topic2
        transport.long_poll(['topic1', 'topic2'])

        call_args = transport.session.post.call_args
        request_json = call_args[1]['json']

        # Should only include topic1 and topic2 in since
        assert 'since' in request_json
        assert 'topic1' in request_json['since']
        assert 'topic2' in request_json['since']
        assert 'topic3' not in request_json['since']
