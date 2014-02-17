from lwr.lwr_client import amqp_exchange
from lwr import manager_endpoint_util
import threading
import logging

log = logging.getLogger(__name__)


def bind_manager_to_queue(manager, queue_state, connection_string):
    lwr_exchange = amqp_exchange.LwrExchange(connection_string, manager.name)

    def process_messages(body, message):
        __process_message(manager, body, message)

    def drain():
        __drain(queue_state, lwr_exchange, process_messages)

    thread_name = "consumer-%s" % connection_string
    thread = threading.Thread(name=thread_name, target=drain)
    thread.daemon = True
    thread.start()

    # TODO: Think through job recovery, jobs shouldn't complete until after bind
    # has occurred.
    def bind_on_complete(final_status, job_id):
        payload = manager_endpoint_util.job_complete_dict(final_status, manager, job_id)
        lwr_exchange.publish("complete", payload)

    manager.set_completion_callback(bind_on_complete)


def __drain(queue_state, lwr_exchange, callback):
    lwr_exchange.consume("setup", callback=callback, check=queue_state)


def __process_message(manager, body, message):
    manager_endpoint_util.submit_job(manager, body)
    message.ack()
