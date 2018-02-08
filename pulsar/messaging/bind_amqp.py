import functools
import logging
import threading

from galaxy.util import asbool, mask_password_from_url

from pulsar import manager_endpoint_util
from pulsar.client import amqp_exchange_factory

log = logging.getLogger(__name__)


TYPED_PARAMS = {
    "amqp_consumer_timeout": lambda val: None if str(val) == "None" else float(val),
    "amqp_publish_retry": asbool,
    "amqp_publish_retry_max_retries": int,
    "amqp_publish_retry_interval_start": int,
    "amqp_publish_retry_interval_step": int,
    "amqp_publish_retry_interval_max": int,
}


def get_exchange(connection_string, manager_name, conf):
    # HACK: Fixup non-string parameters - utlimately this should reuse spec
    # stuff from Galaxy.
    for param, to_type in TYPED_PARAMS.items():
        if param in conf:
            val = conf[param]
            conf[param] = to_type(val)

    pulsar_exchange = amqp_exchange_factory.get_exchange(
        connection_string,
        manager_name,
        conf
    )
    return pulsar_exchange


def bind_manager_to_queue(manager, queue_state, connection_string, conf):
    pulsar_exchange = get_exchange(connection_string, manager.name, conf)

    process_setup_messages = functools.partial(__process_setup_message, manager)
    process_kill_messages = functools.partial(__process_kill_message, manager)

    def drain(callback, name):
        __drain(name, queue_state, pulsar_exchange, callback)
        log.info("Finished consuming %s queue - no more messages will be processed." % (name))

    if conf.get("message_queue_consume", True):
        setup_thread = start_setup_consumer(pulsar_exchange, functools.partial(drain, process_setup_messages, "setup"))
        kill_thread = start_kill_consumer(pulsar_exchange, functools.partial(drain, process_kill_messages, "kill"))
        if hasattr(queue_state, "threads"):
            queue_state.threads.extend([setup_thread, kill_thread])
        if conf.get("amqp_acknowledge", False):
            status_update_ack_thread = start_status_update_ack_consumer(pulsar_exchange, functools.partial(drain, None, "status_update_ack"))
            getattr(queue_state, 'threads', []).append(status_update_ack_thread)

    # TODO: Think through job recovery, jobs shouldn't complete until after bind
    # has occurred.
    def bind_on_status_change(new_status, job_id):
        job_id = job_id or 'unknown'
        try:
            message = "Publishing Pulsar state change with status %s for job_id %s" % (new_status, job_id)
            log.debug(message)
            payload = manager_endpoint_util.full_status(manager, new_status, job_id)
            pulsar_exchange.publish("status_update", payload)
        except Exception:
            log.exception("Failure to publish Pulsar state change for job_id %s." % job_id)
            raise

    if conf.get("message_queue_publish", True):
        manager.set_state_change_callback(bind_on_status_change)


def __start_consumer(name, exchange, target):
    exchange_url = mask_password_from_url(exchange.url)
    thread_name = "consume-%s-%s" % (name, exchange_url)
    thread = threading.Thread(name=thread_name, target=target)
    # TODO: If the shutdown code is actually called make this
    # not a daemon.
    thread.daemon = True
    thread.start()
    return thread


start_setup_consumer = functools.partial(__start_consumer, "setup")
start_kill_consumer = functools.partial(__start_consumer, "kill")
start_status_update_ack_consumer = functools.partial(__start_consumer, "status_update_ack")


def __drain(name, queue_state, pulsar_exchange, callback):
    pulsar_exchange.consume(name, callback=callback, check=queue_state)


def __process_kill_message(manager, body, message):
    if message.acknowledged:
        log.info("Message is already acknowledged (by an upstream callback?), Pulsar will not handle this message")
        return
    try:
        job_id = __client_job_id_from_body(body)
        assert job_id, 'Could not parse job id from body: %s' % body
        log.debug("Received message in kill queue for Pulsar job id: %s", job_id)
        manager.kill(job_id)
    except Exception:
        log.exception("Failed to kill job.")
    message.ack()


def __process_setup_message(manager, body, message):
    if message.acknowledged:
        log.info("Message is already acknowledged (by an upstream callback?), Pulsar will not handle this message")
        return
    try:
        job_id = __client_job_id_from_body(body)
        assert job_id, 'Could not parse job id from body: %s' % body
        log.debug("Received message in setup queue for Pulsar job id: %s", job_id)
        manager_endpoint_util.submit_job(manager, body)
    except Exception:
        job_id = job_id or 'unknown'
        log.exception("Failed to setup job %s obtained via message queue." % job_id)
    message.ack()


def __client_job_id_from_body(body):
    job_id = body.get("job_id", None)
    return job_id
