import threading
from .test_utils import (
    TempDirectoryTestCase,
    skip_unless_module,
    restartable_pulsar_app_provider,
)
from pulsar.manager_endpoint_util import (
    submit_job,
)
from pulsar.client.amqp_exchange_factory import get_exchange
from pulsar.managers.util.drmaa import DrmaaSessionFactory
import time


class RestartTestCase(TempDirectoryTestCase):

    @skip_unless_module("drmaa")
    @skip_unless_module("kombu")
    def test_restart_finishes_job(self):
        mq_url = "memory://test1092"
        app_conf = dict(message_queue_url=mq_url)
        app_conf["managers"] = {"manager_restart": {'type': 'queued_drmaa'}}
        with restartable_pulsar_app_provider(app_conf=app_conf, web=False) as app_provider:
            job_id = '12345'

            with app_provider.new_app() as app:
                manager = app.only_manager
                job_info = {
                    'job_id': job_id,
                    'command_line': 'sleep 1000',
                    'setup': True,
                }
                submit_job(manager, job_info)
                # TODO: unfortunate breaking of abstractions here.
                time.sleep(.2)
                external_id = manager._proxied_manager._external_id(job_id)

            drmaa_session = DrmaaSessionFactory().get()
            drmaa_session.kill(external_id)
            drmaa_session.close()
            time.sleep(.2)

            consumer = SimpleConsumer(queue="status_update", url=mq_url, manager="manager_restart")
            consumer.start()

            with app_provider.new_app() as app:
                time.sleep(.3)

            consumer.join()
            assert len(consumer.messages) == 1, len(consumer.messages)
            assert consumer.messages[0]["status"] == "complete"


class SimpleConsumer(object):

    def __init__(self, queue, url, manager="_default_"):
        self.queue = queue
        self.url = url
        self.manager = manager
        self.active = True
        self.exchange = get_exchange("memory://test1092", manager, {})

        self.messages = []

    def start(self):
        t = threading.Thread(target=self._run)
        t.start()
        self.thread = t

    def join(self):
        self.active = False
        self.thread.join(10)

    def _run(self):
        self.exchange.consume("status_update", self._callback, check=self)

    def _callback(self, body, message):
        self.messages.append(body)
        message.ack()

    def __nonzero__(self):
        return self.active
