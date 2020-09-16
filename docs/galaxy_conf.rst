.. _galaxy_conf:

--------------------
Galaxy Configuration
--------------------

Examples
--------

The most complete and updated documentation for configuring Galaxy job
destinations is Galaxy's ``job_conf.xml.sample_advanced`` file (check it out on
`GitHub
<https://github.com/galaxyproject/galaxy/blob/dev/lib/galaxy/config/sample/job_conf.xml.sample_advanced>`_).
These examples just provide a different Pulsar-centric perspective on some of the documentation in that file.

Simple Windows Pulsar Web Server
````````````````````````````````

The following Galaxy ``job_conf.xml`` assumes you have deployed a simple Pulsar
web server to the Windows host ``windowshost.examle.com`` on the default port
(``8913``) with a ``private_token`` (defined in ``app.yml``) of
``123456789changeme``. Most Galaxy jobs will just route use Galaxy's local job
runner but ``msconvert`` and ``proteinpilot`` will be sent to the Pulsar server
on ``windowshost.examle.com``. Sophisticated tool dependency resolution is not
available for Windows-based Pulsar servers so ensure the underlying application
are on the Pulsar's path.

.. literalinclude:: files/job_conf_sample_windows.xml
   :language: xml

Targeting a Linux Cluster (Pulsar Web Server)
`````````````````````````````````````````````

The following Galaxy ``job_conf.xml`` assumes you have a very typical Galaxy
setup - there is a local, smaller cluster that mounts all of Galaxy's data (so
no need for the Pulsar) and a bigger shared resource that cannot mount Galaxy's
files requiring the use of the Pulsar. This variant routes some larger assembly
jobs to the remote cluster - namely the ``trinity`` and ``abyss`` tools.

.. literalinclude:: files/job_conf_sample_remote_cluster.xml
   :language: xml

For this configuration, on the Pulsar side be sure to also set a
``DRMAA_LIBRARY_PATH`` in ``local_env.sh``, install the Python ``drmaa``
module, and configure a DRMAA job manager for Pulsar in ``app.yml`` as described
in :ref:`job_managers`.

Targeting a Linux Cluster (Pulsar over Message Queue)
`````````````````````````````````````````````````````

For Pulsar instances sitting behind a firewall, a web server may be impossible. If
the same Pulsar configuration discussed above is additionally configured with a
``message_queue_url`` of ``amqp://rabbituser:rabb8pa8sw0d@mqserver:5672//`` in
``app.yml``, the following Galaxy configuration will cause this message
queue to be used for communication. This is also likely better for large file
transfers since typically your production Galaxy server will be sitting behind
a high-performance proxy while Pulsar will not.

.. literalinclude:: files/job_conf_sample_mq.xml
   :language: xml

The ``manager`` param to the ``PulsarMQJobRunner`` plugin allows for using the
same AMQP server and vhost (in this example, the default ``/`` vhost) between
multiple Pulsar servers, or submitting jobs to multiple managers (see:
:ref:`job_managers`) on the same Pulsar server.

In this example, the ``_default_`` job manager will be used for ``trinity``
jobs, and the ``hugenodes`` job manager will be used for ``abyss`` jobs.

.. note::

    If you only need to define different ``submit_native_specification`` params
    on the same cluster for these tools/destinations, it is not necessary to use
    a separate manager - multiple destinations can reference the same plugin.
    This example is for documentation purposes.

All of the ``amqp_*`` options documented in `app.yml.sample`_ can be specified
as params to the ``PulsarMQJobRunner`` plugin. These configure Galaxy's
connection to the AMQP server (rather than Pulsar's connection, which is
configured in Pulsar's ``app.yml``). Additionally, specifying the
``persistence_directory`` param controls where AMQP acknowledgement receipts
will be stored on the Galaxy side.

For those interested in this deployment option and new to Message Queues, there
is more documentation in :ref:`galaxy_with_rabbitmq_conf`.

Additionally, Pulsar ships with an RSync and SCP transfer action rather than
making use of the HTTP transport method:

.. literalinclude:: files/job_conf_sample_mq_rsync.xml
   :language: xml

Targeting Apache Mesos (Prototype)
``````````````````````````````````

See `commit message <https://github.com/galaxyproject/pulsar/commit/5888810b47da5065f532534b9594704bdd241d03>`_ for initial work on this and `this post on galaxy-dev <http://dev.list.galaxyproject.org/Using-Mesos-to-Enable-distributed-computing-under-Galaxy-tp4662310p4664829.html>`_.

Generating Galaxy Metadata in Pulsar Jobs
`````````````````````````````````````````

This option is often referred to as *remote metadata*.

Typically Galaxy will process Pulsar job outputs and generate metadata on the
Galaxy server. One can force this to happen inside Pulsar jobs (wherever the
Pulsar job runs).  This is similar to the way that non-Pulsar Galaxy jobs work:
job output metadata is generated at the end of a standard Galaxy job, not by the
Galaxy server.

This option comes with a downside that you should be aware of, explained in
`Issue #234 <https://github.com/galaxyproject/pulsar/issues/234>`__. Unless you
are seeing high load on your Galaxy server while finishing Pulsar jobs, it is
safest to use the default (remote metadata disabled).

In order to enable the remote metadata option:

1. Set ``GALAXY_VIRTUAL_ENV`` to the path to Galaxy's virtualenv (or one
   containing Galaxy's dependencies) when starting Pulsar. This can be done in
   the ``local_env.sh`` file. Instructions on setting up a Galaxy virtualenv can
   be found in the `Galaxy Docs <http://docs.galaxyproject.org/>`__.

2. Instruct Pulsar with the path to a copy of Galaxy at the same version as your
   Galaxy server. This can either be done by setting ``GALAXY_HOME`` in
   ``local_env.sh``, or by setting ``galaxy_home`` in ``app.yml``.

3. In the Galaxy ``job_conf.xml`` *destination(s)* you want to enable remote
   metadata on, set the following params::

        <param id="remote_metadata">true</param>
        <param id="remote_property_galaxy_home">/path/to/galaxy</param>

   and one of either::

        <param id="use_metadata_binary">true</param>

   or::

        <param id="use_remote_datatypes">false</param>

Data Staging
------------

Most of the parameters settable in Galaxy's job configuration file
``job_conf.xml`` are straight forward - but specifying how Galaxy and the Pulsar
stage various files may benefit from more explanation.

``default_file_action`` defined in Galaxy's `job_conf.xml` describes how
inputs, outputs, indexed reference data, etc... are staged. The default
``transfer`` has Galaxy initiate HTTP transfers. This makes little sense in the
context of message queues so this should be set to ``remote_transfer``, which
causes Pulsar to initiate the file transfers. Additional options are available
including ``none``, ``copy``, and ``remote_copy``.

In addition to this default - paths may be overridden based on various
patterns to allow optimization of file transfers in production
infrastructures where various systems mount different file stores and file
stores with different paths on different systems.

To do this, the defined Pulsar destination in Galaxy's ``job_conf.xml`` may
specify a parameter named ``file_action_config``. This needs to be a config
file path (if relative, relative to Galaxy's root) like
``config/pulsar_actions.yaml`` (can be YAML or JSON - but older Galaxy's only
supported JSON). The following captures available options:

.. literalinclude:: files/file_actions_sample_1.yaml
   :language: yaml

.. _app.yml.sample: https://github.com/galaxyproject/pulsar/blob/master/app.yml.sample
