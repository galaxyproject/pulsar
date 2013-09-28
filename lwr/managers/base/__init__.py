"""

Base Classes and Infrastructure Supporting Concret Manager Implementations.

"""
from os.path import exists, isdir, join, basename
from os import listdir
from os import makedirs
from uuid import uuid4

from lwr.util import JobDirectory
from lwr.managers import ManagerInterface

JOB_DIRECTORY_INPUTS = "inputs"
JOB_DIRECTORY_OUTPUTS = "outputs"
JOB_DIRECTORY_WORKING = "working"
JOB_DIRECTORY_CONFIGS = "configs"
JOB_DIRECTORY_TOOL_FILES = "tool_files"

DEFAULT_ID_ASSIGNER = "galaxy"

ID_ASSIGNER = {
    # Generate a random id, needed if multiple
    # Galaxy instances submitting to same LWR.
    'uuid': lambda galaxy_job_id: uuid4().hex,
    # Pass galaxy id through, default for single
    # Galaxy LWR instance.
    'galaxy': lambda galaxy_job_id: galaxy_job_id
}

from logging import getLogger
log = getLogger(__name__)


def get_id_assigner(assign_ids):
    default_id_assigner = ID_ASSIGNER[DEFAULT_ID_ASSIGNER]
    return ID_ASSIGNER.get(assign_ids, default_id_assigner)


class BaseManager(ManagerInterface):

    def __init__(self, name, app, **kwds):
        self.name = name
        self.persistence_directory = getattr(app, 'persistence_directory', None)
        self._setup_staging_directory(app.staging_directory)
        self.id_assigner = get_id_assigner(kwds.get("assign_ids", None))
        self.debug = str(kwds.get("debug", False)).lower() == "true"
        self.authorizer = app.authorizer

    def clean(self, job_id):
        if self.debug:
            # In debug mode skip cleaning job directories.
            return

        job_directory = self._job_directory(job_id)
        if job_directory.exists():
            try:
                job_directory.delete()
            except:
                pass

    def working_directory(self, job_id):
        return self._job_directory(job_id).working_directory()

    def inputs_directory(self, job_id):
        return self._job_directory(job_id).inputs_directory()

    def outputs_directory(self, job_id):
        return self._job_directory(job_id).outputs_directory()

    def configs_directory(self, job_id):
        return self._job_directory(job_id).configs_directory()

    def tool_files_directory(self, job_id):
        return self._job_directory(job_id).tool_files_directory()

    def _setup_staging_directory(self, staging_directory):
        assert not staging_directory is None
        if not exists(staging_directory):
            makedirs(staging_directory)
        assert isdir(staging_directory)
        self.staging_directory = staging_directory

    def _job_directory(self, job_id):
        return JobDirectory(self.staging_directory, job_id)

    def _setup_job_directory(self, job_id):
        job_directory = self._job_directory(job_id)
        job_directory.setup()
        for directory in [JOB_DIRECTORY_INPUTS,
                          JOB_DIRECTORY_WORKING,
                          JOB_DIRECTORY_OUTPUTS,
                          JOB_DIRECTORY_CONFIGS,
                          JOB_DIRECTORY_TOOL_FILES]:
            job_directory.make_directory(directory)
        return job_directory

    def _build_persistent_store(self, store_class, suffix):
        store_path = None
        if self.persistence_directory:
            store_name = "%s_%s" % (self.name, suffix)
            store_path = join(self.persistence_directory, store_name)
        return store_class(store_path)

    def _get_authorization(self, job_id, tool_id):
        return self.authorizer.get_authorization(tool_id)

    def _check_execution(self, job_id, tool_id, command_line):
        log.debug("job_id: %s - Checking authorization of command_line [%s]" % (job_id, command_line))
        authorization = self._get_authorization(job_id, tool_id)
        job_directory = self._job_directory(job_id)
        tool_files_dir = self.tool_files_directory(job_id)
        for file in listdir(tool_files_dir):
            contents = open(join(tool_files_dir, file), 'r').read()
            log.debug("job_id: %s - checking tool file %s" % (job_id, file))
            authorization.authorize_tool_file(basename(file), contents)
        config_files_dir = self.configs_directory(job_id)
        for file in listdir(config_files_dir):
            path = join(config_files_dir, file)
            authorization.authorize_config_file(job_directory, file, path)
        authorization.authorize_execution(job_directory, command_line)
