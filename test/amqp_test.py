"""Tests for ``pulsar.client.amqp_exchange``."""
import time
import threading

from pulsar.client import amqp_exchange

from .test_utils import (
    skip_unless_module,
    timed,
)

TEST_CONNECTION = "memory://test_amqp"


@skip_unless_module("kombu")
@timed(15)
def test_amqp():
    """Test the client PulsarExchange abstraction with an in-memory connection."""
    manager1_exchange = amqp_exchange.PulsarExchange(TEST_CONNECTION, "manager_test")
    manager3_exchange = amqp_exchange.PulsarExchange(TEST_CONNECTION, "manager3_test")
    manager2_exchange = amqp_exchange.PulsarExchange(TEST_CONNECTION, "manager2_test")
    thread1 = TestThread("manager_test", manager1_exchange)
    thread2 = TestThread("manager2_test", manager2_exchange)
    thread3 = TestThread("manager3_test", manager3_exchange)
    thread1.start()
    thread2.start()
    thread3.start()
    time.sleep(0.5)
    manager1_exchange.publish("manager_test", u"cow1")
    manager2_exchange.publish("manager2_test", u"cow2")
    manager3_exchange.publish("manager3_test", u"cow3")
    time.sleep(0.1)
    thread1.wait_for_message(u"cow1")
    thread2.wait_for_message(u"cow2")
    thread3.wait_for_message(u"cow3")


class TestThread(threading.Thread):

    def __init__(self, queue_name, exchange):
        super(TestThread, self).__init__(target=self.run)
        self.queue_name = queue_name
        self.daemon = True
        self.exchange = exchange
        self.message = None

    def __nonzero__(self):
        return self.message is None

    __bool__ = __nonzero__  # Both needed Py2 v 3

    def run(self):
        def callback(body, message):
            self.message = body
            message.ack()

        self.exchange.consume(self.queue_name, callback=callback, check=self)

    def wait_for_message(self, expected_message):
        while self:
            time.sleep(.05)
        if self.message != expected_message:
            msg = "Expected [%s], got [%s]." % (expected_message, self.message)
            raise AssertionError(msg)

        self.join(2)


__all__ = ["test_amqp"]
