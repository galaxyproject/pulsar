import os.path
from .action_mapper import FileActionMapper


class PathMapper(object):
    """ Ties together a FileActionMapper and remote job configuration returned
    by the LWR setup method to pre-determine the location of files for staging
    on the remote LWR server.

    This is not useful when rewrite_paths (as has traditionally been done with
    the LWR) because when doing that the LWR determines the paths as files are
    uploaded. When rewrite_paths is disabled however, the destination of files
    needs to be determined prior to transfer so an object of this class can be
    used.
    """

    def __init__(self, client, remote_job_config):
        self.action_mapper = FileActionMapper(client)
        self.input_directory = remote_job_config["inputs_directory"]
        self.output_directory = remote_job_config["outputs_directory"]
        self.working_directory = remote_job_config["working_directory"]
        self.config_directory = remote_job_config["configs_directory"]
        self.separator = remote_job_config["system_properties"]["separator"]

    def remote_path_rewrite(self, dataset_path, path_type):
        """ Return remote path of this file (if staging is required) else None.
        """
        path = str(dataset_path)  # Use false_path if needed.
        action = self.action_mapper.action(path, path_type)
        remote_path_rewrite = None
        if action.staging_needed:
            name = os.path.basename(path)
            remote_directory = self.__remote_directory(path_type)
            remote_path_rewrite = r"%s%s%s" % (remote_directory, self.separator, name)
        return remote_path_rewrite

    def __remote_directory(self, path_type):
        if path_type in ["output"]:
            return self.output_directory
        elif path_type in ["output_workdir", "workdir"]:
            return self.working_directory
        elif path_type in ["input"]:
            return self.input_directory
        else:
            message = "PathMapper cannot handle path type %s" % path_type
            raise Exception(message)

__all__ = [PathMapper]
