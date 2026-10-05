"""Job staging constants and lazily loaded job descriptions."""

import warnings
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .inputs import (
        CLIENT_INPUT_PATH_TYPES,
        ClientInput,
        ClientInputs,
    )
    from .models import (
        ClientJobDescription,
        ClientOutputs,
        DynamicFileSourceType,
        PulsarOutputs,
    )

COMMAND_VERSION_FILENAME = "COMMAND_VERSION"
DEFAULT_DYNAMIC_COLLECTION_PATTERN = [
    r"primary_.*|galaxy.json|metadata_.*|dataset_\d+\.dat|__instrument_.*|dataset_\d+_files.+|outputs_populated/.*|tool_stdout|tool_stderr"
]
EXTENDED_METADATA_DYNAMIC_COLLECTION_PATTERN = [
    r"outputs_populated/.*"
]

_EXPORTS = {
    'CLIENT_INPUT_PATH_TYPES': '.inputs',
    'ClientInput': '.inputs',
    'ClientInputs': '.inputs',
    'ClientJobDescription': '.models',
    'ClientOutputs': '.models',
    'DynamicFileSourceType': '.models',
    'PulsarOutputs': '.models',
}

__all__ = [
    'CLIENT_INPUT_PATH_TYPES',
    'COMMAND_VERSION_FILENAME',
    'DEFAULT_DYNAMIC_COLLECTION_PATTERN',
    'EXTENDED_METADATA_DYNAMIC_COLLECTION_PATTERN',
    'ClientInput',
    'ClientInputs',
    'ClientJobDescription',
    'ClientOutputs',
    'DynamicFileSourceType',
    'PulsarOutputs',
]


def __getattr__(name):
    """Load staging models only when they are requested."""
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(_EXPORTS[name], __name__), name)
    warnings.warn(
        f"{__name__}.{name} is deprecated; import {name} from {__name__}{_EXPORTS[name]} instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
