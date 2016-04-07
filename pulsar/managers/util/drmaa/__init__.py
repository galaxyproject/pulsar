import contextlib
import logging
import threading

try:
    from drmaa import Session, JobControlAction
except OSError as e:
    LOAD_ERROR_MESSAGE = "OSError - problem loading shared library [%s]." % e
    Session = None
except ImportError as e:
    LOAD_ERROR_MESSAGE = "ImportError - problem importing library (`pip install drmaa` may fix this) [%s]." % e
    # Will not be able to use DRMAA
    Session = None

NO_DRMAA_MESSAGE = "Attempt to use DRMAA, but DRMAA Python library cannot be loaded. "

log = logging.getLogger(__name__)


class DrmaaSessionFactory(object):
    """
    Abstraction used to production DrmaaSession wrappers.
    """
    def __init__(self):
        self.session_constructor = Session

    def get(self, **kwds):
        session_constructor = self.session_constructor
        if session_constructor is None:
            raise Exception(NO_DRMAA_MESSAGE + LOAD_ERROR_MESSAGE)
        return DrmaaSession(session_constructor, **kwds)


class DrmaaSession(object):
    """
    Abstraction around `drmaa` module `Session` objects.
    """
    session_lock = threading.Lock()
    session_count = 0
    session = None

    def __init__(self, session_constructor, **kwds):
        with self._session_lock():
            if DrmaaSession.session is None:
                if DrmaaSession.session_count != 0:
                    log.warn("DrmaaSession.session is None but session_count is non-zero - logic error occurred.")
                log.debug("Initializing DRMAA session from thread %s", threading.current_thread().name)
                DrmaaSession.session = session_constructor()
                DrmaaSession.session.initialize()
            DrmaaSession.session_count += 1

    @contextlib.contextmanager
    def _session_lock(self):
        with DrmaaSession.session_lock:
            yield

    def run_job(self, **kwds):
        """
        Create a DRMAA job template, populate with specified properties,
        run the job, and return the external_job_id.
        """
        template = DrmaaSession.session.createJobTemplate()
        try:
            for key in kwds:
                setattr(template, key, kwds[key])
            with DrmaaSession.session_lock:
                return DrmaaSession.session.runJob(template)
        finally:
            DrmaaSession.session.deleteJobTemplate(template)

    def kill(self, external_job_id):
        with DrmaaSession.session_lock:
            return DrmaaSession.session.control(str(external_job_id), JobControlAction.TERMINATE)

    def job_status(self, external_job_id):
        return DrmaaSession.session.jobStatus(str(external_job_id))

    def close(self):
        with self._session_lock():
            if DrmaaSession.session_count == 0:
                log.warn("close() called with zero active session counted - logic error.")
                return

            DrmaaSession.session_count -= 1
            if DrmaaSession.session_count == 0:
                if DrmaaSession.session is None:
                    log.warn("close() called with a non-zero session count but no session is defined.")
                    return

                DrmaaSession.session.exit()
                DrmaaSession.session = None


__all__ = ['DrmaaSessionFactory']
