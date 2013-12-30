from os.path import join
from os.path import relpath
from re import compile
from contextlib import contextmanager

from ..staging import COMMAND_VERSION_FILENAME
from ..action_mapper import FileActionMapper

from logging import getLogger
log = getLogger(__name__)

# All output files marked with from_work_dir attributes will copied or downloaded
# this pattern picks up attiditional files to copy back - such as those
# associated with multiple outputs and metadata configuration. Set to .* to just
# copy everything
COPY_FROM_WORKING_DIRECTORY_PATTERN = compile(r"primary_.*|galaxy.json|metadata_.*|dataset_.*_files.+")


def finish_job(client, cleanup_job, job_completed_normally, galaxy_outputs, lwr_outputs):
    """
    """
    download_failure_exceptions = []
    if job_completed_normally:
        download_failure_exceptions = __download_results(client, galaxy_outputs, lwr_outputs)
    return __clean(download_failure_exceptions, cleanup_job, client)


def __download_results(client, galaxy_outputs, lwr_outputs):
    action_mapper = FileActionMapper(client)
    downloaded_working_directory_files = []
    exception_tracker = DownloadExceptionTracker()
    working_directory = galaxy_outputs.working_directory
    output_files = galaxy_outputs.output_files
    working_directory_contents = lwr_outputs.working_directory_contents or []

    # Fetch explicit working directory outputs.
    for source_file, output_file in galaxy_outputs.work_dir_outputs:
        name = relpath(source_file, working_directory)
        remote_name = lwr_outputs.path_helper.remote_name(name)
        with exception_tracker():
            action = action_mapper.action(output_file, 'output')
            client.fetch_work_dir_output(remote_name, working_directory, output_file, action_type=action.action_type)
            downloaded_working_directory_files.append(remote_name)
        # Remove from full output_files list so don't try to download directly.
        output_files.remove(output_file)

    # Legacy LWR not returning list of files, iterate over the list of
    # expected outputs for tool.
    for output_file in output_files:
        # Fetch ouptut directly...
        with exception_tracker():
            action = action_mapper.action(output_file, 'output')
            output_generated = lwr_outputs.has_output_file(output_file)
            if output_generated is None:
                client.fetch_output(output_file, check_exists_remotely=True, action_type=action.action_type)
            elif output_generated:
                client.fetch_output(output_file, action_type=action.action_type)

        for local_path, remote_name in lwr_outputs.output_extras(output_file).iteritems():
            with exception_tracker():
                action = action_mapper.action(local_path, 'output')
                client.fetch_output(path=local_path, name=remote_name, action_type=action.action_type)
        # else not output generated, do not attempt download.

    version_file = galaxy_outputs.version_file
    if version_file and COMMAND_VERSION_FILENAME in lwr_outputs.output_directory_contents:
        action = action_mapper.action(output_file, 'version')
        client.fetch_output(path=version_file, name=COMMAND_VERSION_FILENAME, action_type=action.action_type)

    # Fetch remaining working directory outputs of interest.
    for name in working_directory_contents:
        if name in downloaded_working_directory_files:
            continue
        if COPY_FROM_WORKING_DIRECTORY_PATTERN.match(name):
            with exception_tracker():
                output_file = join(working_directory, lwr_outputs.path_helper.local_name(name))
                action = action_mapper.action(output_file, 'output')
                client.fetch_work_dir_output(name, working_directory, output_file, action_type=action.action_type)
                downloaded_working_directory_files.append(name)

    return exception_tracker.download_failure_exceptions


class DownloadExceptionTracker(object):

    def __init__(self):
        self.download_failure_exceptions = []

    @contextmanager
    def __call__(self):
        try:
            yield
        except Exception as e:
            self.download_failure_exceptions.append(e)


def __clean(download_failure_exceptions, cleanup_job, client):
    failed = (len(download_failure_exceptions) > 0)
    if (not failed and cleanup_job != "never") or cleanup_job == "always":
        try:
            client.clean()
        except:
            log.warn("Failed to cleanup remote LWR job")
    return failed
