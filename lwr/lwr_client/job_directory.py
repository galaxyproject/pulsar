"""
"""
from .util import PathHelper


class RemoteJobDirectory(object):
    """ Representation of a (potentially) remote LWR-style staging directory.
    """

    def __init__(self, remote_staging_directory, remote_id, remote_sep):
        self.path_helper = PathHelper(remote_sep)
        self.job_directory = self.path_helper.remote_join(
            remote_staging_directory,
            remote_id
        )

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

    def _sub_dir(self, name):
        return self.path_helper.remote_join(self.job_directory, name)
