"""Thread-safe append-only recorder of status updates received from Pulsar.

Tests assert against this recorder via the ``/_recorder`` endpoints exposed by
the mock Galaxy app: list events, await a terminal status for a given job,
clear between scenarios.

This recorder is the canonical model for what Galaxy itself should do with
Pulsar status updates:

1. **Dedupe by (job_id, status).** Pulsar's outbox can legitimately
   re-publish a message whose ack was lost but whose payload reached the
   broker. Galaxy's job state machine is naturally idempotent in
   ``(job_id, status)``, so the duplicate is just dropped.

2. **Refuse non-terminal-after-terminal regressions.** The outbox itself is
   FIFO per Pulsar instance, but a redelivery from broker durability or a
   replay across a Pulsar restart could in principle expose Galaxy to a
   stale, in-flight status (e.g. a buffered ``running`` arriving after
   ``complete``). Once a job has reached a terminal status, drop any
   non-terminal updates for it.

3. **Allow explicit Galaxy-side resets.** Operators (or Galaxy itself) need
   to reset a job — e.g. resubmit after cancel, or restart a failed job.
   Such transitions deliberately re-enter a non-terminal state from a
   terminal one. Mark the reset payload with ``_galaxy_reset_token`` (any
   truthy value): the recorder treats that update as a fresh epoch and
   forgets the prior history for that job_id.
"""
import threading
import time
from collections import defaultdict


class StatusRecorder:
    TERMINAL = {"complete", "failed", "cancelled", "lost"}

    def __init__(self):
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._events = []
        self._by_job = defaultdict(list)

    def record(self, payload):
        job_id = payload.get("job_id", "unknown")
        status = payload.get("status", "unknown")
        reset_token = payload.get("_galaxy_reset_token")
        ts = time.time()
        event = {
            "job_id": job_id,
            "status": status,
            "ts": ts,
            "reset_token": reset_token,
            "payload": payload,
        }
        with self._cv:
            prior_events = self._by_job.get(job_id, ())
            if reset_token:
                # Galaxy explicitly restarted the job; forget its prior
                # transitions so the new lifecycle can replay from scratch.
                self._by_job[job_id] = []
                # Keep the global event log; it's a record of what was
                # observed in time, not the authoritative state.
                self._events.append(event)
                self._by_job[job_id].append(event)
                self._cv.notify_all()
                return

            # Dedupe by (job_id, status).
            for prior in prior_events:
                if prior["status"] == status:
                    return

            # Regression guard: once a job has reached a terminal status,
            # any subsequent update without a reset_token is stale. This
            # covers both "non-terminal after terminal" (an old buffered
            # ``running``) and "different terminal after terminal" (a
            # delayed ``failed`` after ``complete`` or vice versa).
            if prior_events:
                last_status = prior_events[-1]["status"]
                if last_status in self.TERMINAL:
                    return

            self._events.append(event)
            self._by_job[job_id].append(event)
            self._cv.notify_all()

    def events(self, job_id=None):
        with self._lock:
            if job_id is None:
                return list(self._events)
            return list(self._by_job.get(job_id, ()))

    def clear(self):
        with self._lock:
            self._events.clear()
            self._by_job.clear()

    def await_terminal(self, job_id, timeout=60.0):
        deadline = time.time() + timeout
        with self._cv:
            while True:
                for ev in self._by_job.get(job_id, ()):
                    if ev["status"] in self.TERMINAL:
                        return ev
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                self._cv.wait(timeout=remaining)
