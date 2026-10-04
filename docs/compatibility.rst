.. This file is generated from compatibility.yml by gen_compatibility_doc.py;
   edit the YAML and run ``make compatibility-docs``.

.. _compatibility:

------------------------------
Galaxy Compatibility
------------------------------

Each Galaxy release pins a ``pulsar-galaxy-lib`` version, the client half of
Pulsar. The tables below record, per Pulsar modality, which Pulsar servers
each Galaxy release is expected to work with. This is a best-effort record,
not a support guarantee.

Statuses:

``expected``
    Believed compatible from reading the code; not exercised by CI.
``tested``
    A CI job exercised this pairing.
``broken``
    A known break; see the linked issue.
``n/a``
    The modality does not exist for this Galaxy release.

Server ranges are `PEP 440 <https://peps.python.org/pep-0440/>`__ version
specifiers on the Pulsar server version. Servers older than 0.15.6 were not
surveyed. Issues listed against a range describe behavior changes or
configuration pitfalls for that pairing, many only relevant when an optional
feature is enabled.

The data lives in ``docs/compatibility.yml``.

Galaxy Releases
---------------

.. list-table::
   :header-rows: 1

   * - Galaxy
     - pulsar-galaxy-lib
   * - 24.0
     - ``0.15.6``
   * - 24.1
     - ``0.15.6``
   * - 24.2
     - ``0.15.7``
   * - 25.0
     - ``0.15.9``
   * - 25.1
     - ``0.15.14``
   * - 26.0
     - ``0.15.14``
   * - 26.1
     - ``0.15.15``
   * - 26.2
     - ``0.16`` (planned)

REST
----

Galaxy ``PulsarRESTJobRunner`` -> Pulsar web server over HTTP.

Contract: ``pulsar/web/routes.py`` routes and params; setup response; status fields; file-action types.

.. list-table::
   :header-rows: 1

   * - Galaxy
     - pulsar-galaxy-lib
     - Pulsar server
     - Status
     - Issues
   * - 24.0
     - ``0.15.6``
     - ``>=0.15.6``
     - ``expected``
     - * :ref:`live-stdout-needs-galaxy-24.2 <compat-issue-live-stdout-needs-galaxy-24.2>`
       * :ref:`jobs-directory-token-removed <compat-issue-jobs-directory-token-removed>`
       * :ref:`tus-now-real <compat-issue-tus-now-real>`
       * :ref:`resubmit-same-id-ignored <compat-issue-resubmit-same-id-ignored>`
       * :ref:`status-stdout-capped <compat-issue-status-stdout-capped>`
   * - 24.1
     - ``0.15.6``
     - ``>=0.15.6``
     - ``expected``
     - * :ref:`live-stdout-needs-galaxy-24.2 <compat-issue-live-stdout-needs-galaxy-24.2>`
       * :ref:`jobs-directory-token-removed <compat-issue-jobs-directory-token-removed>`
       * :ref:`tus-now-real <compat-issue-tus-now-real>`
       * :ref:`resubmit-same-id-ignored <compat-issue-resubmit-same-id-ignored>`
       * :ref:`status-stdout-capped <compat-issue-status-stdout-capped>`
   * - 24.2
     - ``0.15.7``
     - ``>=0.15.6``
     - ``expected``
     - * :ref:`jobs-directory-token-removed <compat-issue-jobs-directory-token-removed>`
       * :ref:`tus-now-real <compat-issue-tus-now-real>`
       * :ref:`resubmit-same-id-ignored <compat-issue-resubmit-same-id-ignored>`
       * :ref:`status-stdout-capped <compat-issue-status-stdout-capped>`
   * - 25.0
     - ``0.15.9``
     - ``>=0.15.6``
     - ``expected``
     - * :ref:`jobs-directory-token-removed <compat-issue-jobs-directory-token-removed>`
       * :ref:`tus-now-real <compat-issue-tus-now-real>`
       * :ref:`resubmit-same-id-ignored <compat-issue-resubmit-same-id-ignored>`
       * :ref:`status-stdout-capped <compat-issue-status-stdout-capped>`
   * - 25.1
     - ``0.15.14``
     - ``>=0.15.6``
     - ``expected``
     - * :ref:`jobs-directory-token-removed <compat-issue-jobs-directory-token-removed>`
       * :ref:`tus-now-real <compat-issue-tus-now-real>`
       * :ref:`resubmit-same-id-ignored <compat-issue-resubmit-same-id-ignored>`
       * :ref:`status-stdout-capped <compat-issue-status-stdout-capped>`
   * - 26.0
     - ``0.15.14``
     - ``>=0.15.13``
     - ``expected``
     - * :ref:`jobs-directory-token-removed <compat-issue-jobs-directory-token-removed>`
       * :ref:`tus-now-real <compat-issue-tus-now-real>`
       * :ref:`resubmit-same-id-ignored <compat-issue-resubmit-same-id-ignored>`
       * :ref:`status-stdout-capped <compat-issue-status-stdout-capped>`
   * - 
     - 
     - ``>=0.15.6,<0.15.13``
     - ``expected``
     - * :ref:`collector-descriptions-version-gate <compat-issue-collector-descriptions-version-gate>`
   * - 26.1
     - ``0.15.15``
     - ``>=0.15.13``
     - ``expected``
     - * :ref:`jobs-directory-token-removed <compat-issue-jobs-directory-token-removed>`
       * :ref:`tus-now-real <compat-issue-tus-now-real>`
       * :ref:`resubmit-same-id-ignored <compat-issue-resubmit-same-id-ignored>`
       * :ref:`status-stdout-capped <compat-issue-status-stdout-capped>`
   * - 
     - 
     - ``>=0.15.6,<0.15.13``
     - ``expected``
     - * :ref:`collector-descriptions-version-gate <compat-issue-collector-descriptions-version-gate>`
   * - 26.2
     - ``0.16``
     - ``>=0.16.0.dev0``
     - ``expected``
     - * :ref:`jobs-directory-token-removed <compat-issue-jobs-directory-token-removed>`
       * :ref:`tus-now-real <compat-issue-tus-now-real>`
       * :ref:`resubmit-same-id-ignored <compat-issue-resubmit-same-id-ignored>`
       * :ref:`status-stdout-capped <compat-issue-status-stdout-capped>`
   * - 
     - 
     - ``>=0.15.13,<0.16.0.dev0``
     - ``expected``
     - * :ref:`master-features-unavailable <compat-issue-master-features-unavailable>`
   * - 
     - 
     - ``>=0.15.6,<0.15.13``
     - ``expected``
     - * :ref:`collector-descriptions-version-gate <compat-issue-collector-descriptions-version-gate>`
       * :ref:`master-features-unavailable <compat-issue-master-features-unavailable>`


Message Queue (AMQP)
--------------------

Galaxy ``PulsarMQJobRunner`` -> Pulsar over AMQP (kombu); setup built Galaxy-side (``jobs_directory`` required).

Contract: exchange ``pulsar``; queues ``<prefix>_{setup,kill,status,status_update}[_ack]``; setup/status payload dicts.

.. list-table::
   :header-rows: 1

   * - Galaxy
     - pulsar-galaxy-lib
     - Pulsar server
     - Status
     - Issues
   * - 24.0
     - ``0.15.6``
     - ``>=0.15.6``
     - ``expected``
     - * :ref:`live-stdout-needs-galaxy-24.2 <compat-issue-live-stdout-needs-galaxy-24.2>`
       * :ref:`jobs-directory-token-removed <compat-issue-jobs-directory-token-removed>`
       * :ref:`amqp-durable-mismatch <compat-issue-amqp-durable-mismatch>`
       * :ref:`outbox-duplicate-final-status <compat-issue-outbox-duplicate-final-status>`
       * :ref:`status-stdout-capped <compat-issue-status-stdout-capped>`
   * - 24.1
     - ``0.15.6``
     - ``>=0.15.6``
     - ``expected``
     - * :ref:`live-stdout-needs-galaxy-24.2 <compat-issue-live-stdout-needs-galaxy-24.2>`
       * :ref:`jobs-directory-token-removed <compat-issue-jobs-directory-token-removed>`
       * :ref:`amqp-durable-mismatch <compat-issue-amqp-durable-mismatch>`
       * :ref:`outbox-duplicate-final-status <compat-issue-outbox-duplicate-final-status>`
       * :ref:`status-stdout-capped <compat-issue-status-stdout-capped>`
   * - 24.2
     - ``0.15.7``
     - ``>=0.15.6``
     - ``expected``
     - * :ref:`jobs-directory-token-removed <compat-issue-jobs-directory-token-removed>`
       * :ref:`amqp-durable-mismatch <compat-issue-amqp-durable-mismatch>`
       * :ref:`outbox-duplicate-final-status <compat-issue-outbox-duplicate-final-status>`
       * :ref:`status-stdout-capped <compat-issue-status-stdout-capped>`
   * - 25.0
     - ``0.15.9``
     - ``>=0.15.6``
     - ``expected``
     - * :ref:`jobs-directory-token-removed <compat-issue-jobs-directory-token-removed>`
       * :ref:`amqp-durable-mismatch <compat-issue-amqp-durable-mismatch>`
       * :ref:`outbox-duplicate-final-status <compat-issue-outbox-duplicate-final-status>`
       * :ref:`status-stdout-capped <compat-issue-status-stdout-capped>`
   * - 25.1
     - ``0.15.14``
     - ``>=0.15.6``
     - ``expected``
     - * :ref:`jobs-directory-token-removed <compat-issue-jobs-directory-token-removed>`
       * :ref:`amqp-durable-mismatch <compat-issue-amqp-durable-mismatch>`
       * :ref:`outbox-duplicate-final-status <compat-issue-outbox-duplicate-final-status>`
       * :ref:`status-stdout-capped <compat-issue-status-stdout-capped>`
   * - 26.0
     - ``0.15.14``
     - ``>=0.15.13``
     - ``expected``
     - * :ref:`jobs-directory-token-removed <compat-issue-jobs-directory-token-removed>`
       * :ref:`amqp-durable-mismatch <compat-issue-amqp-durable-mismatch>`
       * :ref:`outbox-duplicate-final-status <compat-issue-outbox-duplicate-final-status>`
       * :ref:`status-stdout-capped <compat-issue-status-stdout-capped>`
   * - 
     - 
     - ``>=0.15.6,<0.15.13``
     - ``expected``
     - * :ref:`collector-descriptions-version-gate <compat-issue-collector-descriptions-version-gate>`
   * - 26.1
     - ``0.15.15``
     - ``>=0.15.13``
     - ``expected``
     - * :ref:`jobs-directory-token-removed <compat-issue-jobs-directory-token-removed>`
       * :ref:`amqp-durable-mismatch <compat-issue-amqp-durable-mismatch>`
       * :ref:`outbox-duplicate-final-status <compat-issue-outbox-duplicate-final-status>`
       * :ref:`status-stdout-capped <compat-issue-status-stdout-capped>`
   * - 
     - 
     - ``>=0.15.6,<0.15.13``
     - ``expected``
     - * :ref:`collector-descriptions-version-gate <compat-issue-collector-descriptions-version-gate>`
   * - 26.2
     - ``0.16``
     - ``>=0.16.0.dev0``
     - ``expected``
     - * :ref:`jobs-directory-token-removed <compat-issue-jobs-directory-token-removed>`
       * :ref:`amqp-durable-mismatch <compat-issue-amqp-durable-mismatch>`
       * :ref:`outbox-duplicate-final-status <compat-issue-outbox-duplicate-final-status>`
       * :ref:`status-stdout-capped <compat-issue-status-stdout-capped>`
   * - 
     - 
     - ``>=0.15.13,<0.16.0.dev0``
     - ``expected``
     - * :ref:`master-features-unavailable <compat-issue-master-features-unavailable>`
   * - 
     - 
     - ``>=0.15.6,<0.15.13``
     - ``expected``
     - * :ref:`collector-descriptions-version-gate <compat-issue-collector-descriptions-version-gate>`
       * :ref:`master-features-unavailable <compat-issue-master-features-unavailable>`


Relay
-----

Galaxy and Pulsar exchange MQ-shaped messages through the ``pulsar-relay`` HTTP service.

Contract: topics ``[prefix_]job_{setup,status_request,kill,status_update}[_manager]``; same payloads as mq.

Other axes:

- ``pulsar_relay_server``: unverified; device flow, refresh tokens, topic ownership need newer relay servers.
- ``pulsar_relay_client``: >=0.2.1 (lib 0.15.15+); Galaxy dev pins 0.2.2; unpinned in 26.1.

.. list-table::
   :header-rows: 1

   * - Galaxy
     - pulsar-galaxy-lib
     - Pulsar server
     - Status
     - Issues
   * - 24.0
     - ``0.15.6``
     - 
     - ``n/a``
     -
   * - 24.1
     - ``0.15.6``
     - 
     - ``n/a``
     -
   * - 24.2
     - ``0.15.7``
     - 
     - ``n/a``
     -
   * - 25.0
     - ``0.15.9``
     - 
     - ``n/a``
     -
   * - 25.1
     - ``0.15.14``
     - 
     - ``n/a``
     - * lib 0.15.14 has relay but the 25.1 runner rejects ``relay_url``
   * - 26.0
     - ``0.15.14``
     - ``>=0.15.13``
     - ``expected``
     - * :ref:`relay-default-username-dropped <compat-issue-relay-default-username-dropped>`
       * :ref:`outbox-duplicate-final-status <compat-issue-outbox-duplicate-final-status>`
   * - 
     - 
     - ``==0.15.12``
     - ``expected``
     - * :ref:`relay-topic-prefix-needs-0.15.13 <compat-issue-relay-topic-prefix-needs-0.15.13>`
       * :ref:`collector-descriptions-version-gate <compat-issue-collector-descriptions-version-gate>`
   * - 26.1
     - ``0.15.15``
     - ``>=0.15.13``
     - ``expected``
     - * :ref:`relay-default-username-dropped <compat-issue-relay-default-username-dropped>`
       * :ref:`outbox-duplicate-final-status <compat-issue-outbox-duplicate-final-status>`
   * - 
     - 
     - ``==0.15.12``
     - ``expected``
     - * :ref:`relay-topic-prefix-needs-0.15.13 <compat-issue-relay-topic-prefix-needs-0.15.13>`
       * :ref:`collector-descriptions-version-gate <compat-issue-collector-descriptions-version-gate>`
   * - 26.2
     - ``0.16``
     - ``>=0.15.13``
     - ``expected``
     - * :ref:`relay-default-username-dropped <compat-issue-relay-default-username-dropped>`
       * :ref:`outbox-duplicate-final-status <compat-issue-outbox-duplicate-final-status>`
       * :ref:`master-features-unavailable <compat-issue-master-features-unavailable>`
   * - 
     - 
     - ``==0.15.12``
     - ``expected``
     - * :ref:`relay-topic-prefix-needs-0.15.13 <compat-issue-relay-topic-prefix-needs-0.15.13>`
       * :ref:`collector-descriptions-version-gate <compat-issue-collector-descriptions-version-gate>`


Coexecution
-----------

Galaxy K8s/TES/GCP runners launch a pod/task with a Pulsar sidecar; no long-running server. The peer is the sidecar image, hardcoded in Galaxy as ``DEFAULT_PULSAR_CONTAINER`` (overridable per destination with ``pulsar_container_image``).

Contract: ``pulsar-submit [--wait|--no-wait] --base64 <setup> --app_conf_base64 <conf>``; tool container waits on a ``command_line`` file.

Default Pulsar image: ``galaxy/pulsar-pod-staging:0.15.0.2`` (Pulsar 0.15.0.dev0 (49bc5bc, 2023-02)).

Backends:

- ``k8s``: all releases
- ``tes``: all releases
- ``gcp_batch``: Galaxy 25.1+ (lib 0.15.10+)
- ``aws_batch``: lib client only; no Galaxy runner

.. list-table::
   :header-rows: 1

   * - Galaxy
     - pulsar-galaxy-lib
     - Pulsar image
     - Status
     - Issues
   * - 24.0
     - ``0.15.6``
     - ``default``
     - ``expected``
     - * :ref:`coexec-token-endpoint-ignored <compat-issue-coexec-token-endpoint-ignored>`
       * :ref:`coexec-stdio-not-separated <compat-issue-coexec-stdio-not-separated>`
   * - 24.1
     - ``0.15.6``
     - ``default``
     - ``expected``
     - * :ref:`coexec-token-endpoint-ignored <compat-issue-coexec-token-endpoint-ignored>`
       * :ref:`coexec-stdio-not-separated <compat-issue-coexec-stdio-not-separated>`
   * - 24.2
     - ``0.15.7``
     - ``default``
     - ``expected``
     - * :ref:`coexec-token-endpoint-ignored <compat-issue-coexec-token-endpoint-ignored>`
       * :ref:`coexec-stdio-not-separated <compat-issue-coexec-stdio-not-separated>`
   * - 25.0
     - ``0.15.9``
     - ``default``
     - ``expected``
     - * :ref:`coexec-token-endpoint-ignored <compat-issue-coexec-token-endpoint-ignored>`
       * :ref:`coexec-stdio-not-separated <compat-issue-coexec-stdio-not-separated>`
   * - 25.1
     - ``0.15.14``
     - ``default``
     - ``expected``
     - * :ref:`coexec-token-endpoint-ignored <compat-issue-coexec-token-endpoint-ignored>`
       * :ref:`coexec-stdio-not-separated <compat-issue-coexec-stdio-not-separated>`
       * :ref:`gcp-runnable-ordering <compat-issue-gcp-runnable-ordering>`
   * - 26.0
     - ``0.15.14``
     - ``default``
     - ``expected``
     - * :ref:`collector-descriptions-version-gate <compat-issue-collector-descriptions-version-gate>`
       * :ref:`coexec-token-endpoint-ignored <compat-issue-coexec-token-endpoint-ignored>`
       * :ref:`coexec-stdio-not-separated <compat-issue-coexec-stdio-not-separated>`
       * :ref:`gcp-runnable-ordering <compat-issue-gcp-runnable-ordering>`
   * - 26.1
     - ``0.15.15``
     - ``default``
     - ``expected``
     - * :ref:`collector-descriptions-version-gate <compat-issue-collector-descriptions-version-gate>`
       * :ref:`coexec-token-endpoint-ignored <compat-issue-coexec-token-endpoint-ignored>`
       * :ref:`coexec-stdio-not-separated <compat-issue-coexec-stdio-not-separated>`
   * - 26.2
     - ``0.16``
     - ``default``
     - ``expected``
     - * :ref:`collector-descriptions-version-gate <compat-issue-collector-descriptions-version-gate>`
       * :ref:`coexec-token-endpoint-ignored <compat-issue-coexec-token-endpoint-ignored>`
       * :ref:`coexec-stdio-not-separated <compat-issue-coexec-stdio-not-separated>`


Embedded
--------

Pulsar runs inside Galaxy's process; always the same version. No matrix.


Known Issues
------------

.. _compat-issue-collector-descriptions-version-gate:

``collector-descriptions-version-gate`` (break)
   Galaxy 26.0+ (3a3d872460c) sends ``dataset_collector_descriptions`` in place of raw ``discover_datasets`` patterns once ``pulsar_version`` >= 0.15.13.dev0. With setup built Galaxy-side (``jobs_directory`` set: all MQ, relay, coexecution; REST only if configured), ``pulsar_version`` is Galaxy's own lib version, not the server's. Servers < 0.15.13 (2e28241) ignore the new key: custom ``discover_datasets`` outputs are never staged back and the job still finishes green.

.. _compat-issue-live-stdout-needs-galaxy-24.2:

``live-stdout-needs-galaxy-24.2`` (conditional)
   Opt-in ``send_stdout_update`` (server, master 7b4e451). Galaxy 24.0/24.1 lack d336cadddba, so stdout is overwritten per chunk / dropped.

.. _compat-issue-jobs-directory-token-removed:

``jobs-directory-token-removed`` (conditional)
   Master servers (aefd720) reject jobs using ``__PULSAR_JOBS_DIRECTORY__``. The 0.15.15 sample ``job_conf_sample_mq_rsync.yml`` still uses it.

.. _compat-issue-tus-now-real:

``tus-now-real`` (conditional)
   ``remote_transfer_tus`` really uses TUS on master (1f7eb9a); servers without ``tuspy`` now fail stage-out instead of silently using POST.

.. _compat-issue-resubmit-same-id-ignored:

``resubmit-same-id-ignored`` (conditional)
   0.15.15+ servers (37e0ad5) ignore a setup reusing a job id whose directory still exists; Galaxy sees the old final status. Written for MQ redelivery, REST shares the path. Needs a test.

.. _compat-issue-status-stdout-capped:

``status-stdout-capped`` (degraded)
   Master servers cap stdout/stderr in status responses at 64 KiB (6eb8dae).

.. _compat-issue-amqp-durable-mismatch:

``amqp-durable-mismatch`` (conditional)
   0.15.15 (0463d37) makes durability configurable; ``amqp_durable`` false on only one side -> RabbitMQ 406, consumer thread dies.

.. _compat-issue-outbox-duplicate-final-status:

``outbox-duplicate-final-status`` (degraded)
   0.15.15 at-least-once outbox (de95b65) can redeliver a final status after a crash; Galaxy doesn't dedupe.

.. _compat-issue-master-features-unavailable:

``master-features-unavailable`` (degraded)
   Galaxy 26.2 features need a 0.16 server: per-job ``cvmfsexec`` (5ec0bc6) is silently dropped; container rewrite rules using ``__PULSAR_JOB_DIRECTORY__`` (81be9db) leave the token literal and the job fails.

.. _compat-issue-relay-topic-prefix-needs-0.15.13:

``relay-topic-prefix-needs-0.15.13`` (conditional)
   ``relay_topic_prefix`` arrived in 0.15.13; setting it against 0.15.12 mismatches topics.

.. _compat-issue-relay-default-username-dropped:

``relay-default-username-dropped`` (conditional)
   0.15.15 servers drop the default relay username ``admin``; operators relying on the default must set it.

.. _compat-issue-coexec-token-endpoint-ignored:

``coexec-token-endpoint-ignored`` (degraded)
   ``token_endpoint`` (lib 0.15.3, 39697ad) is ignored by the 0.15.0.2 image; OIDC-token remote file sources unusable in the pod.

.. _compat-issue-coexec-stdio-not-separated:

``coexec-stdio-not-separated`` (degraded)
   0.15.0.2 image predates job/tool stdio separation (00fa8c6); Galaxy copes.

.. _compat-issue-gcp-runnable-ordering:

``gcp-runnable-ordering`` (break)
   GCP Batch client in lib 0.15.14 orders runnables wrongly; fixed in 0.15.15.
