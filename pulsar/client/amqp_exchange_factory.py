from .amqp_exchange import PulsarExchange
from .util import (
    filter_destination_params,
    MessageQueueUUIDStore,
)


def get_exchange(url, manager_name, params):
    connect_ssl = parse_amqp_connect_ssl_params(params)
    exchange_kwds = dict(
        manager_name=manager_name,
        amqp_key_prefix=params.get("amqp_key_prefix"),
        connect_ssl=connect_ssl,
        publish_kwds=parse_amqp_publish_kwds(params),
    )
    # Default True: kombu declares durable queues/exchanges by default, which is
    # what Pulsar did before opt-in durability was added, and RabbitMQ 4.x
    # rejects transient non-exclusive queues outright (transient_nonexcl_queues
    # is deprecated). Keep the knob for explicit opt-out on legacy brokers.
    durable_param = params.get("amqp_durable", True)
    if isinstance(durable_param, str):
        durable_param = durable_param.strip().lower() in ("true", "1", "yes", "on")
    exchange_kwds["durable"] = bool(durable_param)
    if params.get('amqp_acknowledge', False):
        exchange_kwds.update(parse_ack_kwds(params, manager_name))
    timeout = params.get('amqp_consumer_timeout', False)
    if timeout is not False:
        exchange_kwds['timeout'] = timeout
    exchange = PulsarExchange(url, **exchange_kwds)
    return exchange


def parse_amqp_connect_ssl_params(params):
    ssl_params = filter_destination_params(params, "amqp_connect_ssl_")
    if not ssl_params:
        return

    ssl = __import__('ssl')
    if 'cert_reqs' in ssl_params:
        value = ssl_params['cert_reqs']
        ssl_params['cert_reqs'] = getattr(ssl, value.upper())
    return ssl_params


DEFAULT_PUBLISH_RETRY_POLICY = {
    "max_retries": 5,
    "interval_start": 1,
    "interval_step": 2,
    "interval_max": 30,
}


def parse_amqp_publish_kwds(params):
    all_publish_params = filter_destination_params(params, "amqp_publish_")
    retry_policy_params = {}
    for key in all_publish_params.copy().keys():
        if key.startswith("retry_"):
            value = all_publish_params[key]
            retry_policy_params[key[len("retry_"):]] = value
            del all_publish_params[key]
    if all_publish_params.get("retry"):
        # Defense-in-depth: a single broker hiccup at the wrong moment must not
        # drop a status_update. Defaults are bounded so we don't block the
        # postprocess thread indefinitely; the persistent outbox handles the
        # case where retries are exhausted.
        for key, default in DEFAULT_PUBLISH_RETRY_POLICY.items():
            retry_policy_params.setdefault(key, default)
    if retry_policy_params:
        all_publish_params["retry_policy"] = retry_policy_params
        all_publish_params.setdefault("retry", True)
    return all_publish_params


def parse_ack_kwds(params, manager_name):
    ack_params = {}
    persistence_directory = params.get('persistence_directory', None)
    if persistence_directory:
        subdirs = ['amqp_ack-%s' % manager_name]
        ack_params['publish_uuid_store'] = MessageQueueUUIDStore(persistence_directory, subdirs=subdirs + ['publish'])
        ack_params['consume_uuid_store'] = MessageQueueUUIDStore(persistence_directory, subdirs=subdirs + ['consume'])
    republish_time = params.get('amqp_ack_republish_time', None)
    if republish_time:
        ack_params['republish_time'] = int(republish_time)
    return ack_params
