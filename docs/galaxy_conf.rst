.. _galaxy-conf:

--------------------
Galaxy Configuration
--------------------

Examples
--------

The most complete and updated documentation for configuring Galaxy job
destinations is Galaxy's ``job_conf.xml.sample_advanced`` file (check it out on
`GitHub
<https://github.com/galaxyproject/galaxy/blob/dev/config/job_conf.xml.sample_advanced>`_).
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
jobs to the remote cluster - namely the `trinity` and `abyss` tools. Be sure
the underlying applications required by the ``trinity`` and ``abyss`` tools
are on the Pulsar path or set ``tool_dependency_dir`` in ``app.yml`` and setup
Galaxy env.sh-style packages definitions for these applications.

.. literalinclude:: files/job_conf_sample_remote_cluster.xml
   :language: xml

For this configuration, on the Pulsar side be sure to also set a
``DRMAA_LIBRARY_PATH`` in ``local_env.sh``, install the Python ``drmaa``
module, and configure a DRMAA job manager for Pulsar in ``job_managers.ini`` as
follows:

.. literalinclude:: files/job_managers_sample_remote_cluster.ini

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

For those interested in this deployment option and new to Message Queues, there
is more documentation in :ref:`gx-pulsar-mq-setup`.

Additionally, Pulsar now ships with an RSync and SCP transfer action rather
than making use of the HTTP transport method.

.. literalinclude:: files/job_conf_sample_mq_rsync.xml
   :language: xml

Targeting Apache Mesos (Prototype)
``````````````````````````````````

See `commit message <https://github.com/galaxyproject/pulsar/commit/5888810b47da5065f532534b9594704bdd241d03>`_ for initial work on this and `this post on galaxy-dev <http://dev.list.galaxyproject.org/Using-Mesos-to-Enable-distributed-computing-under-Galaxy-tp4662310p4664829.html>`_.

Forcing Pulsar to Generate Galaxy Metadata
``````````````````````````````````````````

Typically Galaxy will process Pulsar's outputs and generate metadata
on the Galaxy server. One can force this to happen with Pulsar. (TODO:
document how here).

Etc...
``````

There are many more options for configuring what paths get staged/unstaged,
how Galaxy metadata is generated, running jobs as the real user, defining
multiple job managers on the Pulsar side, etc.... If you ever have any questions
please don't hesitate to ask John Chilton (jmchilton@gmail.com).



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
