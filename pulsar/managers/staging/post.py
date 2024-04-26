"""
"""
import logging
import os

from pulsar.client import (
    action_mapper,
    staging,
)
from pulsar.client.staging import PulsarOutputs
from pulsar.client.staging.down import ResultsCollector

log = logging.getLogger(__name__)


def postprocess(job_directory, action_executor, was_cancelled):
    # Returns True if outputs were collected.
    try:
        if job_directory.has_metadata("launch_config"):
            staging_config = job_directory.load_metadata("launch_config").get("remote_staging", None)
        else:
            staging_config = None
        collected = __collect_outputs(job_directory, staging_config, action_executor, was_cancelled)
        return collected
    finally:
        job_directory.write_file("postprocessed", "")
    return False


def __collect_outputs(job_directory, staging_config, action_executor, was_cancelled):
    collected = True
    if "action_mapper" in staging_config:
        file_action_mapper = action_mapper.FileActionMapper(config=staging_config["action_mapper"])
        client_outputs = staging.ClientOutputs.from_dict(staging_config["client_outputs"])
        pulsar_outputs = __pulsar_outputs(job_directory)
        output_collector = PulsarServerOutputCollector(job_directory, action_executor, was_cancelled)
        results_collector = ResultsCollector(output_collector, file_action_mapper, client_outputs, pulsar_outputs)
        collection_failure_exceptions = results_collector.collect()
        if collection_failure_exceptions:
            log.warn("Failures collecting results %s" % collection_failure_exceptions)
            collected = False
    return collected


def realized_dynamic_file_sources(job_directory):
    launch_config = job_directory.load_metadata("launch_config")
    if launch_config is None:
        log.warning(f"Failed to load launch_config from: {job_directory.job_directory}")
        return []
    dynamic_file_sources = launch_config.get("dynamic_file_sources")
    realized_dynamic_file_sources = []
    for dynamic_file_source in (dynamic_file_sources or []):
        dynamic_file_source_path = dynamic_file_source["path"]
        realized_dynamic_file_source = dynamic_file_source.copy()
        dynamic_file_source_bytes = job_directory.working_directory_file_contents(dynamic_file_source_path)
        if dynamic_file_source_bytes is not None:
            dynamic_file_source_contents = dynamic_file_source_bytes.decode("utf-8")
            realized_dynamic_file_source["contents"] = dynamic_file_source_contents
            realized_dynamic_file_sources.append(realized_dynamic_file_source)
    return realized_dynamic_file_sources


class PulsarServerOutputCollector:

    def __init__(self, job_directory, action_executor, was_cancelled):
        self.job_directory = job_directory
        self.action_executor = action_executor
        self.was_cancelled = was_cancelled

    def collect_output(self, results_collector, output_type, action, name):
        def action_if_not_cancelled():
            if self.was_cancelled():
                log.info(f"Skipped output collection '{name}', job is cancelled")
                return
            action.write_from_path(pulsar_path)
        # Not using input path, this is because action knows it path
        # in this context.
        if action.staging_action_local:
            return  # Galaxy (client) will collect output.

        if not name:
            # TODO: Would not work on Windows. Any use in allowing
            # remote_transfer action for Windows?
            name = os.path.basename(action.path)

        pulsar_path = self.job_directory.calculate_path(name, output_type)
        description = "staging out file {} via {}".format(pulsar_path, action)
        self.action_executor.execute(action_if_not_cancelled, description)


def __pulsar_outputs(job_directory):
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


__all__ = ('postprocess', 'realized_dynamic_file_sources')
