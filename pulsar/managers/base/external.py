import logging

from string import Template

from pulsar.managers import status
from .directory import DirectoryBaseManager
from six import binary_type

DEFAULT_JOB_NAME_TEMPLATE = "pulsar_$job_id"
JOB_FILE_EXTERNAL_ID = "external_id"
FAILED_TO_LOAD_EXTERNAL_ID = object()

log = logging.getLogger(__name__)


class ExternalBaseManager(DirectoryBaseManager):
    """ Base class for managers that interact with external distributed
    resource managers.
    """

    def __init__(self, name, app, **kwds):
        super(ExternalBaseManager, self).__init__(name, app, **kwds)
        self._external_ids = {}
        self.job_name_template = kwds.get('job_name_template', DEFAULT_JOB_NAME_TEMPLATE)

    def clean(self, job_id):
        super(ExternalBaseManager, self).clean(job_id)

    def setup_job(self, input_job_id, tool_id, tool_version):
        job_id = self._get_job_id(input_job_id)
        return self._setup_job_for_job_id(job_id, tool_id, tool_version)

    def kill(self, job_id):
        self._record_cancel(job_id)
        external_id = self._external_id(job_id)
        if external_id:
            try:
                self._kill_external(external_id)
            except Exception:
                log.exception("Failed to kill job with id %s and external id %s", job_id, external_id)

    def get_status(self, job_id):
        if self._was_cancelled(job_id):
            return status.CANCELLED
        external_id = self._external_id(job_id)
        if not external_id:
            raise KeyError("Failed to find external id for job_id %s" % job_id)
        return self._get_status_external(external_id)

    def _get_job_id(self, input_job_id):
        return str(self.id_assigner(input_job_id))

    def _register_external_id(self, job_id, external_id):
        if isinstance(external_id, binary_type):
            external_id = external_id.decode("utf-8")
        self._job_directory(job_id).store_metadata(JOB_FILE_EXTERNAL_ID, external_id)
        self._external_ids[job_id] = external_id
        return external_id

    def _external_id(self, job_id):
        return self._external_ids.get(job_id, None)

    def _job_name(self, job_id):
        env = self._job_template_env(job_id)
        return Template(self.job_name_template).safe_substitute(env)

    def _recover_active_job(self, job_id):
        external_id = self._job_directory(job_id).load_metadata(JOB_FILE_EXTERNAL_ID, FAILED_TO_LOAD_EXTERNAL_ID)
        if external_id and external_id is not FAILED_TO_LOAD_EXTERNAL_ID:
            self._external_ids[job_id] = external_id
        else:
            raise Exception("Could not determine external ID for job_id [%s]" % job_id)

    def _deactivate_job(self, job_id):
        del self._external_ids[job_id]
