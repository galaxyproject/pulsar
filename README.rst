===
LWR
===

This project is a Python server application that allows a `Galaxy
<http://galaxyproject.org>`_ server to run jobs on remote systems (including
Windows) without requiring a shared mounted file systems. Unlike traditional
Galaxy job runners - input files, scripts, and config files may be transferred
to the remote system, the job is executed, and the result downloaded back to
the Galaxy server.

Full documentation for the project can be found on `Read The Docs
<https://lwr.readthedocs.org/>`_.

------------------
Configuring Galaxy
------------------

Galaxy job runners are configured in Galaxy's ``job_conf.xml`` file. See ``job_conf.xml.sample_advanced``
in your Galaxy code base or on
`Bitbucket <https://bitbucket.org/galaxy/galaxy-dist/src/tip/job_conf.xml.sample_advanced?at=default>`_
for information on how to configure Galaxy to interact with the LWR.

---------------
Downloading LWR
---------------

The LWR server application is distributed as a Python project and can
be obtained via mercurial from bitbucket.org using the following
command::

    hg clone http://bitbucket.org/jmchilton/lwr

----------------
LWR Dependencies
----------------

Several Python packages must be installed to run the LWR server. These can
either be installed into a Python ``virtualenv`` or into your system wide
Python environment using ``easy_install``. Instructions for both are outlined
below. Additionally, if DRMAA is going to be used to communicate with a
cluster, this dependency must be installed as well - again see note below.

virtualenv
----------

The script ``setup_venv.sh`` distributed with the LWR server is a
short-cut for \*nix machines to setup a Python environment (including
the installation of virtualenv). Full details for installation
suitable for \*nix or Windows are as follows.

1. Install `virtualenv <http://www.virtualenv.org/en/latest/#installation>`_ (if not available)::

    pip install virtualenv

2. Create a new Python environment::

    virtualenv -q --no-site-packages .venv

3. Activate environment (varies by OS). 

From a Linux or MacOS terminal::

    . .venv/bin/activate

From a Windows terminal::

    .venv\Scripts\activate

4. Install required dependencies into this virtual environment::

    pip install -r requirements.txt

easy_install
------------

Install python setuptools for your platform, more details on how to do
this can be found `here <http://pypi.python.org/pypi/setuptools>`_.

The ``easy_install`` command line application will be installed as
part of setuptools. Use the following command to install the needed
packages via ``easy_install``::

    easy_install paste wsgiutils PasteScript PasteDeploy webob six psutil pyOpenSSL

``pyOpenSSL`` is only required if LWR is configured to use HTTPS/SSL.

DRMAA
-----

If your LWR instance is going to communicate with a cluster via DRMAA, in
addition to the above dependencies, a DRMAA library will need to be installed
and the python dependency drmaa will need to be installed as well.::

    . .venv/bin/activate; pip install drmaa

or::

    easy_install drmaa

----------------------------------
Running the LWR Server Application
----------------------------------

\*nix Instructions
------------------

The LWR can be started and stopped via the ``run.sh`` script distributed with
the LWR.::

    ./run.sh --daemon
    ./run.sh --stop-daemon

These commands will start and stop the WSGI web server in daemon mode. In this
mode, logs are writtin to ``paster.log``.

If `circus <http://circus.readthedocs.org/en/0.9.2/>`_ and/or `chassuette
<https://chaussette.readthedocs.org/>`_, are available, more sophisticated web
servers can be launched via this ``run.sh`` command. See the script for more
details.

Alternative Cross Platform Instructions (Windows and \*nix)
-----------------------------------------------------------

The ``paster`` command line application will be installed as part of the
previous dependency installation process. This application can be used to
start and stop a paste web server running the LWR. This can be done by
executing the following command::

The server may be ran as a daemon via the command::

    paster serve server.ini --daemon

When running as daemon, the server may be stopped with the following command::

    paster serve server.ini --stop-daemon

If you setup a virtual environment for the LWR you will need
to activate this before executing these commands.

--------------------------------------
Configuring the LWR Server Application
--------------------------------------

Rename the ``server.ini.sample`` file distributed with LWR to ``server.ini``,
and edit the values therein to configure the server
application. Default values are specified for all configuration
options that will work if LWR is running on the same host as
Galaxy. However, the parameter "host" must be specified for remote
submissions to the LWR server to run properly. The ``server.ini`` file
contains documentation for many configuration parameters you may want
to modify.

Some advanced configuration topics are discussed below.

Securing the LWR Web Server
---------------------------

Out of the box the LWR essentially allows anyone with network access
to the LWR server to execute arbitrary code and read and write any
files the web server can. Hence, in most settings steps should be
taken to secure the LWR server.

The LWR can be configured to use SSL and to require the client
(i.e. Galaxy) to pass along a private token authorizing use.

To enable SSL, set the option ``ssl_pem`` in ``server.ini``. This
parameter should reference an OpenSSL certificate file for use by the
Python paste server. This parameter can be set to ``*`` to
automatically generate such a certificate. Such a certificate can
manually be generated by the following method::

    $ openssl genrsa 1024 > host.key
    $ chmod 400 host.key
    $ openssl req -new -x509 -nodes -sha1 -days 365  \
              -key host.key > host.cert
    $ cat host.cert host.key > host.pem
    $ chmod 400 host.pem

More information can be found in the `paste httpserver documentation
<http://pythonpaste.org/modules/httpserver.html>`_.

To specify a private token, simply set to ``private_key`` to some long
random string in ``server.ini``.

Once SSL has been enabled and a private token configured, Galaxy job
destinations should include a ``private_token`` parameter to authenticate
these jobs.

In the newer, experimental message queue driven LWR operation the underlying
security mechanisms of the message queue should be used to secure the LWR
communication - configuring SSL with the LWR and a ``private_token`` are not
required.

Job Managers (Queues)
---------------------

By default the LWR will maintain its own queue of jobs. While ideal for
Windows usage for instance, if the LWR is going to be used on more
sophisticate clusters, it can be configured to maintain multiple such queues
with different properties or to delegate to external job queues (via DRMAA,
qsub/qstat CLI commands, or Condor).

For more information on configured external job managers, see 
`the job managers documentation <https://lwr.readthedocs.org/#job-managers>`_.

Galaxy Tools
------------

Many Galaxy tool wrappers require a copy of the Galaxy codebase itself to run,
these tools will not run under Windows, but on \*nix hosts the LWR can be
configured to add the required Galaxy code a jobs ``PYTHON_PATH`` by setting
copying ``local_env.sh.sample`` to ``local_env.sh`` and setting the
``GALAXY_HOME`` environment variable.

Caching (Experimental)
----------------------

LWR and its clients can be configured to cache job input files. For some
workflows this can result in a significant decrease in data transfer and
greater throughput. On the LWR side - the property ``file_cache_dir`` in
``server.ini`` must be set. See Galaxy's 
`job_conf.xml <https://bitbucket.org/galaxy/galaxy-dist/src/tip/job_conf.xml.sample_advanced?at=default>`_
for information on configuring the client.

More discussion on this can be found in `this galaxy-dev mailing list thread <http://dev.list.galaxyproject.org/Re-Missing-module-in-the-lwr-repository-tc4664474.html>`_
and future plans and progress can be tracked on `this Trello card <https://trello.com/c/MPlt8DHJ>`_.

Message Queue (Experimental)
----------------------------

Galaxy and the LWR can be configured to communicate via a message queue
instead of an LWR web server. In this mode, the LWR will download files
from and upload files to Galaxy instead of the inverse - this may be very
advantageous if the LWR needs to be deployed behind a firewall or if the
Galaxy server is already setup (via proxy web server) for large file
transfers.

To bind the LWR server to a message queue, one needs to first ensure the
`kombu` Python dependency is installed (``pip install kombu``). Once this
available, simply set the ``message_queue_url`` property to the correct
URL of your configured `AMQP <http://en.wikipedia.org/wiki/AMQP>`_ endpoint.

Configuring your AMQP compatible message queue is beyond the scope of this
document - see `RabbitMQ <http://en.wikipedia.org/wiki/RabbitMQ>`_ for instance
for more details (other MQs should work also).

------
Puppet
------

A puppet module for automating the configuration an LWR server can be
found `here <https://github.com/jmchilton/puppet-lwr>`_.

-------
Testing
-------

.. image:: https://travis-ci.org/jmchilton/lwr.png?branch=master
    :target: https://travis-ci.org/jmchilton/lwr
.. image:: https://coveralls.io/repos/jmchilton/lwr/badge.png?branch=master 
    :target: https://coveralls.io/r/jmchilton/lwr?branch=master

A simple sanity test can be run against a running LWR server by
executing the following command (replace the URL command with the URL
of your running LWR application)::

    python run_client_tests.py --url=http://localhost:8913

-----------
Development
-----------

This project is distributed with unit and integration tests (many of
which will not run under Windows), the following command will install
the needed python components to run these tests.::

    pip install -r dev-requirements.txt

The following command will then run these tests::

    nosetests

The following command will then produce a coverage report
corresponding to this test and place it in the coverage_html_report
subdirectory of this project.::

    coverage html
