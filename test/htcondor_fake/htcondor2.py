"""Fake ``htcondor2`` module for testing the HTCondor manager without HTCondor.

``JobEventType`` integer values match the real htcondor2 library exactly so
that tests exercising event-log logic stay faithful to production behaviour.

Set :data:`AUTO_COMPLETE` (or ``PULSAR_TEST_FAKE_HTCONDOR_AUTO_COMPLETE`` for
the helper subprocess) to have ``Schedd.submit()`` actually run the submitted
script and inject completion events, so a manager can drive a job to
completion.  Otherwise the job stays queued and tests drive it by pushing
events with :meth:`JobEventLog.set_events`.
"""
import enum
import os
import re
import subprocess
import threading

AUTO_COMPLETE = os.environ.get("PULSAR_TEST_FAKE_HTCONDOR_AUTO_COMPLETE", "") == "1"

SUBMISSIONS: list = []
REMOVALS: list = []

_NEXT_CLUSTER_ID = 100
_NEXT_CLUSTER_ID_LOCK = threading.Lock()


def reset():
    """Clear all recorded state - call between tests."""
    global AUTO_COMPLETE
    AUTO_COMPLETE = False
    SUBMISSIONS[:] = []
    REMOVALS[:] = []
    JobEventLog.events_by_log.clear()


def _next_cluster_id():
    global _NEXT_CLUSTER_ID
    with _NEXT_CLUSTER_ID_LOCK:
        cluster_id = _NEXT_CLUSTER_ID
        _NEXT_CLUSTER_ID += 1
    return cluster_id


def _parse_submit_field(submit_description, field):
    match = re.search(rf"^{re.escape(field)}\s*=\s*(.+)$", submit_description, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else None


def _mark_job_queued(submit_description, cluster_id):
    log_path = _parse_submit_field(submit_description, "log")
    if log_path:
        JobEventLog.set_events(log_path, [FakeJobEvent(cluster_id, 0, JobEventType.SUBMIT)])


def _auto_complete_job(submit_description, cluster_id):
    """Run the submitted script and inject the events a completed job produces."""
    log_path = _parse_submit_field(submit_description, "log")
    executable = _parse_submit_field(submit_description, "executable")
    stdout_path = _parse_submit_field(submit_description, "output")
    stderr_path = _parse_submit_field(submit_description, "error")

    if executable and os.path.isfile(executable):
        with open(stdout_path or os.devnull, "w") as out_handle:
            with open(stderr_path or os.devnull, "w") as err_handle:
                subprocess.run(["/bin/bash", executable], stdout=out_handle, stderr=err_handle)

    if log_path:
        JobEventLog.set_events(log_path, [
            FakeJobEvent(cluster_id, 0, JobEventType.SUBMIT),
            FakeJobEvent(cluster_id, 0, JobEventType.EXECUTE),
            FakeJobEvent(cluster_id, 0, JobEventType.JOB_TERMINATED),
        ])


class Submit:

    def __init__(self, description):
        self.description = description


class SubmitResult:

    def __init__(self, cluster_id):
        self._cluster_id = cluster_id

    def cluster(self):
        return self._cluster_id


# Values match real htcondor2 exactly (IntEnum, same integers).
class JobEventType(enum.IntEnum):
    SUBMIT = 0
    EXECUTE = 1
    EXECUTABLE_ERROR = 2
    CHECKPOINTED = 3
    JOB_EVICTED = 4
    JOB_TERMINATED = 5
    IMAGE_SIZE = 6
    SHADOW_EXCEPTION = 7
    GENERIC = 8
    JOB_ABORTED = 9
    JOB_SUSPENDED = 10
    JOB_UNSUSPENDED = 11
    JOB_HELD = 12
    JOB_RELEASED = 13
    CLUSTER_SUBMIT = 35
    CLUSTER_REMOVE = 36


class JobAction(enum.IntEnum):
    Hold = 1
    Release = 2
    Remove = 3
    RemoveX = 4
    Vacate = 5
    VacateFast = 6
    Suspend = 8
    Continue = 9


class DaemonType(enum.IntEnum):
    Schedd = 1


class FakeJobEvent:

    def __init__(self, cluster, proc, event_type, **classad_attrs):
        self.cluster = cluster
        self.proc = proc
        self.type = event_type
        self._classad = classad_attrs

    def get(self, key, default=None):
        return self._classad.get(key, default)


class Collector:

    def __init__(self, pool=None):
        self.pool = pool

    def locate(self, daemon_type, name=None):
        return dict(Name=name or "schedd@local", MyAddress="addr", CondorVersion="v1", Pool=self.pool)

    def locateAll(self, daemon_type):
        return [self.locate(daemon_type)]


class JobEventLog:
    events_by_log: dict = {}

    def __init__(self, filename):
        self.filename = filename
        self.closed = False

    @classmethod
    def set_events(cls, filename, events):
        cls.events_by_log[filename] = list(events)

    def events(self, stop_after=None):
        # Like the real API, only events not yet consumed are returned.
        pending = self.events_by_log.pop(self.filename, [])
        yield from pending

    def close(self):
        self.closed = True


class Schedd:

    def __init__(self, location=None):
        self.location = location

    def submit(self, description, count=0, spool=False, itemdata=None, queue=None):
        cluster_id = _next_cluster_id()
        SUBMISSIONS.append(dict(
            collector=None if self.location is None else self.location.get("Pool"),
            schedd_name=None if self.location is None else self.location.get("Name"),
            submit_description=description.description,
            cluster_id=cluster_id,
        ))
        if AUTO_COMPLETE:
            _auto_complete_job(description.description, cluster_id)
        else:
            _mark_job_queued(description.description, cluster_id)
        return SubmitResult(cluster_id)

    def act(self, action, job_spec, reason=None):
        REMOVALS.append(dict(
            collector=None if self.location is None else self.location.get("Pool"),
            schedd_name=None if self.location is None else self.location.get("Name"),
            action=action.name if hasattr(action, "name") else str(action),
            job_spec=job_spec,
            reason=reason,
        ))
        return {}


def reload_config():
    return None
