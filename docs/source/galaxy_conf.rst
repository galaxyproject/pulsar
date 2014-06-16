-----------------------------
Galaxy Configuration Examples
-----------------------------

The most complete and updated documentation for configuring Galaxy job
destinations is Galaxy's ``job_conf.xml.sample_advanced`` file (check it out on
`Bitbucket
<https://bitbucket.org/galaxy/galaxy-dist/src/tip/job_conf.xml.sample_advanced?at=default>`_).
These examples just provide a different LWR-centric perspective on some of the
documentation in that file.


Simple Windows LWR Web Server
-----------------------------

The following Galaxy ``job_conf.xml`` assumes you have deployed a simple LWR
web server to the Windows host ``windowshost.examle.com`` on the default port
(``8913``) with a ``private_key`` (defined in ``server.ini``) of
``123456789changeme``. Most Galaxy jobs will just route use Galaxy's local job
runner but ``msconvert`` and ``proteinpilot`` will be sent to the LWR server
on ``windowshost.examle.com``. Sophisticated tool dependency resolution is not
available for Windows-based LWR servers so ensure the underlying application
are on the LWR's path.

.. literalinclude:: files/job_conf_sample_windows.xml

Targetting a Linux Cluster (LWR Web Server)
-------------------------------------------

The following Galaxy ``job_conf.xml`` assumes you have a very typical Galaxy
setup - there is a local, smaller cluster that mounts all of Galaxy's data (so
no need for the LWR) and a bigger shared resource that cannot mount Galaxy's
files requiring the use of the LWR. This variant routes some larger assembly
jobs to the remote cluster - namely the `trinity` and `abyss` tools. Be sure
the underlying applications required by the ``trinity`` and ``abyss`` tools
are the LWR path or set ``tool_dependency_dir`` in ``server.ini`` and setup
Galaxy env.sh-style packages definitions for these applications).

.. literalinclude:: files/job_conf_sample_remote_cluster.xml

For this configuration, on the LWR side be sure to set a
``DRMAA_LIBRARY_PATH`` in ``local_env.sh``, install the Python ``drmaa``
module, and configure a DRMAA job manager (example ``job_managers.ini``
follows).

.. literalinclude:: files/job_managers_sample_remote_cluster.ini

Targetting a Linux Cluster (LWR over Message Queue)
---------------------------------------------------

For LWR instances sitting behind a firewall a web server may be impossible. If
the same LWR configuration discussed above is additionally configured with a
``message_queue_url`` of ``amqp://rabbituser:rabb8pa8sw0d@mqserver:5672//`` in
``server.ini`` the following Galaxy configuration will cause this message
queue to be used for communication. This is also likely better for large file
transfers since typically your production Galaxy server will be sitting behind
a high-performance proxy but not the LWR.

.. literalinclude:: files/job_conf_sample_mq.xml

Etc...
------

There are many more options for configuring what paths get staging/unstaged
how, how Galaxy metadata is generated, running jobs as the real user, defining
multiple job managers on the LWR side, etc.... If you ever have any questions
please don't hesistate to ask John Chilton (jmchilton@gmail.com).
