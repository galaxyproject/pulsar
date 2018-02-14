"""
Base Classes and Infrastructure Supporting Concret Manager Implementations.

"""
from collections import deque
import errno
import logging
import os
from os.path import exists, isdir, join, basename
from os.path import relpath
from os import curdir
from os import listdir
from os import makedirs
from os import sep
from os import getenv
from os import walk
import json
from uuid import uuid4
import posixpath
from shutil import rmtree

import six

from pulsar import locks
from pulsar.managers import ManagerInterface
from pulsar.client.job_directory import RemoteJobDirectory
from pulsar.client.job_directory import verify_is_in_directory

JOB_DIRECTORY_INPUTS = "inputs"
JOB_DIRECTORY_OUTPUTS = "outputs"
JOB_DIRECTORY_WORKING = "working"
JOB_DIRECTORY_METADATA = "metadata"
JOB_DIRECTORY_CONFIGS = "configs"
JOB_DIRECTORY_TOOL_FILES = "tool_files"

DEFAULT_ID_ASSIGNER = "galaxy"

ID_ASSIGNER = {
    # Generate a random id, needed if multiple
    # Galaxy instances submitting to same Pulsar.
    'uuid': lambda galaxy_job_id: uuid4().hex,
    # Pass galaxy id through, default for single
    # Galaxy Pulsar instance.
    'galaxy': lambda galaxy_job_id: galaxy_job_id
}

log = logging.getLogger(__name__)


def get_id_assigner(assign_ids):
    default_id_assigner = ID_ASSIGNER[DEFAULT_ID_ASSIGNER]
    return ID_ASSIGNER.get(assign_ids, default_id_assigner)


class BaseManager(ManagerInterface):

    def __init__(self, name, app, **kwds):
        self.name = name
        self.persistence_directory = getattr(app, 'persistence_directory', None)
        self.lock_manager = locks.LockManager()
        self._directory_maker = DirectoryMaker(kwds.get("job_directory_mode", None))
        staging_directory = kwds.get("staging_directory", app.staging_directory)
        self._setup_staging_directory(staging_directory)
        self.id_assigner = get_id_assigner(kwds.get("assign_ids", None))
        self.maximum_stream_size = kwds.get("maximum_stream_size", -1)
        self.__init_galaxy_system_properties(kwds)
        self.debug = str(kwds.get("debug", False)).lower() == "true"
        self.authorizer = app.authorizer
        self.__init_system_properties()
        self.__init_env_vars(**kwds)
        self.dependency_manager = app.dependency_manager
        self.job_metrics = app.job_metrics

    def clean(self, job_id):
        if self.debug:
            # In debug mode skip cleaning job directories.
            return

        job_directory = self._job_directory(job_id)
        if job_directory.exists():
            try:
                job_directory.delete()
            except Exception:
                pass

    def system_properties(self):
        return self.__system_properties

    def __init_galaxy_system_properties(self, kwds):
        self.galaxy_home = kwds.get('galaxy_home', None)
        self.galaxy_virtual_env = kwds.get('galaxy_virtual_env', None)
        self.galaxy_config_file = kwds.get('galaxy_config_file', None)
        self.galaxy_dataset_files_path = kwds.get('galaxy_dataset_files_path', None)
        self.galaxy_datatypes_config_file = kwds.get('galaxy_datatypes_config_file', None)

    def __init_system_properties(self):
        system_properties = {
            "separator": sep,
        }
        galaxy_home = self._galaxy_home()
        if galaxy_home:
            system_properties["galaxy_home"] = galaxy_home
        galaxy_virtual_env = self._galaxy_virtual_env()
        if galaxy_virtual_env:
            system_properties["galaxy_virtual_env"] = galaxy_virtual_env
        for property in ['galaxy_config_file', 'galaxy_dataset_files_path', 'galaxy_datatypes_config_file']:
            value = getattr(self, property, None)
            if value:
                system_properties[property] = value

        self.__system_properties = system_properties

    def __init_env_vars(self, **kwds):
        env_vars = []
        for key, value in six.iteritems(kwds):
            if key.lower().startswith("env_"):
                name = key[len("env_"):]
                env_vars.append(dict(name=name, value=value, raw=False))
        self.env_vars = env_vars

    def _galaxy_home(self):
        return self.galaxy_home or getenv('GALAXY_HOME', None)

    def _galaxy_virtual_env(self):
        return self.galaxy_virtual_env or getenv('GALAXY_VIRTUAL_ENV', None)

    def _galaxy_lib(self):
        galaxy_home = self._galaxy_home()
        galaxy_lib = None
        if galaxy_home and str(galaxy_home).lower() != 'none':
            galaxy_lib = join(galaxy_home, 'lib')
        return galaxy_lib

    def _setup_staging_directory(self, staging_directory):
        assert staging_directory is not None
        if not exists(staging_directory):
            self._directory_maker.make(staging_directory, recursive=True)
        assert isdir(staging_directory)
        self.staging_directory = staging_directory

    def _job_directory(self, job_id):
        return JobDirectory(
            self.staging_directory,
            job_id,
            self.lock_manager,
            self._directory_maker,
        )

    job_directory = _job_directory

    def _setup_job_directory(self, job_id):
        job_directory = self._job_directory(job_id)
        job_directory.setup()
        for directory in [JOB_DIRECTORY_INPUTS,
                          JOB_DIRECTORY_WORKING,
                          JOB_DIRECTORY_OUTPUTS,
                          JOB_DIRECTORY_CONFIGS,
                          JOB_DIRECTORY_TOOL_FILES,
                          JOB_DIRECTORY_METADATA]:
            job_directory.make_directory(directory)
        return job_directory

    def _get_authorization(self, job_id, tool_id):
        return self.authorizer.get_authorization(tool_id)

    def _check_execution(self, job_id, tool_id, command_line):
        log.debug("job_id: %s - Checking authorization of command_line [%s]" % (job_id, command_line))
        authorization = self._get_authorization(job_id, tool_id)
        job_directory = self._job_directory(job_id)
        tool_files_dir = job_directory.tool_files_directory()
        for file in self._list_dir(tool_files_dir):
            contents = open(join(tool_files_dir, file), 'r').read()
            log.debug("job_id: %s - checking tool file %s" % (job_id, file))
            authorization.authorize_tool_file(basename(file), contents)
        config_files_dir = job_directory.configs_directory()
        for file in self._list_dir(config_files_dir):
            path = join(config_files_dir, file)
            authorization.authorize_config_file(job_directory, file, path)
        authorization.authorize_execution(job_directory, command_line)

    def _list_dir(self, directory_or_none):
        if directory_or_none is None or not exists(directory_or_none):
            return []
        else:
            return listdir(directory_or_none)

    def _expand_command_line(self, command_line, dependencies_description, job_directory=None):
        if dependencies_description is None:
            return command_line

        requirements = dependencies_description.requirements
        installed_tool_dependencies = dependencies_description.installed_tool_dependencies
        dependency_commands = self.dependency_manager.dependency_shell_commands(
            requirements=requirements,
            installed_tool_dependencies=installed_tool_dependencies,
            job_directory=job_directory,
        )
        if dependency_commands:
            command_line = "%s; %s" % ("; ".join(dependency_commands), command_line)
        return command_line

    def __str__(self):
        return "{0}[name={1}]".format(type(self).__name__, self.name)


class JobDirectory(RemoteJobDirectory):

    def __init__(
        self,
        staging_directory,
        job_id,
        lock_manager=None,
        directory_maker=None
    ):
        super(JobDirectory, self).__init__(staging_directory, remote_id=job_id, remote_sep=sep)
        self._directory_maker = directory_maker or DirectoryMaker()
        self.lock_manager = lock_manager
        # Assert this job id isn't hacking path somehow.
        assert job_id == basename(job_id)

    def enable_metadata_directory(self):
        self.store_metadata("use_metadata_directory", True)

    @property
    def use_metadata_directory(self):
        return self.has_metadata("use_metadata_directory")

    def _job_file(self, name):
        return os.path.join(self.job_directory, name)

    def calculate_path(self, remote_path, input_type):
        """ Verify remote_path is in directory for input_type inputs
        and create directory if needed.
        """
        directory, allow_nested_files = self._directory_for_file_type(input_type)
        path = get_mapped_file(directory, remote_path, allow_nested_files=allow_nested_files)
        return path

    def read_file(self, name, size=-1, default=None):
        path = self._job_file(name)
        job_file = None
        try:
            job_file = open(path, 'rb')
            return job_file.read(size)
        except Exception:
            if default is not None:
                return default
            else:
                raise
        finally:
            if job_file:
                job_file.close()

    def write_file(self, name, contents):
        path = self._job_file(name)
        job_file = open(path, 'wb')
        try:
            if isinstance(contents, six.text_type):
                contents = contents.encode("UTF-8")
            job_file.write(contents)
        finally:
            job_file.close()
        return path

    def remove_file(self, name):
        """
        Quietly remove a job file.
        """
        try:
            os.remove(self._job_file(name))
        except OSError:
            pass

    def contains_file(self, name):
        return os.path.exists(self._job_file(name))

    def open_file(self, name, mode='wb'):
        return open(self._job_file(name), mode)

    def exists(self):
        return os.path.exists(self.path)

    def delete(self):
        return rmtree(self.path)

    def setup(self):
        self._directory_maker.make(self.job_directory)

    def make_directory(self, name):
        path = self._job_file(name)
        self._directory_maker.make(path)

    def lock(self, name=".state"):
        assert self.lock_manager, "Can only use job directory locks if lock manager defined."
        return self.lock_manager.get_lock(self._job_file(name))

    def working_directory_contents(self):
        working_directory = self.working_directory()
        return self.__directory_contents(working_directory)

    def outputs_directory_contents(self):
        outputs_directory = self.outputs_directory()
        return self.__directory_contents(outputs_directory)

    def metadata_directory_contents(self):
        metadata_directory = self.metadata_directory()
        return self.__directory_contents(metadata_directory)

    def metadata_directory(self):
        if self.use_metadata_directory:
            return super(JobDirectory, self).metadata_directory()
        else:
            return self.working_directory()

    def __directory_contents(self, directory):
        contents = []
        for path, _, files in walk(directory):
            relative_path = relpath(path, directory)
            for name in files:
                # Return file1.txt, dataset_1_files/image.png, etc... don't
                # include . in path.
                if relative_path != curdir:
                    contents.append(join(relative_path, name))
                else:
                    contents.append(name)
        return contents

    # Following abstractions store metadata related to jobs.
    def store_metadata(self, metadata_name, metadata_value):
        self.write_file(metadata_name, json.dumps(metadata_value))

    def load_metadata(self, metadata_name, default=None):
        DEFAULT_RAW = object()
        contents = self.read_file(metadata_name, default=DEFAULT_RAW)
        if contents is DEFAULT_RAW:
            return default
        else:
            return json.loads(contents.decode())

    def has_metadata(self, metadata_name):
        return self.contains_file(metadata_name)

    def remove_metadata(self, metadata_name):
        self.remove_file(metadata_name)


def get_mapped_file(directory, remote_path, allow_nested_files=False, local_path_module=os.path, mkdir=True):
    """

    >>> import ntpath
    >>> get_mapped_file(r'C:\\pulsar\\staging\\101', 'dataset_1_files/moo/cow', allow_nested_files=True, local_path_module=ntpath, mkdir=False)
    'C:\\\\pulsar\\\\staging\\\\101\\\\dataset_1_files\\\\moo\\\\cow'
    >>> get_mapped_file(r'C:\\pulsar\\staging\\101', 'dataset_1_files/moo/cow', allow_nested_files=False, local_path_module=ntpath)
    'C:\\\\pulsar\\\\staging\\\\101\\\\cow'
    >>> get_mapped_file(r'C:\\pulsar\\staging\\101', '../cow', allow_nested_files=True, local_path_module=ntpath, mkdir=False)
    Traceback (most recent call last):
    Exception: Attempt to read or write file outside an authorized directory.
    """
    if not allow_nested_files:
        name = local_path_module.basename(remote_path)
        path = local_path_module.join(directory, name)
    else:
        local_rel_path = __posix_to_local_path(remote_path, local_path_module=local_path_module)
        local_path = local_path_module.join(directory, local_rel_path)
        verify_is_in_directory(local_path, directory, local_path_module=local_path_module)
        local_directory = local_path_module.dirname(local_path)
        if mkdir and not local_path_module.exists(local_directory):
            os.makedirs(local_directory)
        path = local_path
    return path


def __posix_to_local_path(path, local_path_module=os.path):
    """
    Converts a posix path (coming from Galaxy), to a local path (be it posix or Windows).

    >>> import ntpath
    >>> __posix_to_local_path('dataset_1_files/moo/cow', local_path_module=ntpath)
    'dataset_1_files\\\\moo\\\\cow'
    >>> import posixpath
    >>> __posix_to_local_path('dataset_1_files/moo/cow', local_path_module=posixpath)
    'dataset_1_files/moo/cow'
    """
    partial_path = deque()
    while True:
        if not path or path == '/':
            break
        (path, base) = posixpath.split(path)
        partial_path.appendleft(base)
    return local_path_module.join(*partial_path)


class DirectoryMaker(object):

    def __init__(self, mode=None):
        self.mode = mode

    def make(self, path, recursive=False):
        makedir_args = [path]
        if self.mode is not None:
            makedir_args.append(self.mode)
        try:
            if recursive:
                makedirs(*makedir_args)
            else:
                os.mkdir(*makedir_args)
        except (OSError, IOError) as exc:
            if exc.errno != errno.EEXIST:
                raise
