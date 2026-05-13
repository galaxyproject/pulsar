"""Tests for ``pulsar-config register-with-galaxy`` orchestration."""

import base64
import importlib.util
import json
import os

import pytest
import responses

from pulsar.client.galaxy_byoc import (
    GalaxyBYOCRegistrationError,
    _decode_jwt_sub,
    register_with_galaxy,
)

# ``register_with_galaxy`` lazily imports ``pulsar_relay_client``, whose
# wheel requires Python >=3.10. The pure-Python ``_decode_jwt_sub``
# tests don't need it; the end-to-end tests do.
requires_relay_client = pytest.mark.skipif(
    importlib.util.find_spec("pulsar_relay_client") is None,
    reason="pulsar-relay-client requires Python >=3.10",
)


RELAY_URL = "https://relay.test"
GALAXY_URL = "https://galaxy.test"
BOOTSTRAP_TOKEN = "one-shot-from-galaxy"


def _b64url(payload: dict) -> str:
    raw = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _jwt_with_sub(sub: str) -> str:
    """Mint a JWT-shaped string. Signature is bogus — we only test the
    base64-decoded payload extraction here."""
    return ".".join([_b64url({"alg": "RS256"}), _b64url({"sub": sub}), "sig"])


def test_decode_jwt_sub_pulls_claim():
    assert _decode_jwt_sub(_jwt_with_sub("byoc_7_lab")) == "byoc_7_lab"


def test_decode_jwt_sub_returns_none_on_malformed():
    assert _decode_jwt_sub("not.a.jwt") is None
    assert _decode_jwt_sub("only-two.segments") is None


@requires_relay_client
@responses.activate
def test_register_with_galaxy_happy_path(tmp_path):
    """End-to-end: drive the device-flow with pair=true, then POST the
    secondary to Galaxy. Verify the *primary* token (not the secondary)
    lands in ``relay_credentials.json``."""
    cred_path = str(tmp_path / "relay_credentials.json")

    # 1. /auth/device/code returns a device_code + user_code.
    responses.add(
        responses.POST,
        f"{RELAY_URL}/auth/device/code",
        json={
            "device_code": "DEV-1",
            "user_code": "AAAA-BBBB",
            "verification_uri": f"{RELAY_URL}/auth/device",
            "verification_uri_complete": f"{RELAY_URL}/auth/device?user_code=AAAA-BBBB",
            "expires_in": 60,
            "interval": 0,  # so the poll loop returns immediately in tests
        },
        status=200,
    )
    # 2. /auth/device/token returns a token pair.
    responses.add(
        responses.POST,
        f"{RELAY_URL}/auth/device/token",
        json={
            "access_token": _jwt_with_sub("byoc_7_lab"),
            "refresh_token": "PRIMARY",
            "refresh_token_secondary": "SECONDARY",
            "expires_in": 3600,
        },
        status=200,
    )
    # 3. Galaxy accepts the bootstrap callback.
    responses.add(
        responses.POST,
        f"{GALAXY_URL}/api/pulsar_byoc/bootstrap",
        json={"id": 42, "manager_name": "byoc_7_lab", "status": "active"},
        status=200,
    )

    result = register_with_galaxy(
        galaxy_url=GALAXY_URL,
        bootstrap_token=BOOTSTRAP_TOKEN,
        relay_url=RELAY_URL,
        credentials_path=cred_path,
    )

    assert result == {"relay_url": RELAY_URL, "manager_name": "byoc_7_lab"}
    # The credentials file holds only the primary; the secondary went over
    # the wire to Galaxy and is never persisted on the host.
    with open(cred_path) as f:
        creds = json.load(f)
    assert creds["refresh_token"] == "PRIMARY"
    assert "refresh_token_secondary" not in creds
    # File mode is locked down.
    assert os.stat(cred_path).st_mode & 0o777 == 0o600

    # Galaxy got the right payload.
    galaxy_call = next(c for c in responses.calls if c.request.url.endswith("/bootstrap"))
    body = json.loads(galaxy_call.request.body)
    assert body == {
        "bootstrap_token": BOOTSTRAP_TOKEN,
        "refresh_token": "SECONDARY",
        "relay_url": RELAY_URL,
        "manager_name": "byoc_7_lab",
    }


@requires_relay_client
@responses.activate
def test_register_with_galaxy_fails_when_relay_omits_secondary(tmp_path):
    """If the relay returns a single refresh token (i.e. doesn't honor
    pair=true), the orchestrator must refuse to register — Galaxy would
    otherwise get a token that, when rotated, locks out the daemon."""
    cred_path = str(tmp_path / "relay_credentials.json")

    responses.add(
        responses.POST,
        f"{RELAY_URL}/auth/device/code",
        json={
            "device_code": "DEV-1",
            "user_code": "X",
            "verification_uri": f"{RELAY_URL}/auth/device",
            "verification_uri_complete": f"{RELAY_URL}/auth/device?user_code=X",
            "expires_in": 60,
            "interval": 0,
        },
        status=200,
    )
    responses.add(
        responses.POST,
        f"{RELAY_URL}/auth/device/token",
        json={
            "access_token": _jwt_with_sub("anyone"),
            "refresh_token": "PRIMARY",
            # No refresh_token_secondary.
            "expires_in": 3600,
        },
        status=200,
    )

    with pytest.raises(GalaxyBYOCRegistrationError, match="refresh_token_secondary"):
        register_with_galaxy(
            galaxy_url=GALAXY_URL,
            bootstrap_token=BOOTSTRAP_TOKEN,
            relay_url=RELAY_URL,
            credentials_path=cred_path,
        )


@requires_relay_client
@responses.activate
def test_register_with_galaxy_surfaces_galaxy_error(tmp_path):
    """If Galaxy rejects the bootstrap (e.g. token expired), the error
    must propagate cleanly to the caller."""
    cred_path = str(tmp_path / "relay_credentials.json")

    responses.add(
        responses.POST,
        f"{RELAY_URL}/auth/device/code",
        json={
            "device_code": "DEV-1",
            "user_code": "X",
            "verification_uri": f"{RELAY_URL}/auth/device",
            "verification_uri_complete": f"{RELAY_URL}/auth/device?user_code=X",
            "expires_in": 60,
            "interval": 0,
        },
        status=200,
    )
    responses.add(
        responses.POST,
        f"{RELAY_URL}/auth/device/token",
        json={
            "access_token": _jwt_with_sub("byoc_7_lab"),
            "refresh_token": "PRIMARY",
            "refresh_token_secondary": "SECONDARY",
            "expires_in": 3600,
        },
        status=200,
    )
    responses.add(
        responses.POST,
        f"{GALAXY_URL}/api/pulsar_byoc/bootstrap",
        json={"detail": "bootstrap_token has expired"},
        status=410,
    )

    with pytest.raises(GalaxyBYOCRegistrationError, match="410"):
        register_with_galaxy(
            galaxy_url=GALAXY_URL,
            bootstrap_token=BOOTSTRAP_TOKEN,
            relay_url=RELAY_URL,
            credentials_path=cred_path,
        )
