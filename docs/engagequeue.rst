EngageQueue local execution
===========================

EngageQueue is an independent single-host executor, available through Pulsar's
existing ``queued_cli`` manager. Pulsar prepares scripts, dependencies, staging,
and outputs; the executor owns queue admission and execution lifetime. No
EngageQueue Python imports or new detached manager are required in Pulsar.

EngageQueue 0.1.1 supports Linux and macOS with Python 3.10 or newer. It is
optional: Pulsar does not import the executor or require it for other managers,
including on older
Python versions or Windows. Install the published package into its own execution
environment, or alongside Pulsar, using that environment's Python::

    /path/to/environment/bin/python -m pip install 'engagequeue==0.1.1'

Configure the absolute CLI path and create a persistent pool before using it::

    engagequeue --state-dir /ssd/engagequeue init --pool batch --max-jobs 50

An ``app.yml`` manager can then use it:

.. code-block:: yaml

    managers:
      local:
        type: queued_cli
        job_plugin: EngageQueue
        job_executable: /path/to/environment/bin/engagequeue
        job_state_dir: /ssd/engagequeue
        job_pool: batch

The adapter explicitly selects local execution. Use an ordinary local state
directory; managed Docker runtime profiles are unsupported here and must use a
separate directory. This prevents automatic profile detection from silently
changing the execution host or the meaning of staged paths.

On Linux, native supervision includes daemonized descendants. On macOS, keep
prepared jobs in the foreground and keep descendants in the original job
process group. Daemonizing, double-forking and escaping that group are outside
the macOS native contract. The systemd backend is Linux-only. Native macOS CI
tests prepared foreground jobs, queue admission, recovery, controller SIGKILL,
cancellation and collection acknowledgment; it does not validate managed Docker
or full Galaxy interactive-tool integration.

EngageQueue chooses UUID Pulsar setup directories by default. Repeated submit
operations for the same prepared script share a stable submission key. A
controller interrupted after acceptance recovers the external ID by lookup;
it does not resubmit the command. Uncertain transport outcomes remain visible
for recovery. A lookup miss cannot prove the original submit process has exited:
it may survive its controller and accept work later. Such attempts stay queued
and are looked up again, without replay. Status transport failures for known
executions stay running. Both remain nonterminal for existing Pulsar clients.
Inspect Pulsar and executor diagnostics before resolving a persistently
uncertain attempt; stopping and verifying the original launcher is part of any
operator decision to abandon it.

Pulsar shutdown leaves the executor and accepted work running. Deploy the
executor runtime outside the Pulsar service or container shutdown boundary when
those facilities terminate all contained processes. ``job_attach_only: true``
attaches to an explicitly managed runtime. Shared state and execution paths must
remain available to that runtime at their configured locations.

Cancellation and resources
--------------------------

Cancellation normally requests termination asynchronously. Pulsar continues
polling the actual executor state, including owned processes and containers,
before reporting cancellation complete. Pending cancellation is retried after
ID recovery or failed delivery. ``job_cancel_wait: true`` additionally
waits in the delete command; ``job_cancel_timeout`` bounds that wait.

Per-job submit parameters ``cpus``, ``memory_mb``, ``timeout``, and
``output_limit`` override their configured ``job_`` defaults. They cannot change
the executable, state directory, or plugin. Native memory observation differs
from kernel resource enforcement. On Linux, use a systemd-backed pool and
``job_require_hard_limits: true`` when hard CPU/memory controls are required;
unsupported requests fail explicitly.

Owned containers
----------------

Prepared Docker commands must supply explicit ownership descriptors when a
container can outlive its CLI. Set ``job_container_spec`` to a JSON file, such as
``metadata/engagequeue-containers.json`` relative to the Pulsar job directory.
The file accepts one descriptor or a list for tool and metadata containers:

.. code-block:: json

    [{"name": "unique-container-name", "label_value": "unique-attempt"}]

The Docker command must use the same name and
``--label engagequeue.attempt=unique-attempt``. Descriptors may also select the
Docker executable, daemon endpoint, and CID file. The executor verifies labels
and immutable container IDs before stopping them. Caller workspaces remain
Pulsar's responsibility. Apptainer commands run through ordinary process
supervision.

Collection acknowledgment is a separate, optional client protocol described in
:doc:`collection_ack`. The executor does not decide whether Galaxy imported
datasets, metadata, or interactive entry points.

The basic scheduler adapter works with prepared Pulsar scripts and does not
require Galaxy runner changes or collection acknowledgment. Advanced clients
may opt into acknowledgment or supply the container ownership sidecar when
their collection and container lifecycle require those capabilities.
