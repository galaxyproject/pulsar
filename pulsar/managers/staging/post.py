"""
"""
import os

from pulsar.client import action_mapper
from pulsar.client import staging
from pulsar.client.staging import PulsarOutputs
from pulsar.client.staging.down import ResultsCollector

import logging
log = logging.getLogger(__name__)


def postprocess(job_directory, action_executor):
    # Returns True if outputs were collected.
    try:
        if job_directory.has_metadata("launch_config"):
            staging_config = job_directory.load_metadata("launch_config").get("remote_staging", None)
        elif job_directory.has_metadata("staging_config"):
            # This branch of the if is for Pulsar servers that have created jobs prior to
            # #164 but are postprocessing after the inclusion of #164 (upgraded in the middle).
            # This can be eliminated sometime - say in 2019 or whenever there is a breaking
            # change in some other way.
            staging_config = job_directory.load_metadata("staging_config", None)
        else:
            staging_config = None
        collected = __collect_outputs(job_directory, staging_config, action_executor)
        return collected
    finally:
        job_directory.write_file("postprocessed", "")
    return False


def __collect_outputs(job_directory, staging_config, action_executor):
    collected = True
    if "action_mapper" in staging_config:
        file_action_mapper = action_mapper.FileActionMapper(config=staging_config["action_mapper"])
        client_outputs = staging.ClientOutputs.from_dict(staging_config["client_outputs"])
        pulsar_outputs = __pulsar_outputs(job_directory)
        output_collector = PulsarServerOutputCollector(job_directory, action_executor)
        results_collector = ResultsCollector(output_collector, file_action_mapper, client_outputs, pulsar_outputs)
        collection_failure_exceptions = results_collector.collect()
        if collection_failure_exceptions:
            log.warn("Failures collecting results %s" % collection_failure_exceptions)
            collected = False
    return collected


class PulsarServerOutputCollector(object):

    def __init__(self, job_directory, action_executor):
        self.job_directory = job_directory
        self.action_executor = action_executor

    def collect_output(self, results_collector, output_type, action, name):
        # Not using input path, this is because action knows it path
        # in this context.
        if action.staging_action_local:
            return  # Galaxy (client) will collect output.

        if not name:
            # TODO: Would not work on Windows. Any use in allowing
            # remote_transfer action for Windows?
            name = os.path.basename(action.path)

        pulsar_path = self.job_directory.calculate_path(name, output_type)
        description = "staging out file %s via %s" % (pulsar_path, action)
        self.action_executor.execute(lambda: action.write_from_path(pulsar_path), description)


def __pulsar_outputs(job_directory):
    working_directory_contents = job_directory.working_directory_contents()
    output_directory_contents = job_directory.outputs_directory_contents()
    metadata_directory_contents = job_directory.metadata_directory_contents()
    return PulsarOutputs(
        working_directory_contents,
        output_directory_contents,
        metadata_directory_contents,
    )


__all__ = ('postprocess',)
