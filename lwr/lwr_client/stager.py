from os.path import abspath, basename, join, exists
from os.path import dirname
from os.path import relpath
from os import listdir, sep
from re import findall
from re import compile
from io import open
from contextlib import contextmanager

from .action_mapper import FileActionMapper
from .util import PathHelper
from .util import directory_files


from logging import getLogger
log = getLogger(__name__)

# All output files marked with from_work_dir attributes will copied or downloaded
# this pattern picks up attiditional files to copy back - such as those
# associated with multiple outputs and metadata configuration. Set to .* to just
# copy everything
COPY_FROM_WORKING_DIRECTORY_PATTERN = compile(r"primary_.*|galaxy.json|metadata_.*|dataset_.*_files.+")
COMMAND_VERSION_FILENAME = "COMMAND_VERSION"


class JobInputs(object):
    """
    Abstractions over dynamic inputs created for a given job (namely the command to
    execute and created configfiles).

    **Parameters**

    command_line : str
        Local command to execute for this job. (To be rewritten.)
    config_files : str
        Config files created for this job. (To be rewritten.)


    >>> import tempfile
    >>> tf = tempfile.NamedTemporaryFile()
    >>> def setup_inputs(tf):
    ...     open(tf.name, "w").write(u"world /path/to/input the rest")
    ...     inputs = JobInputs(u"hello /path/to/input", [tf.name])
    ...     return inputs
    >>> inputs = setup_inputs(tf)
    >>> inputs.rewrite_paths(u"/path/to/input", u'C:\\input')
    >>> inputs.command_line == u'hello C:\\\\input'
    True
    >>> inputs.config_files[tf.name] == u'world C:\\\\input the rest'
    True
    >>> tf.close()
    >>> tf = tempfile.NamedTemporaryFile()
    >>> inputs = setup_inputs(tf)
    >>> inputs.find_referenced_subfiles('/path/to') == [u'/path/to/input']
    True
    >>> inputs.path_referenced('/path/to')
    True
    >>> inputs.path_referenced(u'/path/to')
    True
    >>> inputs.path_referenced('/path/to/input')
    True
    >>> inputs.path_referenced('/path/to/notinput')
    False
    >>> tf.close()
    """

    def __init__(self, command_line, config_files):
        self.command_line = command_line
        self.config_files = {}
        for config_file in config_files or []:
            config_contents = _read(config_file)
            self.config_files[config_file] = config_contents

    def find_referenced_subfiles(self, directory):
        """
        Return list of files below specified `directory` in job inputs. Could
        use more sophisticated logic (match quotes to handle spaces, handle
        subdirectories, etc...).

        **Parameters**

        directory : str
            Full path to directory to search.

        """
        pattern = r"(%s%s\S+)" % (directory, sep)
        referenced_files = set()
        for input_contents in self.__items():
            referenced_files.update(findall(pattern, input_contents))
        return list(referenced_files)

    def path_referenced(self, path):
        pattern = r"%s" % path
        found = False
        for input_contents in self.__items():
            if findall(pattern, input_contents):
                found = True
                break
        return found

    def rewrite_paths(self, local_path, remote_path):
        """
        Rewrite references to `local_path` with  `remote_path` in job inputs.
        """
        self.__rewrite_command_line(local_path, remote_path)
        self.__rewrite_config_files(local_path, remote_path)

    def __rewrite_command_line(self, local_path, remote_path):
        self.command_line = self.command_line.replace(local_path, remote_path)

    def __rewrite_config_files(self, local_path, remote_path):
        for config_file, contents in self.config_files.items():
            self.config_files[config_file] = contents.replace(local_path, remote_path)

    def __items(self):
        items = [self.command_line]
        items.extend(self.config_files.values())
        return items


class TransferTracker(object):

    def __init__(self, client, job_inputs, rewrite_paths):
        self.client = client
        self.action_mapper = FileActionMapper(client)
        self.job_inputs = job_inputs
        self.rewrite_paths = rewrite_paths
        self.file_renames = {}

    def handle_transfer(self, path, type, name=None, contents=None):
        if contents:
            # If contents loaded in memory, no need to write out file and copy,
            # just transfer.
            action_type = 'transfer'
        else:
            if not exists(path):
                message = "handle_tranfer called on non-existent file - [%s]" % path
                log.warn(message)
                raise Exception(message)
            action_type = self.__action(path, type).action_type

        if action_type in ['transfer', 'copy']:
            response = self.client.put_file(path, type, name=name, contents=contents)
            register = self.rewrite_paths or type == 'tool'  # Even if inputs not rewritten, tool must be.
            if register:
                self.register_rewrite(path, response['path'], type, force=True)
        elif action_type == 'none':
            # No action for this file.
            pass
        else:
            raise Exception("Unknown action type (%s) encountered for path (%s)" % (action_type, path))

    def register_rewrite(self, local_path, remote_path, type, force=False):
        action = self.__action(local_path, type)
        if action.action_type in ['transfer', 'copy'] or force:
            self.file_renames[local_path] = remote_path

    def rewrite_input_paths(self):
        """
        For each file that has been transferred and renamed, updated
        command_line and configfiles to reflect that rewrite.
        """
        for local_path, remote_path in self.file_renames.items():
            self.job_inputs.rewrite_paths(local_path, remote_path)

    def __action(self, path, type):
        return self.action_mapper.action(path, type)


class FileStager(object):
    """
    Objects of the FileStager class interact with an LWR client object to
    stage the files required to run jobs on a remote LWR server.

    **Parameters**

    client : JobClient
        LWR client object.
    client_job_description : client_job_description
        Description of client view of job to stage and execute remotely.
    """

    def __init__(self, client, client_job_description, job_config):
        """
        """
        self.client = client
        self.command_line = client_job_description.command_line
        self.config_files = client_job_description.config_files
        self.input_files = client_job_description.input_files
        self.output_files = client_job_description.output_files
        self.tool_id = client_job_description.tool.id
        self.tool_version = client_job_description.tool.version
        self.tool_dir = abspath(client_job_description.tool.tool_dir)
        self.working_directory = client_job_description.working_directory
        self.version_file = client_job_description.version_file
        self.rewrite_paths = client_job_description.rewrite_paths

        # Setup job inputs, these will need to be rewritten before
        # shipping off to remote LWR server.
        self.job_inputs = JobInputs(self.command_line, self.config_files)

        self.transfer_tracker = TransferTracker(client, self.job_inputs, rewrite_paths=self.rewrite_paths)

        self.__handle_setup(job_config)
        self.__initialize_referenced_tool_files()
        self.__upload_tool_files()
        self.__upload_input_files()
        self.__upload_working_directory_files()

        if self.rewrite_paths:
            self.__initialize_output_file_renames()
            self.__initialize_task_output_file_renames()
            self.__initialize_config_file_renames()
            self.__initialize_version_file_rename()

        self.__handle_rewrites()

        self.__upload_rewritten_config_files()

    def __handle_setup(self, job_config):
        if not job_config:
            job_config = self.client.setup(self.tool_id, self.tool_version)

        self.new_working_directory = job_config['working_directory']
        self.new_outputs_directory = job_config['outputs_directory']
        # Default configs_directory to match remote working_directory to mimic
        # behavior of older LWR servers.
        self.new_configs_directory = job_config.get('configs_directory', self.new_working_directory)
        self.remote_separator = self.__parse_remote_separator(job_config)
        self.path_helper = PathHelper(self.remote_separator)
        # If remote LWR server assigned job id, use that otherwise
        # just use local job_id assigned.
        galaxy_job_id = self.client.job_id
        self.job_id = job_config.get('job_id', galaxy_job_id)
        if self.job_id != galaxy_job_id:
            # Remote LWR server assigned an id different than the
            # Galaxy job id, update client to reflect this.
            self.client.job_id = self.job_id

    def __parse_remote_separator(self, job_config):
        separator = job_config.get("system_properties", {}).get("separator", None)
        if not separator:  # Legacy LWR
            separator = job_config["path_separator"]  # Poorly named
        return separator

    def __initialize_referenced_tool_files(self):
        self.referenced_tool_files = self.job_inputs.find_referenced_subfiles(self.tool_dir)

    def __upload_tool_files(self):
        for referenced_tool_file in self.referenced_tool_files:
            self.transfer_tracker.handle_transfer(referenced_tool_file, 'tool')

    def __upload_input_files(self):
        for input_file in self.input_files:
            self.__upload_input_file(input_file)
            self.__upload_input_extra_files(input_file)

    def __upload_input_file(self, input_file):
        if self.__stage_input(input_file):
            if exists(input_file):
                self.transfer_tracker.handle_transfer(input_file, 'input')
            else:
                message = "LWR: __upload_input_file called on empty or missing dataset." + \
                          " So such file: [%s]" % input_file
                log.debug(message)

    def __upload_input_extra_files(self, input_file):
        files_path = "%s_files" % input_file[0:-len(".dat")]
        if exists(files_path) and self.__stage_input(files_path):
            for extra_file_name in directory_files(files_path):
                extra_file_path = join(files_path, extra_file_name)
                remote_name = self.path_helper.remote_name(relpath(extra_file_path, dirname(files_path)))
                self.transfer_tracker.handle_transfer(extra_file_path, 'input_extra', name=remote_name)

    def __upload_working_directory_files(self):
        # Task manager stages files into working directory, these need to be
        # uploaded if present.
        working_directory_files = listdir(self.working_directory) if exists(self.working_directory) else []
        for working_directory_file in working_directory_files:
            path = join(self.working_directory, working_directory_file)
            self.transfer_tracker.handle_transfer(path, 'work_dir')

    def __initialize_version_file_rename(self):
        version_file = self.version_file
        if version_file:
            remote_path = self.path_helper.remote_join(self.new_outputs_directory, COMMAND_VERSION_FILENAME)
            self.transfer_tracker.register_rewrite(version_file, remote_path, "output")

    def __initialize_output_file_renames(self):
        for output_file in self.output_files:
            remote_path = self.path_helper.remote_join(self.new_outputs_directory, basename(output_file))
            self.transfer_tracker.register_rewrite(output_file, remote_path, 'output')

    def __initialize_task_output_file_renames(self):
        for output_file in self.output_files:
            name = basename(output_file)
            task_file = join(self.working_directory, name)
            remote_path = self.path_helper.remote_join(self.new_working_directory, name)
            self.transfer_tracker.register_rewrite(task_file, remote_path, 'output_task')

    def __initialize_config_file_renames(self):
        for config_file in self.config_files:
            remote_path = self.path_helper.remote_join(self.new_configs_directory, basename(config_file))
            self.transfer_tracker.register_rewrite(config_file, remote_path, 'config')

    def __handle_rewrites(self):
        """
        For each file that has been transferred and renamed, updated
        command_line and configfiles to reflect that rewrite.
        """
        self.transfer_tracker.rewrite_input_paths()

    def __upload_rewritten_config_files(self):
        for config_file, new_config_contents in self.job_inputs.config_files.items():
            self.client.put_file(config_file, input_type='config', contents=new_config_contents)

    def get_command_line(self):
        """
        Returns the rewritten version of the command line to execute suitable
        for remote host.
        """
        return self.job_inputs.command_line

    def __stage_input(self, file_path):
        # If we have disabled path rewriting, just assume everything needs to be transferred,
        # else check to ensure the file is referenced before transferring it.
        return (not self.rewrite_paths) or self.job_inputs.path_referenced(file_path)


def finish_job(client, cleanup_job, job_completed_normally, galaxy_outputs, lwr_outputs):
    """
    """
    download_failure_exceptions = []
    if job_completed_normally:
        download_failure_exceptions = __download_results(client, galaxy_outputs, lwr_outputs)
    return __clean(download_failure_exceptions, cleanup_job, client)


class GalaxyOutputs(object):
    """ Abstraction describing the output datasets EXPECTED by the Galaxy job
    runner client. """

    def __init__(self, working_directory, work_dir_outputs, output_files, version_file):
        self.working_directory = working_directory
        self.work_dir_outputs = work_dir_outputs
        self.output_files = output_files
        self.version_file = version_file


class LwrOutputs(object):
    """ Abstraction describing the output files PRODUCED by the remote LWR
    server. """

    def __init__(self, complete_response):
        # Default to None instead of [] to distinguish between empty contents and it not set
        # by the LWR - older LWR instances will not set these in complete response.
        self.working_directory_contents = complete_response.get("working_directory_contents", None)
        self.output_directory_contents = complete_response.get("outputs_directory_contents", None)
        # Older (pre-2014) LWR servers will not include separator in response,
        #so this should only be used when reasoning about outputs in
        # subdirectories which was not previously supported.
        self.path_helper = PathHelper(complete_response.get("system_properties", {}).get("separator", sep))

    def has_output_file(self, output_file):
        if self.output_directory_contents is None:
            # Legacy LWR doesn't report this, return None indicating unsure if
            # output was generated.
            return None
        else:
            return basename(output_file) in self.output_directory_contents

    def has_output_directory_listing(self):
        return self.output_directory_contents is not None

    def output_extras(self, output_file):
        """
        Returns dict mapping local path to remote name.
        """
        output_directory = dirname(output_file)

        def local_path(name):
            return join(output_directory, self.path_helper.local_name(name))

        files_directory = "%s_files%s" % (basename(output_file)[0:-len(".dat")], self.path_helper.separator)
        names = filter(lambda o: o.startswith(files_directory),  self.output_directory_contents)
        return dict(map(lambda name: (local_path(name), name), names))


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


def submit_job(client, client_job_description, job_config=None):
    """
    """
    file_stager = FileStager(client, client_job_description, job_config)
    rebuilt_command_line = file_stager.get_command_line()
    job_id = file_stager.job_id
    client.launch(rebuilt_command_line, requirements=client_job_description.requirements)
    return job_id


def _read(path):
    """
    Utility method to quickly read small files (config files and tool
    wrappers) into memory as bytes.
    """
    input = open(path, "r", encoding="utf-8")
    try:
        return input.read()
    finally:
        input.close()


class ClientJobDescription(object):
    """ A description of how client views job - command_line, inputs, etc..

    **Parameters**

    command_line : str
        The local command line to execute, this will be rewritten for the remote server.
    config_files : list
        List of Galaxy 'configfile's produced for this job. These will be rewritten and sent to remote server.
    input_files :  list
        List of input files used by job. These will be transferred and references rewritten.
    output_files : list
        List of output_files produced by job.
    tool_dir : str
        Directory containing tool to execute (if a wrapper is used, it will be transferred to remote server).
    working_directory : str
        Local path created by Galaxy for running this job.
    requirements : list
        List of requirements for tool execution.
    version_file : str
        Path to version file expected on the client server
    rewrite_paths : boolean
        Indicates whether paths should be rewritten in job inputs (command_line
        and config files) while staging files).
    """

    def __init__(
        self,
        tool,
        command_line,
        config_files,
        input_files,
        output_files,
        working_directory,
        requirements,
        version_file=None,
        rewrite_paths=True,
    ):
        self.tool = tool
        self.command_line = command_line
        self.config_files = config_files
        self.input_files = input_files
        self.output_files = output_files
        self.working_directory = working_directory
        self.requirements = requirements
        self.version_file = version_file
        self.rewrite_paths = rewrite_paths


__all__ = [submit_job, ClientJobDescription, finish_job, LwrOutputs, GalaxyOutputs]
