"""Record file staging metrics for Galaxy's ``pulsar_transfer`` plugin."""

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

if TYPE_CHECKING:
    from pulsar.managers.base import JobDirectory

log = logging.getLogger(__name__)

PLUGIN_TYPE = "pulsar_transfer"
PREPROCESS = "preprocess"
POSTPROCESS = "postprocess"


def transfer_metrics_file_name(phase: str) -> str:
    """Name Galaxy's ``pulsar_transfer`` plugin looks for this phase's metrics under."""
    return f"{INSTRUMENT_FILE_PREFIX}_{PLUGIN_TYPE}_{phase}"


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
        try:
            path = job_directory.calculate_path(
                transfer_metrics_file_name(phase), "metadata"
            )
            with open(path, "w") as fh:
                json.dump(metrics.to_dict(), fh)
        except Exception:
            log.warning(
                "Failed to record Pulsar %s transfer metrics", phase, exc_info=True
            )


__all__ = (
    "POSTPROCESS",
    "PREPROCESS",
    "TransferMetrics",
    "record_transfer",
    "transfer_metrics_file_name",
)
