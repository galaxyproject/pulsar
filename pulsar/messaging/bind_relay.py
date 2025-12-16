"""Pulsar server-side integration with pulsar-relay.

This module provides functionality to bind Pulsar job managers to the
pulsar-relay, allowing them to receive control messages (setup, status
requests, kill) and publish status updates.
"""
import functools
import logging
import threading
import time

from pulsar import manager_endpoint_util
from pulsar.client.transport.relay import RelayTransport
from .relay_state import RelayState

log = logging.getLogger(__name__)


def bind_manager_to_relay(manager, relay_state: RelayState, relay_url, conf):
    """Bind a specific manager to the relay.

    Args:
        manager: Pulsar job manager instance
        relay_state: RelayState for managing consumer threads
        relay_url: URL of the pulsar-relay server
        conf: Configuration dictionary with relay credentials
    """
    manager_name = manager.name
    log.info("bind_manager_to_relay called for relay [%s] and manager [%s]", relay_url, manager_name)

    # Extract relay credentials
    username = conf.get('message_queue_username', 'admin')
    password = conf.get('message_queue_password')
    if not password:
        raise Exception("message_queue_password is required for relay communication")

    # Extract optional relay topic prefix
    relay_topic_prefix = conf.get('relay_topic_prefix', '')

    # Create relay transport
    relay_transport = RelayTransport(relay_url, username, password)

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

        # Single consumer thread for all control messages
        consumer_thread = start_consumer(
            relay_transport,
            relay_state,
            [setup_topic, status_request_topic, kill_topic],
            {
                setup_topic: process_setup_messages,
                status_request_topic: process_status_messages,
                kill_topic: process_kill_messages,
            }
        )

        relay_state.threads.append(consumer_thread)

    # Bind status change callback to publish status updates to relay
    if conf.get("message_queue_publish", True):
        log.info("Binding status change callback for manager '%s'", manager_name)

        def bind_on_status_change(new_status, job_id):
            job_id = job_id or 'unknown'
            try:
                message = "Publishing Pulsar state change with status %s for job_id %s via relay"
                log.debug(message, new_status, job_id)
                payload = manager_endpoint_util.full_status(manager, new_status, job_id)
                relay_transport.post_message(status_update_topic, payload)
            except Exception:
                log.exception("Failure to publish Pulsar state change for job_id %s via relay." % job_id)
                raise

        manager.set_state_change_callback(bind_on_status_change)


def start_consumer(relay_transport, relay_state: RelayState, topics, handlers):
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
                # Long poll for messages (30 second timeout)
                messages = relay_transport.long_poll(topics, timeout=30)

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
