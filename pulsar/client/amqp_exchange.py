import copy
import logging
import socket
import threading
import uuid
from time import (
    sleep,
    time,
)
from typing import Optional

from packaging.version import parse as parse_version
try:
    import kombu
    import kombu.exceptions
    from kombu import pools
except ImportError:
    kombu = None

try:
    import amqp
    import amqp.exceptions
except ImportError:
    amqp = None

log = logging.getLogger(__name__)


KOMBU_UNAVAILABLE = "Attempting to bind to AMQP message queue, but kombu dependency unavailable"
AMQP_UNAVAILABLE = "Attempting to bind to AMQP message queue, but pyampq dependency unavailable"

DEFAULT_EXCHANGE_NAME = "pulsar"
DEFAULT_EXCHANGE_TYPE = "direct"
# Set timeout to periodically give up looking and check if polling should end.
DEFAULT_TIMEOUT = 0.2
DEFAULT_HEARTBEAT = 580

DEFAULT_RECONNECT_CONSUMER_WAIT = 1
DEFAULT_HEARTBEAT_WAIT = 1
DEFAULT_HEARTBEAT_JOIN_TIMEOUT = 10

ACK_QUEUE_SUFFIX = "_ack"
ACK_UUID_KEY = 'acknowledge_uuid'
ACK_QUEUE_KEY = 'acknowledge_queue'
ACK_SUBMIT_QUEUE_KEY = 'acknowledge_submit_queue'
ACK_UUID_RESPONSE_KEY = 'acknowledge_uuid_response'
ACK_FORCE_NOACK_KEY = 'force_noack'
DEFAULT_ACK_MANAGER_SLEEP = 15
DEFAULT_REPUBLISH_TIME = 30
MINIMUM_KOMBU_VERSION_PUBLISH_TIMEOUT = parse_version("5.2.0")


class PulsarExchange:
    """ Utility for publishing and consuming structured Pulsar queues using kombu.
    This is shared between the server and client - an exchange should be setup
    for each manager (or in the case of the client, each manager one wished to
    communicate with.)

    Each Pulsar manager is defined solely by name in the scheme, so only one Pulsar
    should target each AMQP endpoint or care should be taken that unique
    manager names are used across Pulsar servers targeting the same AMQP endpoint -
    and in particular only one such Pulsar should define an default manager with
    name _default_.
    """

    def __init__(
        self,
        url,
        manager_name,
        amqp_key_prefix=None,
        connect_ssl=None,
        timeout=DEFAULT_TIMEOUT,
        publish_kwds={},
        publish_uuid_store=None,
        consume_uuid_store=None,
        republish_time=DEFAULT_REPUBLISH_TIME,
    ):
        """
        """
        if not kombu:
            raise Exception(KOMBU_UNAVAILABLE)
        if not amqp:
            raise Exception(AMQP_UNAVAILABLE)
        # conditional imports and type checking prevent us from doing this at the module level.
        self.recoverable_exceptions = (
            ConnectionResetError,  # https://github.com/galaxyproject/pulsar/issues/328
            TimeoutError,
            socket.timeout,
            # Needed as long as py-ampq raises plain OSError:
            # https://github.com/celery/py-amqp/blob/a92dd037712b5b7b1622f4f9d83157d095c90910/amqp/transport.py#L584
            OSError,
            amqp.exceptions.ConnectionForced,  # e.g. connection closed on rabbitmq sigterm
            amqp.exceptions.RecoverableConnectionError,  # connection closed
            amqp.exceptions.RecoverableChannelError,  # publish time out
            kombu.exceptions.OperationalError,  # ConnectionRefusedError, e.g. when getting a new connection while rabbitmq is down
        )
        self.__kombu_version = parse_version(kombu.__version__)
        self.__url = url
        self.__manager_name = manager_name
        self.__amqp_key_prefix = amqp_key_prefix
        self.__connect_ssl = connect_ssl
        self.__exchange = kombu.Exchange(DEFAULT_EXCHANGE_NAME, DEFAULT_EXCHANGE_TYPE)
        self.__timeout = timeout
        self.__republish_time = republish_time
        # Be sure to log message publishing failures.
        if publish_kwds.get("retry", False):
            if "retry_policy" not in publish_kwds:
                publish_kwds["retry_policy"] = {}
        self.__publish_kwds = publish_kwds
        self.publish_uuid_store = publish_uuid_store
        self.consume_uuid_store = consume_uuid_store
        self.publish_ack_lock = threading.Lock()
        # Ack manager should sleep before checking for
        # republishes, but if that changes, need to drain the
        # queue once before the ack manager starts doing its
        # thing
        self.ack_manager_thread = self.__start_ack_manager()

    @staticmethod
    def __publish_errback(exc, interval, publish_log_prefix=""):
        log.error("%sConnection error while publishing: %r", publish_log_prefix, exc, exc_info=1)
        log.info("%sRetrying in %s seconds", publish_log_prefix, interval)

    @property
    def url(self):
        return self.__url

    @property
    def acks_enabled(self):
        return self.publish_uuid_store is not None

    def consume(self, queue_name, callback, check=True, connection_kwargs={}):
        queue = self.__queue(queue_name)
        log.debug("Consuming queue '%s'", queue)
        callbacks = [self.__ack_callback]
        if callback is not None:
            callbacks.append(callback)
        while check:
            heartbeat_thread = None
            try:
                with self.connection(self.__url, heartbeat=DEFAULT_HEARTBEAT, **connection_kwargs) as connection:
                    with kombu.Consumer(connection, queues=[queue], callbacks=callbacks, accept=['json']):
                        heartbeat_thread = self.__start_heartbeat(queue_name, connection)
                        while check and connection.connected:
                            try:
                                connection.drain_events(timeout=self.__timeout)
                            except (socket.timeout, TimeoutError):
                                pass
            except self.recoverable_exceptions as exc:
                self.__handle_io_error(exc, heartbeat_thread)
            except BaseException:
                log.exception("Problem consuming queue, consumer quitting in problematic fashion!")
                raise
        log.info("Done consuming queue %s" % queue_name)

    def __ack_callback(self, body, message):
        if ACK_UUID_KEY in body:
            # The consumer of a normal queue has received a message requiring
            # acknowledgement
            ack_uuid = body[ACK_UUID_KEY]
            ack_queue = body[ACK_QUEUE_KEY]
            response = {ACK_UUID_RESPONSE_KEY: ack_uuid}
            log.debug('Acknowledging UUID %s on queue %s', ack_uuid, ack_queue)
            self.publish(ack_queue, response)
            if self.consume_uuid_store is None:
                log.warning('Received an ack request (UUID: %s, response queue: '
                            '%s) but ack UUID persistence is not enabled, check '
                            'your config', ack_uuid, ack_queue)
            elif ack_uuid not in self.consume_uuid_store:
                # This message has not been seen before, store the uuid so it
                # is not operated on more than once
                self.consume_uuid_store[ack_uuid] = time()
            else:
                # This message has been seen before, prevent downstream
                # callbacks from processing normally by acknowledging it here,
                # still send the ack reply
                log.warning('Message with UUID %s on queue %s has already '
                            'been performed, skipping callback', ack_uuid, ack_queue)
                message.ack()
        elif ACK_UUID_RESPONSE_KEY in body:
            # The consumer of an ack queue has received an ack, remove it from the store
            ack_uuid = body[ACK_UUID_RESPONSE_KEY]
            log.debug('Got acknowledgement for UUID %s, will remove from store', ack_uuid)
            try:
                with self.publish_ack_lock:
                    del self.publish_uuid_store[ack_uuid]
            except KeyError:
                log.warning('Cannot remove UUID %s from store, already removed', ack_uuid)
            message.ack()

    def __handle_io_error(self, exc: BaseException, heartbeat_thread: Optional[threading.Thread] = None):
        # In testing, errno is None
        log.warning('Got %s, will retry: %s', exc.__class__.__name__, exc)
        try:
            if heartbeat_thread:
                heartbeat_thread.join(DEFAULT_HEARTBEAT_JOIN_TIMEOUT)
        except Exception:
            log.exception("Failed to join heartbeat thread, this is bad?")
        try:
            sleep(DEFAULT_RECONNECT_CONSUMER_WAIT)
        except Exception:
            log.exception("Interrupted sleep while waiting to reconnect to message queue, may restart unless problems encountered.")

    def heartbeat(self, connection):
        log.debug('AMQP heartbeat thread alive')
        try:
            while connection.connected:
                connection.heartbeat_check()
                sleep(DEFAULT_HEARTBEAT_WAIT)
        except BaseException:
            log.exception("Problem with heartbeat, leaving heartbeat method in problematic state!")
            raise
        log.debug('AMQP heartbeat thread exiting')

    def publish(self, name, payload):
        # Consider optionally disabling if throughput becomes main concern.
        transaction_uuid = uuid.uuid1()
        key = self.__queue_name(name)
        publish_log_prefix = self.__publish_log_prefex(transaction_uuid)
        log.debug("%sBegin publishing to key %s", publish_log_prefix, key)
        if (self.acks_enabled and not name.endswith(ACK_QUEUE_SUFFIX) and
                ACK_FORCE_NOACK_KEY not in payload):
            # Publishing a message on a normal queue and it's not a republish
            # (or explicitly forced do-not-ack), so add ack keys
            ack_uuid = str(transaction_uuid)
            ack_queue = name + ACK_QUEUE_SUFFIX
            payload[ACK_UUID_KEY] = ack_uuid
            payload[ACK_QUEUE_KEY] = ack_queue
            payload[ACK_SUBMIT_QUEUE_KEY] = name
            self.publish_uuid_store[ack_uuid] = payload
            log.debug('Requesting acknowledgement of UUID %s on queue %s', ack_uuid, ack_queue)
        with self.connection(self.__url) as connection:
            with pools.producers[connection].acquire() as producer:
                log.debug("%sHave producer for publishing to key %s", publish_log_prefix, key)
                publish_kwds = self.__prepare_publish_kwds(publish_log_prefix)
                try:
                    producer.publish(
                        payload,
                        serializer='json',
                        exchange=self.__exchange,
                        declare=[self.__exchange],
                        routing_key=key,
                        **publish_kwds
                    )
                    log.debug("%sPublished to key %s", publish_log_prefix, key)
                    return True
                except Exception as e:
                    log.error("%sFailed to publish to key %s: %s", publish_log_prefix, key, str(e))
                    self.__fail_publish(name, payload, e)

    def ack_manager(self):
        log.debug('Acknowledgement manager thread alive')
        failed = set()
        try:
            while True:
                sleep(DEFAULT_ACK_MANAGER_SLEEP)
                with self.publish_ack_lock:
                    for unack_uuid in self.publish_uuid_store.keys():
                        if self.publish_uuid_store.get_time(unack_uuid) < time() - self.__republish_time:
                            payload = self.__get_payload(unack_uuid, failed)
                            if payload is None:
                                continue
                            payload[ACK_FORCE_NOACK_KEY] = True
                            resubmit_queue = payload[ACK_SUBMIT_QUEUE_KEY]
                            log.debug('UUID %s has not been acknowledged, '
                                      'republishing original message on queue %s',
                                      unack_uuid, resubmit_queue)
                            try:
                                if self.publish(resubmit_queue, payload):
                                    self.publish_uuid_store.set_time(unack_uuid)
                                else:
                                    # If we fail to publish, we need to remove the uuid from the store
                                    # so it doesn't get republished again.
                                    self.__discard_publish_uuid(unack_uuid, failed)
                            except self.recoverable_exceptions as e:
                                self.__handle_io_error(e)
                                continue
        except Exception:
            log.exception("Problem with acknowledgement manager, leaving ack manager in problematic state!")
            raise

    def __fail_publish(self, name, payload, exception):
        # Send just a few safe keys if we have them:
        keys_to_send = [
            "job_id",
            "returncode",
            "stdout",
            "stderr",
            "job_stdout",
            "job_stderr",
        ]
        new_payload = {}
        for key in keys_to_send:
            if key in payload:
                new_payload[key] = payload[key]
        # Add the original payload to the new payload
        new_payload["exception"] = str(exception)
        new_payload["status"] = "failed"
        self.publish(name, new_payload)

    def __get_payload(self, uuid, failed):
        """Retry reading a message from the publish_uuid_store once, delete on the second failure."""
        # Caller should have the publish_uuid_store lock
        try:
            return self.publish_uuid_store[uuid]
        except Exception as exc:
            msg = "Failed to load payload from publish store for UUID %s, %s: %s"
            if uuid in failed:
                log.error(msg, uuid, "discarding", str(exc))
                self.__discard_publish_uuid(uuid, failed)
            else:
                log.error(msg, uuid, "will try agan", str(exc))
                failed.add(uuid)
        return None

    def __discard_publish_uuid(self, uuid, failed):
        try:
            del self.publish_uuid_store[uuid]
            failed.discard(uuid)
        except Exception as exc:
            log.error("Failed to discard UUID %s from publish store: %s", uuid, str(exc))

    def __prepare_publish_kwds(self, publish_log_prefix):
        if "retry_policy" in self.__publish_kwds:
            publish_kwds = copy.deepcopy(self.__publish_kwds)

            def errback(exc, interval):
                return PulsarExchange.__publish_errback(exc, interval, publish_log_prefix)
            publish_kwds["retry_policy"]["errback"] = errback
        else:
            publish_kwds = self.__publish_kwds
        if self.__kombu_version < MINIMUM_KOMBU_VERSION_PUBLISH_TIMEOUT:
            log.warning(f"kombu version {kombu.__version__} does not support timeout argument to publish. Consider updating to 5.2.0 or newer")
            publish_kwds.pop("timeout", None)
        return publish_kwds

    def __publish_log_prefex(self, transaction_uuid=None):
        prefix = ""
        if transaction_uuid:
            prefix = "[publish:%s] " % str(transaction_uuid)
        return prefix

    def connection(self, connection_string, **kwargs):
        if "ssl" not in kwargs:
            kwargs["ssl"] = self.__connect_ssl
        return kombu.Connection(connection_string, **kwargs)

    def __queue(self, name):
        queue_name = self.__queue_name(name)
        queue = kombu.Queue(queue_name, self.__exchange, routing_key=queue_name)
        return queue

    def __queue_name(self, name):
        key_prefix = self.__key_prefix()
        queue_name = '{}_{}'.format(key_prefix, name)
        return queue_name

    def __key_prefix(self):
        if self.__amqp_key_prefix is not None:
            key_prefix = self.__amqp_key_prefix
        else:
            if self.__manager_name == "_default_":
                key_prefix = "pulsar_"
            else:
                key_prefix = "pulsar_%s_" % self.__manager_name
        return key_prefix

    def __start_heartbeat(self, queue_name, connection):
        thread_name = "consume-heartbeat-%s" % (self.__queue_name(queue_name))
        thread = threading.Thread(name=thread_name, target=self.heartbeat, args=(connection,))
        thread.start()
        return thread

    def __start_ack_manager(self):
        if self.acks_enabled:
            thread_name = "acknowledgement-manager"
            thread = threading.Thread(name=thread_name, target=self.ack_manager)
            thread.daemon = True
            thread.start()
            return thread
