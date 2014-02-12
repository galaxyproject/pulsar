import os

from lwr.managers import ManagerProxy


import logging
log = logging.getLogger(__name__)

DECACTIVATE_FAILED_MESSAGE = "Failed to deactivate job with job id %s. May be problems when starting LWR next."
ACTIVATE_FAILED_MESSAGE = "Failed to activate job wiht job id %s. This job may not recover properly upon LWR restart."

JOB_FILE_FINAL_STATUS = "final_status"


class StatefulManagerProxy(ManagerProxy):
    """
    """

    def __init__(self, manager):
        super(StatefulManagerProxy, self).__init__(manager)
        self.active_jobs = ActiveJobs(manager)
        self.__recover_active_jobs()

    def setup_job(self, *args, **kwargs):
        job_id = self._proxied_manager.setup_job(*args, **kwargs)
        self.active_jobs.activate_job(job_id)
        return job_id

    def get_status(self, job_id):
        job_directory = self._proxied_manager.job_directory(job_id)
        deactivate = False
        with job_directory.lock("status"):
            if job_directory.contains_file(JOB_FILE_FINAL_STATUS):
                proxy_status = job_directory.read_file(JOB_FILE_FINAL_STATUS)
            else:
                proxy_status = self._proxied_manager.get_status(job_id)
                if proxy_status in ['complete', 'cancelled']:
                    job_directory.write_file(JOB_FILE_FINAL_STATUS, proxy_status)
                    deactivate = True
        if deactivate:
            self.__deactivate(job_id)

        return proxy_status

    def __recover_active_jobs(self):
        recover_method = getattr(self._proxied_manager, "_recover_active_job", None)
        if recover_method is None:
            return

        for job_id in self.active_jobs.active_jobs():
            try:
                recover_method(job_id)
            except Exception:
                log.warn("Failed to recover active job %s" % job_id)

    def __deactivate(self, job_id):
        self.active_jobs.deactivate_job(job_id)
        deactivate_method = getattr(self._proxied_manager, "_deactivate_job", None)
        if deactivate_method:
            try:
                deactivate_method(job_id)
            except Exception:
                log.warn("Failed to deactivate via proxied manager job %s" % job_id)


class ActiveJobs(object):
    """ Keeps track of active jobs (those that are not yet "complete").
    Current implementation is file based, but could easily be made
    database-based instead.
    """

    def __init__(self, manager):
        persistence_directory = manager.persistence_directory
        if persistence_directory:
            active_job_directory = os.path.join(persistence_directory, "%s-active-jobs" % manager.name)
            if not os.path.exists(active_job_directory):
                os.makedirs(active_job_directory)
        else:
            active_job_directory = None
        self.active_job_directory = active_job_directory

    def active_jobs(self):
        job_ids = []
        if self.active_job_directory:
            job_ids = os.listdir(self.active_job_directory)
        return job_ids

    def activate_job(self, job_id):
        if self.active_job_directory:
            path = self._active_job_file(job_id)
            try:
                open(path, "w").close()
            except Exception:
                log.warn(ACTIVATE_FAILED_MESSAGE % job_id)

    def deactivate_job(self, job_id):
        if self.active_job_directory:
            path = self._active_job_file(job_id)
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    log.warn(DECACTIVATE_FAILED_MESSAGE % job_id)

    def _active_job_file(self, job_id):
        return os.path.join(self.active_job_directory, job_id)

__all__ = [StatefulManagerProxy]
