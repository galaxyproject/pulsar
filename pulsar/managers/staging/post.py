"""
"""

import logging
import os
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    TYPE_CHECKING,
)

from pulsar.client import action_mapper
from pulsar.client.staging.down import ResultsCollector
from pulsar.client.staging.models import (
    ClientOutputs,
    PulsarOutputs,
)
from pulsar.managers.util.retry import RetryActionExecutor
from .failure import (
    output_staging_failure,
    raising_staging_failure,
)
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
) -> None:
    """Stage out the job's outputs.

    Raises ``StagingFailure``, and only that, if any output could not be staged out.
    """
    with raising_staging_failure("outputs"):
        if job_directory.has_metadata("launch_config"):
            staging_config = (
                job_directory.load_metadata("launch_config").get("remote_staging") or {}
            )
        else:
            staging_config = {}
        __collect_outputs(
            job_directory, staging_config, action_executor, was_cancelled
        )


def __collect_outputs(
    job_directory: "JobDirectory",
    staging_config: Dict[str, Any],
    action_executor: "RetryActionExecutor",
    was_cancelled,
) -> None:
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
                job_directory, action_executor, was_cancelled, metrics
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
            failures = [
                (output_collector.failed_output_name(exc), exc)
                for exc in collection_failure_exceptions
            ]
            raise output_staging_failure(failures) from collection_failure_exceptions[0]


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
            job_directory, RetryActionExecutor(), was_cancelled
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
    ):
        self.job_directory = job_directory
        self.action_executor = action_executor
        self.was_cancelled = was_cancelled
        self.metrics = metrics
        # Errors raised by transfers, with the output each was for. ``ResultsCollector``
        # decides which fail the job, so these are only looked up, never reported as is.
        self._transfer_errors: List[Tuple[str, BaseException]] = []

    def failed_output_name(self, exc: BaseException) -> Optional[str]:
        """Name of the output whose transfer raised ``exc``, if a transfer raised it."""
        for name, transfer_error in self._transfer_errors:
            if transfer_error is exc:
                return name
        return None

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
        description = f"staging out file {pulsar_path} via {action}"
        try:
            transferred = self.action_executor.execute(action_if_not_cancelled, description)
        except Exception as e:
            self._transfer_errors.append((name, e))
            raise
        if self.metrics is not None and action.staging_needed and transferred:
            self.metrics.record_file(pulsar_path)


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
