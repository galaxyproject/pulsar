.. _job_managers:

-------------------------------
Job Managers
-------------------------------

By default the Pulsar will maintain its own queue of jobs. Under Linux
however, Pulsar can be configured to maintain multiple such queues with
different properties or to delegate to external job queues (via DRMAA_,
qsub/qstat CLI commands, or Condor_).

To configure job managers, uncomment the ``managers`` section of ``app.yml``
and modify it as needed. For instance, the default job manager corresponds to
a configuration of

.. code-block:: YAML

    managers:
      _default_:
        type: queued_python
        num_concurrent_jobs: 1

The ``type`` of ``queued_python`` is indicating that the jobs are queued but
that the queue is managed locally by Pulsar. Other possible values for
``type`` include ``detached_local``, ``queued_drmaa``, ``queued_condor``, ``queued_cli``,
``queued_external_drmaa`` (examples of each follow).

Named Managers
-------------------------------

The ``managers`` section can contain any number of named managers. For example::

    managers:
      _default_:
        type: queued_python
        num_concurrent_jobs: 1

      example:
        type: queued_python
        num_concurrent_jobs: "*"

In this instance, Pulsar creates a second named queued (``example``) that will
run as many concurrent jobs as the server has cores. The Galaxy Pulsar url
should have ``/managers/example`` appended to it to use a named manager such
as this.

Detached local execution
-------------------------------

``detached_local`` runs ordinary Pulsar commands on the same POSIX host while
keeping their execution independent of the Pulsar server process. Galaxy can
use it through its existing ``PulsarEmbeddedJobRunner`` with matching
capability-aware integration for attempt IDs, asynchronous cancellation,
execution policies, and collection acknowledgment. Unmodified Galaxy does not
implement this client contract. With that integration, restarting Galaxy
restarts its embedded Pulsar control code, while detached tools continue and
the replacement manager reconnects to their saved identities and exit records.
No separately managed execution service is required. For example::

    managers:
      local:
        type: detached_local
        staging_directory: /fast-local-disk/pulsar-staging
        num_concurrent_jobs: 2
        cancel_grace_seconds: 10
        poll_interval: 0.5
        supervisor_respawn_interval: 3

``num_concurrent_jobs`` defaults to one. A positive integer caps concurrent
executions, ``null`` or zero allows unlimited executions, and ``"*"`` uses the
host CPU count. Boolean, negative, and fractional values are invalid. All
managers sharing a staging directory share one FIFO capacity pool, coordinated
using a file lock; conflicting capacities fail at startup. Use separate staging
directories for independent batch and interactive pools. The cap is an
execution count, not a CPU or memory quota. Native dependency resolution, Conda,
staging, job scripts, metadata, and output collection remain available.
Capacity is recorded in ``.pulsar-detached-pool/configuration.json`` under the
staging directory. To change it, stop every manager sharing that directory,
update or remove that configuration record, and restart all managers with the
same new value. Keep the lock file and job manifests in place; existing
executions retain their reservations and new work waits for the new capacity.

Each ``setup_job`` generates a fresh remote identifier by default, allowing
resubmission of one Galaxy job to create a distinct attempt. Deployments that
explicitly choose ``assign_ids: galaxy`` must supply a distinct input ID per
attempt. Repeating ``launch`` for an existing attempt reconnects without
executing its command again.

The detached worker is copied into the private job directory before launch.
It records the host and boot identity, process IDs with creation times, launch
ownership, cancellation requests, and terminal exit proof. Replacement
supervisors reconnect to the same command. An ambiguous launch, inaccessible
process, host/boot mismatch, or Docker daemon outage retains the job and its
capacity rather than replaying a command or reporting false completion.
This supports server restarts on the same running host, not host reboot or
cross-host process recovery. Staging must remain available and the execution
identity must retain access to its Python environment (including ``psutil``).

Host commands and foreground Apptainer ``exec`` are tracked through their
process session. Docker batch and interactive commands additionally require
container lifecycle descriptors from a capable client. The native Galaxy
integration supplies a private ``configs/detached_execution.json`` policy with
``schema: 1``, a ``containers`` list, and ``limits``. Docker descriptors contain
``container_type: docker``, ``container_name``, ``connection_configuration``,
``expected_mount``, and ``role``. The expected mount is an absolute path or a
mapping with ``source`` and ``destination``. The worker records the immutable
container ID and verifies the mount before managing it. Foreground Apptainer
needs no Docker descriptor; independently managed Apptainer instances are not
supported. ``walltime_seconds`` and ``output_size_bytes`` remain enforced while
the server is down. ``output_size_bytes`` applies separately to each declared
file in ``output_paths``, matching Galaxy's native output-size limit. An
optional aggregate directory policy uses the distinct
``output_directory_size_bytes`` limit together with ``output_directory``;
it counts regular files recursively without following symlinks. Host CPU and
memory settings retain ordinary local execution semantics.

Interactive tools keep Galaxy's normal entry-point records and authentication.
The manager consumes the native ``configs/container_config.json`` callback
configuration, persists port discovery, and retries publication while Galaxy is
unavailable. Stop revokes access at the client and requests asynchronous worker
termination. A job becomes cancelled only after all verified process/container
writers have stopped. There is no implicit interactive-session expiry.
Command/dependency preparation holds an attempt-specific lock, so a slow
environment installation does not block other jobs' status, cancellation, or
admission. Cancellation before launch is confirmed only after preprocessing
and command-preparation writers return. A setup followed by Stop without any
submit remains uncertain: the manager cannot prove the client has finished
staging, so it retains that attempt rather than reporting false completion.

Cleanup is deliberately two-phase. ``clean(job_id)`` requests deletion, while
``acknowledge_collection(job_id)`` confirms the client has successfully imported
outputs and metadata. Only a verified terminal job with both records may be
deleted; duplicate cleanup calls do not count as acknowledgment. Failed or
uncertain collection therefore preserves staging. The capability map returned
by ``system_properties()["detached_local"]`` advertises ``schema: 1``,
``asynchronous_cancel``, ``collection_ack``, and ``execution_policy`` so clients
can opt into these interfaces. Existing managers are unaffected.

Detached execution and native completion recovery do not make arbitrary
external completion hooks transactional. Applications requiring stronger
output-import checkpoints must implement those guarantees separately.

DRMAA
-------------------------------

The ``queued_python`` manager type is easy to configure but has serious
limitations - for instance jobs running when Pulsar is restarted will be lost.
For these reasons it is best to configure a real external job manager when
possible.

Likely the cleanest way to interface with an external queueing system is going
to be DRMAA_. This method will likely work with Slurm_, PBS Torque_, LSF_,
etc.... In this case, one should likely setup a ``local_env.sh`` file and
update it to set ``DRMAA_LIBRARY_PATH`` to point to the correct
``libdrmaa.so`` file. Also, the Python ``drmaa`` module must be installed
(e.g. via ``pip install drmaa``).::

    managers:
      _default_:
        type: queued_drmaa
        native_specification: "-P bignodes -R y -pe threads 8"

Here the optional ``native_specification`` is going to depend on the underlying job
manager.

In addition to the default dependencies described in the installation
documentation, a DRMAA library will need to be installed and the python
dependency ``drmaa`` will need to be installed as well to use the
``queued_drmaa`` manager. This can be done by activating Pulsar's virtual environment and running::

    pip install drmaa

If you are using DRMAA, be sure to define ``DRMAA_LIBRARY_PATH`` in Pulsar's
``local_env.sh`` file.

Condor
-------------------------------

Condor_ can also be used as a backend.

::

    managers:
      _default_:
        type: queued_condor
        # Optional attributes...
        submit_universe: vanilla
        submit_request_memory: 32
        submit_requirements: 'OpSys == "LINUX" && Arch =="INTEL"'
        submit_rank: "Memory >= 64"

This would set universe, request_memory, requirements, and rank in the condor
submission file to the specified values. For more information on condor
submission files see the `HTCondor quickstart
<http://research.cs.wisc.edu/htcondor/quick-start.html>`__ for more
information.

CLI
-------------------------------

Pulsar can manage jobs via command-line execution of ``qsub``, ``qdel``,
``stat`` on the local machine.

::

    managers:
      _default_:
        type: queued_cli
        job_plugin: Torque

``job_plugin`` can also be ``Slurm`` (to use ``srun``, etc...) or
``SlurmTorque`` (to use the Slurm variant of ``qsub``, etc...).

Pulsar can also login into a remote host before executing these commands if
the job manager is not accessible from the Pulsar host.

::

    managers:
      _default_:
        type: queued_cli
        job_plugin: Torque
        shell_plugin: SecureShell
        shell_hostname: queuemanager
        shell_username: queueuser

This will login to ``queuemanager`` as user ``queueuser`` to submit jobs. Be
sure keyless SSH between Pulsar and the remote host is configured in this
case.


Run-As-Real User DRMAA
-------------------------------

All of the proceeding will run jobs as the same operating system user that
Pulsar is running as. The ``queued_external_drmaa`` manager type will actually
run DRMAA jobs via the user requested by the client (e.g. the Galaxy user).

::

    managers:
      _default_:
        type: queued_external_drmaa
        production: true
        # Following are optional - should leave as defaults in most cases.
        #chown_working_directory_script: scripts/chown_working_directory.bash
        #drmaa_kill_script: scripts/drmaa_kill.bash
        #drmaa_launch_script: scripts/drmaa_launch.bash
        #user_mapping_script:
        #user_mapping_timeout: 30

Additionally, set ``submit_user`` to ``$__user_name__`` in Galaxy's Pulsar job
destination. See Galaxy's `sample job configuration
<https://github.com/galaxyproject/galaxy/blob/dev/lib/galaxy/config/sample/job_conf.sample.yml>`__.


A script that maps the user name Pulsar receives from the Galaxy server onto a user
name on the target system can be configured with the optional parameter
``user_mapping_script``. The script receives the client-supplied name as a single
positional argument and should print the mapped name to stdout. If a mapping is not
possible it should exit with a non-zero status and print an error message to stderr,
which Pulsar logs.

The mapped name is passed to ``sudo -u`` and to the working-directory chown, so it is
validated before use: it must match ``[A-Za-z0-9._][A-Za-z0-9._-]*``. A script that
exits successfully but prints nothing, or prints a name outside that set, fails the
job rather than falling through to an unintended account. The script must return within
``user_mapping_timeout`` seconds (default 30).

More Options
-------------------------------

Most managers can override the ``staging_directory`` used by setting this
property in its configuration section.

The ``min_polling_interval: 0.5`` option can be set on any manager to control
how frequently Pulsar will poll the resource manager for job updates.

For staging actions initiated by Pulsar (e.g. when driving Pulsar by message queue) - the following parameters can be set to control retrying these actions (if they) fail. (XXX_max_retries=-1 => no retry, XXX_max_retries=0 => retry forever -
this may be a bit counter-intuitive but is consistent with Kombu_.

::

    preprocess_action_max_retries: -1
    preprocess_action_interval_start: 2
    preprocess_action_interval_step: 2
    preprocess_action_interval_max: 30
    postprocess_action_max_retries: -1
    postprocess_action_interval_start: 2
    postprocess_action_interval_step: 2
    postprocess_action_interval_max: 30


.. _DRMAA: http://www.drmaa.org/
.. _Condor: http://research.cs.wisc.edu/htcondor/
.. _Slurm: http://slurm.schedmd.com/
.. _Torque: http://www.adaptivecomputing.com/products/open-source/torque/
.. _LSF: http://www-03.ibm.com/systems/platformcomputing/products/lsf/
.. _Kombu: https://kombu.readthedocs.org/en/latest/
