"""Entry point for client creation.

``build_client_manager`` in particular is the abstraction that should be used
to create a ``ClientManager``, that in return can create Pulsar clients for
specific actions.
"""

import functools
import threading
from logging import getLogger
from os import getenv
from queue import Queue
from typing import (
    Any,
    Dict,
    Optional,
    Type,
    TYPE_CHECKING,
)

from typing_extensions import Protocol

from .amqp_exchange_factory import get_exchange
from .client import (
    BaseJobClient,
    InputCachingJobClient,
    JobClient,
    GcpMessageCoexecutionJobClient,
    GcpPollingCoexecutionJobClient,
    K8sMessageCoexecutionJobClient,
    K8sPollingCoexecutionJobClient,
    MessageCLIJobClient,
    MessageJobClient,
    RelayJobClient,
    TesMessageCoexecutionJobClient,
    TesPollingCoexecutionJobClient,
)
from .destination import url_to_destination_params
from .object_client import ObjectStoreClient
from .server_interface import (
    HttpPulsarInterface,
    LocalPulsarInterface,
    PulsarInterface,
)
from .transport import get_transport
from .transport.relay import RelayTransport
from .util import TransferEventManager

if TYPE_CHECKING:
    from pulsar.managers import ManagerInterface

log = getLogger(__name__)

DEFAULT_TRANSFER_THREADS = 2


class ClientManagerInterface(Protocol):

    def get_client(self, destination_params: Dict[str, Any], job_id: str, **kwargs: Dict[str, Any]) -> BaseJobClient:
        """Get client instance for specified job description."""

    def shutdown(self, ensure_cleanup=False) -> None:
        """Mark client manager's work as complete and clean up resources it managed."""
        return


class ClientManager(ClientManagerInterface):
    """Factory class to create Pulsar clients.

    This class was introduced for classes of clients that need to potential
    share state between multiple client connections.
    """
    job_manager_interface_class: Type[PulsarInterface]
    client_class: Type[BaseJobClient]

    def __init__(self, job_manager: Optional["ManagerInterface"] = None, **kwds: Dict[str, Any]):
        """Build a HTTP client or a local client that talks directly to a job manger."""
        if 'pulsar_app' in kwds or job_manager:
            self.job_manager_interface_class = LocalPulsarInterface
            pulsar_app = kwds.get('pulsar_app', None)
            file_cache = kwds.get('file_cache', None)
            self.job_manager_interface_args = dict(
                job_manager=job_manager,
                pulsar_app=pulsar_app,
                file_cache=file_cache,
            )
        else:
            print(kwds)
            self.job_manager_interface_class = HttpPulsarInterface
            transport_type = kwds.get('transport', None)
            transport_params = {p.replace('transport_', '', 1): v for p, v in kwds.items() if p.startswith('transport_')}
            transport = get_transport(transport_type, transport_params=transport_params)
            self.job_manager_interface_args = dict(transport=transport)
        cache = kwds.get('cache', None)
        if cache is None:
            cache = _environ_default_int('PULSAR_CACHE_TRANSFERS')
        if cache:
            log.info("Setting Pulsar client class to caching variant.")
            self.client_cacher = ClientCacher(**kwds)
            self.client_class = InputCachingJobClient
            self.extra_client_kwds = {"client_cacher": self.client_cacher}
        else:
            log.info("Setting Pulsar client class to standard, non-caching variant.")
            self.client_class = JobClient
            self.extra_client_kwds = {}

    def get_client(self, destination_params, job_id, **kwargs):
        """Build a client given specific destination parameters and job_id."""
        destination_params = _parse_destination_params(destination_params)
        destination_params.update(**kwargs)
        job_manager_interface_class = self.job_manager_interface_class
        job_manager_interface_args = dict(destination_params=destination_params, **self.job_manager_interface_args)
        job_manager_interface = job_manager_interface_class(**job_manager_interface_args)
        return self.client_class(destination_params, job_id, job_manager_interface, **self.extra_client_kwds)


try:
    from galaxy.jobs.runners.util.cli import factory as cli_factory
except ImportError:
    from pulsar.managers.util.cli import factory as cli_factory


class BaseRemoteConfiguredJobClientManager(ClientManagerInterface):

    def __init__(self, **kwds: Dict[str, Any]):
        self.manager_name = kwds.get("manager", None) or "_default_"


class MessageQueueClientManager(BaseRemoteConfiguredJobClientManager):
    status_cache: Dict[str, Any]
    ack_consumer_threads: Dict[str, threading.Thread]

    def __init__(self, amqp_url: str, **kwds: Dict[str, Any]):
        super().__init__(**kwds)
        self.url = amqp_url
        self.amqp_key_prefix = kwds.get("amqp_key_prefix", None)
        self.exchange = get_exchange(self.url, self.manager_name, kwds)
        self.status_cache = {}
        self.callback_lock = threading.Lock()
        self.callback_thread = None
        self.ack_consumer_threads = {}
        self.active = True

    def callback_wrapper(self, callback, body, message):
        if message.acknowledged:
            log.info("Message is already acknowledged (by an upstream "
                     "callback?), Pulsar client will not handle this message")
            return
        if not self.active:
            log.debug("Obtained update message for inactive client manager, attempting requeue.")
            try:
                message.requeue()
                log.debug("Requeue succeeded, will likely be handled next time consumer is enabled.")
            except Exception:
                log.debug("Requeue failed, message may be lost?")
            return

        try:
            if "job_id" in body:
                job_id = body["job_id"]
                self.status_cache[job_id] = body
            log.debug("Handling asynchronous status update from remote Pulsar.")
            callback(body)
        except Exception:
            log.exception("Failure processing job status update message.")
        except BaseException as e:
            log.exception("Failure processing job status update message - BaseException type %s" % type(e))
        finally:
            message.ack()

    def callback_consumer(self, callback_wrapper):
        try:
            self.exchange.consume("status_update", callback_wrapper, check=self)
        except Exception:
            log.exception("Exception while handling status update messages, "
                          "this shouldn't really happen. Handler should be "
                          "restarted.")
        finally:
            log.debug("Leaving Pulsar client status update thread, no "
                      "additional Pulsar updates will be processed.")

    def ensure_has_status_update_callback(self, callback):
        with self.callback_lock:
            if self.callback_thread is not None:
                return

            callback_wrapper = functools.partial(self.callback_wrapper, callback)
            run = functools.partial(self.callback_consumer, callback_wrapper)
            thread = threading.Thread(
                name="pulsar_client_%s_status_update_callback" % self.manager_name,
                target=run
            )
            thread.daemon = False  # Lets not interrupt processing of this.
            thread.start()
            self.callback_thread = thread

    def ack_consumer(self, queue_name: str):
        try:
            self.exchange.consume(queue_name + '_ack', None, check=self)
        except Exception:
            log.exception("Exception while handling %s acknowledgement "
                          "messages, this shouldn't really happen. Handler "
                          "should be restarted.", queue_name)
        finally:
            log.debug("Leaving Pulsar client %s acknowledgement thread, no "
                      "additional acknowledgements will be processed.",
                      queue_name)

    def ensure_has_ack_consumers(self):
        with self.callback_lock:
            for name in ('setup', 'kill'):
                if name in self.ack_consumer_threads:
                    return

                run = functools.partial(self.ack_consumer, name)
                thread = threading.Thread(
                    name="pulsar_client_{}_{}_ack".format(self.manager_name, name),
                    target=run
                )
                thread.daemon = False  # Lets not interrupt processing of this.
                thread.start()
                self.ack_consumer_threads[name] = thread

    def shutdown(self, ensure_cleanup: bool = False):
        self.active = False
        if ensure_cleanup:
            if self.callback_thread is not None:
                self.callback_thread.join()
            for v in self.ack_consumer_threads.values():
                v.join()

    def __nonzero__(self):
        return self.active

    __bool__ = __nonzero__  # Both needed Py2 v 3

    def get_client(self, destination_params, job_id, **kwargs):
        if job_id is None:
            raise Exception("Cannot generate Pulsar client for empty job_id.")
        destination_params = _parse_destination_params(destination_params)
        destination_params.update(**kwargs)
        if self.amqp_key_prefix:
            destination_params["amqp_key_prefix"] = self.amqp_key_prefix
        if 'shell_plugin' in destination_params:
            shell = cli_factory.get_shell(destination_params)
            return MessageCLIJobClient(destination_params, job_id, self, shell)
        elif destination_params.get('k8s_enabled', False):
            return K8sMessageCoexecutionJobClient(destination_params, job_id, self)
        elif destination_params.get("tes_url", False):
            return TesMessageCoexecutionJobClient(destination_params, job_id, self)
        elif destination_params.get("project_id", False):
            return GcpMessageCoexecutionJobClient(destination_params, job_id, self)
        else:
            return MessageJobClient(destination_params, job_id, self)


class RelayClientManager(BaseRemoteConfiguredJobClientManager):
    """Client manager that communicates with Pulsar via pulsar-relay.

    This manager uses HTTP-based long-polling to receive status updates from
    Pulsar through the relay, while posting control messages (setup, status
    requests, kill) to the relay for Pulsar to consume.
    """
    status_cache: Dict[str, Any]

    def __init__(self, relay_url: str, relay_username: str, relay_password: str, relay_topic_prefix: str = '', **kwds: Dict[str, Any]):
        super().__init__(**kwds)

        if not relay_url:
            raise Exception("relay_url is required for RelayClientManager")

        # Initialize relay transport
        self.relay_transport = RelayTransport(relay_url, relay_username, relay_password)
        self.relay_topic_prefix = relay_topic_prefix
        self.status_cache = {}
        self.callback_lock = threading.Lock()
        self.callback_thread = None
        self.active = True
        self.shutdown_event = threading.Event()

    def callback_wrapper(self, callback, message_data):
        """Process status update messages from the relay."""
        if not self.active:
            log.debug("Obtained update message for inactive client manager, ignoring.")
            return

        try:
            payload = message_data.get('payload', {})
            if "job_id" in payload:
                job_id = payload["job_id"]
                self.status_cache[job_id] = payload
            log.debug("Handling asynchronous status update from Pulsar via relay.")
            callback(payload)
        except Exception:
            log.exception("Failure processing job status update message.")
        except BaseException as e:
            log.exception("Failure processing job status update message - BaseException type %s" % type(e))

    def status_consumer(self, callback_wrapper):
        """Long-poll the relay for status update messages."""
        manager_name = self.manager_name
        topic = self._make_topic_name("job_status_update", manager_name)

        log.info("Starting relay status consumer for topic '%s'", topic)

        while self.active:
            try:
                # Long poll for status updates (30 second timeout)
                messages = self.relay_transport.long_poll([topic], timeout=30)

                for message in messages:
                    callback_wrapper(message)

            except Exception:
                if self.active:
                    log.exception("Exception while polling for status updates from relay, will retry.")
                    # Brief sleep before retrying to avoid tight loop on persistent errors
                    # Use wait() instead of sleep() to allow immediate interruption on shutdown
                    if self.shutdown_event.wait(timeout=5):
                        break
                else:
                    log.debug("Exception during shutdown, ignoring.")
                    break

        log.info("Done consuming relay status updates for topic %s", topic)

    def ensure_has_status_update_callback(self, callback):
        """Start a thread to poll for status updates if not already running."""
        with self.callback_lock:
            if self.callback_thread is not None:
                return

            callback_wrapper = functools.partial(self.callback_wrapper, callback)
            run = functools.partial(self.status_consumer, callback_wrapper)
            thread = threading.Thread(
                name="pulsar_client_%s_relay_status_consumer" % self.manager_name,
                target=run
            )
            # Make daemon so Python can exit even if thread is blocked in HTTP request.
            # Unlike MessageQueueClientManager which uses AMQP connections that can be
            # interrupted cleanly, HTTP long-poll requests block until timeout.
            thread.daemon = True
            thread.start()
            self.callback_thread = thread

    def ensure_has_ack_consumers(self):
        """No-op for relay client manager, as acknowledgements are handled via HTTP."""
        pass

    def _make_topic_name(self, base_topic: str, manager_name: str) -> str:
        """Create a topic name with optional prefix and manager suffix.

        Args:
            base_topic: Base topic name (e.g., 'job_setup', 'job_status_update')
            manager_name: Manager name (e.g., '_default_', 'cluster_a')

        Returns:
            Fully qualified topic name
        """
        parts = []

        # Add prefix if provided
        if self.relay_topic_prefix:
            parts.append(self.relay_topic_prefix)

        # Add base topic
        parts.append(base_topic)

        # Add manager name if not default
        if manager_name != "_default_":
            parts.append(manager_name)

        return "_".join(parts)

    def shutdown(self, ensure_cleanup: bool = False):
        """Shutdown the client manager and cleanup resources."""
        self.active = False
        # Signal the shutdown event to interrupt any waiting threads
        self.shutdown_event.set()
        if ensure_cleanup:
            if self.callback_thread is not None:
                self.callback_thread.join()
        # Close relay transport
        if hasattr(self, 'relay_transport'):
            self.relay_transport.close()

    def __nonzero__(self):
        return self.active

    __bool__ = __nonzero__  # Both needed Py2 v 3

    def get_client(self, destination_params, job_id, **kwargs):
        """Create a RelayJobClient for the given job."""
        if job_id is None:
            raise Exception("Cannot generate Pulsar client for empty job_id.")
        destination_params = _parse_destination_params(destination_params)
        destination_params.update(**kwargs)
        return RelayJobClient(destination_params, job_id, self)


class PollingJobClientManager(BaseRemoteConfiguredJobClientManager):

    def get_client(self, destination_params, job_id, **kwargs):
        if job_id is None:
            raise Exception("Cannot generate Pulsar client for empty job_id.")
        destination_params = _parse_destination_params(destination_params)
        destination_params.update(**kwargs)
        # TODO: cli version of this...
        if destination_params.get('k8s_enabled', False):
            return K8sPollingCoexecutionJobClient(destination_params, job_id, self)
        elif destination_params.get("tes_url", False):
            return TesPollingCoexecutionJobClient(destination_params, job_id, self)
        elif destination_params.get("project_id", False):
            return GcpPollingCoexecutionJobClient(destination_params, job_id, self)
        else:
            raise Exception("Unknown client configuration")

    def shutdown(self, ensure_cleanup=False):
        pass


def build_client_manager(
    job_manager: Optional["ManagerInterface"] = None,
    relay_url: Optional[str] = None,
    relay_username: Optional[str] = None,
    relay_password: Optional[str] = None,
    relay_topic_prefix: Optional[str] = None,
    amqp_url: Optional[str] = None,
    k8s_enabled: Optional[bool] = None,
    tes_enabled: Optional[bool] = None,
    gcp_batch_enabled: Optional[bool] = None,
    **kwargs
) -> ClientManagerInterface:
    if job_manager:
        return ClientManager(job_manager=job_manager, **kwargs)  # TODO: Consider more separation here.
    elif relay_url:
        assert relay_password and relay_username, "relay_url set, but relay_username and relay_password must also be set"
        return RelayClientManager(
            relay_url=relay_url,
            relay_username=relay_username,
            relay_password=relay_password,
            relay_topic_prefix=relay_topic_prefix or '',
            **kwargs
        )
    elif amqp_url:
        return MessageQueueClientManager(amqp_url=amqp_url, **kwargs)
    elif k8s_enabled or tes_enabled or gcp_batch_enabled:
        return PollingJobClientManager(**kwargs)
    else:
        return ClientManager(**kwargs)


class ObjectStoreClientManager:

    def __init__(self, **kwds):
        if 'object_store' in kwds:
            self.interface_class = LocalPulsarInterface
            self.interface_args = dict(object_store=kwds['object_store'])
        else:
            self.interface_class = HttpPulsarInterface
            transport_type = kwds.get('transport', None)
            transport = get_transport(transport_type)
            self.interface_args = dict(transport=transport)
        self.extra_client_kwds = {}

    def get_client(self, client_params):
        interface_class = self.interface_class
        interface_args = dict(destination_params=client_params, **self.interface_args)
        interface = interface_class(**interface_args)
        return ObjectStoreClient(interface)


class ClientCacher:

    def __init__(self, **kwds):
        self.event_manager = TransferEventManager()
        default_transfer_threads = _environ_default_int('PULSAR_CACHE_THREADS', DEFAULT_TRANSFER_THREADS)
        num_transfer_threads = int(kwds.get('transfer_threads', default_transfer_threads))
        self.__init_transfer_threads(num_transfer_threads)

    def queue_transfer(self, client, path):
        self.transfer_queue.put((client, path))

    def acquire_event(self, input_path):
        return self.event_manager.acquire_event(input_path)

    def _transfer_worker(self):
        while True:
            transfer_info = self.transfer_queue.get()
            try:
                self.__perform_transfer(transfer_info)
            except BaseException as e:
                log.warn("Transfer failed.")
                log.exception(e)
                pass
            self.transfer_queue.task_done()

    def __perform_transfer(self, transfer_info):
        (client, path) = transfer_info
        event_holder = self.event_manager.acquire_event(path, force_clear=True)
        failed = True
        try:
            client.cache_insert(path)
            failed = False
        finally:
            event_holder.failed = failed
            event_holder.release()

    def __init_transfer_threads(self, num_transfer_threads):
        self.num_transfer_threads = num_transfer_threads
        self.transfer_queue = Queue()
        for _ in range(num_transfer_threads):
            t = threading.Thread(target=self._transfer_worker)
            t.daemon = True
            t.start()


def _parse_destination_params(destination_params):
    try:
        unicode_type = unicode
    except NameError:
        unicode_type = str
    if isinstance(destination_params, str) or isinstance(destination_params, unicode_type):
        destination_params = url_to_destination_params(destination_params)
    return destination_params


def _environ_default_int(variable, default="0"):
    val = getenv(variable, default)
    int_val = int(default)
    if str(val).isdigit():
        int_val = int(val)
    return int_val


__all__ = (
    'ClientManager',
    'ObjectStoreClientManager',
    'HttpPulsarInterface',
)
