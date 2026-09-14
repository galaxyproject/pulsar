"""Pulsar server-side integration with pulsar-relay.

This module provides functionality to bind Pulsar job managers to the
pulsar-relay, allowing them to receive control messages (setup, status
requests, kill) and publish status updates.
"""
import datetime
import functools
import logging
import os
import threading
import time
from typing import Optional

import requests

from pulsar import manager_endpoint_util
from pulsar.capabilities import collect_capabilities
from .outbox import build_status_outbox
from .relay_state import RelayState

log = logging.getLogger(__name__)

DEFAULT_RELAY_LONG_POLL_TIMEOUT = 30.0


def _server_cursor_path(manager) -> Optional[str]:
    persistence_directory = manager.persistence_directory
    if not persistence_directory:
        return None
    return os.path.join(persistence_directory, "%s-relay-cursor.json" % manager.name)


def _relay_long_poll_timeout(conf):
    return float(conf.get("relay_long_poll_timeout", DEFAULT_RELAY_LONG_POLL_TIMEOUT))


def build_relay_transport(manager, relay_url, conf):
    """Construct a ``RelayTransport`` for ``manager``."""
    from pulsar_relay_client import RelayTransport

    # Relay credentials: prefer a refresh-token credentials file
    # (written by ``pulsar-config --login``); fall back to legacy
    # username/password for existing deployments.
    credentials_file = conf.get('message_queue_credentials_file')
    username = conf.get('message_queue_username')
    password = conf.get('message_queue_password')
    if not credentials_file and not password:
        raise Exception(
            "Relay auth not configured: set either message_queue_credentials_file "
            "(recommended; run `pulsar-config --login`) or message_queue_username + "
            "message_queue_password."
        )
    return RelayTransport(
        relay_url,
        username=username,
        password=password,
        cursor_path=_server_cursor_path(manager),
        credentials_file=credentials_file,
    )


def bind_manager_to_relay(manager, relay_state: RelayState, relay_url, conf, relay_transport=None):
    """Bind a specific manager to the relay.

    Args:
        manager: Pulsar job manager instance
        relay_state: RelayState for managing consumer threads
        relay_url: URL of the pulsar-relay server
        conf: Configuration dictionary with relay credentials
        relay_transport: Optional pre-built ``RelayTransport``; if omitted,
            one is constructed via :func:`build_relay_transport`.
    """
    # Imported lazily so pulsar still installs on Pythons that don't meet
    # pulsar-relay-client's requires-python (currently 3.10+); the relay
    # code path is simply unreachable on those interpreters.
    from pulsar_relay_client import RelayTransportError

    manager_name = manager.name
    log.info("bind_manager_to_relay called for relay [%s] and manager [%s]", relay_url, manager_name)

    if relay_transport is None:
        relay_transport = build_relay_transport(manager, relay_url, conf)

    # Extract optional relay topic prefix
    relay_topic_prefix = conf.get('relay_topic_prefix', '')

    # Define message handlers
    process_setup_messages = functools.partial(__process_setup_message, manager)
    process_kill_messages = functools.partial(__process_kill_message, manager)
    process_status_messages = functools.partial(__process_status_message, manager)

    # Determine topics based on manager name and optional prefix
    setup_topic = __make_topic_name(relay_topic_prefix, "job_setup", manager_name)
    status_request_topic = __make_topic_name(relay_topic_prefix, "job_status_request", manager_name)
    kill_topic = __make_topic_name(relay_topic_prefix, "job_kill", manager_name)
    status_update_topic = __make_topic_name(relay_topic_prefix, "job_status_update", manager_name)

    # Start consumer threads if message_queue_consume is enabled
    if conf.get("message_queue_consume", True):
        log.info("Starting relay consumer threads for manager '%s'", manager_name)
        long_poll_timeout = _relay_long_poll_timeout(conf)

        # Single consumer thread for all control messages
        consumer_thread = start_consumer(
            relay_transport,
            relay_state,
            [setup_topic, status_request_topic, kill_topic],
            {
                setup_topic: process_setup_messages,
                status_request_topic: process_status_messages,
                kill_topic: process_kill_messages,
            },
            long_poll_timeout=long_poll_timeout,
        )

        relay_state.threads.append(consumer_thread)

    # Bind status change callback to publish status updates to relay
    if conf.get("message_queue_publish", True):
        log.info("Binding status change callback for manager '%s'", manager_name)

        outbox = build_status_outbox(
            manager,
            conf,
            publish_fn=lambda payload: relay_transport.post_message(status_update_topic, payload),
            suffix="relay-status-outbox",
        )
        if outbox is not None:
            relay_state.outboxes.append(outbox)

        def bind_on_status_change(new_status, job_id):
            job_id = job_id or 'unknown'
            log.debug(
                "Publishing Pulsar state change with status %s for job_id %s via relay",
                new_status, job_id,
            )
            payload = manager_endpoint_util.full_status(manager, new_status, job_id)
            if outbox is not None:
                outbox.enqueue(payload)
                return
            try:
                relay_transport.post_message(status_update_topic, payload)
            except (RelayTransportError, requests.RequestException):
                log.exception(
                    "Failure to publish Pulsar state change for job_id %s via "
                    "relay (no outbox configured; status update may be lost).",
                    job_id,
                )

        manager.set_state_change_callback(bind_on_status_change)


def start_consumer(
    relay_transport,
    relay_state: RelayState,
    topics,
    handlers,
    long_poll_timeout=DEFAULT_RELAY_LONG_POLL_TIMEOUT,
):
    """Start a consumer thread that polls for messages.

    Args:
        relay_transport: RelayTransport instance
        relay_state: RelayState for checking if consumer should continue
        topics: List of topics to subscribe to
        handlers: Dict mapping topics to handler functions

    Returns:
        Thread object
    """
    def consume():
        log.info("Starting relay consumer for topics: %s", topics)

        while relay_state.active:
            try:
                messages = relay_transport.long_poll(topics, timeout=long_poll_timeout)

                for message in messages:
                    topic = message.get('topic')
                    payload = message.get('payload', {})

                    handler = handlers.get(topic)
                    if handler:
                        try:
                            handler(payload)
                        except Exception:
                            job_id = payload.get('job_id', 'unknown')
                            log.exception("Failed to process message for job_id %s from topic %s", job_id, topic)
                    else:
                        log.warning("No handler found for topic '%s'", topic)

            except Exception:
                if relay_state.active:
                    log.exception("Exception while polling relay, will retry after delay.")
                    # Brief sleep before retrying
                    time.sleep(5)
                else:
                    log.debug("Exception during shutdown, stopping consumer.")
                    break

        log.info("Finished consuming relay messages - no more messages will be processed.")

    thread = threading.Thread(
        name="relay-consumer-%s" % "-".join(topics),
        target=consume
    )
    thread.daemon = True
    thread.start()
    return thread


def __process_setup_message(manager, body):
    """Process a job setup message.

    Args:
        manager: Job manager instance
        body: Message payload containing job setup parameters
    """
    job_id = __client_job_id_from_body(body)
    if not job_id:
        log.error('Could not parse job id from body: %s', body)
        return

    try:
        log.info("Processing setup message for job_id %s", job_id)
        manager_endpoint_util.submit_job(manager, body)
    except Exception:
        log.exception("Failed to process setup message for job_id %s", job_id)


def __process_status_message(manager, body):
    """Process a status request message.

    Args:
        manager: Job manager instance
        body: Message payload containing job_id
    """
    job_id = __client_job_id_from_body(body)
    if not job_id:
        log.error('Could not parse job id from body: %s', body)
        return

    try:
        log.debug("Processing status request for job_id %s", job_id)
        manager.trigger_state_change_callback(job_id)
    except Exception:
        log.exception("Failed to process status message for job_id %s", job_id)


def __process_kill_message(manager, body):
    """Process a job kill message.

    Args:
        manager: Job manager instance
        body: Message payload containing job_id
    """
    job_id = __client_job_id_from_body(body)
    if not job_id:
        log.error('Could not parse job id from body: %s', body)
        return

    try:
        log.info("Processing kill request for job_id %s", job_id)
        manager.kill(job_id)
    except Exception:
        log.exception("Failed to process kill message for job_id %s", job_id)


def __client_job_id_from_body(body):
    """Extract job_id from message body.

    Args:
        body: Message payload dictionary

    Returns:
        job_id string or None if not found
    """
    job_id = body.get("job_id", None)
    return job_id


def publish_manager_capabilities_to_relay(app, manager, relay_transport, conf):
    """Collect and POST this manager's capability snapshot to its relay topic.

    Collection happens lazily here (not at app init) so non-relay deployments
    do zero capability work. Both collection and POST failures are logged but
    never raised: capabilities are advisory and must not prevent the manager's
    control consumers from coming up.
    """
    # One POST per pulsar startup; the relay retains topic messages so
    # Galaxy can fetch the snapshot synchronously via the REST messages
    # endpoint. No heartbeat — the snapshot is static for the lifetime
    # of the process.
    if not conf.get("message_queue_publish_capabilities", True):
        return
    try:
        capabilities = collect_capabilities(app, manager)
    except Exception:
        log.exception(
            "Failed to collect capabilities for manager %s; skipping relay publish.",
            manager.name,
        )
        return
    relay_topic_prefix = conf.get('relay_topic_prefix', '')
    topic = __make_capabilities_topic_name(relay_topic_prefix, manager.name)
    payload = capabilities.to_dict()
    payload["published_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        relay_transport.post_message(topic, payload)
        log.info("Published capabilities for manager %s to relay topic %s", manager.name, topic)
    except Exception:
        # Includes RelayTransportError, requests.RequestException, network errors.
        # Swallow: capabilities are advisory and downstream Galaxy already handles a missing snapshot.
        log.exception(
            "Failed to publish capabilities for manager %s to relay topic %s",
            manager.name, topic,
        )


def __make_capabilities_topic_name(prefix, manager_name):
    """Topic name for capability snapshots.

    Examples:
        __make_capabilities_topic_name('', '_default_') -> 'pulsar_capabilities'
        __make_capabilities_topic_name('', 'cluster_a') -> 'pulsar_capabilities_cluster_a'
        __make_capabilities_topic_name('prod', '_default_') -> 'prod_pulsar_capabilities'
    """
    return __make_topic_name(prefix, "pulsar_capabilities", manager_name)


def __make_topic_name(prefix, base_topic, manager_name):
    """Create a topic name with optional prefix and manager suffix.

    Args:
        prefix: Optional prefix string (e.g., 'galaxy1', 'prod')
        base_topic: Base topic name (e.g., 'job_setup', 'job_status_update')
        manager_name: Manager name (e.g., '_default_', 'cluster_a')

    Returns:
        Fully qualified topic name

    Examples:
        __make_topic_name('', 'job_setup', '_default_') -> 'job_setup'
        __make_topic_name('', 'job_setup', 'cluster_a') -> 'job_setup_cluster_a'
        __make_topic_name('prod', 'job_setup', '_default_') -> 'prod_job_setup'
        __make_topic_name('prod', 'job_setup', 'cluster_a') -> 'prod_job_setup_cluster_a'
    """
    parts = []

    # Add prefix if provided
    if prefix:
        parts.append(prefix)

    # Add base topic
    parts.append(base_topic)

    # Add manager name if not default
    if manager_name != "_default_":
        parts.append(manager_name)

    return "_".join(parts)
