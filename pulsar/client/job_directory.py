"""
"""
import os.path
import posixpath

from collections import deque
from logging import getLogger

from galaxy.util import in_directory

from .util import PathHelper
log = getLogger(__name__)


TYPES_TO_METHOD = dict(
    input="inputs_directory",
    unstructured="unstructured_files_directory",
    config="configs_directory",
    tool="tool_files_directory",
    jobdir="job_directory",
    workdir="working_directory",
    metadata="metadata_directory",
    output="outputs_directory",
    output_workdir="working_directory",
    output_metadata="metadata_directory",
    output_jobdir="job_directory",
)


class RemoteJobDirectory(object):
    """ Representation of a (potentially) remote Pulsar-style staging directory.
    """

    def __init__(self, remote_staging_directory, remote_id, remote_sep):
        self.path_helper = PathHelper(remote_sep)
        if remote_id:
            self.job_directory = self.path_helper.remote_join(
                remote_staging_directory,
                remote_id
            )
        else:
            self.job_directory = remote_staging_directory

    def metadata_directory(self):
        return self._sub_dir('metadata')

    def working_directory(self):
        return self._sub_dir('working')

    def inputs_directory(self):
        return self._sub_dir('inputs')

    def outputs_directory(self):
        return self._sub_dir('outputs')

    def configs_directory(self):
        return self._sub_dir('configs')

    def tool_files_directory(self):
        return self._sub_dir('tool_files')

    def unstructured_files_directory(self):
        return self._sub_dir('unstructured')

    @property
    def path(self):
        return self.job_directory

    @property
    def separator(self):
        return self.path_helper.separator

    def calculate_path(self, remote_relative_path, input_type):
        """ Only for used by Pulsar client, should override for managers to
        enforce security and make the directory if needed.
        """
        directory, allow_nested_files = self._directory_for_file_type(input_type)
        return self.path_helper.remote_join(directory, remote_relative_path)

    def _directory_for_file_type(self, file_type):
        allow_nested_files = False
        # work_dir and input_extra are types used by legacy clients...
        # Obviously this client won't be legacy because this is in the
        # client module, but this code is reused on server which may
        # serve legacy clients.
        allow_nested_files = file_type in ['input', 'unstructured', 'output', 'output_workdir', 'metadata', 'output_metadata']
        allow_nested_files = file_type in ['input', 'unstructured', 'output', 'output_workdir', 'metadata', 'output_metadata', 'tool']
        directory_source = getattr(self, TYPES_TO_METHOD.get(file_type, None), None)
        if not directory_source:
            raise Exception("Unknown file_type specified %s" % file_type)
        if callable(directory_source):
            directory_source = directory_source()
        return directory_source, allow_nested_files

    def _sub_dir(self, name):
        return self.path_helper.remote_join(self.job_directory, name)


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


def verify_is_in_directory(path, directory, local_path_module=os.path):
    if not in_directory(path, directory, local_path_module):
        msg = "Attempt to read or write file outside an authorized directory."
        log.warn("%s Attempted path: %s, valid directory: %s" % (msg, path, directory))
        raise Exception(msg)
