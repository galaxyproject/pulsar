import os
import threading

from lwr.managers import ManagerProxy
from lwr.managers import status
from lwr.lwr_client.action_mapper import from_dict

import logging
log = logging.getLogger(__name__)

DEFAULT_DO_MONITOR = False

DECACTIVATE_FAILED_MESSAGE = "Failed to deactivate job with job id %s. May be problems when starting LWR next."
ACTIVATE_FAILED_MESSAGE = "Failed to activate job wiht job id %s. This job may not recover properly upon LWR restart."

JOB_FILE_FINAL_STATUS = "final_status"
JOB_FILE_POSTPROCESSED = "postprocessed"


class StatefulManagerProxy(ManagerProxy):
    """
    """

    def __init__(self, manager, **manager_options):
        super(StatefulManagerProxy, self).__init__(manager)
        self.active_jobs = ActiveJobs(manager)
        self.__recover_active_jobs()
        monitor = None
        if manager_options.get("monitor", DEFAULT_DO_MONITOR):
            monitor = ManagerMonitor(self)
        self.__monitor = monitor

    @property
    def name(self):
        return self._proxied_manager.name

    def setup_job(self, *args, **kwargs):
        job_id = self._proxied_manager.setup_job(*args, **kwargs)
        self.active_jobs.activate_job(job_id)
        return job_id

    def handle_remote_staging(self, job_id, remote_staging_config):
        # TODO: Serialize and handle postprocessing.
        # TODO: Introduce preprocessing state and do this preprocessing step
        #  asynchronously.
        for remote_staging_action in remote_staging_config.get("setup", []):
            name = remote_staging_action["name"]
            input_type = remote_staging_action["type"]
            action = from_dict(remote_staging_action["action"])
            path = self._proxied_manager.job_directory(job_id).calculate_input_path(name, input_type)
            action.write_to_path(path)

    def get_status(self, job_id):
        job_directory = self._proxied_manager.job_directory(job_id)
        deactivate = False
        with job_directory.lock("status"):
            if job_directory.contains_file(JOB_FILE_FINAL_STATUS):
                proxy_status = job_directory.read_file(JOB_FILE_FINAL_STATUS)
            else:
                proxy_status = self._proxied_manager.get_status(job_id)
                if proxy_status in [status.COMPLETE, status.CANCELLED]:
                    job_directory.write_file(JOB_FILE_FINAL_STATUS, proxy_status)
                    deactivate = True
        if deactivate:
            self.__deactivate(job_id)
            if proxy_status == status.COMPLETE:
                self.__postprocess(job_id)

        if proxy_status == status.COMPLETE:
            if not job_directory.contains_file(JOB_FILE_POSTPROCESSED):
                job_status = status.POSTPROCESSING
            else:
                job_status = status.COMPLETE
        else:
            job_status = proxy_status

        return job_status

    def shutdown(self):
        if self.__monitor:
            try:
                self.__monitor.shutdown()
            except Exception:
                log.exception("Failed to shutdown job monitor for manager %s" % self.name)
        super(StatefulManagerProxy, self).shutdown()

    def __postprocess(self, job_id):
        # TODO: Postprocess in new thread and then write this file.
        self._proxied_manager.job_directory(job_id).write_file(JOB_FILE_POSTPROCESSED, "")

    def __recover_active_jobs(self):
        recover_method = getattr(self._proxied_manager, "_recover_active_job", None)
        if recover_method is None:
            return

        for job_id in self.active_jobs.active_job_ids():
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

    TODO: Keep active jobs in memory after initial load so don't need to repeatedly
    hit disk to recover this information.
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

    def active_job_ids(self):
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


class ManagerMonitor(object):
    """ Monitors active jobs of a StatefulManagerProxy.
    """

    def __init__(self, stateful_manager):
        self.stateful_manager = stateful_manager
        self.active = True
        name = "%s-monitor-thread" % stateful_manager.name
        thread = threading.Thread(name=name)
        thread.daemon = True
        thread.start()
        self.thread = thread

    def shutdown(self):
        self.active = False
        self.thread.join()

    def _run(self):
        """ Main loop, repeatedly checking active jobs of stateful manager.
        """
        while self.active:
            try:
                self._monitor_active_jobs()
            except Exception:
                log.exception("Failure in stateful manager monitor step.")

    def _monitor_active_jobs(self):
        active_job_ids = self.stateful_manager.active_jobs.active_job_ids()
        for active_job_id in active_job_ids:
            try:
                self._check_active_job_status(active_job_id)
            except Exception:
                log.exception("Failed checking active job status for job_id %s" % active_job_id)

    def _check_active_job_status(self, active_job_id):
        # Manager itself will handle state transitions when status changes,
        # just need to poll get_statu
        self.stateful_manager.get_status(active_job_id)


__all__ = [StatefulManagerProxy]
