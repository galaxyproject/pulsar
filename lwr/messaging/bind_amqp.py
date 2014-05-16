from lwr.lwr_client import amqp_exchange
from lwr import manager_endpoint_util
import functools
import threading
import logging

log = logging.getLogger(__name__)


def bind_manager_to_queue(manager, queue_state, connection_string, connect_ssl=None):
    lwr_exchange = amqp_exchange.LwrExchange(connection_string, manager.name, connect_ssl=connect_ssl)

    process_setup_messages = functools.partial(__process_setup_message, manager)
    process_kill_messages = functools.partial(__process_kill_message, manager)

    def drain(callback, name):
        __drain(name, queue_state, lwr_exchange, callback)
        log.info("Finished consuming %s queue - no more messages will be processed." % (name))

    __start_consumer("setup", lwr_exchange, functools.partial(drain, process_setup_messages, "setup"))
    __start_consumer("kill", lwr_exchange, functools.partial(drain, process_kill_messages, "kill"))

    # TODO: Think through job recovery, jobs shouldn't complete until after bind
    # has occurred.
    def bind_on_status_change(new_status, job_id):
        try:
            log.debug("Publishing LWR state change with status %s" % new_status)
            payload = manager_endpoint_util.full_status(manager, new_status, job_id)
            lwr_exchange.publish("status_update", payload)
        except:
            log.exception("Failure to publish LWR state change.")
            raise

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
    job_id = body.get("job_id", None)
    if job_id:
        manager.kill(job_id)
    message.ack()


def __process_setup_message(manager, body, message):
    manager_endpoint_util.submit_job(manager, body)
    message.ack()
