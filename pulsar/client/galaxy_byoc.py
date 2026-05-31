"""``pulsar-config register-with-galaxy`` orchestration.

A user runs ``pulsar-config register-with-galaxy --galaxy <url> --token <one-shot>
--relay <url>`` on the host that will run the Pulsar daemon. This module:

1. Drives the relay's RFC 8628 device flow with ``pair=true`` so the relay
   issues *two* independent refresh tokens for the freshly-signed-in user.
2. Decodes the ``sub`` claim out of the access token — that's the relay user
   id, which we adopt as the BYOC manager name (and as the Pulsar manager
   name in the local ``app.yml``).
3. Posts the secondary refresh token to Galaxy at
   ``/api/compute_resources/registrations/complete`` (authenticated by the
   one-shot token from ``POST /api/compute_resources/registrations``).
4. Writes the local ``relay_credentials.json`` with the *primary* refresh
   token only; the secondary is in-flight to Galaxy and never persisted on
   the host.

Network calls go through ``requests``; the device-flow / credentials-file
plumbing is reused from :mod:`pulsar_relay_client.device_flow`.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from typing import Optional

import requests


log = logging.getLogger(__name__)


class GalaxyBYOCRegistrationError(Exception):
    """Top-level error for ``register-with-galaxy`` failures."""


def _decode_jwt_sub(access_token: str) -> Optional[str]:
    """Extract the ``sub`` claim from a JWT without verifying its signature.

    The relay validated the token before issuing it; we only need the claim.
    Avoids a hard dep on PyJWT — base64-decoding the middle segment is enough.
    """
    try:
        _, payload_b64, _ = access_token.split(".")
    except ValueError:
        return None
    # JWTs use unpadded URL-safe base64.
    padding = "=" * (-len(payload_b64) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
    except (ValueError, json.JSONDecodeError):
        return None
    sub = payload.get("sub")
    return str(sub) if sub is not None else None


def register_with_galaxy(
    *,
    galaxy_url: str,
    bootstrap_token: str,
    relay_url: str,
    credentials_path: str,
    client_hint: Optional[str] = None,
    timeout: int = 30,
) -> dict:
    """Run the full bootstrap. Returns ``{relay_url, manager_name}``.

    Side effects:
      * Writes the primary refresh token to ``credentials_path``.
      * Calls Galaxy's ``POST /api/compute_resources/registrations/complete``
        with the secondary.
    """
    # Imported lazily so pulsar still installs on Pythons that don't meet
    # pulsar-relay-client's requires-python.
    from pulsar_relay_client import (
        CredentialsFile,
        DeviceFlowError,
        RelayDeviceFlowAuthenticator,
    )

    cred_file = CredentialsFile(credentials_path)
    flow = RelayDeviceFlowAuthenticator(
        relay_url=relay_url,
        credentials_file=cred_file,
        client_hint=client_hint or f"pulsar-config-byoc on {os.uname().nodename}",
        pair=True,
    )
    try:
        outcome = flow.run()
    except DeviceFlowError as exc:
        raise GalaxyBYOCRegistrationError(f"device-flow login failed: {exc}") from exc

    secondary = outcome.get("refresh_token_secondary")
    if not secondary:
        raise GalaxyBYOCRegistrationError(
            "Relay did not return refresh_token_secondary — does it support pair-issuance?"
        )
    manager_name = _decode_jwt_sub(outcome["access_token"])
    if not manager_name:
        raise GalaxyBYOCRegistrationError(
            "Could not decode 'sub' claim from relay access token; refusing to register."
        )

    payload = {
        "bootstrap_token": bootstrap_token,
        "refresh_token": secondary,
        "relay_url": relay_url,
        "manager_name": manager_name,
    }
    bootstrap_url = galaxy_url.rstrip("/") + "/api/compute_resources/registrations/complete"
    try:
        resp = requests.post(bootstrap_url, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise GalaxyBYOCRegistrationError(
            f"Galaxy bootstrap POST failed (network): {exc}"
        ) from exc
    if resp.status_code >= 400:
        raise GalaxyBYOCRegistrationError(
            f"Galaxy bootstrap POST returned HTTP {resp.status_code}: {resp.text}"
        )

    log.info(
        "Registered BYOC resource with Galaxy at %s as manager %r", galaxy_url, manager_name
    )
    return {"relay_url": relay_url, "manager_name": manager_name}


__all__ = [
    "register_with_galaxy",
    "GalaxyBYOCRegistrationError",
]
