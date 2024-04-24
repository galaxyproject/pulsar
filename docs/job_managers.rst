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
``type`` include ``queued_drmaa``, ``queued_condor``, ``queued_cli``,
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
``SlurmTorque`` (to use the Slurm varaint of ``qsub``, etc...).

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

For more information on running jobs as the real user, check out `this discussion
<http://dev.list.galaxyproject.org/Managing-Data-Locality-tp4662438.html>`__ from
the Galaxy mailing list.

More Options
-------------------------------

Any manager can override the ``staging_directory`` used by setting this
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
