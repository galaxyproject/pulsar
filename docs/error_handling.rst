.. _error_handling:

Error Handling and Resilience (Admin Guide)
============================================

This page documents how Pulsar reacts to operational failures —
RabbitMQ/relay outages, Pulsar restarts, Galaxy unreachability, transient
HTTP errors during staging — and what an administrator needs to configure
or monitor to make those guarantees real.

The single guarantee Pulsar provides is: **for every job submitted by
Galaxy, exactly one terminal status update (** ``complete`` **,**
``failed`` **,** ``cancelled`` **, or** ``lost`` **) is delivered, in
non-decreasing lifecycle order, within bounded time after the underlying
fault clears.**

The mechanisms below combine to deliver that guarantee. Each section names
the configuration knobs, defaults, on-disk artifacts, and operational
signals so you can verify the system is doing what it claims.

.. contents::
   :local:
   :depth: 2

------------------------------------------------------------------------
1. The job lifecycle and where status updates come from
------------------------------------------------------------------------

A job moves through these states (see ``pulsar/managers/status.py``):

::

    preprocessing -> queued -> running -> postprocessing -> complete | failed | cancelled | lost

Status transitions are emitted by the *stateful* manager wrapper
(``pulsar/managers/stateful.py``):

* ``preprocessing`` — the moment the setup message is accepted and the
  staging thread begins; the job directory contains ``launch_config`` but
  not yet ``preprocessed``.
* ``running`` — first call to ``get_status()`` that detects the job has
  begun executing on the underlying runner.
* terminal (``complete``/``failed``/``cancelled``/``lost``) — written as
  the on-disk metadata file ``final_status`` after postprocessing.

All transitions go through a single callback registered by the messaging
binding (``pulsar/messaging/bind_amqp.py`` and
``pulsar/messaging/bind_relay.py``), which writes the payload to the
**status-update outbox** and lets a background drain thread retry the
publish. The synchronous publish path is gone.

------------------------------------------------------------------------
2. The persistent status-update outbox
------------------------------------------------------------------------

Why
~~~

Before this layer existed, a Pulsar that hit a broker hiccup *just* as a
job finished would log the publish exception, kill the postprocess
thread, and leave Galaxy permanently unaware that the job was done. This
was the single largest data-loss path in the lifecycle.

How
~~~

Every status update is written to a per-manager directory before any
attempt to publish:

::

    <persistence_directory>/<manager>-status-outbox/        # AMQP modes
    <persistence_directory>/<manager>-relay-status-outbox/  # relay mode

Each entry is a single JSON file named ``<seq>-<uuid>.json``. ``seq`` is a
monotonic per-outbox counter primed from the maximum seq found on disk at
startup, so a lexically sorted directory listing yields strict FIFO drain
order even after a restart.

A daemon thread (named ``status-outbox-<dir-basename>``) drains pending
entries every few seconds:

* on enqueue success the file is removed only **after** ``publish_fn``
  returns;
* on publish failure the file is left on disk, the drain thread retries on
  the next pass, and ``enqueue`` itself never raises;
* on Pulsar startup the drain thread runs once before consumer threads
  start, so any backlog left by the previous process is delivered first.

What this gives you
~~~~~~~~~~~~~~~~~~~

* A broker outage — even one that lasts for minutes or spans a Pulsar
  restart — does not lose a status update. The terminal state sits on
  disk until the broker is reachable again.
* The postprocess thread cannot be terminated by a publish failure.
* If the broker eventually has to be replaced or wiped, you can simply
  delete the affected outbox directories *after* you accept that those
  updates are lost — no other Pulsar state needs touching.

Configuration
~~~~~~~~~~~~~

* ``persistence_directory`` (yaml, default ``files/persisted_data``) —
  where the outbox lives. **Required** for at-least-once semantics. If
  set to ``__none__`` the outbox is disabled and the legacy synchronous
  publish path is used; do not run production this way.
* ``status_outbox_drain_interval`` (yaml, default ``5.0`` seconds) — how
  often the daemon thread retries pending entries when no immediate
  wakeup has fired.

Monitoring
~~~~~~~~~~

* The directory size of ``<persistence_directory>/*-status-outbox*/`` is
  the natural backpressure signal. Steady state should be 0 entries.
  Sustained growth means the broker (or Galaxy's consumer) is
  unreachable, not that Pulsar is broken.
* The log line ``Outbox <dir> has N pending messages to retry`` fires on
  startup whenever the previous run left a backlog — alert on it if N
  is non-zero for more than a few drain intervals.

------------------------------------------------------------------------
3. AMQP durability defenses
------------------------------------------------------------------------

When Pulsar talks to RabbitMQ:

* ``amqp_durable: true`` (off by default) declares the ``pulsar``
  exchange and every per-name queue with ``durable=true``, and stamps
  publishes with ``delivery_mode=2`` (persistent). With this enabled,
  setup, kill, and status-update messages survive a RabbitMQ restart.
  The default is ``false`` so existing deployments with non-durable
  queues keep working — RabbitMQ refuses to redeclare an existing queue
  with mismatched durability, so flipping this on a live deployment
  requires deleting the affected queues first or migrating to a fresh
  broker. The outbox already covers the publisher-side leak (LP1)
  regardless of this setting; durable queues are an extra defense for
  the *broker-restart* case specifically.
* ``amqp_publish_retry: true`` enables kombu's connection-retry policy.
  When set, pulsar fills in bounded defaults (``max_retries: 5``,
  ``interval_start: 1``, ``interval_step: 2``, ``interval_max: 30``) so a
  single transient hiccup is absorbed in-band without round-tripping
  through the outbox drain loop.
* ``amqp_acknowledge: true`` (off by default) layers an additional
  publisher-confirms protocol on top, with its own UUID store under
  ``<persistence_directory>/amqp_ack-<manager>/``. This is independent of
  the outbox; both can be enabled together for defense-in-depth.

.. note::

   To enable durable queues on an existing deployment, drain or delete
   the existing ``pulsar__*`` queues (e.g. ``rabbitmqctl delete_queue
   pulsar__setup`` for each one) before flipping
   ``amqp_durable: true``. On a fresh install you can simply set the
   flag from the start.

------------------------------------------------------------------------
4. pulsar-relay durability defenses
------------------------------------------------------------------------

Relay uses HTTP long-polling with a per-topic *cursor* (``last_message_id``)
that the consumer advances as it reads messages. Without persistence the
cursor would reset on every restart, silently skipping any setup or
status_update messages published while the consumer was down.

Pulsar persists the cursor at:

::

    <persistence_directory>/<manager>-relay-cursor.json

written atomically (rename-temp) on every advance, loaded on startup. The
Galaxy-side ``RelayClientManager`` accepts a ``relay_cursor_path`` keyword
to do the same on the receiver side.

Galaxy job handlers run as separate processes — each one polls the relay
independently and tracks its own cursor — so ``RelayClientManager``
expands the operator-supplied path with a **stable, per-handler
identifier** before passing it to the transport. The suffix is resolved
in this order:

1. ``relay_handler_id`` constructor kwarg (typically
   ``app.config.server_name`` from the Galaxy runner — stable across
   restarts).
2. ``GALAXY_SERVER_NAME`` environment variable (Galaxy's standard
   handler tag, set by the launcher).
3. ``pidNNN`` as a last resort, with a startup ``WARNING`` log: PID is
   unique per process but changes on every restart, so the persisted
   cursor would not be picked up by the next run and the F4 guarantee
   is degraded to "no Galaxy-side cursor persistence."

A shared file would suffer last-writer-wins corruption when two handlers
persist concurrently and could silently rewind another handler's
progress, which is why the suffix is mandatory whenever
``relay_cursor_path`` is set.

The startup capability snapshot is intentionally *advisory* and is excluded
from these durability defenses — it carries no outbox or cursor; a missed
or failed publish simply means Galaxy uses operator-supplied destination
parameters until the next Pulsar restart re-publishes.

------------------------------------------------------------------------
5. Setup-message idempotency
------------------------------------------------------------------------

Setup messages can be redelivered: if Pulsar SIGKILLs after consuming a
setup but before AMQP records the ack, the broker will redeliver to the
next consumer. ``submit_job`` short-circuits the redelivery to a no-op
**only when the prior run can finish on its own**:

* the job has reached a terminal status (``final_status`` metadata
  exists), or
* the job is still tracked by ``active_jobs`` and ``recover_active_jobs``
  will resume it on next get_status().

If the prior run crashed *between* persisting ``launch_config`` and
activating the job — a narrow window — there is no recovery hook, so the
redelivered setup drives a fresh ``preprocess_and_launch`` instead of
silently dropping the work.

This is invisible to admins under normal operation; it surfaces in logs
as ``Ignoring duplicate setup message for job_id <id>``.

------------------------------------------------------------------------
6. Active-job recovery on restart
------------------------------------------------------------------------

Pulsar's stateful manager keeps two persistent indices under
``persistence_directory``:

::

    <persistence_directory>/<manager>-active-jobs/
    <persistence_directory>/<manager>-preprocessing-jobs/

Each file is a job_id; its existence means the job was active when the
process last ran. On startup ``recover_active_jobs`` walks both
directories and:

1. for jobs in ``-preprocessing-jobs/``, re-reads ``launch_config`` and
   re-launches the preprocessing thread;
2. for jobs in ``-active-jobs/``, calls the manager's
   ``_recover_active_job`` method (e.g. requeue from the persisted
   command line, or re-attach to the DRMAA external id).

Two outcomes you should be aware of:

* If recovery cannot reattach to the job (e.g. the DRMAA external id is
  no longer known) Pulsar publishes a single ``lost`` status update and
  removes the active-jobs entry. From Galaxy's perspective the job ended
  with ``lost``; nothing is silently abandoned.
* The ``queued_python`` runner — the one used in the resilience test
  framework — runs jobs as direct Pulsar subprocesses and cannot survive
  a Pulsar SIGKILL. Such a restart yields ``lost``, not ``complete``,
  for the in-flight job. **Use a real DRM (DRMAA/Slurm/Kubernetes) for
  workloads that need to survive Pulsar restarts.**

------------------------------------------------------------------------
7. Staging error handling (file transfer to/from Galaxy)
------------------------------------------------------------------------

Pulsar pulls inputs from Galaxy and pushes outputs back over HTTP. Both
sides go through the ``RetryActionExecutor`` with a
``should_retry=is_transient_http_error`` predicate
(``pulsar/client/transport/transient.py``):

* **Transient errors are retried** — 408, 425, 429, 500, 502, 503, 504,
  connection errors, and timeouts. Default policy retries indefinitely
  with bounded backoff (start 2 s, step 2 s, max 30 s).
* **Permanent errors fail the job** — any 4xx other than the rate-limit
  set above (404, 403, 400, etc.) immediately marks the job ``failed``
  with the upstream HTTP body in the captured stderr.

This is why a misconfigured Galaxy URL or a deleted dataset surfaces as a
single fast ``failed``, while a Galaxy restart or a load-balancer hiccup
recovers transparently after retries.

Configuration knobs (per-manager YAML):

* ``preprocess_action_max_retries`` / ``postprocess_action_max_retries``
* ``preprocess_action_interval_start`` / ``_step`` / ``_max``
* ``preprocess_action_should_retry`` (advanced — replaces the default
  predicate; only do this if you understand which errors are safe to
  retry in your environment)

------------------------------------------------------------------------
8. Status-update ordering guarantees
------------------------------------------------------------------------

Pulsar (sender side)
~~~~~~~~~~~~~~~~~~~~

Within one Pulsar instance, status updates for a given job are emitted in
strict lifecycle order, and the outbox drains them in strict FIFO via the
monotonic seq prefix described above. That ordering is preserved across
process restarts: pending entries from the previous run drain before any
new entries from the new run, because their seqs are smaller.

Galaxy (receiver side)
~~~~~~~~~~~~~~~~~~~~~~

The broker can re-deliver a message whose ack was lost, and the relay
backend can replay messages a client claims it has not yet seen. Galaxy
must therefore enforce two invariants:

1. **Dedupe by** ``(job_id, status)``. The pulsar status-update payload
   for a given (job_id, status) is idempotent in content, so a duplicate
   is safe to drop.
2. **A terminal status is a sink.** Once Galaxy has recorded a terminal
   status for a job, drop any further updates for that job — both
   non-terminal regressions (a stale ``running`` arriving late) and
   conflicting later terminals (a delayed ``failed`` after ``complete``).

The reference implementation of these rules is the
``StatusRecorder`` class in
``test/resilience/mock_galaxy/recorder.py``; treat it as the canonical
behavior to mirror in production Galaxy.

Explicit Galaxy-side resets
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Operators (or Galaxy itself) sometimes need to reset a job's state — for
example resubmitting after a ``cancel`` or restarting a ``failed`` job.
Such a transition deliberately re-enters a non-terminal state from a
terminal one and would be rejected by the regression guard above.

The agreed escape hatch is a ``_galaxy_reset_token`` field in the status
payload (any truthy value, intended to be unique per reset event):

* the receiver treats the update as the start of a fresh epoch for that
  ``job_id``;
* prior transitions are forgotten for the *current-state* view of the
  job;
* the audit log retains the full observed history.

Pulsar itself does not emit reset tokens. Galaxy is the authority on what
constitutes a reset.

------------------------------------------------------------------------
9. Failure-mode → outcome cheat sheet
------------------------------------------------------------------------

=================================================  ====================================  ===========================================================================
Failure                                            Recovery mechanism                    What you see in logs / on disk
=================================================  ====================================  ===========================================================================
Broker brief disconnect                            kombu/relay reconnect loop            ``recoverable_exceptions`` log; queue drains on reconnect
Broker down for minutes                            outbox holds terminal status          outbox dir size > 0 until reconnect; warns on next drain
RabbitMQ crash + restart (``amqp_durable: true``)  durable queues + delivery_mode=2      no Pulsar-side log; messages restored from broker disk
RabbitMQ crash + restart (default, non-durable)    outbox replays publisher side         in-flight inbound msgs are lost broker-side; outbound resume from outbox
Pulsar SIGKILL during preprocessing                ``-preprocessing-jobs/`` recovery     ``Failed to find launch parameters`` warning if missing
Pulsar SIGKILL during running (DRM)                ``-active-jobs/`` recovery            re-attach via runner; no status change visible to Galaxy
Pulsar SIGKILL during running (queued_python)      job dies, ``lost`` reported           one ``lost`` status update; admin should know this runner
Pulsar SIGKILL after final_status, before publish  outbox replay on restart              ``Outbox ... has N pending messages to retry`` warning
Galaxy 5xx during input download                   transient retry                       ``Failed to execute action[...], retrying`` info logs
Galaxy 4xx during input download                   fail-fast, ``failed`` reported        single ``failed`` status; HTTP body in job stderr
Galaxy unreachable during status_update            outbox holds, broker buffers          same as broker outage from Pulsar's perspective
Both Pulsar and broker restart together            outbox (+ durable queues if enabled)  everything resumes once both are up; ordering preserved
=================================================  ====================================  ===========================================================================

------------------------------------------------------------------------
10. Verifying resilience in your environment
------------------------------------------------------------------------

The repo includes a docker-compose-based resilience suite under
``test/resilience/`` that exercises every failure mode above end-to-end
against a real RabbitMQ, ``ghcr.io/mvdbeek/pulsar-relay``, and toxiproxy
fault injection. Before relying on this guide in production, run::

    docker compose -f test/resilience/docker-compose.yml up -d --build
    pytest test/resilience -v

48 scenarios pass across the ``amqp``, ``amqp_ack``, and ``relay`` modes.
See ``test/resilience/README.md`` for layout, what each scenario asserts,
and how to add new ones (e.g. for a custom runner).

------------------------------------------------------------------------
11. Tunables, defaults, and where they live
------------------------------------------------------------------------

================================  =======================================  ====================================================================
Setting                           Default                                  Effect
================================  =======================================  ====================================================================
``persistence_directory``         ``files/persisted_data``                 outbox + active-jobs + relay cursor live here
``status_outbox_drain_interval``  ``5.0`` (seconds)                        background outbox retry cadence
``amqp_durable``                  ``false``                                opt-in: durable queues + delivery_mode=2 (broker-restart resilience)
``amqp_publish_retry``            unset (off)                              kombu publish retry; defaults bounded when on
``amqp_acknowledge``              ``false``                                additional publisher-confirms layer
``amqp_consumer_timeout``         ``0.2``                                  consumer drain_events timeout (responsiveness)
``message_queue_publish``         ``true``                                 disable to make Pulsar receive-only
``message_queue_consume``         ``true``                                 disable to make Pulsar send-only
``ensure_cleanup``                ``false``                                join consumer threads on shutdown
================================  =======================================  ====================================================================

For deep debugging set ``logging.loggers.pulsar.level: DEBUG`` in
``server.ini`` (the resilience tests run with INFO and grep for the bind
and outbox log lines as readiness signals — the same pattern works for
production health checks).
