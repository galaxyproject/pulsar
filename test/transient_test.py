"""Unit tests for ``pulsar.client.transport.transient.is_transient_http_error``.

Pure unit tests with synthetic exceptions — no network, no fixtures. The
integration test that proves the predicate fires correctly through
``RetryActionExecutor`` lives in ``client_transport_test.py``.
"""
import socket
from urllib.error import (
    HTTPError as UrllibHTTPError,
    URLError,
)

import requests

from pulsar.client.exceptions import PulsarClientTransportError
from pulsar.client.transport.transient import (
    http_status_code,
    is_transient_http_error,
    TRANSIENT_HTTP_STATUS,
)


def _requests_http_error(status_code):
    response = requests.Response()
    response.status_code = status_code
    return requests.HTTPError(response=response)


def _urllib_http_error(code):
    return UrllibHTTPError(url="http://example/", code=code, msg="err", hdrs=None, fp=None)


def test_transient_status_set():
    # Lock the policy so changing it requires a deliberate test edit.
    assert TRANSIENT_HTTP_STATUS == frozenset({408, 425, 429, 500, 502, 503, 504})


def test_requests_5xx_is_transient():
    for code in (500, 502, 503, 504):
        assert is_transient_http_error(_requests_http_error(code)), code


def test_requests_429_is_transient():
    assert is_transient_http_error(_requests_http_error(429))


def test_requests_4xx_is_permanent():
    for code in (400, 401, 403, 404, 405, 409, 410, 413, 415, 422):
        assert not is_transient_http_error(_requests_http_error(code)), code


def test_requests_connection_and_timeout_are_transient():
    assert is_transient_http_error(requests.ConnectionError())
    assert is_transient_http_error(requests.Timeout())


def test_urllib_status_classified():
    assert is_transient_http_error(_urllib_http_error(502))
    assert is_transient_http_error(_urllib_http_error(429))
    assert not is_transient_http_error(_urllib_http_error(404))
    assert not is_transient_http_error(_urllib_http_error(403))


def test_urllib_urlerror_no_status_is_transient():
    """URLError without an HTTP status is a connection-level failure."""
    assert is_transient_http_error(URLError("connection refused"))


def test_pulsar_client_transport_error_status_classified():
    assert is_transient_http_error(PulsarClientTransportError(transport_code=502))
    assert is_transient_http_error(PulsarClientTransportError(transport_code=429))
    assert not is_transient_http_error(PulsarClientTransportError(transport_code=404))


def test_pulsar_client_transport_error_string_codes_are_transient():
    """Non-numeric transport_code values (TIMEOUT, CONNECTION_REFUSED) come
    from connection-level failures and should be retried."""
    assert is_transient_http_error(
        PulsarClientTransportError(code=PulsarClientTransportError.TIMEOUT)
    )
    assert is_transient_http_error(
        PulsarClientTransportError(code=PulsarClientTransportError.CONNECTION_REFUSED)
    )


def test_socket_and_builtin_connection_errors_are_transient():
    assert is_transient_http_error(socket.timeout())
    assert is_transient_http_error(TimeoutError())
    assert is_transient_http_error(ConnectionError())


def test_http_status_code_extracts_across_exception_shapes():
    assert http_status_code(_requests_http_error(403)) == 403
    assert http_status_code(_urllib_http_error(403)) == 403
    assert http_status_code(PulsarClientTransportError(transport_code=403)) == 403


def test_http_status_code_none_when_unavailable():
    # Connection-level / non-numeric transport codes have no HTTP status.
    assert http_status_code(ConnectionError()) is None
    assert http_status_code(PulsarClientTransportError(code=PulsarClientTransportError.TIMEOUT)) is None
    assert http_status_code(requests.HTTPError()) is None


def test_unknown_exception_defaults_to_transient():
    """Non-HTTP exceptions (filesystem, SSH, etc.) preserve the prior
    retry-everything behavior so this change is additive, not regressive."""
    class SomeOtherError(Exception):
        pass

    assert is_transient_http_error(SomeOtherError())
    assert is_transient_http_error(OSError("disk hiccup"))
