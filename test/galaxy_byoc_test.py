"""Tests for ``pulsar-config register-with-galaxy`` orchestration."""

import base64
import importlib.util
import json
import os

import pytest
import responses

from pulsar.client.galaxy_byoc import (
    _decode_jwt_sub,
    GalaxyBYOCRegistrationError,
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


def _mock_relay_device_flow(sub, secondary="SECONDARY"):
    """Mock the relay's device flow through to a token response.

    ``secondary=None`` simulates a relay that ignores ``pair=true`` and hands
    back a single refresh token.
    """
    responses.add(
        responses.POST,
        f"{RELAY_URL}/auth/device/code",
        json={
            "device_code": "DEV-1",
            "user_code": "X",
            "verification_uri": f"{RELAY_URL}/auth/device",
            "verification_uri_complete": f"{RELAY_URL}/auth/device?user_code=X",
            "expires_in": 60,
            "interval": 0,  # so the poll loop returns immediately in tests
        },
        status=200,
    )
    token_response = {
        "access_token": _jwt_with_sub(sub),
        "refresh_token": "PRIMARY",
        "expires_in": 3600,
    }
    if secondary is not None:
        token_response["refresh_token_secondary"] = secondary
    responses.add(
        responses.POST,
        f"{RELAY_URL}/auth/device/token",
        json=token_response,
        status=200,
    )


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

    # 1. + 2. Device flow yields an access token plus a paired refresh token.
    _mock_relay_device_flow("byoc_7_lab")
    # 3. Galaxy accepts the bootstrap callback.
    responses.add(
        responses.POST,
        f"{GALAXY_URL}/api/compute_resources/registrations/complete",
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
    galaxy_call = next(c for c in responses.calls if c.request.url.endswith("/registrations/complete"))
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

    _mock_relay_device_flow("anyone", secondary=None)

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

    _mock_relay_device_flow("byoc_7_lab")
    responses.add(
        responses.POST,
        f"{GALAXY_URL}/api/compute_resources/registrations/complete",
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


@requires_relay_client
@responses.activate
def test_register_with_galaxy_uses_galaxy_minted_manager_name(tmp_path):
    """Galaxy mints its own manager name and returns it. Pulsar must use that
    name, not the relay ``sub``, or it listens on topics Galaxy never publishes
    to and jobs stay queued."""
    _mock_relay_device_flow("relay-user-uuid")
    responses.add(
        responses.POST,
        f"{GALAXY_URL}/api/compute_resources/registrations/complete",
        json={"id": 42, "manager_name": "cr-0123abcd", "status": "active"},
        status=200,
    )
    result = register_with_galaxy(
        galaxy_url=GALAXY_URL,
        bootstrap_token=BOOTSTRAP_TOKEN,
        relay_url=RELAY_URL,
        credentials_path=str(tmp_path / "relay_credentials.json"),
    )
    assert result["manager_name"] == "cr-0123abcd"


@requires_relay_client
@responses.activate
def test_register_with_galaxy_falls_back_to_sub_without_minted_name(tmp_path):
    """A Galaxy that doesn't return a manager name keeps the old behaviour."""
    _mock_relay_device_flow("relay-user-uuid")
    responses.add(
        responses.POST,
        f"{GALAXY_URL}/api/compute_resources/registrations/complete",
        json={"id": 42, "status": "active"},
        status=200,
    )
    result = register_with_galaxy(
        galaxy_url=GALAXY_URL,
        bootstrap_token=BOOTSTRAP_TOKEN,
        relay_url=RELAY_URL,
        credentials_path=str(tmp_path / "relay_credentials.json"),
    )
    assert result["manager_name"] == "relay-user-uuid"
