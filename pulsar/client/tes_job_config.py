"""Configuration and resource objects for GA4GH TES jobs."""

import base64
from typing import Optional

from galaxy.util import listify
from pydantic import (
    BaseModel,
    Field,
)
from pydantictes.models import TesResources
from typing_extensions import Literal

from pulsar.managers.util.tes import TesClient


class BasicAuth(BaseModel):
    username: str = Field(..., description="Username for basic authentication.")
    password: str = Field(..., description="Password for basic authentication.")


class TesJobParams(TesResources):
    tes_url: str = Field(..., description="URL of the TES service.")
    # Literal comes from typing_extensions, which backports it to 3.7.
    authorization: Literal["none", "basic"] = Field(  # novermin
        "none", description="Authorization type for TES service."
    )
    basic_auth: Optional[BasicAuth] = Field(None, description="Authorization for TES service.")


def parse_tes_job_params(params: dict) -> TesJobParams:
    """
    Parse GCP job parameters parameters from a dictionary (e.g., Galaxy's job destination/environment params).
    """
    legacy_style_keys = {
        "tes_cpu_cores": "cpu_cores",
        "tes_preemptible": "preemptible",
        "tes_ram_gb": "ram_gb",
        "tes_disk_gb": "disk_gb",
        "tes_zones": "zones",
        "tes_backend_parameters": "backend_parameters",
        "tes_backend_parameters_strict": "backend_parameters_strict",
        "tes_galaxy_instance_id": "galaxy_instance_id",
    }
    expanded_params = {}
    for key, value in params.items():
        if key in legacy_style_keys:
            new_key = legacy_style_keys[key]
            expanded_params[new_key] = value
        else:
            expanded_params[key] = value

    if "zones" in expanded_params:
        expanded_params["zones"] = listify(expanded_params["zones"])

    return TesJobParams(**expanded_params)


def tes_client_from_params(tes_params: TesJobParams) -> TesClient:
    tes_url = tes_params.tes_url
    assert tes_url
    auth_type = tes_params.authorization  # Default to "none"

    headers = {}

    if auth_type == "basic":
        basic_auth = tes_params.basic_auth
        username = basic_auth.username if basic_auth else None
        password = basic_auth.password if basic_auth else None
        if username and password:
            auth_string = f"{username}:{password}"
            auth_base64 = base64.b64encode(auth_string.encode()).decode()
            headers["Authorization"] = f"Basic {auth_base64}"

    return TesClient(url=tes_url, headers=headers)


def tes_resources(tes_params: TesJobParams) -> TesResources:
    # TesJobParams subclasses it so just pass through as is.
    return tes_params
