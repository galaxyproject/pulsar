"""Mock Galaxy used by the resilience test framework.

Exposes the surface Pulsar actually exercises:

- ``/api/jobs/_resilience/files`` (GET/POST/PUT/HEAD) for input/output
  staging. The wire shape (``?path=...`` query param, multipart POST, raw
  PUT) is provided by the upstream `simple-job-files`_ package, which
  itself emulates Galaxy's job-files API. We mount it as a WSGI sub-app so
  the resilience suite exercises the same wire format real Galaxy serves
  rather than a bespoke ``/files/{path}`` shape.
- An AMQP consumer of the ``status_update`` queue and a relay long-poll
  consumer of the ``job_status_update`` topic. Both push received messages
  into a shared :class:`StatusRecorder`.
- ``/_recorder/events`` and ``/_recorder/clear`` endpoints used by tests to
  observe and reset state between scenarios.
- ``/_publish_setup`` and ``/_publish_status_request`` endpoints that
  publish control messages into the broker / relay on behalf of a test, so
  the harness doesn't need to import kombu or pulsar-relay client code
  directly.

The app does NOT execute jobs or care about Pulsar's internals beyond the
wire format. It only records what it sees.

.. _simple-job-files: https://github.com/jmchilton/simple-job-files
"""
import json
import logging
import os
import threading
import time
from pathlib import Path

import kombu
import requests
import uvicorn
from a2wsgi import WSGIMiddleware
from fastapi import (
    FastAPI,
    Request,
)
from fastapi.responses import JSONResponse
from simplejobfiles.app import JobFilesApp
from webob.exc import HTTPException as WebObHTTPException

from recorder import StatusRecorder  # type: ignore

log = logging.getLogger("mock_galaxy")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

FILES_ROOT = Path(os.environ.get("MOCK_GALAXY_FILES_ROOT", "/galaxy/files"))
FILES_ROOT.mkdir(parents=True, exist_ok=True)
AMQP_URL = os.environ.get("MOCK_GALAXY_AMQP_URL", "")
RELAY_URL = os.environ.get("MOCK_GALAXY_RELAY_URL", "")
RELAY_USER = os.environ.get("MOCK_GALAXY_RELAY_USERNAME", "admin")
RELAY_PASS = os.environ.get("MOCK_GALAXY_RELAY_PASSWORD", "admin1234")
MANAGER = os.environ.get("MOCK_GALAXY_MANAGER", "_default_")

recorder = StatusRecorder()
app = FastAPI()


# ----- file-staging endpoints --------------------------------------------------
# Mounted simple-job-files WSGI app. The mount prefix is stripped before the
# WSGI sub-app sees the request, so the URL path is irrelevant to JobFilesApp
# (which dispatches purely on HTTP method and reads ``?path=`` from the query
# string). The prefix exists to mimic real Galaxy's ``/api/jobs/{id}/files``
# shape and to keep this surface namespaced away from the recorder / publish
# helpers below.
#
# ``allow_multiple_downloads=True`` is essential: resilience scenarios retry
# staging on transient failures, so the same input may be GET'd more than
# once for a single job. simple-job-files defaults to refusing duplicate
# downloads (to match a stricter Galaxy mode); we opt out.
#
# simple-job-files raises ``webob.exc.HTTPNotFound`` for missing files
# instead of returning it as a response; a2wsgi turns the bare exception
# into a 500. The c3 fail-fast scenario specifically asserts that a 404
# from Galaxy short-circuits Pulsar's retry classifier, so we wrap the
# WSGI app to turn raised WebOb HTTPExceptions back into proper responses.
class _WebObExceptionShim:
    def __init__(self, wsgi_app):
        self._app = wsgi_app

    def __call__(self, environ, start_response):
        try:
            return self._app(environ, start_response)
        except WebObHTTPException as e:
            return e(environ, start_response)


_jfa = JobFilesApp(root_directory=str(FILES_ROOT), allow_multiple_downloads=True)
app.mount("/api/jobs/_resilience/files", WSGIMiddleware(_WebObExceptionShim(_jfa)))  # type: ignore[arg-type]


# ----- recorder/control endpoints ---------------------------------------------

@app.get("/_recorder/events")
def list_events(job_id: str | None = None):
    return JSONResponse(recorder.events(job_id))


@app.post("/_recorder/clear")
def clear_events():
    recorder.clear()
    return {"cleared": True}


@app.post("/_recorder/inject_status")
async def inject_status(req: Request):
    """Test helper: feed a status payload directly into the recorder.

    Used to model Galaxy-side actions that don't come over the wire from
    Pulsar (an operator restart, an admin cancel) when validating the
    regression-guard / reset-token semantics end-to-end.
    """
    payload = await req.json()
    recorder.record(payload)
    return {"recorded": True}


@app.post("/_consumer/reset")
def consumer_reset():
    """Drop the relay long-poll cursor and the cached relay JWT in-place.

    Lets the test harness wipe per-test state (after a Valkey topic flush)
    without restarting the mock-galaxy container, which is one of the
    biggest fixed costs in the resilience-suite per-test cycle.
    """
    _relay_cursor.clear()
    with _token_lock:
        _token_cache["token"] = None
        _token_cache["exp"] = 0.0
    recorder.clear()
    return {"reset": True}


@app.post("/_publish_setup")
async def publish_setup(req: Request):
    payload = await req.json()
    _publish_amqp("setup", payload)
    _publish_relay("job_setup", payload)
    return {"published": True}


@app.post("/_publish_status_request")
async def publish_status_request(req: Request):
    payload = await req.json()
    _publish_amqp("status", payload)
    _publish_relay("job_status_request", payload)
    return {"published": True}


@app.post("/_publish_kill")
async def publish_kill(req: Request):
    payload = await req.json()
    _publish_amqp("kill", payload)
    _publish_relay("job_kill", payload)
    return {"published": True}


# ----- AMQP consumer ----------------------------------------------------------

def _queue_name(name: str) -> str:
    if MANAGER == "_default_":
        return f"pulsar__{name}"
    return f"pulsar_{MANAGER}__{name}"


def _topic_name(base: str) -> str:
    if MANAGER == "_default_":
        return base
    return f"{base}_{MANAGER}"


def _publish_amqp(queue: str, payload: dict):
    if not AMQP_URL:
        return
    queue_name = _queue_name(queue)
    try:
        with kombu.Connection(AMQP_URL) as conn:
            exchange = kombu.Exchange("pulsar", "direct", durable=True)
            q = kombu.Queue(queue_name, exchange, routing_key=queue_name, durable=True)
            with conn.Producer(serializer="json") as producer:
                producer.publish(
                    payload,
                    exchange=exchange,
                    declare=[exchange, q],
                    routing_key=queue_name,
                    delivery_mode=2,
                )
    except Exception:
        log.exception("AMQP publish to %s failed", queue_name)


def _publish_relay(topic_base: str, payload: dict):
    if not RELAY_URL:
        return
    topic = _topic_name(topic_base)
    try:
        token = _relay_token()
        r = requests.post(
            f"{RELAY_URL.rstrip('/')}/api/v1/messages",
            json={"topic": topic, "payload": payload},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
    except Exception:
        log.exception("Relay publish to %s failed", topic)


_token_lock = threading.Lock()
_token_cache = {"token": None, "exp": 0.0}


def _relay_token():
    with _token_lock:
        if _token_cache["token"] and _token_cache["exp"] > time.time() + 30:
            return _token_cache["token"]
        r = requests.post(
            f"{RELAY_URL.rstrip('/')}/auth/login",
            data={
                "username": RELAY_USER,
                "password": RELAY_PASS,
                "grant_type": "password",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        r.raise_for_status()
        body = r.json()
        _token_cache["token"] = body["access_token"]
        _token_cache["exp"] = time.time() + int(body.get("expires_in", 600))
        return _token_cache["token"]


def _amqp_consume_loop():
    if not AMQP_URL:
        return
    queue_name = _queue_name("status_update")
    while True:
        try:
            with kombu.Connection(AMQP_URL, heartbeat=60) as conn:
                exchange = kombu.Exchange("pulsar", "direct", durable=True)
                q = kombu.Queue(queue_name, exchange, routing_key=queue_name, durable=True)

                def cb(body, message):
                    if isinstance(body, str):
                        body = json.loads(body)
                    recorder.record(body)
                    message.ack()

                with conn.Consumer([q], callbacks=[cb], accept=["json"]):
                    while True:
                        try:
                            conn.drain_events(timeout=1.0)
                        except Exception:
                            pass
        except Exception:
            log.exception("AMQP consumer dropped, reconnecting")
            time.sleep(2.0)


_relay_cursor: dict[str, str] = {}


def _relay_consume_loop():
    if not RELAY_URL:
        return
    topic = _topic_name("job_status_update")
    while True:
        try:
            token = _relay_token()
            poll = {"topics": [topic], "timeout": 30}
            if _relay_cursor:
                poll["since"] = dict(_relay_cursor)
            r = requests.post(
                f"{RELAY_URL.rstrip('/')}/messages/poll",
                json=poll,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=40,
            )
            if r.status_code != 200:
                time.sleep(1)
                continue
            messages = r.json().get("messages") or []
            for msg in messages:
                payload = msg.get("payload", {})
                recorder.record(payload)
                mid = msg.get("message_id")
                tpc = msg.get("topic")
                if mid and tpc:
                    _relay_cursor[tpc] = mid
        except Exception:
            log.exception("Relay consumer error, retrying")
            time.sleep(2.0)


def _start_consumers():
    if AMQP_URL:
        threading.Thread(target=_amqp_consume_loop, name="amqp-consumer", daemon=True).start()
    if RELAY_URL:
        threading.Thread(target=_relay_consume_loop, name="relay-consumer", daemon=True).start()


@app.on_event("startup")
def on_startup():
    _start_consumers()


@app.get("/healthz")
def healthz():
    return {"ok": True}


if __name__ == "__main__":
    bind = os.environ.get("MOCK_GALAXY_BIND", "0.0.0.0:8088")
    host, _, port = bind.partition(":")
    uvicorn.run(app, host=host, port=int(port))
