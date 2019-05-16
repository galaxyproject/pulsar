from io import open
from logging import getLogger
from os import sep
from os.path import (
    abspath,
    basename,
    exists,
    join,
    relpath,
)
from re import escape, findall

from ..action_mapper import FileActionMapper
from ..action_mapper import MessageAction
from ..action_mapper import path_type
from ..job_directory import RemoteJobDirectory
from ..staging import CLIENT_INPUT_PATH_TYPES, COMMAND_VERSION_FILENAME
from ..util import directory_files
from ..util import PathHelper

log = getLogger(__name__)


def submit_job(client, client_job_description, job_config=None):
    """
    """
    file_stager = FileStager(client, client_job_description, job_config)
    rebuilt_command_line = file_stager.get_command_line()
    job_id = file_stager.job_id
    launch_kwds = dict(
        command_line=rebuilt_command_line,
        dependencies_description=client_job_description.dependencies_description,
        env=client_job_description.env,
    )
    if client_job_description.container:
        launch_kwds["container"] = client_job_description.container
    if client_job_description.remote_pulsar_app_config:
        launch_kwds["pulsar_app_config"] = client_job_description.remote_pulsar_app_config

    if file_stager.job_config:
        launch_kwds["job_config"] = file_stager.job_config
    remote_staging = {}
    remote_staging_actions = file_stager.transfer_tracker.remote_staging_actions
    if remote_staging_actions:
        remote_staging["setup"] = remote_staging_actions
    # Somehow make the following optional.
    remote_staging["action_mapper"] = file_stager.action_mapper.to_dict()
    remote_staging["client_outputs"] = client_job_description.client_outputs.to_dict()

    if remote_staging:
        launch_kwds["remote_staging"] = remote_staging

    client.launch(**launch_kwds)
    return job_id


class FileStager(object):
    """
    Objects of the FileStager class interact with an Pulsar client object to
    stage the files required to run jobs on a remote Pulsar server.

    **Parameters**

    client : JobClient
        Pulsar client object.
    client_job_description : client_job_description
        Description of client view of job to stage and execute remotely.
    """

    def __init__(self, client, client_job_description, job_config):
        """
        """
        self.client = client
        self.command_line = client_job_description.command_line
        self.config_files = client_job_description.config_files
        self.client_inputs = client_job_description.client_inputs
        self.output_files = client_job_description.output_files
        if client_job_description.tool is not None:
            self.tool_id = client_job_description.tool.id
            self.tool_version = client_job_description.tool.version
            self.tool_dir = abspath(client_job_description.tool.tool_dir)
        else:
            self.tool_id = None
            self.tool_version = None
            self.tool_dir = None
        self.working_directory = client_job_description.working_directory
        self.metadata_directory = client_job_description.metadata_directory
        self.version_file = client_job_description.version_file
        self.arbitrary_files = client_job_description.arbitrary_files
        self.rewrite_paths = client_job_description.rewrite_paths

        # Setup job inputs, these will need to be rewritten before
        # shipping off to remote Pulsar server.
        self.job_inputs = JobInputs(self.command_line, self.config_files)

        self.action_mapper = FileActionMapper(client)

        self.__handle_setup(job_config)
        self.__setup_touch_outputs(client_job_description.touch_outputs)

        self.transfer_tracker = TransferTracker(
            client,
            self.path_helper,
            self.action_mapper,
            self.job_inputs,
            self.rewrite_paths,
            self.job_directory,
        )

        self.__initialize_referenced_tool_files()
        if self.rewrite_paths:
            self.__initialize_referenced_arbitrary_files()

        self.__upload_tool_files()
        self.__upload_input_files()
        self.__upload_working_directory_files()
        self.__upload_metadata_directory_files()
        self.__upload_arbitrary_files()

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
        self.new_tool_directory = job_config.get('tools_directory', None)
        # Default configs_directory to match remote working_directory to mimic
        # behavior of older Pulsar servers.
        self.new_configs_directory = job_config.get('configs_directory', self.new_working_directory)
        self.remote_separator = self.__parse_remote_separator(job_config)
        self.path_helper = PathHelper(self.remote_separator)
        # If remote Pulsar server assigned job id, use that otherwise
        # just use local job_id assigned.
        galaxy_job_id = self.client.job_id
        self.job_id = job_config.get('job_id', galaxy_job_id)
        if self.job_id != galaxy_job_id:
            # Remote Pulsar server assigned an id different than the
            # Galaxy job id, update client to reflect this.
            self.client.job_id = self.job_id
        self.job_config = job_config
        self.job_directory = self.__setup_job_directory()

    def __setup_touch_outputs(self, touch_outputs):
        self.job_config['touch_outputs'] = touch_outputs

    def __parse_remote_separator(self, job_config):
        separator = job_config.get("system_properties", {}).get("separator", None)
        if not separator:  # Legacy Pulsar
            separator = job_config["path_separator"]  # Poorly named
        return separator

    def __setup_job_directory(self):
        if self.client.job_directory:
            return self.client.job_directory
        elif self.job_config.get('job_directory', None):
            return RemoteJobDirectory(
                remote_staging_directory=self.job_config['job_directory'],
                remote_id=None,
                remote_sep=self.remote_separator,
            )
        else:
            return None

    def __initialize_referenced_tool_files(self):
        # Was this following line only for interpreter, should we disable it of 16.04+ tools
        self.referenced_tool_files = self.job_inputs.find_referenced_subfiles(self.tool_dir)
        # If the tool was created with a correct $__tool_directory__ find those files and transfer
        new_tool_directory = self.new_tool_directory
        if not new_tool_directory:
            return

        for potential_tool_file in self.job_inputs.find_referenced_subfiles(new_tool_directory):
            local_file = potential_tool_file.replace(new_tool_directory, self.tool_dir)
            if exists(local_file):
                self.referenced_tool_files.append(local_file)

    def __initialize_referenced_arbitrary_files(self):
        referenced_arbitrary_path_mappers = dict()
        for mapper in self.action_mapper.unstructured_mappers():
            mapper_pattern = mapper.to_pattern()
            # TODO: Make more sophisticated, allow parent directories,
            # grabbing sibbling files based on patterns, etc...
            paths = self.job_inputs.find_pattern_references(mapper_pattern)
            for path in paths:
                if path not in referenced_arbitrary_path_mappers:
                    referenced_arbitrary_path_mappers[path] = mapper
        for path, mapper in referenced_arbitrary_path_mappers.items():
            action = self.action_mapper.action({"path": path}, path_type.UNSTRUCTURED, mapper)
            unstructured_map = action.unstructured_map(self.path_helper)
            self.arbitrary_files.update(unstructured_map)

    def __upload_tool_files(self):
        for referenced_tool_file in self.referenced_tool_files:
            self.transfer_tracker.handle_transfer_path(referenced_tool_file, path_type.TOOL)

    def __upload_arbitrary_files(self):
        for path, name in self.arbitrary_files.items():
            self.transfer_tracker.handle_transfer_path(path, path_type.UNSTRUCTURED, name=name)

    def __upload_input_files(self):
        handled_inputs = set()
        for client_input in self.client_inputs:
            # TODO: use object identity to handle this.
            path = client_input.path
            if path in handled_inputs:
                continue

            if client_input.input_type == CLIENT_INPUT_PATH_TYPES.INPUT_PATH:
                self.__upload_input_file(client_input.action_source)
                handled_inputs.add(path)
            elif client_input.input_type == CLIENT_INPUT_PATH_TYPES.INPUT_EXTRA_FILES_PATH:
                self.__upload_input_extra_files(client_input.action_source)
                handled_inputs.add(path)
            elif client_input.input_type == CLIENT_INPUT_PATH_TYPES.INPUT_METADATA_PATH:
                self.__upload_input_metadata_file(client_input.action_source)
                handled_inputs.add(path)
            else:
                raise NotImplementedError()

    def __upload_input_file(self, input_action_source):
        if self.__stage_input(input_action_source):
            self.transfer_tracker.handle_transfer_source(input_action_source, path_type.INPUT)

    def __upload_input_extra_files(self, input_action_source):
        if self.__stage_input(input_action_source):
            # TODO: needs to happen else where if using remote object store staging
            # but we don't have the action type yet.
            self.transfer_tracker.handle_transfer_directory(path_type.INPUT, action_source=input_action_source)

    def __upload_input_metadata_file(self, input_action_source):
        if self.__stage_input(input_action_source):
            # Name must match what is generated in remote_input_path_rewrite in path_mapper.
            remote_name = "metadata_%s" % basename(input_action_source['path'])
            self.transfer_tracker.handle_transfer_source(input_action_source, path_type.INPUT, name=remote_name)

    def __upload_working_directory_files(self):
        # Task manager stages files into working directory, these need to be
        # uploaded if present.
        directory = self.working_directory
        if directory and exists(directory):
            self.transfer_tracker.handle_transfer_directory(path_type.WORKDIR, directory=directory)

    def __upload_metadata_directory_files(self):
        directory = self.metadata_directory
        if directory and exists(directory):
            self.transfer_tracker.handle_transfer_directory(path_type.METADATA, directory=directory)

    def __initialize_version_file_rename(self):
        version_file = self.version_file
        if version_file:
            remote_path = self.path_helper.remote_join(self.new_outputs_directory, COMMAND_VERSION_FILENAME)
            self.transfer_tracker.register_rewrite(version_file, remote_path, path_type.OUTPUT)

    def __initialize_output_file_renames(self):
        for output_file in self.output_files:
            remote_path = self.path_helper.remote_join(self.new_outputs_directory, basename(output_file))
            self.transfer_tracker.register_rewrite(output_file, remote_path, path_type.OUTPUT)

    def __initialize_task_output_file_renames(self):
        for output_file in self.output_files:
            name = basename(output_file)
            task_file = join(self.working_directory, name)
            remote_path = self.path_helper.remote_join(self.new_working_directory, name)
            self.transfer_tracker.register_rewrite(task_file, remote_path, path_type.OUTPUT_WORKDIR)

    def __initialize_config_file_renames(self):
        for config_file in self.config_files:
            remote_path = self.path_helper.remote_join(self.new_configs_directory, basename(config_file))
            self.transfer_tracker.register_rewrite(config_file, remote_path, path_type.CONFIG)

    def __handle_rewrites(self):
        """
        For each file that has been transferred and renamed, updated
        command_line and configfiles to reflect that rewrite.
        """
        self.transfer_tracker.rewrite_input_paths()

    def __upload_rewritten_config_files(self):
        for config_file, new_config_contents in self.job_inputs.config_files.items():
            self.transfer_tracker.handle_transfer_path(config_file, type=path_type.CONFIG, contents=new_config_contents)

    def get_command_line(self):
        """
        Returns the rewritten version of the command line to execute suitable
        for remote host.
        """
        return self.job_inputs.command_line

    def __stage_input(self, source):
        if not self.rewrite_paths:
            return True

        # If we have disabled path rewriting, just assume everything needs to be transferred,
        # else check to ensure the file is referenced before transferring it.
        return self.job_inputs.path_referenced(source['path'])


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
    ...     open(tf.name, "w").write(u'''world /path/to/input '/path/to/moo' "/path/to/cow" the rest''')
    ...     inputs = JobInputs(u"hello /path/to/input", [tf.name])
    ...     return inputs
    >>> inputs = setup_inputs(tf)
    >>> inputs.rewrite_paths(u"/path/to/input", u'C:\\input')
    >>> inputs.command_line == u'hello C:\\\\input'
    True
    >>> inputs.config_files[tf.name] == u'''world C:\\\\input '/path/to/moo' "/path/to/cow" the rest'''
    True
    >>> tf.close()
    >>> tf = tempfile.NamedTemporaryFile()
    >>> inputs = setup_inputs(tf)
    >>> sorted(inputs.find_referenced_subfiles('/path/to')) == [u'/path/to/cow', u'/path/to/input', u'/path/to/moo']
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

    def find_pattern_references(self, pattern):
        referenced_files = set()
        for input_contents in self.__items():
            referenced_files.update(findall(pattern, input_contents))
        return list(referenced_files)

    def find_referenced_subfiles(self, directory):
        """
        Return list of files below specified `directory` in job inputs. Could
        use more sophisticated logic (match quotes to handle spaces, handle
        subdirectories, etc...).

        **Parameters**

        directory : str
            Full path to directory to search.

        """
        if directory is None:
            return []

        pattern = r'''[\'\"]?(%s%s[^\s\'\"]+)[\'\"]?''' % (escape(directory), escape(sep))
        return self.find_pattern_references(pattern)

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

    def __init__(self, client, path_helper, action_mapper, job_inputs, rewrite_paths, job_directory):
        self.client = client
        self.path_helper = path_helper
        self.action_mapper = action_mapper

        self.job_inputs = job_inputs
        self.rewrite_paths = rewrite_paths
        self.job_directory = job_directory
        self.file_renames = {}
        self.remote_staging_actions = []

    def handle_transfer_path(self, path, type, name=None, contents=None):
        source = {"path": path}
        return self.handle_transfer_source(source, type, name=name, contents=contents)

    def handle_transfer_directory(self, type, directory=None, action_source=None):
        # TODO: needs to happen else where if using remote object store staging
        # but we don't have the action type yet.
        if directory is None:
            assert action_source is not None
            action = self.__action_for_transfer(action_source, type, None)
            if not action.staging_action_local and action.whole_directory_transfer_supported:
                # If we're going to transfer the whole directory remotely, don't walk the files
                # here.

                # We could still rewrite paths and just not transfer the files.
                assert not self.rewrite_paths
                self.__add_remote_staging_input(self, action, None, type)
                return

            directory = action_source['path']
        else:
            assert action_source is None

        for directory_file_name in directory_files(directory):
            directory_file_path = join(directory, directory_file_name)
            remote_name = self.path_helper.remote_name(relpath(directory_file_path, directory))
            self.handle_transfer_path(directory_file_path, type, name=remote_name)

    def handle_transfer_source(self, source, type, name=None, contents=None):
        action = self.__action_for_transfer(source, type, contents)

        if action.staging_needed:
            local_action = action.staging_action_local
            if local_action:
                path = source['path']
                if not exists(path):
                    message = "Pulsar: __upload_input_file called on empty or missing dataset." + \
                              " No such file: [%s]" % path
                    log.debug(message)
                    return

                response = self.client.put_file(path, type, name=name, contents=contents, action_type=action.action_type)

                def get_path():
                    return response['path']
            else:
                path = source['path']
                job_directory = self.job_directory
                assert job_directory, "job directory required for action %s" % action
                if not name:
                    # TODO: consider fetching this from source so an actual input path
                    # isn't needed. At least it isn't used though.
                    name = basename(path)
                self.__add_remote_staging_input(action, name, type)

                def get_path():
                    return job_directory.calculate_path(name, type)
            register = self.rewrite_paths or type == 'tool'  # Even if inputs not rewritten, tool must be.
            if register:
                self.register_rewrite_action(action, get_path(), force=True)
        elif self.rewrite_paths:
            path_rewrite = action.path_rewrite(self.path_helper)
            if path_rewrite:
                self.register_rewrite_action(action, path_rewrite, force=True)

        # else: # No action for this file

    def __add_remote_staging_input(self, action, name, type):
        input_dict = dict(
            name=name,
            type=type,
            action=action.to_dict(),
        )
        self.remote_staging_actions.append(input_dict)

    def __action_for_transfer(self, source, type, contents):
        if contents:
            # If contents loaded in memory, no need to write out file and copy,
            # just transfer.
            action = MessageAction(contents=contents, client=self.client)
        else:
            path = source.get("path")
            if path is not None and not exists(path):
                message = "__action_for_transfer called on non-existent file - [%s]" % path
                log.warn(message)
                raise Exception(message)
            action = self.__action(source, type)
        return action

    def register_rewrite(self, local_path, remote_path, type, force=False):
        action = self.__action({"path": local_path}, type)
        self.register_rewrite_action(action, remote_path, force=force)

    def register_rewrite_action(self, action, remote_path, force=False):
        if action.staging_needed or force:
            path = getattr(action, 'path', None)
            if path:
                self.file_renames[path] = remote_path

    def rewrite_input_paths(self):
        """
        For each file that has been transferred and renamed, updated
        command_line and configfiles to reflect that rewrite.
        """
        for local_path, remote_path in self.file_renames.items():
            self.job_inputs.rewrite_paths(local_path, remote_path)

    def __action(self, source, type):
        return self.action_mapper.action(source, type)


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


__all__ = ['submit_job']
