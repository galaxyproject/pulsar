"""
"""

import errno
import logging
import os
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    TYPE_CHECKING,
)

from pulsar.client import action_mapper
from pulsar.client.staging.down import ResultsCollector
from pulsar.client.staging.models import (
    ClientOutputs,
    PulsarOutputs,
)
from pulsar.client.util import (
    DEFAULT_OUTPUT_COLLECTION_RETRIES,
    retry_missing_source,
)
from pulsar.managers.util.retry import RetryActionExecutor
from .metrics import (
    POSTPROCESS,
    record_transfer,
    transfer_metrics_file_name,
    TransferMetrics,
)

if TYPE_CHECKING:
    from pulsar.managers.base import JobDirectory

log = logging.getLogger(__name__)


def postprocess(
    job_directory: "JobDirectory",
    action_executor: "RetryActionExecutor",
    was_cancelled: Callable[[], Optional[bool]],
    output_collection_retries: int = DEFAULT_OUTPUT_COLLECTION_RETRIES,
) -> bool:
    # Returns True if outputs were collected.
    if job_directory.has_metadata("launch_config"):
        staging_config = (
            job_directory.load_metadata("launch_config").get("remote_staging") or {}
        )
    else:
        staging_config = {}
    return __collect_outputs(
        job_directory, staging_config, action_executor, was_cancelled, output_collection_retries
    )


def __collect_outputs(
    job_directory: "JobDirectory",
    staging_config: Dict[str, Any],
    action_executor: "RetryActionExecutor",
    was_cancelled,
    output_collection_retries: int,
) -> bool:
    collected = True
    if "action_mapper" in staging_config:
        file_action_mapper = action_mapper.FileActionMapper(
            config=staging_config["action_mapper"]
        )
        client_outputs = ClientOutputs.from_dict(
            staging_config["client_outputs"]
        )
        pulsar_outputs = __pulsar_outputs(job_directory)
        with record_transfer(job_directory, POSTPROCESS) as metrics:
            output_collector = PulsarServerOutputCollector(
                job_directory, action_executor, was_cancelled, metrics, output_collection_retries
            )
            results_collector = ResultsCollector(
                output_collector, file_action_mapper, client_outputs, pulsar_outputs
            )
            collection_failure_exceptions = list(results_collector.collect())
        __stage_out_transfer_metrics(
            job_directory, file_action_mapper, client_outputs, was_cancelled
        )
        if collection_failure_exceptions:
            log.warning("Failures collecting results %s" % collection_failure_exceptions)
            collected = False
    return collected


def __stage_out_transfer_metrics(
    job_directory: "JobDirectory",
    file_action_mapper: "action_mapper.FileActionMapper",
    client_outputs: ClientOutputs,
    was_cancelled,
) -> None:
    """Stage out metrics recorded after output collection, on a best effort basis.

    This push ignores the client's dynamic output patterns, so the postprocess file reaches
    Galaxy even with extended metadata, whose patterns leave every other ``__instrument_*``
    file - preprocess metrics included - on the Pulsar side.
    """
    metadata_directory = client_outputs.metadata_directory
    if not metadata_directory:
        return
    name = transfer_metrics_file_name(POSTPROCESS)
    try:
        action = file_action_mapper.action(
            {"path": os.path.join(metadata_directory, name)}, "output_metadata"
        )
        if action.staging_action_local:
            # Galaxy pulls the metadata directory itself, and this file is in it by now.
            return
        # No retries: the job's own retry budget must not hold up its terminal state for metrics.
        collector = PulsarServerOutputCollector(
            job_directory, RetryActionExecutor(), was_cancelled, output_collection_retries=0
        )
        collector.collect_output(None, "output_metadata", action, name)
    except Exception:
        log.warning("Failed to stage out Pulsar transfer metrics", exc_info=True)


def realized_dynamic_file_sources(
    job_directory: "JobDirectory",
) -> List[Dict[str, str]]:
    launch_config = job_directory.load_metadata("launch_config")
    if launch_config is None:
        log.warning(f"Failed to load launch_config from: {job_directory.job_directory}")
        return []
    dynamic_file_sources = launch_config.get("dynamic_file_sources")
    realized_dynamic_file_sources = []
    for dynamic_file_source in dynamic_file_sources or []:
        dynamic_file_source_path = dynamic_file_source["path"]
        realized_dynamic_file_source = dynamic_file_source.copy()
        dynamic_file_source_bytes = job_directory.working_directory_file_contents(
            dynamic_file_source_path
        )
        if dynamic_file_source_bytes is not None:
            dynamic_file_source_contents = dynamic_file_source_bytes.decode("utf-8")
            realized_dynamic_file_source["contents"] = dynamic_file_source_contents
            realized_dynamic_file_sources.append(realized_dynamic_file_source)
    return realized_dynamic_file_sources


class PulsarServerOutputCollector:

    def __init__(
        self,
        job_directory: "JobDirectory",
        action_executor: "RetryActionExecutor",
        was_cancelled: Callable[[], Optional[bool]],
        metrics: Optional[TransferMetrics] = None,
        output_collection_retries: int = DEFAULT_OUTPUT_COLLECTION_RETRIES,
    ):
        self.job_directory = job_directory
        self.action_executor = action_executor
        self.was_cancelled = was_cancelled
        self.metrics = metrics
        self.output_collection_retries = output_collection_retries

    def collect_output(self, results_collector, output_type, action, name):
        def action_if_not_cancelled():
            if self.was_cancelled():
                log.info(f"Skipped output collection '{name}', job is cancelled")
                return False
            action.write_from_path(pulsar_path)
            return True

        # Not using input path, this is because action knows it path
        # in this context.
        if action.staging_action_local:
            return  # Galaxy (client) will collect output.

        if not name:
            # TODO: Would not work on Windows. Any use in allowing
            # remote_transfer action for Windows?
            name = os.path.basename(action.path)

        pulsar_path = self.job_directory.calculate_path(name, output_type)
        if action.staging_needed:
            # A missing output is not transient: the tool did not write it, or was killed
            # first. Retrying it with the executor's backoff only delays the job's terminal
            # state while it holds a postprocess slot, so check here instead, giving NFS a
            # few short revalidations to show a file the compute node just wrote. A job
            # cancelled meanwhile stops the checks, and the executor then skips the output.
            def require_output_unless_cancelled():
                if not self.was_cancelled():
                    _require_output_file(pulsar_path)

            retry_missing_source(require_output_unless_cancelled, pulsar_path, self.output_collection_retries)
        description = f"staging out file {pulsar_path} via {action}"
        transferred = self.action_executor.execute(action_if_not_cancelled, description)
        if self.metrics is not None and action.staging_needed and transferred:
            self.metrics.record_file(pulsar_path)


def _require_output_file(path: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(errno.ENOENT, "Output file does not exist", path)


def __pulsar_outputs(job_directory: "JobDirectory") -> PulsarOutputs:
    working_directory_contents = job_directory.working_directory_contents()
    output_directory_contents = job_directory.outputs_directory_contents()
    metadata_directory_contents = job_directory.metadata_directory_contents()
    job_directory_contents = job_directory.job_directory_contents()
    return PulsarOutputs(
        working_directory_contents,
        output_directory_contents,
        metadata_directory_contents,
        job_directory_contents,
        realized_dynamic_file_sources=realized_dynamic_file_sources(job_directory),
    )


__all__ = ("postprocess", "realized_dynamic_file_sources")
