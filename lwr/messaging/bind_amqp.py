from galaxy.util import asbool
from lwr.lwr_client import amqp_exchange_factory
from lwr import manager_endpoint_util
import functools
import threading
import logging

log = logging.getLogger(__name__)


def bind_manager_to_queue(manager, queue_state, connection_string, conf):
    # HACK: Fixup non-string parameters - utlimately this should reuse spec
    # stuff from Galaxy.
    for param in [ "amqp_consumer_timeout" ]:
        if param in conf:
            val = conf[param]
            new_val = None if str(val) == "None" else float(val)
            conf[param] = new_val
    for param in [ "amqp_publish_retry" ]:
        if param in conf:
            val = conf[param]
            new_val = asbool(val)
            conf[param] = new_val

    lwr_exchange = amqp_exchange_factory.get_exchange(
        connection_string,
        manager.name,
        conf
    )
    process_setup_messages = functools.partial(__process_setup_message, manager)
    process_kill_messages = functools.partial(__process_kill_message, manager)

    def drain(callback, name):
        __drain(name, queue_state, lwr_exchange, callback)
        log.info("Finished consuming %s queue - no more messages will be processed." % (name))

    if conf.get("message_queue_consume", True):
        __start_consumer("setup", lwr_exchange, functools.partial(drain, process_setup_messages, "setup"))
        __start_consumer("kill", lwr_exchange, functools.partial(drain, process_kill_messages, "kill"))

    # TODO: Think through job recovery, jobs shouldn't complete until after bind
    # has occurred.
    def bind_on_status_change(new_status, job_id):
        try:
            message = "Publishing LWR state change with status %s for job_id %s" % (new_status, job_id)
            log.debug(message)
            payload = manager_endpoint_util.full_status(manager, new_status, job_id)
            lwr_exchange.publish("status_update", payload)
        except:
            log.exception("Failure to publish LWR state change.")
            raise

    if conf.get("message_queue_publish", True):
        manager.set_state_change_callback(bind_on_status_change)


def __start_consumer(name, exchange, target):
    thread_name = "consume-%s-%s" % (name, exchange.url)
    thread = threading.Thread(name=thread_name, target=target)
    thread.daemon = False
    thread.start()
    return thread


def __drain(name, queue_state, lwr_exchange, callback):
    lwr_exchange.consume(name, callback=callback, check=queue_state)


def __process_kill_message(manager, body, message):
    try:
        job_id = __client_job_id_from_body(body)
        if job_id:
            manager.kill(job_id)
    except Exception:
        log.exception("Failed to kill job.")
    message.ack()


def __process_setup_message(manager, body, message):
    try:
        manager_endpoint_util.submit_job(manager, body)
    except Exception:
        job_id = __client_job_id_from_body(body)
        log.warn("Failed to setup job %s obtained via message queue." % job_id)
    message.ack()


def __client_job_id_from_body(body):
    job_id = body.get("job_id", None)
    return job_id
