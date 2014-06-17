--------------------
Galaxy Configuration
--------------------

Examples
--------

The most complete and updated documentation for configuring Galaxy job
destinations is Galaxy's ``job_conf.xml.sample_advanced`` file (check it out on
`Bitbucket
<https://bitbucket.org/galaxy/galaxy-dist/src/tip/job_conf.xml.sample_advanced?at=default>`_).
These examples just provide a different LWR-centric perspective on some of the
documentation in that file.


Simple Windows LWR Web Server
`````````````````````````````

The following Galaxy ``job_conf.xml`` assumes you have deployed a simple LWR
web server to the Windows host ``windowshost.examle.com`` on the default port
(``8913``) with a ``private_key`` (defined in ``server.ini``) of
``123456789changeme``. Most Galaxy jobs will just route use Galaxy's local job
runner but ``msconvert`` and ``proteinpilot`` will be sent to the LWR server
on ``windowshost.examle.com``. Sophisticated tool dependency resolution is not
available for Windows-based LWR servers so ensure the underlying application
are on the LWR's path.

.. literalinclude:: files/job_conf_sample_windows.xml
   :language: xml

Targeting a Linux Cluster (LWR Web Server)
``````````````````````````````````````````

The following Galaxy ``job_conf.xml`` assumes you have a very typical Galaxy
setup - there is a local, smaller cluster that mounts all of Galaxy's data (so
no need for the LWR) and a bigger shared resource that cannot mount Galaxy's
files requiring the use of the LWR. This variant routes some larger assembly
jobs to the remote cluster - namely the `trinity` and `abyss` tools. Be sure
the underlying applications required by the ``trinity`` and ``abyss`` tools
are the LWR path or set ``tool_dependency_dir`` in ``server.ini`` and setup
Galaxy env.sh-style packages definitions for these applications).

.. literalinclude:: files/job_conf_sample_remote_cluster.xml
   :language: xml

For this configuration, on the LWR side be sure to set a
``DRMAA_LIBRARY_PATH`` in ``local_env.sh``, install the Python ``drmaa``
module, and configure a DRMAA job manager (example ``job_managers.ini``
follows).

.. literalinclude:: files/job_managers_sample_remote_cluster.ini

Targeting a Linux Cluster (LWR over Message Queue)
``````````````````````````````````````````````````

For LWR instances sitting behind a firewall a web server may be impossible. If
the same LWR configuration discussed above is additionally configured with a
``message_queue_url`` of ``amqp://rabbituser:rabb8pa8sw0d@mqserver:5672//`` in
``server.ini`` the following Galaxy configuration will cause this message
queue to be used for communication. This is also likely better for large file
transfers since typically your production Galaxy server will be sitting behind
a high-performance proxy but not the LWR.

.. literalinclude:: files/job_conf_sample_mq.xml
   :language: xml

Targeting Apache Mesos (Prototype)
``````````````````````````````````

See `commit message <https://bitbucket.org/jmchilton/lwr/commits/555438d2fe266899338474b25c540fef42bcece7>`_ for initial work on this and `this post on galaxy-dev <http://dev.list.galaxyproject.org/Using-Mesos-to-Enable-distributed-computing-under-Galaxy-tp4662310p4664829.html>`_.

Etc...
``````

There are many more options for configuring what paths get staging/unstaged
how, how Galaxy metadata is generated, running jobs as the real user, defining
multiple job managers on the LWR side, etc.... If you ever have any questions
please don't hesistate to ask John Chilton (jmchilton@gmail.com).



File Actions
------------

Most of the parameters settable in Galaxy's job configuration file
``job_conf.xml`` are straight forward - but specifing how Galaxy and the LWR
stage various files may benefit from more explaination.

As demonstrated in the above ``default_file_action`` describes how inputs,
outputs, etc... are staged. The default ``transfer`` has Galaxy initiate HTTP
transfers. This makes little sense in the contxt of message queues so this
should be overridden and set to ``remote_transfer`` which causes the LWR to
initiate the file transfers. Additional options are available including
``none``, ``copy``, and ``remote_copy``.

In addition to this default - paths may be overridden based on various
patterns to allow optimization of file transfers in real production
infrastructures where various systems mount different file stores and file
stores with different paths on different systems.

To do this, the LWR destination in ``job_conf.xml`` may specify a parameter
named ``file_action_config``. This needs to be some config file path (if
relative, relative to Galaxy's root) like ``lwr_actions.yaml`` (can be YAML or
JSON - but older Galaxy's only supported JSON).

.. literalinclude:: files/file_actions_sample_1.yaml
   :language: yaml
