"""``pulsar-config register-with-galaxy`` orchestration.

A user runs ``pulsar-config register-with-galaxy --galaxy <url> --token <one-shot>
--relay <url>`` on the host that will run the Pulsar daemon. This module:

1. Drives the relay's RFC 8628 device flow with ``pair=true`` so the relay
   issues *two* independent refresh tokens for the freshly-signed-in user.
2. Posts the secondary refresh token to Galaxy at
   ``/api/compute_resources/registrations/complete`` (authenticated by the
   one-shot token from ``POST /api/compute_resources/registrations``).
   Galaxy mints the authoritative manager name and returns it; that is the
   only name Pulsar may bind to in the local ``app.yml``, so a response
   without one is a hard error rather than something to guess around.
3. Writes the local ``relay_credentials.json`` with the *primary* refresh
   token only; the secondary is in-flight to Galaxy and never persisted on
   the host.

Network calls go through ``requests``; the device-flow / credentials-file
plumbing is reused from :mod:`pulsar_relay_client.device_flow`.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

log = logging.getLogger(__name__)


class GalaxyBYOCRegistrationError(Exception):
    """Top-level error for ``register-with-galaxy`` failures."""


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
    payload = {
        "bootstrap_token": bootstrap_token,
        "refresh_token": secondary,
        "relay_url": relay_url,
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

    # Galaxy mints its own manager name and returns it; Pulsar must listen on
    # that name or jobs are never picked up. There is no name we could guess
    # instead, so a response we cannot read a name out of fails the whole
    # registration rather than writing an app.yml that silently never works.
    try:
        body = resp.json()
    except ValueError:
        raise GalaxyBYOCRegistrationError(
            f"Galaxy bootstrap response was not JSON: {resp.text}"
        ) from None
    manager_name = body.get("manager_name") if isinstance(body, dict) else None
    if not manager_name:
        raise GalaxyBYOCRegistrationError(
            "Galaxy did not return a manager_name; refusing to write app.yml "
            "with a guessed name."
        )

    log.info(
        "Registered BYOC resource with Galaxy at %s as manager %r", galaxy_url, manager_name
    )
    return {"relay_url": relay_url, "manager_name": manager_name}


__all__ = [
    "GalaxyBYOCRegistrationError",
    "register_with_galaxy",
]
