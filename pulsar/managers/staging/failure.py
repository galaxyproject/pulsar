"""Describe staging failures in words safe to show the Galaxy user whose job failed.

An exception's own text is never used: a transport error names the URL it
failed on, and a staging URL to Galaxy's job files API carries the job key.
"""

from contextlib import contextmanager
from typing import (
    Iterator,
    List,
    Optional,
    Tuple,
)

from pulsar.client.exceptions import PulsarClientTransportError
from pulsar.client.transport.transient import http_status_code


class StagingFailure(Exception):
    """A file could not be staged; ``str()`` is safe to show the user.

    The original error is chained as ``__cause__``, for Pulsar's log.
    """


def describe_transfer_error(exc: BaseException) -> str:
    """Why a transfer failed - an HTTP status, a transport error kind or the exception class."""
    status = http_status_code(exc)
    if status is not None:
        return f"HTTP {status}"
    if isinstance(exc, PulsarClientTransportError):
        # Fixed per error code, unlike ``message``, which can include the URL.
        return PulsarClientTransportError.messages.get(
            exc.code, PulsarClientTransportError.messages[PulsarClientTransportError.UNKNOWN]
        )
    return type(exc).__name__


@contextmanager
def raising_staging_failure(files: str) -> Iterator[None]:
    """Raise any error staging the job's ``files`` (inputs or outputs) as a ``StagingFailure``."""
    try:
        yield
    except StagingFailure:
        raise
    except Exception as e:
        raise StagingFailure(f"Failed to transfer job {files}: {describe_transfer_error(e)}") from e


def input_staging_failure(name: str, exc: BaseException) -> StagingFailure:
    return StagingFailure(f"Failed to transfer input '{name}': {describe_transfer_error(exc)}")


def output_staging_failure(failures: List[Tuple[Optional[str], BaseException]]) -> StagingFailure:
    """Describe the first of the outputs that could not be staged out, and count the rest."""
    name, exc = failures[0]
    subject = f"output '{name}'" if name else "outputs"
    message = f"Failed to transfer {subject}: {describe_transfer_error(exc)}"
    if len(failures) > 1:
        message += f" ({len(failures) - 1} more failed)"
    return StagingFailure(message)


__all__ = (
    "StagingFailure",
    "describe_transfer_error",
    "input_staging_failure",
    "output_staging_failure",
    "raising_staging_failure",
)
