"""Public client APIs, loaded on access for compatibility.

Implementation modules can also be imported directly. Keeping this package
lightweight allows staging constants to be used without client dependencies.
"""

import warnings
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .coexecution_manager import build_client_manager
    from .destination import url_to_destination_params
    from .exceptions import (
        OutputNotFoundException,
        PulsarClientTransportError,
    )
    from .path_mapper import PathMapper
    from .staging import EXTENDED_METADATA_DYNAMIC_COLLECTION_PATTERN
    from .staging.down import finish_job
    from .staging.inputs import (
        CLIENT_INPUT_PATH_TYPES,
        ClientInput,
        ClientInputs,
    )
    from .staging.models import (
        ClientJobDescription,
        ClientOutputs,
        PulsarOutputs,
    )
    from .staging.up import submit_job


_EXPORTS = {
    'CLIENT_INPUT_PATH_TYPES': '.staging.inputs',
    'EXTENDED_METADATA_DYNAMIC_COLLECTION_PATTERN': '.staging',
    'ClientInput': '.staging.inputs',
    'ClientInputs': '.staging.inputs',
    'ClientJobDescription': '.staging.models',
    'ClientOutputs': '.staging.models',
    'OutputNotFoundException': '.exceptions',
    'PathMapper': '.path_mapper',
    'PulsarClientTransportError': '.exceptions',
    'PulsarOutputs': '.staging.models',
    'build_client_manager': '.coexecution_manager',
    'finish_job': '.staging.down',
    'submit_job': '.staging.up',
    'url_to_destination_params': '.destination',
}

__all__ = [
    'CLIENT_INPUT_PATH_TYPES',
    'EXTENDED_METADATA_DYNAMIC_COLLECTION_PATTERN',
    'ClientInput',
    'ClientInputs',
    'ClientJobDescription',
    'ClientOutputs',
    'OutputNotFoundException',
    'PathMapper',
    'PulsarClientTransportError',
    'PulsarOutputs',
    'build_client_manager',
    'finish_job',
    'submit_job',
    'url_to_destination_params',
]


def __getattr__(name):
    """Load client entry points only when they are requested."""
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
