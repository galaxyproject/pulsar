import threading

from .test_utils import skipUnlessModule
from lwr.lwr_client import amqp_exchange

TEST_CONNECTION = "memory://test_amqp"


@skipUnlessModule("kombu")
def test_amqp():
    manager1_exchange = amqp_exchange.LwrExchange(TEST_CONNECTION, "manager_test")
    manager3_exchange = amqp_exchange.LwrExchange(TEST_CONNECTION, "manager3_test")
    manager2_exchange = amqp_exchange.LwrExchange(TEST_CONNECTION, "manager2_test")
    thread1 = TestThread("manager_test", manager1_exchange)
    thread2 = TestThread("manager2_test", manager2_exchange)
    thread3 = TestThread("manager3_test", manager3_exchange)
    thread1.start()
    thread2.start()
    thread3.start()
    manager1_exchange.publish("manager_test", "cow1")
    manager2_exchange.publish("manager2_test", "cow2")
    manager3_exchange.publish("manager3_test", "cow3")
    thread1.join(1)
    thread2.join(1)
    thread3.join(1)
    assert thread1.message == "cow1", thread1.message
    assert thread2.message == "cow2", thread2.message
    assert thread3.message == "cow3", thread3.message


class TestThread(threading.Thread):

    def __init__(self, queue_name, exchange):
        super(TestThread, self).__init__()
        self.queue_name = queue_name
        self.daemon = True
        self.exchange = exchange
        self.message = None

    def __nonzero__(self):
        return self.message is None

    def run(self):
        def callback(body, message):
            self.message = body
            message.ack()

        self.exchange.consume(self.queue_name, callback=callback, check=self)
