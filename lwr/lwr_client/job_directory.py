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

    def directory_for_input_type(self, input_type, remote_path):
        allow_nested_files = False
        # work_dir and input_extra are types used by legacy clients...
        # Obviously this client won't be legacy because this is in the
        # client module, but this code is reused on server which may
        # serve legacy clients.
        if input_type in ['input', 'input_extra']:
            directory = self.inputs_directory()
            allow_nested_files = True
        elif input_type in ['unstructured']:
            directory = self.unstructured_files_directory()
            allow_nested_files = True
        elif input_type == 'config':
            directory = self.configs_directory()
        elif input_type == 'tool':
            directory = self.tool_files_directory()
        elif input_type in ['work_dir', 'workdir']:
            directory = self.working_directory()
        else:
            raise Exception("Unknown input_type specified %s" % input_type)
        return directory, allow_nested_files

    def _sub_dir(self, name):
        return self.path_helper.remote_join(self.job_directory, name)
