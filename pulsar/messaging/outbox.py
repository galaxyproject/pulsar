"""Persistent outbox for status update messages.

Provides at-least-once delivery of status updates from Pulsar to Galaxy,
independent of broker durability. Each payload is written to disk before
publish is attempted; the on-disk file is removed only after the publish
callable returns successfully. A daemon thread retries any messages that
remain on disk.

This addresses the most critical loss path in the job lifecycle: when the
AMQP broker (or pulsar-relay) is unreachable at the moment a job reaches a
terminal state, the synchronous publish in the postprocess thread would
otherwise raise, terminating the thread, and the on-disk ``final_status``
would never be reported back to Galaxy.
"""
import json
import logging
import os
import threading
import uuid
from time import time
from typing import (
    Any,
    Callable,
    Dict,
    Optional,
)

log = logging.getLogger(__name__)

DEFAULT_DRAIN_INTERVAL = 5.0
ENTRY_SUFFIX = ".json"
TMP_SUFFIX = ".tmp"
SEQ_WIDTH = 20  # zero-padded so lexical sort == numeric sort


class StatusUpdateOutbox:
    """At-least-once persistent outbox for status update messages.

    Entries are written as ``<seq>-<uuid>.json`` where ``seq`` is a
    monotonic per-outbox counter, so a lexically sorted ``os.listdir`` gives
    FIFO drain order. This is the in-process ordering guarantee: a single
    Pulsar instance will never re-order its own emissions for a given job
    (e.g. ``running`` will not be drained after ``complete``). The receiver
    is still responsible for collapsing legitimate duplicates and for
    refusing to regress past a terminal status — see the recorder under
    ``test/resilience/mock_galaxy/`` for the canonical Galaxy-side pattern.
    """

    def __init__(
        self,
        store_directory: str,
        publish_fn: Callable[[Dict[str, Any]], Any],
        drain_interval: float = DEFAULT_DRAIN_INTERVAL,
    ) -> None:
        self._store_dir = os.path.abspath(store_directory)
        os.makedirs(self._store_dir, exist_ok=True)
        self._publish_fn = publish_fn
        self._drain_interval = drain_interval
        self._wakeup = threading.Event()
        self._stopping = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._seq_lock = threading.Lock()
        self._next_seq = self._recover_next_seq()

    def _recover_next_seq(self) -> int:
        max_seq = -1
        try:
            for name in os.listdir(self._store_dir):
                if not name.endswith(ENTRY_SUFFIX):
                    continue
                head = name[:-len(ENTRY_SUFFIX)].split("-", 1)[0]
                try:
                    n = int(head)
                except ValueError:
                    continue
                if n > max_seq:
                    max_seq = n
        except FileNotFoundError:
            pass
        return max_seq + 1

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stopping.clear()
        thread_name = "status-outbox-%s" % os.path.basename(self._store_dir.rstrip(os.sep))
        self._thread = threading.Thread(target=self._run, name=thread_name, daemon=True)
        self._thread.start()

    def stop(self, timeout: Optional[float] = None) -> None:
        self._stopping.set()
        self._wakeup.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout if timeout is not None else 1.0)
        # Final drain attempt so an orderly shutdown delivers anything that
        # was enqueued just before the stop signal. If the publish destination
        # is unreachable, entries remain on disk and are retried on restart.
        was_stopping = self._stopping.is_set()
        self._stopping.clear()
        try:
            self.drain_once()
        except OSError:
            log.exception("Final drain on outbox stop failed")
        if was_stopping:
            self._stopping.set()

    def enqueue(self, payload: Dict[str, Any]) -> None:
        """Persist payload and trigger an immediate drain pass.

        Never raises. If the publish fails, the payload remains on disk and
        the drain loop will keep retrying.
        """
        message_id = uuid.uuid4().hex
        with self._seq_lock:
            seq = self._next_seq
            self._next_seq += 1
        filename = self._filename(seq, message_id)
        path = os.path.join(self._store_dir, filename)
        tmp_path = path + TMP_SUFFIX
        try:
            with open(tmp_path, "w") as fh:
                json.dump(
                    {"id": message_id, "seq": seq, "payload": payload, "ts": time()},
                    fh,
                )
            os.replace(tmp_path, path)
        except OSError:
            log.exception("Failed to persist status update to outbox %s", self._store_dir)
            # publish_fn is a user-supplied callback; we deliberately swallow
            # any error from this best-effort fallback so enqueue() never
            # raises into the postprocess thread.
            try:
                self._publish_fn(payload)
            except Exception:
                log.exception("Direct publish failed for unwriteable outbox payload")
            return
        self._wakeup.set()

    def drain_once(self) -> int:
        """Attempt to publish all currently pending messages once.

        Returns the number of messages still pending after the pass.
        """
        with self._lock:
            entries = self._list()
        for entry in entries:
            if self._stopping.is_set():
                break
            self._try_publish(entry)
        with self._lock:
            return len(self._list())

    def pending_count(self) -> int:
        with self._lock:
            return len(self._list())

    def _list(self) -> list:
        try:
            return sorted(
                f for f in os.listdir(self._store_dir)
                if f.endswith(ENTRY_SUFFIX)
            )
        except FileNotFoundError:
            return []

    def _filename(self, seq: int, message_id: str) -> str:
        return f"{seq:0{SEQ_WIDTH}d}-{message_id}{ENTRY_SUFFIX}"

    def _path(self, message_id: str) -> str:
        # Legacy helper used only by tests; production paths flow through
        # _filename() with the monotonic seq prefix.
        return os.path.join(self._store_dir, message_id + ENTRY_SUFFIX)

    def _try_publish(self, filename: str) -> None:
        path = os.path.join(self._store_dir, filename)
        try:
            with open(path) as fh:
                record = json.load(fh)
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError):
            log.exception("Corrupt outbox entry %s, removing", path)
            try:
                os.unlink(path)
            except OSError:
                pass
            return
        # publish_fn is a user-supplied callback (kombu publish, HTTP POST,
        # etc.) — its failure modes are not enumerable from here, so we
        # catch broadly and let the drain loop retry the on-disk entry.
        try:
            self._publish_fn(record["payload"])
        except Exception as exc:
            log.warning(
                "Outbox publish failed for %s; will retry on next drain pass: %s",
                filename, exc,
            )
            return
        try:
            os.unlink(path)
        except OSError:
            log.exception("Failed to remove outbox entry after successful publish: %s", path)

    def _run(self) -> None:
        log.info("Status update outbox drain thread starting (dir=%s)", self._store_dir)
        try:
            remaining = self.drain_once()
            if remaining:
                log.info("Outbox %s has %d pending messages to retry", self._store_dir, remaining)
        except OSError:
            log.exception("Initial outbox drain failed")
        while not self._stopping.is_set():
            self._wakeup.wait(timeout=self._drain_interval)
            self._wakeup.clear()
            if self._stopping.is_set():
                break
            try:
                self.drain_once()
            except OSError:
                log.exception("Outbox drain pass failed")
        log.info("Status update outbox drain thread exiting (dir=%s)", self._store_dir)


def build_status_outbox(
    manager: Any,
    conf: Dict[str, Any],
    publish_fn: Callable[[Dict[str, Any]], Any],
    suffix: str = "status-outbox",
) -> Optional["StatusUpdateOutbox"]:
    """Construct a StatusUpdateOutbox for the given manager, or None if persistence
    is disabled.

    The outbox is rooted at ``<persistence_directory>/<manager_name>-<suffix>/``.
    If the manager has no persistence_directory configured (i.e. the operator
    explicitly opted out), returns ``None`` and the caller should fall back to
    direct publish.
    """
    persistence_directory = manager.persistence_directory
    if not persistence_directory:
        log.warning(
            "Manager %s has no persistence_directory; status updates will be "
            "published without local outbox persistence and may be lost if the "
            "broker is unreachable at publish time.",
            manager.name,
        )
        return None
    drain_interval = float(conf.get("status_outbox_drain_interval", DEFAULT_DRAIN_INTERVAL))
    store_dir = os.path.join(persistence_directory, "%s-%s" % (manager.name, suffix))
    outbox = StatusUpdateOutbox(store_dir, publish_fn, drain_interval=drain_interval)
    outbox.start()
    return outbox
