"""Classify exceptions raised by Pulsar transports as transient or permanent.

Used as the ``should_retry`` predicate for ``RetryActionExecutor`` so that
staging actions retry on transient HTTP failures (5xx, 429, connection
errors) but fail fast on permanent ones (4xx client errors).
"""
import socket
from urllib.error import (
    HTTPError as UrllibHTTPError,
    URLError,
)

import requests

from ..exceptions import PulsarClientTransportError


# Per RFC 6585 / RFC 9110 plus de-facto convention used by urllib3,
# Google Cloud SDK, AWS SDK, Azure SDK:
#   408 Request Timeout    — server gave up waiting
#   425 Too Early          — replay-protection backoff
#   429 Too Many Requests  — rate limited (honor Retry-After)
#   500 Internal Server Error
#   502 Bad Gateway        — the nginx-upstream case from #443
#   503 Service Unavailable
#   504 Gateway Timeout
TRANSIENT_HTTP_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


def http_status_code(exc):
    """Best-effort HTTP status code from a transport exception, else ``None``.

    Normalizes the several exception shapes Pulsar transports raise (requests
    ``HTTPError``, urllib ``HTTPError``, ``PulsarClientTransportError``) into a
    single integer status, so callers can react to specific codes (e.g. a 403
    that means the Galaxy server authoritatively refused an upload).
    """
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code
    if isinstance(exc, UrllibHTTPError):
        return exc.code
    if isinstance(exc, PulsarClientTransportError):
        try:
            return int(exc.transport_code)
        except (TypeError, ValueError):
            return None
    return None


def _status_is_transient(status):
    try:
        return int(status) in TRANSIENT_HTTP_STATUS
    except (TypeError, ValueError):
        # Non-numeric transport_code (e.g. PulsarClientTransportError.TIMEOUT
        # string constants) — these come from connection-level failures, not
        # HTTP responses, and are always transient.
        return True


def is_transient_http_error(exc):
    """Return True if ``exc`` should be retried.

    The default for unrecognized exceptions is True so that non-HTTP failures
    (filesystem hiccups, SSH disconnects, etc.) keep retrying as they did
    before this predicate existed. We only opt *out* of retry for things we
    positively recognize as permanent client errors.
    """
    # Connection-level failures: always transient.
    if isinstance(exc, (ConnectionError, TimeoutError, socket.timeout)):
        return True
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True

    # HTTP responses with a status code we can read.
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return _status_is_transient(exc.response.status_code)
    if isinstance(exc, UrllibHTTPError):
        return _status_is_transient(exc.code)
    if isinstance(exc, PulsarClientTransportError):
        return _status_is_transient(exc.transport_code)

    # urllib.error.URLError without an HTTP status is connection-level.
    if isinstance(exc, URLError):
        return True

    # Unknown — be conservative and retry. Preserves prior behavior for
    # filesystem, SSH, and other non-HTTP exceptions that staging actions
    # can raise.
    return True
