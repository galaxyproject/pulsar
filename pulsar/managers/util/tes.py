from typing import (
    Any,
    Dict,
    Optional,
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


def tes_galaxy_instance_id(destination_params: Dict[str, Any]) -> Optional[str]:
    return destination_params.get("galaxy_instance_id") or destination_params.get("tes_galaxy_instance_id")


__all__ = (
    "ensure_tes_client",
    "TesClient",
    "TesExecutor",
    "TesResources",
    "TesState",
    "TesTask",
)
