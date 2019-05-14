from __future__ import division

import contextlib
import datetime
import os
import time
import threading

try:
    # If galaxy-lib or Galaxy 19.05 present.
    from galaxy.tools.deps.dependencies import DependenciesDescription
except ImportError:
    # If galaxy-tool-util or Galaxy 19.09 present.
    from galaxy.tool_util.deps.dependencies import DependenciesDescription

from pulsar.client.util import filter_destination_params
from pulsar.managers import ManagerProxy
from pulsar.managers import status
from pulsar.managers.util.retry import RetryActionExecutor
from .staging import preprocess
from .staging import postprocess

import logging
log = logging.getLogger(__name__)

DEFAULT_DO_MONITOR = False

DECACTIVATE_FAILED_MESSAGE = "Failed to deactivate job with job id %s. May cause problems on next Pulsar start."
ACTIVATE_FAILED_MESSAGE = "Failed to activate job with job id %s. This job may not recover properly upon Pulsar restart."

JOB_FILE_FINAL_STATUS = "final_status"
JOB_FILE_POSTPROCESSED = "postprocessed"
JOB_FILE_PREPROCESSED = "preprocessed"
JOB_FILE_PREPROCESSING_FAILED = "preprocessing_failed"
JOB_METADATA_RUNNING = "running"

ACTIVE_STATUS_PREPROCESSING = "preprocessing"
ACTIVE_STATUS_LAUNCHED = "launched"

DEFAULT_MIN_POLLING_INTERVAL = 0.5


class StatefulManagerProxy(ManagerProxy):
    """
    """

    def __init__(self, manager, **manager_options):
        super(StatefulManagerProxy, self).__init__(manager)
        min_polling_interval = float(manager_options.get("min_polling_interval", DEFAULT_MIN_POLLING_INTERVAL))
        preprocess_retry_action_kwds = filter_destination_params(manager_options, "preprocess_action_")
        postprocess_retry_action_kwds = filter_destination_params(manager_options, "postprocess_action_")
        self.__preprocess_action_executor = RetryActionExecutor(**preprocess_retry_action_kwds)
        self.__postprocess_action_executor = RetryActionExecutor(**postprocess_retry_action_kwds)
        self.min_polling_interval = datetime.timedelta(0, min_polling_interval)
        self.active_jobs = ActiveJobs.from_manager(manager)
        self.__state_change_callback = self._default_status_change_callback
        self.__monitor = None

    def set_state_change_callback(self, state_change_callback):
        self.__state_change_callback = state_change_callback
        self.__monitor = ManagerMonitor(self)

    def _default_status_change_callback(self, status, job_id):
        log.info("Status of job [%s] changed to [%s]. No callbacks enabled." % (job_id, status))

    @property
    def name(self):
        return self._proxied_manager.name

    def setup_job(self, *args, **kwargs):
        job_id = self._proxied_manager.setup_job(*args, **kwargs)
        return job_id

    def _persist_launch_config(self, job_id, launch_config):
        job_directory = self._proxied_manager.job_directory(job_id)
        job_directory.store_metadata("launch_config", launch_config)

    def touch_outputs(self, job_id, touch_outputs):
        job_directory = self._proxied_manager.job_directory(job_id)
        for name in touch_outputs:
            path = job_directory.calculate_path(name, 'output')
            job_directory.open_file(path, mode='a')

    def preprocess_and_launch(self, job_id, launch_config):
        self._persist_launch_config(job_id, launch_config)
        requires_preprocessing = launch_config.get("remote_staging") and launch_config["remote_staging"].get("setup")
        if requires_preprocessing:
            self.active_jobs.activate_job(job_id, active_status=ACTIVE_STATUS_PREPROCESSING)
            self._launch_prepreprocessing_thread(job_id, launch_config)
        else:
            with self._handling_of_preprocessing_state(job_id, launch_config):
                pass

    def _launch_prepreprocessing_thread(self, job_id, launch_config):
        def do_preprocess():
            with self._handling_of_preprocessing_state(job_id, launch_config):
                job_directory = self._proxied_manager.job_directory(job_id)
                staging_config = launch_config.get("remote_staging", {})
                # TODO: swap out for a generic "job_extra_params"
                if 'action_mapper' in staging_config and \
                        'ssh_key' in staging_config['action_mapper'] and \
                        'setup' in staging_config:
                    for action in staging_config['setup']:
                        action['action'].update(ssh_key=staging_config['action_mapper']['ssh_key'])
                preprocess(job_directory, staging_config.get("setup", []), self.__preprocess_action_executor)
                self.active_jobs.deactivate_job(job_id, active_status=ACTIVE_STATUS_PREPROCESSING)

        new_thread_for_job(self, "preprocess", job_id, do_preprocess, daemon=False)

    @contextlib.contextmanager
    def _handling_of_preprocessing_state(self, job_id, launch_config):
        job_directory = self._proxied_manager.job_directory(job_id)
        try:
            yield
            launch_kwds = {}
            if launch_config.get("dependencies_description"):
                dependencies_description = DependenciesDescription.from_dict(launch_config["dependencies_description"])
                launch_kwds["dependencies_description"] = dependencies_description
            for kwd in ["submit_params", "setup_params", "env"]:
                if kwd in launch_config:
                    launch_kwds[kwd] = launch_config[kwd]

            self._proxied_manager.launch(
                job_id,
                launch_config["command_line"],
                **launch_kwds
            )
            with job_directory.lock("status"):
                job_directory.store_metadata(JOB_FILE_PREPROCESSED, True)
            self.active_jobs.activate_job(job_id)
        except Exception as e:
            with job_directory.lock("status"):
                job_directory.store_metadata(JOB_FILE_PREPROCESSING_FAILED, True)
                job_directory.store_metadata("return_code", 1)
                job_directory.write_file("stderr", str(e))
            self.__state_change_callback(status.FAILED, job_id)
            log.exception("Failed job preprocessing for job %s:", job_id)

    def handle_failure_before_launch(self, job_id):
        self.__state_change_callback(status.FAILED, job_id)

    def get_status(self, job_id):
        """ Compute status used proxied manager and handle state transitions
        and track additional state information needed.
        """
        job_directory = self._proxied_manager.job_directory(job_id)
        with job_directory.lock("status"):
            proxy_status, state_change = self.__proxy_status(job_directory, job_id)

        if state_change == "to_complete":
            self.__deactivate(job_id, proxy_status)
        elif state_change == "to_running":
            self.__state_change_callback(status.RUNNING, job_id)

        return self.__status(job_directory, proxy_status)

    def __proxy_status(self, job_directory, job_id):
        """ Determine state with proxied job manager and if this job needs
        to be marked as deactivated (this occurs when job first returns a
        complete status from proxy.
        """
        state_change = None
        if job_directory.has_metadata(JOB_FILE_PREPROCESSING_FAILED):
            proxy_status = status.FAILED
            job_directory.store_metadata(JOB_FILE_FINAL_STATUS, proxy_status)
            state_change = "to_complete"
        elif not job_directory.has_metadata(JOB_FILE_PREPROCESSED):
            proxy_status = status.PREPROCESSING
        elif job_directory.has_metadata(JOB_FILE_FINAL_STATUS):
            proxy_status = job_directory.load_metadata(JOB_FILE_FINAL_STATUS)
        else:
            proxy_status = self._proxied_manager.get_status(job_id)
            if proxy_status == status.RUNNING:
                if not job_directory.has_metadata(JOB_METADATA_RUNNING):
                    job_directory.store_metadata(JOB_METADATA_RUNNING, True)
                    state_change = "to_running"
            elif proxy_status in [status.COMPLETE, status.CANCELLED]:
                job_directory.store_metadata(JOB_FILE_FINAL_STATUS, proxy_status)
                state_change = "to_complete"
        return proxy_status, state_change

    def __status(self, job_directory, proxy_status):
        """ Use proxied manager's status to compute the real
        (stateful) status of job.
        """
        if proxy_status == status.COMPLETE:
            if not job_directory.has_metadata(JOB_FILE_POSTPROCESSED):
                job_status = status.POSTPROCESSING
            else:
                job_status = status.COMPLETE
        else:
            job_status = proxy_status
        return job_status

    def __deactivate(self, job_id, proxy_status):
        self.active_jobs.deactivate_job(job_id)
        deactivate_method = getattr(self._proxied_manager, "_deactivate_job", None)
        if deactivate_method:
            try:
                deactivate_method(job_id)
            except Exception:
                log.exception("Failed to deactivate via proxied manager job %s" % job_id)
        if proxy_status == status.COMPLETE:
            self.__handle_postprocessing(job_id)

    def __handle_postprocessing(self, job_id):
        def do_postprocess():
            postprocess_success = False
            job_directory = self._proxied_manager.job_directory(job_id)
            try:
                postprocess_success = postprocess(job_directory, self.__postprocess_action_executor)
            except Exception:
                log.exception("Failed to postprocess results for job id %s" % job_id)
            final_status = status.COMPLETE if postprocess_success else status.FAILED
            if job_directory.has_metadata(JOB_FILE_PREPROCESSING_FAILED):
                final_status = status.FAILED
            self.__state_change_callback(final_status, job_id)
        new_thread_for_job(self, "postprocess", job_id, do_postprocess, daemon=False)

    def shutdown(self, timeout=None):
        if self.__monitor:
            try:
                self.__monitor.shutdown(timeout)
            except Exception:
                log.exception("Failed to shutdown job monitor for manager %s" % self.name)
        super(StatefulManagerProxy, self).shutdown(timeout)

    def recover_active_jobs(self):
        unqueue_preprocessing_ids = []
        for job_id in self.active_jobs.active_job_ids(active_status=ACTIVE_STATUS_PREPROCESSING):
            job_directory = self._proxied_manager.job_directory(job_id)
            if not job_directory.has_metadata("launch_config"):
                log.warn("Failed to find launch parameters for job scheduled to prepreprocess [%s]" % job_id)
                unqueue_preprocessing_ids.append(job_id)
            elif job_directory.has_metadata(JOB_FILE_PREPROCESSED):
                log.warn("Job scheduled to prepreprocess [%s] already preprocessed, skipping" % job_id)
                unqueue_preprocessing_ids.append(job_id)
            elif job_directory.has_metadata(JOB_FILE_PREPROCESSING_FAILED):
                log.warn("Job scheduled to prepreprocess [%s] previously failed preprocessing, skipping" % job_id)
                unqueue_preprocessing_ids.append(job_id)
            else:
                launch_config = job_directory.load_metadata("launch_config")
                self._launch_prepreprocessing_thread(job_id, launch_config)

        for unqueue_preprocessing_id in unqueue_preprocessing_ids:
            self.active_jobs.deactivate_job(unqueue_preprocessing_id, active_status=ACTIVE_STATUS_PREPROCESSING)

        recover_method = getattr(self._proxied_manager, "_recover_active_job", None)
        if recover_method is None:
            return

        for job_id in self.active_jobs.active_job_ids(active_status=ACTIVE_STATUS_LAUNCHED):
            try:
                recover_method(job_id)
            except Exception:
                log.exception("Failed to recover active job %s" % job_id)
                self.__handle_recovery_problem(job_id)

    def __handle_recovery_problem(self, job_id):
        # Make sure we tell the client we have lost this job.
        self.active_jobs.deactivate_job(job_id)
        self.__state_change_callback(status.LOST, job_id)


class ActiveJobs(object):
    """ Keeps track of active jobs (those that are not yet "complete").
    Current implementation is file based, but could easily be made
    database-based instead.

    TODO: Keep jobs in memory after initial load so don't need to repeatedly
    hit disk to recover this information.
    """

    @staticmethod
    def from_manager(manager):
        persistence_directory = manager.persistence_directory
        manager_name = manager.name
        return ActiveJobs(manager_name, persistence_directory)

    def __init__(self, manager_name, persistence_directory):
        if persistence_directory:
            active_job_directory = os.path.join(persistence_directory, "%s-active-jobs" % manager_name)
            if not os.path.exists(active_job_directory):
                os.makedirs(active_job_directory)
            preprocessing_job_directory = os.path.join(persistence_directory, "%s-preprocessing-jobs" % manager_name)
            if not os.path.exists(preprocessing_job_directory):
                os.makedirs(preprocessing_job_directory)
        else:
            active_job_directory = None
            preprocessing_job_directory = None
        self.launched_job_directory = active_job_directory
        self.preprocessing_job_directory = preprocessing_job_directory

    def active_job_ids(self, active_status=ACTIVE_STATUS_LAUNCHED):
        job_ids = []
        target_directory = self._active_job_directory(active_status)
        if target_directory:
            job_ids = os.listdir(target_directory)
        return job_ids

    def activate_job(self, job_id, active_status=ACTIVE_STATUS_LAUNCHED):
        if self._active_job_directory(active_status):
            path = self._active_job_file(job_id, active_status=active_status)
            try:
                open(path, "w").close()
            except Exception:
                log.warn(ACTIVATE_FAILED_MESSAGE % job_id)

    def deactivate_job(self, job_id, active_status=ACTIVE_STATUS_LAUNCHED):
        if self._active_job_directory(active_status):
            path = self._active_job_file(job_id, active_status=active_status)
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    log.warn(DECACTIVATE_FAILED_MESSAGE % job_id)

    def _active_job_directory(self, active_status):
        if active_status == ACTIVE_STATUS_LAUNCHED:
            target_directory = self.launched_job_directory
        elif active_status == ACTIVE_STATUS_PREPROCESSING:
            target_directory = self.preprocessing_job_directory
        else:
            raise Exception("Unknown active state encountered [%s]" % active_status)
        return target_directory

    def _active_job_file(self, job_id, active_status=ACTIVE_STATUS_LAUNCHED):
        return os.path.join(self._active_job_directory(active_status), job_id)


class ManagerMonitor(object):
    """ Monitors active jobs of a StatefulManagerProxy.
    """

    def __init__(self, stateful_manager):
        self.stateful_manager = stateful_manager
        self.active = True
        thread = new_thread_for_manager(self.stateful_manager, "[action=monitor]", self._run, True)
        self.thread = thread

    def shutdown(self, timeout=None):
        self.active = False
        self.thread.join(timeout)
        if self.thread.isAlive():
            log.warn("Failed to join monitor thread [%s]" % self.thread)

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
        iteration_start = datetime.datetime.now()
        for active_job_id in active_job_ids:
            try:
                self._check_active_job_status(active_job_id)
            except Exception:
                log.exception("Failed checking active job status for job_id %s" % active_job_id)
        iteration_end = datetime.datetime.now()
        iteration_length = iteration_end - iteration_start
        if iteration_length < self.stateful_manager.min_polling_interval:
            to_sleep = (self.stateful_manager.min_polling_interval - iteration_length)
            microseconds = to_sleep.microseconds + (to_sleep.seconds + to_sleep.days * 24 * 3600) * (10 ** 6)
            total_seconds = microseconds / (10 ** 6)
            time.sleep(total_seconds)

    def _check_active_job_status(self, active_job_id):
        # Manager itself will handle state transitions when status changes,
        # just need to poll get_status
        self.stateful_manager.get_status(active_job_id)


def new_thread_for_job(manager, action, job_id, target, daemon):
    name = "[action=%s]-[job=%s]" % (action, job_id)
    return new_thread_for_manager(manager, name, target, daemon)


def new_thread_for_manager(manager, name, target, daemon):
    thread_name = "[manager=%s]-%s" % (manager.name, name)
    thread = threading.Thread(name=thread_name, target=target)
    thread.daemon = daemon
    thread.start()
    return thread


__all__ = ('StatefulManagerProxy',)
