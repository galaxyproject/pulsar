import contextlib
import threading
import time

from .test_utils import (
    TempDirectoryTestCase,
    skip_unless_module,
    skip_without_drmaa,
    restartable_pulsar_app_provider,
    integration_test,
)
from pulsar.manager_endpoint_util import (
    submit_job,
)
from pulsar.managers.stateful import ActiveJobs
from pulsar.client.amqp_exchange_factory import get_exchange
from pulsar.managers.util.drmaa import DrmaaSessionFactory


class RestartTestCase(TempDirectoryTestCase):

    @skip_without_drmaa
    @skip_unless_module("kombu")
    @integration_test
    def test_restart_finishes_job(self):
        with self._setup_app_provider("restart_and_finish") as app_provider:
            job_id = '12345'

            with app_provider.new_app() as app:
                manager = app.only_manager
                job_info = {
                    'job_id': job_id,
                    'command_line': 'sleep 1000',
                    'setup': True,
                }
                submit_job(manager, job_info)
                external_id = None
                for i in range(10):
                    time.sleep(.05)
                    # TODO: unfortunate breaking of abstractions here.
                    external_id = manager._proxied_manager._external_id(job_id)
                    if external_id:
                        break
                if external_id is None:
                    assert False, "Test failed, couldn't get exteranl id for job id."

            drmaa_session = DrmaaSessionFactory().get()
            drmaa_session.kill(external_id)
            drmaa_session.close()
            consumer = self._status_update_consumer("restart_and_finish")
            consumer.start()

            with app_provider.new_app() as app:
                consumer.wait_for_messages()

            consumer.join()
            assert len(consumer.messages) == 1, len(consumer.messages)
            assert consumer.messages[0]["status"] == "complete"

    @skip_unless_module("drmaa")
    @skip_unless_module("kombu")
    @integration_test
    def test_recovery_failure_fires_lost_status(self):
        test = "restart_and_finish"
        with self._setup_app_provider(test) as app_provider:
            job_id = '12345'

            with app_provider.new_app() as app:
                persistence_directory = app.persistence_directory

            # Break some abstractions to activate a job that
            # never existed.
            manager_name = "manager_%s" % test
            active_jobs = ActiveJobs(manager_name, persistence_directory)
            active_jobs.activate_job(job_id)

            consumer = self._status_update_consumer(test)
            consumer.start()

            with app_provider.new_app() as app:
                consumer.wait_for_messages()

            consumer.join()

            assert len(consumer.messages) == 1, len(consumer.messages)
            assert consumer.messages[0]["status"] == "lost"

    @contextlib.contextmanager
    def _setup_app_provider(self, test):
        mq_url = "memory://test_%s" % test
        manager = "manager_%s" % test
        app_conf = dict(message_queue_url=mq_url)
        app_conf["managers"] = {manager: {'type': 'queued_drmaa'}}
        with restartable_pulsar_app_provider(app_conf=app_conf, web=False) as app_provider:
            yield app_provider

    def _status_update_consumer(self, test):
        mq_url = "memory://test_%s" % test
        manager = "manager_%s" % test
        consumer = SimpleConsumer(queue="status_update", url=mq_url, manager=manager)
        return consumer


class SimpleConsumer(object):

    def __init__(self, queue, url, manager="_default_"):
        self.queue = queue
        self.url = url
        self.manager = manager
        self.active = True
        self.exchange = get_exchange(url, manager, {})

        self.messages = []

    def start(self):
        t = threading.Thread(target=self._run)
        t.start()
        self.thread = t

    def join(self):
        self.active = False
        self.thread.join(10)

    def wait_for_messages(self, n=1):
        accumulate_time = 0.0
        while len(self.messages) < n:
            time.sleep(.1)
            accumulate_time += 0.05
            if accumulate_time > 3.0:
                raise Exception("Waited too long for messages.")

    def _run(self):
        self.exchange.consume("status_update", self._callback, check=self)

    def _callback(self, body, message):
        self.messages.append(body)
        message.ack()

    def __nonzero__(self):
        return self.active

    __bool__ = __nonzero__  # Both needed Py2 v 3
