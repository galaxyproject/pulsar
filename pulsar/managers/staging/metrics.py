"""Record metrics for Galaxy's ``pulsar`` job metrics plugin.

Files land in the job's metadata directory, which is staged back to Galaxy.
"""

import json
import logging
import os
import time
from contextlib import contextmanager
from typing import (
    Any,
    Dict,
    Iterator,
    TYPE_CHECKING,
)

from galaxy.job_metrics.instrumenters import INSTRUMENT_FILE_PREFIX

from pulsar import __version__ as pulsar_version

if TYPE_CHECKING:
    from pulsar.managers.base import JobDirectory

log = logging.getLogger(__name__)

PLUGIN_TYPE = "pulsar"
PREPROCESS = "preprocess"
POSTPROCESS = "postprocess"


def metrics_file_name(name: str) -> str:
    """Name Galaxy's ``pulsar`` job metrics plugin looks for ``name`` under."""
    return f"{INSTRUMENT_FILE_PREFIX}_{PLUGIN_TYPE}_{name}"


def transfer_metrics_file_name(phase: str) -> str:
    return metrics_file_name(f"transfer_{phase}")


VERSION_METRICS_FILE_NAME = metrics_file_name("version")


def write_metrics_file(job_directory: "JobDirectory", file_name: str, metrics: Dict[str, Any]) -> None:
    """Write metrics as JSON; a failure is logged, never raised - metrics mustn't fail a job."""
    try:
        with open(job_directory.calculate_path(file_name, "metadata"), "w") as fh:
            json.dump(metrics, fh)
    except Exception:
        log.warning("Failed to record Pulsar job metrics file %s", file_name, exc_info=True)


def record_version(job_directory: "JobDirectory") -> None:
    """Record the version of the Pulsar actually running this job."""
    write_metrics_file(job_directory, VERSION_METRICS_FILE_NAME, {"version": pulsar_version})


class TransferMetrics:
    """How many files one staging phase moved, how many bytes, and how long it took."""

    def __init__(self) -> None:
        self.files = 0
        self.bytes = 0
        self.seconds = 0.0

    def record_file(self, path: str) -> None:
        """Count a staged file, even if its size cannot be read."""
        self.files += 1
        try:
            self.bytes += os.path.getsize(path)
        except OSError:
            log.debug("Could not size staged file %s, counting it with no bytes", path)

    def to_dict(self) -> Dict[str, Any]:
        return {"files": self.files, "bytes": self.bytes, "seconds": self.seconds}


@contextmanager
def record_transfer(
    job_directory: "JobDirectory", phase: str
) -> Iterator[TransferMetrics]:
    """Record a staging phase, including partial transfers on failure."""
    metrics = TransferMetrics()
    started = time.time()
    try:
        yield metrics
    finally:
        metrics.seconds = time.time() - started
        write_metrics_file(job_directory, transfer_metrics_file_name(phase), metrics.to_dict())


__all__ = (
    "POSTPROCESS",
    "PREPROCESS",
    "VERSION_METRICS_FILE_NAME",
    "TransferMetrics",
    "record_transfer",
    "record_version",
    "transfer_metrics_file_name",
)
