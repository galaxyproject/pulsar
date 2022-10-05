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
    Type,
)

from .amqp_exchange_factory import get_exchange
from .client import (
    BaseJobClient,
    InputCachingJobClient,
    JobClient,
    K8sMessageCoexecutionJobClient,
    K8sPollingCoexecutionJobClient,
    MessageCLIJobClient,
    MessageJobClient,
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
from .util import TransferEventManager

log = getLogger(__name__)

DEFAULT_TRANSFER_THREADS = 2


class ClientManagerInterface:

    def get_client(self, destination_params: Dict[str, Any], job_id: str, **kwargs: Dict[str, Any]) -> BaseJobClient:
        """Get client instance for specified job description."""

    def shutdown(self, ensure_cleanup=False):
        """Mark client manager's work as complete and clean up resources it managed."""


class ClientManager(ClientManagerInterface):
    """Factory class to create Pulsar clients.

    This class was introduced for classes of clients that need to potential
    share state between multiple client connections.
    """
    job_manager_interface_class: Type[PulsarInterface]
    client_class: Type[BaseJobClient]

    def __init__(self, **kwds: Dict[str, Any]):
        """Build a HTTP client or a local client that talks directly to a job manger."""
        if 'pulsar_app' in kwds or 'job_manager' in kwds:
            self.job_manager_interface_class = LocalPulsarInterface
            pulsar_app = kwds.get('pulsar_app', None)
            job_manager = kwds.get('job_manager', None)
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

    def shutdown(self, ensure_cleanup=False):
        """Mark client manager's work as complete and clean up resources it managed."""
        pass


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

    def __init__(self, **kwds: Dict[str, Any]):
        super().__init__(**kwds)
        self.url = kwds.get('amqp_url')
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
        if 'shell_plugin' in destination_params:
            shell = cli_factory.get_shell(destination_params)
            return MessageCLIJobClient(destination_params, job_id, self, shell)
        elif destination_params.get('k8s_enabled', False):
            return K8sMessageCoexecutionJobClient(destination_params, job_id, self)
        elif destination_params.get("tes_url", False):
            return TesMessageCoexecutionJobClient(destination_params, job_id, self)
        else:
            return MessageJobClient(destination_params, job_id, self)


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
        else:
            raise Exception("Unknown client configuration")

    def shutdown(self, ensure_cleanup=False):
        pass


def build_client_manager(**kwargs: Dict[str, Any]) -> ClientManagerInterface:
    if 'job_manager' in kwargs:
        return ClientManager(**kwargs)  # TODO: Consider more separation here.
    elif kwargs.get('amqp_url', None):
        return MessageQueueClientManager(**kwargs)
    elif kwargs.get("k8s_enabled") or kwargs.get("tes_url"):
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
        for i in range(num_transfer_threads):
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
