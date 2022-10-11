from typing import (
    Any,
    cast,
    Dict,
    List,
    Optional,
)

from galaxy.util import (
    asbool,
    listify,
)

IMPORT_MESSAGE = None
try:
    from pydantictes.api import TesClient
    from pydantictes.models import (
        TesExecutor,
        TesResources,
        TesState,
        TesTask,
    )
except ImportError as exc:
    TesClient = None  # type: ignore
    TesExecutor = None  # type: ignore
    TesResources = None  # type: ignore
    TesState = None  # type: ignore
    TesTask = None  # type: ignore
    IMPORT_MESSAGE = (
        "The Python pydantic-tes package is required to use "
        "this feature, please install it or correct the "
        "following error:\nImportError %s" % str(exc)
    )


def ensure_tes_client() -> None:
    if TesClient is None:
        assert IMPORT_MESSAGE
        raise Exception(IMPORT_MESSAGE)


def tes_client_from_dict(destination_params: Dict[str, Any]) -> TesClient:
    # TODO: implement funnel's basic auth in pydantic-tes and expose it here.
    tes_url = destination_params["tes_url"]
    return TesClient(
        url=tes_url,
    )


def tes_resources(destination_params: Dict[str, Any]) -> TesResources:
    cpu_cores: Optional[int]
    preemptible: Optional[bool]
    ram_gb: Optional[float]
    disk_gb: Optional[float]
    zones: Optional[List[str]]
    backend_parameters: Optional[Dict[str, str]] = None
    backend_parameters_strict: Optional[bool]

    raw_cpu_cores = destination_params.get("tes_cpu_cores")
    cpu_cores = int(raw_cpu_cores) if raw_cpu_cores is not None else None

    raw_preemptible = destination_params.get("tes_preemptible")
    preemptible = asbool(raw_preemptible) if raw_preemptible is not None else None

    raw_ram_gb = destination_params.get("tes_ram_gb")
    ram_gb = float(raw_ram_gb) if raw_ram_gb is not None else None

    raw_disk_gb = destination_params.get("tes_disk_gb")
    disk_gb = float(raw_disk_gb) if raw_disk_gb is not None else None

    raw_zones = destination_params.get("tes_zones")
    zones = listify(raw_zones) if raw_zones is not None else None

    raw_backend_parameters = destination_params.get("tes_backend_parameters")
    if raw_backend_parameters is not None:
        backend_parameters = {}
        for k, v in cast(dict, raw_backend_parameters).items():
            backend_parameters[str(k)] = str(v)

    raw_backend_parameters_strict = destination_params.get("tes_backend_parameters_strict")
    if raw_backend_parameters_strict is not None:
        backend_parameters_strict = asbool(raw_backend_parameters_strict)
    else:
        backend_parameters_strict = None

    return TesResources(
        cpu_cores=cpu_cores,
        preemptible=preemptible,
        ram_gb=ram_gb,
        disk_gb=disk_gb,
        zones=zones,
        backend_parameters=backend_parameters,
        backend_parameters_strict=backend_parameters_strict,
    )


def tes_galaxy_instance_id(destinaton_params: Dict[str, Any]) -> Optional[str]:
    return destinaton_params.get("tes_galaxy_instance_id")


__all__ = (
    "ensure_tes_client",
    "TesClient",
    "TesExecutor",
    "TesResources",
    "TesState",
    "TesTask",
)
