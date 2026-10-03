Client API imports
==================

Importing ``pulsar.client`` or ``pulsar.client.staging`` does not load execution
clients, backend SDKs, or Galaxy's tool parser. Their existing public APIs
remain available through lazy compatibility exports, so Galaxy's existing
imports need no changes. Implementation modules can also be imported directly.

Staging constants retain their original paths::

    from pulsar.client.staging import (
        COMMAND_VERSION_FILENAME,
        DEFAULT_DYNAMIC_COLLECTION_PATTERN,
        EXTENDED_METADATA_DYNAMIC_COLLECTION_PATTERN,
    )

Compatibility and explicit imports
----------------------------------

Python initializes parent packages before importing a submodule. Ordinary
re-exports in ``pulsar.client`` would therefore load client dependencies even
for an import of a staging constant. Small package-level ``__getattr__``
functions resolve the public names on first access and cache the actual
objects. There are no proxy classes or function-local import statements.
``__all__``, ``__dir__``, and type-checking imports preserve discovery and
static analysis of the public API.

For example, these existing imports continue to work::

    from pulsar.client import build_client_manager, ClientJobDescription, ClientOutputs
    from pulsar.client.staging import ClientInputs

The compatibility ``build_client_manager`` supports both ordinary clients
and all coexecution backends. Requesting it loads those backend dependencies;
importing just a staging constant does not.

Callers that want to control their dependencies can use the concrete modules:

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - API
     - Import module
   * - ``OutputNotFoundException``, ``PulsarClientTransportError``
     - ``pulsar.client.exceptions``
   * - ``url_to_destination_params``
     - ``pulsar.client.destination``
   * - ``PathMapper``
     - ``pulsar.client.path_mapper``
   * - ``CLIENT_INPUT_PATH_TYPES``, ``ClientInput``, ``ClientInputs``
     - ``pulsar.client.staging.inputs``
   * - ``ClientJobDescription``, ``ClientOutputs``, ``PulsarOutputs``, ``DynamicFileSourceType``
     - ``pulsar.client.staging.models``
   * - ``submit_job``
     - ``pulsar.client.staging.up``
   * - ``finish_job``
     - ``pulsar.client.staging.down``
   * - ``build_client_manager`` for HTTP, local, CLI, AMQP, and relay execution
     - ``pulsar.client.manager``
   * - ``build_client_manager`` with container coexecution support
     - ``pulsar.client.coexecution_manager``

For example, a standard client uses explicit imports::

    from pulsar.client.manager import build_client_manager
    from pulsar.client.staging.models import ClientJobDescription, ClientOutputs
    from pulsar.client.staging.up import submit_job
    from pulsar.client.staging.down import finish_job

Container coexecution
---------------------

``pulsar.client.client`` contains the ordinary HTTP, local, CLI, AMQP, and relay
clients. Shared container launch behavior is in ``pulsar.client.coexecution``.
The backend clients are in ``pulsar.client.gcp``, ``pulsar.client.kubernetes``,
and ``pulsar.client.tes``. The existing AWS Batch placeholders are in
``pulsar.client.aws_batch``.

The standard manager factory imports no backend SDKs. For Kubernetes, TES, or
Google Cloud Batch destinations, use the coexecution factory instead::

    from pulsar.client.coexecution_manager import build_client_manager

    manager = build_client_manager(tes_enabled=True)
    client = manager.get_client({"tes_url": "https://tes.example"}, "job-123")

This factory also supports standard destinations, so a caller that handles
both kinds can use it for all jobs. Importing it explicitly loads all three
supported coexecution backends. Importing an individual backend module loads
only that backend's SDKs.

Backend configuration APIs also have concrete import paths:
``GcpJobParams`` and the ``gcp_*`` helpers are in
``pulsar.client.gcp_job_config``; ``TesJobParams`` and the ``tes_*`` helpers are
in ``pulsar.client.tes_job_config``. ``pulsar.client.container_job_config``
contains only the shared ``CoexecutionContainerCommand`` description.

Existing pickles referring to staging classes through ``pulsar.client.staging``
resolve through the compatibility exports. New pickles use the concrete
implementation paths, so they require a Pulsar version with those modules.
Pulsar's JSON job messages are unchanged. Direct imports of backend classes
from the former ``pulsar.client.client`` and backend configuration objects
from ``pulsar.client.container_job_config`` must use the concrete modules
listed above.
