import functools
import logging
import threading

from galaxy.util import (
    asbool,
    mask_password_from_url,
)

from pulsar import manager_endpoint_util
from pulsar.client import amqp_exchange_factory

log = logging.getLogger(__name__)


TYPED_PARAMS = {
    "amqp_consumer_timeout": lambda val: None if str(val) == "None" else float(val),
    "amqp_publish_timeout": lambda val: None if str(val) == "None" else float(val),
    "amqp_publish_retry": asbool,
    "amqp_publish_retry_max_retries": int,
    "amqp_publish_retry_interval_start": int,
    "amqp_publish_retry_interval_step": int,
    "amqp_publish_retry_interval_max": int,
}


def get_exchange(connection_string, manager_name, conf):
    # HACK: Fixup non-string parameters - ultimately this should reuse spec
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
    manager_name = manager.name
    log.info("bind_manager_to_queue called for [{}] and manager [{}]".format(mask_password_from_url(connection_string), manager_name))
    pulsar_exchange = get_exchange(connection_string, manager_name, conf)

    process_setup_messages = functools.partial(__process_setup_message, manager)
    process_kill_messages = functools.partial(__process_kill_message, manager)
    process_status_messages = functools.partial(__process_status_message, manager)

    def drain(callback, name):
        __drain(name, queue_state, pulsar_exchange, callback)
        log.info("Finished consuming %s queue - no more messages will be processed." % (name))

    if conf.get("message_queue_consume", True):
        setup_thread = start_setup_consumer(pulsar_exchange, functools.partial(drain, process_setup_messages, "setup"))
        kill_thread = start_kill_consumer(pulsar_exchange, functools.partial(drain, process_kill_messages, "kill"))
        status_thread = start_status_consumer(pulsar_exchange, functools.partial(drain, process_status_messages, "status"))
        if hasattr(queue_state, "threads"):
            queue_state.threads.extend([setup_thread, kill_thread, status_thread])
        if conf.get("amqp_acknowledge", False):
            status_update_ack_thread = start_status_update_ack_consumer(pulsar_exchange, functools.partial(drain, None, "status_update_ack"))
            getattr(queue_state, 'threads', []).append(status_update_ack_thread)

    # TODO: Think through job recovery, jobs shouldn't complete until after bind
    # has occurred.
    def bind_on_status_change(new_status, job_id):
        job_id = job_id or 'unknown'
        try:
            message = "Publishing Pulsar state change with status {} for job_id {}".format(new_status, job_id)
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
    thread_name = "consume-{}-{}".format(name, exchange_url)
    thread = threading.Thread(name=thread_name, target=target)
    # TODO: If the shutdown code is actually called make this
    # not a daemon.
    thread.daemon = True
    thread.start()
    return thread


start_setup_consumer = functools.partial(__start_consumer, "setup")
start_kill_consumer = functools.partial(__start_consumer, "kill")
start_status_consumer = functools.partial(__start_consumer, "status")
start_status_update_ack_consumer = functools.partial(__start_consumer, "status_update_ack")


def __drain(name, queue_state, pulsar_exchange, callback):
    pulsar_exchange.consume(name, callback=callback, check=queue_state)


def __processes_message(f):

    @functools.wraps(f)
    def process_message(manager, body, message):
        if message.acknowledged:
            log.info("Message is already acknowledged (by an upstream callback?), Pulsar will not handle this message")
            return

        job_id = None
        try:
            job_id = __client_job_id_from_body(body)
            assert job_id, 'Could not parse job id from body: %s' % body
            f(manager, body, job_id)
        except Exception:
            job_id = job_id or 'unknown'
            log.exception("Failed to process message with function {} for job_id {}".format(f.__name__, job_id))
        message.ack()

    return process_message


@__processes_message
def __process_kill_message(manager, body, job_id):
    manager.kill(job_id)


@__processes_message
def __process_setup_message(manager, body, job_id):
    manager_endpoint_util.submit_job(manager, body)


@__processes_message
def __process_status_message(manager, body, job_id):
    manager.trigger_state_change_callback(job_id)


def __client_job_id_from_body(body):
    job_id = body.get("job_id", None)
    return job_id
