"""Record how much work Pulsar did staging a job's files.

Galaxy's ``pulsar_transfer`` job metrics plugin reads what this writes - see
``galaxy.job_metrics.instrumenters.pulsar_transfer``, which documents the file's contents.
The name follows the instrumentation convention shared with that package, which is also what
gets the file staged back to Galaxy alongside the metrics the job script itself produced.

The file is written whether or not Galaxy has the plugin enabled; Pulsar has no way of
knowing, and it is one small file per job.
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
        """Count a file that has just been staged.

        A file whose size cannot be read still counts toward ``files`` - the transfer
        happened, and undercounting transfers would mislead more than undercounting bytes.
        """
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
    """Time a staging phase and write what it moved where Galaxy will collect it.

    Writing never raises - a job whose files all arrived must not fail because its metrics
    did not. The file is written even when the phase raised part way through, so a failed
    staging attempt still reports how far it got.
    """
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
