import contextlib
import os
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
from pulsar.client.amqp_exchange import ACK_FORCE_NOACK_KEY
from pulsar.client.amqp_exchange_factory import get_exchange
from pulsar.managers.util.drmaa import DrmaaSessionFactory


class StateIntegrationTestCase(TempDirectoryTestCase):

    @skip_without_drmaa
    @skip_unless_module("kombu")
    @integration_test
    def test_restart_finishes_job(self):
        test = "restart_finishes"
        with self._setup_app_provider(test) as app_provider:
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
            consumer = self._status_update_consumer(test)
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
        test = "restart_failure_fires_lost"
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

    @skip_unless_module("kombu")
    @integration_test
    def test_staging_failure_fires_failed_status(self):
        test = "stating_failure_fires_failed"
        with self._setup_app_provider(test, manager_type="queued_python") as app_provider:
            job_id = '12345'

            consumer = self._status_update_consumer(test)
            consumer.start()

            with app_provider.new_app() as app:
                manager = app.only_manager
                job_info = {
                    'job_id': job_id,
                    'command_line': 'sleep 1000',
                    'setup': True,
                    # Invalid staging description...
                    'remote_staging': {"setup": [{"moo": "cow"}]}
                }
                # TODO: redo this with submit_job coming through MQ for test consistency.
                submit_job(manager, job_info)

            import time
            time.sleep(2)
            consumer.wait_for_messages()
            consumer.join()

            assert len(consumer.messages) == 1, len(consumer.messages)
            assert consumer.messages[0]["status"] == "failed"

    @skip_unless_module("kombu")
    @integration_test
    def test_async_request_of_mq_status(self):
        test = "async_request_of_mq_status"
        with self._setup_app_provider(test, manager_type="queued_python") as app_provider:
            job_id = '12345'

            consumer = self._status_update_consumer(test)
            consumer.start()

            with app_provider.new_app() as app:
                manager = app.only_manager
                job_info = {
                    'job_id': job_id,
                    'command_line': 'sleep 1000',
                    'setup': True,
                    # Invalid staging description...
                    'remote_staging': {"setup": [{"moo": "cow"}]}
                }
                # TODO: redo this with submit_job coming through MQ for test consistency.
                submit_job(manager, job_info)
                self._request_status(test, job_id)

            import time
            time.sleep(2)
            consumer.wait_for_messages()
            consumer.join()

            messages = consumer.messages
            assert len(messages) == 2, len(messages)
            assert messages[0]["status"] == "failed"
            assert messages[1]["status"] == "failed", messages[1]

    @skip_unless_module("kombu")
    @integration_test
    def test_async_request_of_mq_status_lost(self):
        test = "async_request_of_mq_status_lost"
        with self._setup_app_provider(test, manager_type="queued_python") as app_provider:
            job_id = '12347'  # should be lost? - never existed right?

            consumer = self._status_update_consumer(test)
            consumer.start()

            with app_provider.new_app() as app:
                app.only_manager
                # do two messages to ensure generation of status message doesn't
                # create a job directory we don't mean to or something like that
                self._request_status(test, job_id)
                self._request_status(test, job_id)

            import time
            time.sleep(2)
            consumer.wait_for_messages()
            consumer.join()

            messages = consumer.messages
            assert len(messages) == 2, len(messages)
            assert messages[0]["status"] == "lost", messages[0]
            assert messages[1]["status"] == "lost", messages[1]

    @skip_unless_module("kombu")
    @integration_test
    def test_setup_failure_fires_failed_status(self):
        test = "stating_failure_fires_failed"
        with self._setup_app_provider(test, manager_type="queued_python") as app_provider:
            job_id = '12345'

            consumer = self._status_update_consumer(test)
            consumer.start()

            with app_provider.new_app() as app:
                manager = app.only_manager
                job_info = {
                    'job_id': job_id,
                    'command_line': 'sleep 1000',
                    'setup': True,
                }

                with open(os.path.join(app_provider.staging_directory, job_id), "w") as f:
                    f.write("File where staging directory should be, setup should fail now.")

                # TODO: redo this with submit_job coming through MQ for test consistency,
                # would eliminate the need for the exception catch as well.
                try:
                    submit_job(manager, job_info)
                except Exception:
                    pass

            consumer.wait_for_messages()
            consumer.join()

            assert len(consumer.messages) == 1, len(consumer.messages)
            assert consumer.messages[0]["status"] == "failed"

    @contextlib.contextmanager
    def _setup_app_provider(self, test, manager_type="queued_drmaa"):
        mq_url = "memory://test_%s" % test
        manager = "manager_%s" % test
        app_conf = dict(message_queue_url=mq_url)
        app_conf["managers"] = {manager: {'type': manager_type}}
        with restartable_pulsar_app_provider(app_conf=app_conf, web=False) as app_provider:
            yield app_provider

    def _status_update_consumer(self, test):
        mq_url = "memory://test_%s" % test
        manager = "manager_%s" % test
        consumer = SimpleConsumer(queue="status_update", url=mq_url, manager=manager)
        return consumer

    def _request_status(self, test, job_id):
        mq_url = "memory://test_%s" % test
        manager = "manager_%s" % test
        exchange = get_exchange(mq_url, manager, {})
        params = {
            "job_id": job_id,
            ACK_FORCE_NOACK_KEY: True,
        }
        exchange.publish("status", params)


class SimpleConsumer:

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
