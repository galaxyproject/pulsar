"""Send tool stdout/stderr to Galaxy while jobs are still running.

One reporter thread per manager walks the jobs that have live output enabled
and POSTs the bytes each stream gained since the last update to Galaxy's job
files endpoint, which appends them to the job's ``outputs/tool_stdout`` and
``outputs/tool_stderr``.

The reporter is built so its cost stays bounded as the number of running jobs
grows:

- a single thread serves every job, so Pulsar holds no thread per job and
  Galaxy sees at most one live output request at a time from this manager;
- it never asks the scheduler for job status: the stateful manager adds a job
  when it sees it start running and removes it when it sees it finish;
- a job with no new output costs two ``stat`` calls per interval, since read
  offsets are kept in memory and written to the job directory only when they
  move;
- every POST is limited in size and time, and the total sent per stream never
  exceeds ``maximum_stream_size``;
- transient Galaxy failures pause updates for the whole endpoint with
  exponential backoff instead of being retried by every job every interval.
"""
import contextlib
import logging
import random
import threading
import time
from pathlib import Path
from typing import (
    Dict,
    Optional,
    Tuple,
)
from urllib.parse import (
    urlencode,
    urlsplit,
)

import requests

from pulsar.client.transport.requests import post_bytes
from pulsar.client.transport.transient import (
    http_status_code,
    is_transient_http_error,
)
from pulsar.managers.base.directory import (
    TOOL_FILE_STANDARD_ERROR,
    TOOL_FILE_STANDARD_OUTPUT,
)

log = logging.getLogger(__name__)

JOB_FILE_LIVE_OUTPUT_STATE = "live_output_state"
STREAMS = (TOOL_FILE_STANDARD_OUTPUT, TOOL_FILE_STANDARD_ERROR)

DEFAULT_INTERVAL = 3.0
DEFAULT_TIMEOUT = 30.0
# Stays under nginx's default client_max_body_size of 1m with multipart overhead.
DEFAULT_CHUNK_SIZE = 512 * 1024
MAX_BACKOFF = 300.0
# Chunks the completion flush may send before handing the rest to the
# completion status, so a large backlog cannot hold up output staging.
MAX_FINISH_CHUNKS = 8


def load_state(job_directory) -> dict:
    """Read a job's persisted read offsets and delivery flag."""
    try:
        state = job_directory.load_metadata(JOB_FILE_LIVE_OUTPUT_STATE, None)
    except Exception:
        # A partially written state file; start over rather than fail the job.
        state = None
    if not isinstance(state, dict):
        state = {}
    return {
        TOOL_FILE_STANDARD_OUTPUT: int(state.get(TOOL_FILE_STANDARD_OUTPUT, 0)),
        TOOL_FILE_STANDARD_ERROR: int(state.get(TOOL_FILE_STANDARD_ERROR, 0)),
        "delivered": bool(state.get("delivered", False)),
    }


def live_output_target(job_directory) -> Optional[Tuple[str, Path]]:
    """Return ``(files_endpoint, galaxy_outputs_directory)`` for a job.

    ``None`` when the job was not set up with remote staging (e.g. a shared
    file system deployment), because there is then nowhere to send output.
    """
    try:
        launch_config = job_directory.load_metadata("launch_config", None) or {}
        remote_staging = launch_config.get("remote_staging") or {}
        files_endpoint = remote_staging["action_mapper"]["files_endpoint"]
        working_directory = remote_staging["client_outputs"]["working_directory"]
    except (KeyError, TypeError, AttributeError):
        return None
    if not files_endpoint or not working_directory:
        return None
    return files_endpoint, Path(working_directory).parent / "outputs"


class _JobDirectoryGone(Exception):
    pass


class _LiveJob:
    """Per-job live output state; ``lock`` serializes all sends for the job."""

    def __init__(self, job_id: str, job_directory, files_endpoint: str, galaxy_outputs: Path):
        self.job_id = job_id
        self.job_directory = job_directory
        self.endpoint = urlsplit(files_endpoint).netloc or files_endpoint
        separator = "&" if "?" in files_endpoint else "?"
        self.urls: Dict[str, Tuple[str, str]] = {}
        for stream in STREAMS:
            galaxy_path = galaxy_outputs / Path(stream).name
            query = urlencode({"path": str(galaxy_path), "file_type": "output"})
            self.urls[stream] = (files_endpoint + separator + query, galaxy_path.name)
        state = load_state(job_directory)
        self.offsets = {stream: state[stream] for stream in STREAMS}
        self.delivered = state["delivered"]
        self.lock = threading.Lock()
        self.finished = False
        self.failures = 0
        self.next_due = 0.0

    def store(self) -> None:
        state: dict = dict(self.offsets)
        state["delivered"] = self.delivered
        # Atomic: a torn write would reset the offsets and resend everything,
        # which Galaxy would append a second time.
        self.job_directory.store_metadata(JOB_FILE_LIVE_OUTPUT_STATE, state, atomic=True)


class LiveOutputReporter:
    """Streams running jobs' stdout/stderr to Galaxy from one background thread."""

    def __init__(
        self,
        manager,
        interval: float = DEFAULT_INTERVAL,
        timeout: float = DEFAULT_TIMEOUT,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        maximum_stream_size: int = -1,
        name: str = "live_output",
    ):
        self._manager = manager
        self.interval = float(interval)
        self.timeout = float(timeout)
        self.chunk_size = int(chunk_size)
        self.maximum_stream_size = int(maximum_stream_size or -1)
        self._name = name
        self._jobs: Dict[str, _LiveJob] = {}
        self._jobs_lock = threading.Lock()
        # endpoint -> (monotonic time updates may resume, current backoff delay)
        self._backoff: Dict[str, Tuple[float, float]] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._session: Optional[requests.Session] = None

    def watch(self, job_id: str) -> bool:
        """Start sending live output for a job that is now running."""
        job_directory = self._manager.job_directory(job_id)
        target = live_output_target(job_directory)
        if target is None:
            log.debug("No Galaxy files endpoint for job %s, not sending live output", job_id)
            return False
        job = _LiveJob(job_id, job_directory, *target)
        # Spread first updates so jobs started together don't stay in lockstep.
        job.next_due = time.monotonic() + random.uniform(0, self.interval)
        with self._jobs_lock:
            self._jobs.setdefault(job_id, job)
            self._ensure_started()
        return True

    def forget(self, job_id: str) -> None:
        """Stop live output for a job that ended without postprocessing.

        Its tail is not sent; instead the job is marked undelivered so the
        completion status carries its streams, which Galaxy prefers over the
        partial files. Does not wait for an in-flight update of the job.
        """
        with self._jobs_lock:
            job = self._jobs.pop(job_id, None)
        if job is None:
            job_directory = self._manager.job_directory(job_id)
            if not load_state(job_directory)["delivered"]:
                return
            target = live_output_target(job_directory)
            if target is None:
                return
            job = _LiveJob(job_id, job_directory, *target)
        if job.lock.acquire(blocking=False):
            try:
                self._abandon(job)
            finally:
                job.lock.release()
        else:
            # Called from the status monitor, which must not wait on a POST.
            threading.Thread(
                name="[manager=%s]-[action=live_output_abandon]-[job=%s]" % (self._name, job_id),
                target=self._abandon_locked,
                args=(job,),
                daemon=True,
            ).start()

    def finish(self, job_id: str) -> bool:
        """Send the rest of a finished job's streams before its completion status.

        Returns whether Galaxy now holds both complete streams. When it does
        not, the job is marked undelivered so that the completion status
        carries the streams instead - Galaxy prefers those over its partial
        files, so nothing is lost or duplicated.
        """
        with self._jobs_lock:
            job = self._jobs.pop(job_id, None)
        if job is None:
            job_directory = self._manager.job_directory(job_id)
            if not load_state(job_directory)["delivered"]:
                return False
            target = live_output_target(job_directory)
            if target is None:
                return False
            job = _LiveJob(job_id, job_directory, *target)
        # Waits for an in-flight update of this job, bounded by the POST timeout.
        with job.lock:
            job.finished = True
            if not job.delivered:
                # Nothing reached Galaxy while running: no extra requests needed.
                return False
            try:
                if self._retry_at(job.endpoint) > time.monotonic():
                    raise Exception("live output updates to %s are backed off" % job.endpoint)
                chunks = 0
                for stream in STREAMS:
                    while True:
                        posted, more = self._send_chunk(job, stream, session=None)
                        chunks += posted
                        if not more:
                            break
                        if chunks >= MAX_FINISH_CHUNKS:
                            raise Exception("more than %d chunks of output left" % chunks)
                    if job.offsets[stream] == 0:
                        # Galaxy reads this file when the status omits the stream.
                        self._post(job, stream, b"", session=None)
                return True
            except Exception as e:
                log.warning(
                    "Failed to send the remaining live output for job %s, "
                    "sending the streams with the completion status instead: %s",
                    job_id,
                    e,
                )
                job.delivered = False
                job.store()
                return False

    def _abandon_locked(self, job: _LiveJob) -> None:
        with job.lock:
            self._abandon(job)

    def _abandon(self, job: _LiveJob) -> None:
        job.finished = True
        if job.delivered:
            job.delivered = False
            try:
                job.store()
            except Exception:
                log.exception("Failed to mark live output of job %s undelivered", job.job_id)

    def shutdown(self, timeout: Optional[float] = None) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _ensure_started(self) -> None:
        if self._thread is None and not self._stop.is_set():
            self._thread = threading.Thread(
                name="[manager=%s]-[action=live_output]" % self._name, target=self._run
            )
            # Nothing is lost if a shutdown interrupts an update: the offsets
            # on disk only move after Galaxy accepted the bytes. A POST that
            # Galaxy accepted just before the process died is sent again.
            self._thread.daemon = True
            self._thread.start()

    def _run(self) -> None:
        self._session = requests.Session()
        try:
            while not self._stop.is_set():
                self._run_once()
                with self._jobs_lock:
                    next_due = min((job.next_due for job in self._jobs.values()), default=None)
                delay = self.interval if next_due is None else next_due - time.monotonic()
                self._stop.wait(min(self.interval, max(delay, 0.05)))
        finally:
            self._session.close()

    def _run_once(self) -> None:
        now = time.monotonic()
        with self._jobs_lock:
            due = sorted(
                (job for job in self._jobs.values() if job.next_due <= now),
                key=lambda job: job.next_due,
            )
        for job in due:
            if self._stop.is_set():
                return
            try:
                self._update(job)
            except Exception:
                log.exception("Unexpected error sending live output for job %s", job.job_id)
                job.next_due = time.monotonic() + self.interval

    def _update(self, job: _LiveJob) -> None:
        with job.lock:
            self._update_locked(job)

    def _update_locked(self, job: _LiveJob) -> None:
        if job.finished:
            return
        now = time.monotonic()
        retry_at = self._retry_at(job.endpoint)
        if retry_at > now:
            job.next_due = retry_at
            return
        posted = more = False
        try:
            for stream in STREAMS:
                stream_posted, stream_more = self._send_chunk(job, stream, self._session)
                posted = posted or stream_posted
                more = more or stream_more
        except _JobDirectoryGone:
            self._drop(job)
            return
        except Exception as e:
            self._handle_failure(job, e)
            return
        if posted:
            # Only a request that went through shows Galaxy has recovered.
            self._backoff.pop(job.endpoint, None)
            job.failures = 0
        # Catch up straight away if a chunk limit left output unsent.
        job.next_due = now if more else now + self.interval

    def _send_chunk(self, job: _LiveJob, stream: str, session) -> Tuple[bool, bool]:
        """POST the next unsent chunk of ``stream``.

        Returns ``(posted, more)``: whether a request was made and whether
        more output is waiting.
        """
        data, more = self._read_chunk(job, stream)
        if not data:
            return False, False
        self._post(job, stream, data, session)
        job.offsets[stream] += len(data)
        job.delivered = True
        job.store()
        return True, more

    def _read_chunk(self, job: _LiveJob, stream: str) -> Tuple[bytes, bool]:
        """Read up to ``chunk_size`` new bytes of ``stream``.

        Returns raw bytes: a chunk boundary can fall inside a multi-byte UTF-8
        sequence, and Galaxy appends the upload verbatim.
        """
        offset = job.offsets[stream]
        try:
            size = job.job_directory.file_size(stream)
        except FileNotFoundError:
            if not job.job_directory.exists():
                raise _JobDirectoryGone()
            # The tool has not started writing yet.
            return b"", False
        available = size - offset
        if self.maximum_stream_size > 0:
            available = min(available, self.maximum_stream_size - offset)
        if available <= 0:
            return b"", False
        to_read = min(available, self.chunk_size)
        with contextlib.closing(job.job_directory.open_file(stream, mode="rb")) as file_output:
            file_output.seek(offset)
            data = file_output.read(to_read)
        return data, available > len(data)

    def _post(self, job: _LiveJob, stream: str, data: bytes, session) -> None:
        url, name = job.urls[stream]
        post_bytes(url, name, data, session=session, timeout=self.timeout)
        log.debug("Posted %d bytes of live output for job %s to %s", len(data), job.job_id, name)

    def _retry_at(self, endpoint: str) -> float:
        return self._backoff.get(endpoint, (0.0, 0.0))[0]

    def _handle_failure(self, job: _LiveJob, exc: Exception) -> None:
        now = time.monotonic()
        status_code = http_status_code(exc)
        if status_code is not None and not is_transient_http_error(exc):
            log.error(
                "Galaxy rejected live output for job %s, stopping live updates for it: %s",
                job.job_id,
                exc,
            )
            self._drop(job)
        elif isinstance(exc, requests.RequestException):
            # Galaxy is unreachable or overloaded; every job on it would fail too.
            retry_at, delay = self._backoff.get(job.endpoint, (0.0, 0.0))
            if retry_at <= now:
                delay = min(MAX_BACKOFF, max(self.interval, delay * 2))
                retry_at = now + delay
                self._backoff[job.endpoint] = (retry_at, delay)
                log.warning(
                    "Live output updates to %s failed, pausing them for %.0f seconds: %s",
                    job.endpoint,
                    delay,
                    exc,
                )
            job.next_due = retry_at
        elif not job.job_directory.exists():
            self._drop(job)
        else:
            job.failures += 1
            if job.failures == 1:
                log.warning("Failed to send live output for job %s, will retry: %s", job.job_id, exc)
            job.next_due = now + min(MAX_BACKOFF, self.interval * 2 ** job.failures)

    def _drop(self, job: _LiveJob) -> None:
        with self._jobs_lock:
            if self._jobs.get(job.job_id) is job:
                del self._jobs[job.job_id]
