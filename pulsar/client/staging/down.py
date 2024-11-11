"""Code run on the client side for unstaging complete Pulsar jobs."""
import fnmatch
from contextlib import contextmanager
from json import loads
from logging import getLogger
from os.path import (
    join,
    relpath,
)

from ..action_mapper import FileActionMapper
from ..staging import COMMAND_VERSION_FILENAME

log = getLogger(__name__)


def finish_job(client, cleanup_job, job_completed_normally, client_outputs, pulsar_outputs):
    """Process for "un-staging" a complete Pulsar job.

    This function is responsible for downloading results from remote
    server and cleaning up Pulsar staging directory (if needed.)
    """
    collection_failure_exceptions = []
    if job_completed_normally:
        output_collector = ClientOutputCollector(client)
        action_mapper = FileActionMapper(client)
        results_stager = ResultsCollector(output_collector, action_mapper, client_outputs, pulsar_outputs)
        collection_failure_exceptions = results_stager.collect()
    _clean(collection_failure_exceptions, cleanup_job, client)
    return collection_failure_exceptions


class ClientOutputCollector:

    def __init__(self, client):
        self.client = client

    def collect_output(self, results_collector, output_type, action, name):
        # This output should have been handled by the Pulsar.
        if not action.staging_action_local:
            return False

        working_directory = results_collector.client_outputs.working_directory
        self.client.fetch_output(
            path=action.path,
            name=name,
            working_directory=working_directory,
            output_type=output_type,
            action_type=action.action_type
        )
        return True


class ResultsCollector:

    def __init__(self, output_collector, action_mapper, client_outputs, pulsar_outputs):
        self.output_collector = output_collector
        self.action_mapper = action_mapper
        self.client_outputs = client_outputs
        self.pulsar_outputs = pulsar_outputs
        self.downloaded_working_directory_files = []
        self.exception_tracker = DownloadExceptionTracker()
        self.output_files = client_outputs.output_files
        self.working_directory_contents = pulsar_outputs.working_directory_contents or []
        self.metadata_directory_contents = pulsar_outputs.metadata_directory_contents or []
        self.job_directory_contents = pulsar_outputs.job_directory_contents or []

    def collect(self):
        self.__collect_working_directory_outputs()
        self.__collect_outputs()
        self.__collect_version_file()
        self.__collect_other_working_directory_files()
        self.__collect_metadata_directory_files()
        self.__collect_job_directory_files()
        # Give actions that require a final action, like those that write a manifest, to write out their content
        self.__finalize_action_mapper()
        # finalize collection here for executors that need this ?
        return self.exception_tracker.collection_failure_exceptions

    def __collect_working_directory_outputs(self):
        working_directory = self.client_outputs.working_directory
        # Fetch explicit working directory outputs.
        for source_file, output_file in self.client_outputs.work_dir_outputs:
            name = relpath(source_file, working_directory)
            if name not in self.working_directory_contents:
                # Could be a glob
                matching = fnmatch.filter(self.working_directory_contents, name)
                if matching:
                    name = matching[0]
                    source_file = join(working_directory, name)
            pulsar = self.pulsar_outputs.path_helper.remote_name(name)
            if self._attempt_collect_output('output_workdir', path=output_file, name=pulsar):
                self.downloaded_working_directory_files.append(pulsar)
            # Remove from full output_files list so don't try to download directly.
            try:
                self.output_files.remove(output_file)
            except ValueError:
                raise Exception("Failed to remove {} from {}".format(output_file, self.output_files))

    def __collect_outputs(self):
        # Legacy Pulsar not returning list of files, iterate over the list of
        # expected outputs for tool.
        for output_file in self.output_files:
            # Fetch output directly...
            output_generated = self.pulsar_outputs.has_output_file(output_file)
            if output_generated:
                self._attempt_collect_output('output', output_file)

            for galaxy_path, pulsar in self.pulsar_outputs.output_extras(output_file).items():
                self._attempt_collect_output('output', path=galaxy_path, name=pulsar)
            # else not output generated, do not attempt download.

    def __collect_version_file(self):
        version_file = self.client_outputs.version_file
        pulsar_output_directory_contents = self.pulsar_outputs.output_directory_contents
        if version_file and COMMAND_VERSION_FILENAME in pulsar_output_directory_contents:
            self._attempt_collect_output('output', version_file, name=COMMAND_VERSION_FILENAME)

    def __collect_other_working_directory_files(self):
        self.__collect_directory_files(
            self.client_outputs.working_directory,
            self.working_directory_contents,
            'output_workdir',
        )

    def __collect_metadata_directory_files(self):
        self.__collect_directory_files(
            self.client_outputs.metadata_directory,
            self.metadata_directory_contents,
            'output_metadata',
        )

    def __collect_job_directory_files(self):
        self.__collect_directory_files(
            self.client_outputs.job_directory,
            self.job_directory_contents,
            'output_jobdir',
        )

    def __finalize_action_mapper(self):
        self.action_mapper.finalize()

    def __realized_dynamic_file_source_references(self):
        references = {"filename": [], "extra_files": []}

        def record_references(from_dict):
            if isinstance(from_dict, list):
                for v in from_dict:
                    record_references(v)
            elif isinstance(from_dict, dict):
                for k, v in from_dict.items():
                    if k in references:
                        references[k].append(v)
                    if isinstance(v, (list, dict)):
                        record_references(v)

        def parse_and_record_references(json_content):
            try:
                as_dict = loads(json_content)
                record_references(as_dict)
            except Exception as e:
                log.warning("problem parsing galaxy.json %s" % e)
                pass

        realized_dynamic_file_sources = (self.pulsar_outputs.realized_dynamic_file_sources or [])
        for realized_dynamic_file_source in realized_dynamic_file_sources:
            contents = realized_dynamic_file_source["contents"]
            source_type = realized_dynamic_file_source["type"]
            assert source_type in ["galaxy", "legacy_galaxy"], source_type
            if source_type == "galaxy":
                parse_and_record_references(contents)
            else:
                for line in contents.splitlines():
                    parse_and_record_references(line)

        return references

    def __collect_directory_files(self, directory, contents, output_type):
        if directory is None:  # e.g. output_metadata_directory
            return

        dynamic_file_source_references = self.__realized_dynamic_file_source_references()

        # Fetch remaining working directory outputs of interest.
        for name in contents:
            collect = False
            if name in self.downloaded_working_directory_files:
                continue
            if self.client_outputs.dynamic_match(name):
                collect = True
            elif name in dynamic_file_source_references["filename"] or any(name.startswith(r) for r in dynamic_file_source_references["extra_files"]):
                collect = True

            if collect:
                log.debug("collecting dynamic {} file {}".format(output_type, name))
                output_file = join(directory, self.pulsar_outputs.path_helper.local_name(name))
                if self._attempt_collect_output(output_type=output_type, path=output_file, name=name):
                    self.downloaded_working_directory_files.append(name)

    def _attempt_collect_output(self, output_type, path, name=None):
        # path is final path on galaxy server (client)
        # name is the 'name' of the file on the Pulsar server (possible a relative)
        # path.
        collected = False
        with self.exception_tracker():
            action = self.action_mapper.action({"path": path}, output_type)
            if self._collect_output(output_type, action, name):
                collected = True

        return collected

    def _collect_output(self, output_type, action, name):
        log.info("collecting output {} with action {}".format(name, action))
        try:
            return self.output_collector.collect_output(self, output_type, action, name)
        except Exception as e:
            if _allow_collect_failure(output_type):
                log.warning(
                    "Allowed failure in postprocessing, will not force job failure but generally indicates a tool"
                    f" failure: {e}")
            else:
                raise


class DownloadExceptionTracker:

    def __init__(self):
        self.collection_failure_exceptions = []

    @contextmanager
    def __call__(self):
        try:
            yield
        except Exception as e:
            self.collection_failure_exceptions.append(e)


def _clean(collection_failure_exceptions, cleanup_job, client):
    failed = (len(collection_failure_exceptions) > 0)
    do_clean = (not failed and cleanup_job != "never") or cleanup_job == "always"
    if do_clean:
        message = "Cleaning up job (failed [%s], cleanup_job [%s])"
    else:
        message = "Skipping job cleanup (failed [%s], cleanup_job [%s])"
    log.debug(message % (failed, cleanup_job))
    if do_clean:
        try:
            client.clean()
        except Exception:
            log.warn("Failed to cleanup remote Pulsar job")


def _allow_collect_failure(output_type):
    return output_type in ['output_workdir']


__all__ = ('finish_job',)
