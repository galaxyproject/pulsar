======
Pulsar
======

This project is a Python server application that allows a `Galaxy
<http://galaxyproject.org>`_ server to run jobs on remote systems (including
Windows) without requiring a shared mounted file systems. Unlike traditional
Galaxy job runners - input files, scripts, and config files may be transferred
to the remote system, the job is executed, and the result downloaded back to
the Galaxy server.

Full documentation for the project can be found on `Read The Docs
<https://pulsar.readthedocs.org/>`_.

------------------
Configuring Galaxy
------------------

Galaxy job runners are configured in Galaxy's ``job_conf.xml`` file. Some small examples of how to configure this can be found `here <https://pulsar.readthedocs.org/en/latest/#galaxy-configuration>`__, but be sure to checkout ``job_conf.xml.sample_advanced``
in your Galaxy code base or on
`Bitbucket <https://bitbucket.org/galaxy/galaxy-dist/src/tip/job_conf.xml.sample_advanced?at=default>`_
for complete information.

------------------
Downloading Pulsar
------------------

Pulsar is distributed as a Python project and can be obtained from
Github using the following command::

    git clone https://github.com/galaxyproject/pulsar

-------------------
Pulsar Dependencies
-------------------

Several Python packages must be installed to run the Pulsar server. These can
either be installed into a Python ``virtualenv`` or into your system wide
Python environment using ``easy_install``. Instructions for both are outlined
below. Additionally, if DRMAA is going to be used to communicate with a
cluster, this dependency must be installed as well - again see note below.

virtualenv
----------

The script ``setup_venv.sh`` distributed with Pulsar is a
short-cut for \*nix machines to setup a Python environment (including
the installation of virtualenv). Full details for installation
suitable for \*nix are as follows. These instructions can work for Windows
as well but generally the ``easy_install`` instructions below are more
robust for Window's environments.

1. Install `virtualenv <http://www.virtualenv.org/en/latest/#installation>`_ (if not available)::

    pip install virtualenv

2. Create a new Python environment::

    virtualenv .venv

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
this can be found `here <http://pypi.python.org/pypi/setuptools>`__.

The ``easy_install`` command line application will be installed as
part of setuptools. Use the following command to install the needed
packages via ``easy_install``::

    easy_install paste wsgiutils PasteScript PasteDeploy webob six psutil

DRMAA
-----

If your Pulsar instance is going to communicate with a cluster via DRMAA, in
addition to the above dependencies, a DRMAA library will need to be installed
and the python dependency drmaa will need to be installed as well.::

    . .venv/bin/activate; pip install drmaa

or::

    easy_install drmaa

--------------
Running Pulsar
--------------

\*nix Instructions
------------------

Pulsar can be started and stopped via the ``run.sh`` script distributed with the project.::

    ./run.sh --daemon
    ./run.sh --stop-daemon

These commands will start and stop the WSGI web server in daemon mode. In this
mode, logs are writtin to ``paster.log``.

If `uWSGI <http://uwsgi-docs.readthedocs.org/>`_, `circus
<http://circus.readthedocs.org/en/0.9.2/>`_ and/or `chassuette
<https://chaussette.readthedocs.org/>`_, are available, more sophisticated web
servers can be launched via this ``run.sh`` command. See the script for more
details.

Alternative Cross Platform Instructions (Windows and \*nix)
-----------------------------------------------------------

The ``paster`` command line application will be installed as part of the
previous dependency installation process. This application can be used to
start and stop a paste web server running the Pulsar.

The server may be ran as a daemon via the command::

    paster serve server.ini --daemon

When running as daemon, the server may be stopped with the following command::

    paster serve server.ini --stop-daemon

If you setup a virtual environment for the Pulsar you will need
to activate this before executing these commands.

------------------
Configuring Pulsar
------------------

Rename the ``server.ini.sample`` file distributed with Pulsar to ``server.ini``,
and edit the values therein to configure the server
application. Default values are specified for all configuration
options that will work if Pulsar is running on the same host as
Galaxy. However, the parameter "host" must be specified for remote
submissions to the Pulsar server to run properly. The ``server.ini`` file
contains documentation for many configuration parameters you may want
to modify.

Some advanced configuration topics are discussed below.

Security
--------

Out of the box the Pulsar essentially allows anyone with network access
to the Pulsar server to execute arbitrary code and read and write any
files the web server can. Hence, in most settings steps should be
taken to secure the Pulsar server.

Pulsar Web Server
`````````````````

The Pulsar web server can be configured to use SSL and to require the client
(i.e. Galaxy) to pass along a private token authorizing use.

``pyOpenSSL`` is required to configure a Pulsar web server to server content via
HTTPS/SSL. This dependency can be difficult to install and seems to be getting
more difficult. Under Linux you will want to ensure the needed dependencies to
compile pyOpenSSL are available - for instance in a fresh Ubuntu image you
will likely need::

    sudo apt-get install libffi-dev python-dev libssl-dev

Then pyOpenSSL can be installed with the following command (be sure to source
your virtualenv if setup above)::

    pip install pyOpenSSL

Under Windows only older versions for pyOpenSSL are installable via pre-
compiled binaries (i.e. using `easy_install`) so it might be good to use non-
standard sources such as `eGenix <http://www.egenix.com/products/python/pyOpenSSL/>`_.

Once installed, you will need to set the option ``ssl_pem`` in ``server.ini``.
This parameter should reference an OpenSSL certificate file for use by the
Python paste server. This parameter can be set to ``*`` to automatically
generate such a certificate. Such a certificate can manually be generated by
the following method::

    $ openssl genrsa 1024 > host.key
    $ chmod 400 host.key
    $ openssl req -new -x509 -nodes -sha1 -days 365  \
              -key host.key > host.cert
    $ cat host.cert host.key > host.pem
    $ chmod 400 host.pem

More information can be found in the `paste httpserver documentation
<http://pythonpaste.org/modules/httpserver.html>`_.

Finally, in order to force Galaxy to authorize itself, you will want to
specify a private token - by simply setting ``private_token`` to some long
random string in ``server.ini``.

Once SSL has been enabled and a private token configured, Galaxy job
destinations should include a ``private_token`` parameter to authenticate
these jobs.

Pulsar Message Queue
````````````````````

If Pulsar is processing requests via a `message queue
<https://pulsar.readthedocs.org/en/latest/galaxy_with_rabbitmq_conf.html>`_
instead of a web server the underlying security mechanisms of the message
queue should be used to secure communication - deploying Pulsar with SSL and a
``private_token`` described above are not required.

This will likely consist of setting some combination of
``amqp_connect_ssl_ca_certs``, ``amqp_connect_ssl_keyfile``,
``amqp_connect_ssl_certfile``, ``amqp_connect_ssl_cert_reqs``, in Pulsar's
``server.ini`` file. See ``server.ini.sample`` for more details and the `Kombu
documentation
<http://kombu.readthedocs.org/en/latest/reference/kombu.connection.html>`_ for
even more information.

Customizing the Pulsar Environment
-----------------------------------

In more sophisticated deployments, the Pulsar's environment will need to be
tweaked - for instance to define a ``DRMAA_LIBRARY_PATH`` environment variable
for the ``drmaa`` Python module or to define the location to a find a location
of Galaxy (via ``GALAXY_HOME``) if certain Galaxy tools require it or if
Galaxy metadata is being set by the Pulsar. The recommend way to do this is to
copy ``local_env.sh.sample`` to ``local_env.sh`` and customize it.

This file of deployment specific environment tweaks will be source by
``run.sh`` if it exists as well as by other Pulsar scripts in more advanced
usage scenarios.

Job Managers (Queues)
---------------------

By default the Pulsar will maintain its own queue of jobs. While ideal for
simple deployments such as those targetting a single Windows instance, if the
Pulsar is going to be used on more sophisticate clusters, it can be configured
to maintain multiple such queues with different properties or to delegate to
external job queues (via DRMAA, qsub/qstat CLI commands, or Condor).

For more information on configured external job managers, see
`the job managers documentation <https://pulsar.readthedocs.org/en/latest/job_managers.html>`_.

Warning: If you are using DRMAA, be sure to define ``DRMAA_LIBRARY_PATH`` in
``local_env.sh`` defined above.

Galaxy Tools
------------

Some Galaxy tool wrappers require a copy of the Galaxy codebase itself to run.
Such tools will not run under Windows, but on \*nix hosts the Pulsar can be
configured to add the required Galaxy code a jobs ``PYTHON_PATH`` by setting
``GALAXY_HOME`` environment variable in the Pulsar's ``local_env.sh`` file
(described above).

Caching (Experimental)
----------------------

Pulsar and its client can be configured to cache job input files. For some
workflows this can result in a significant decrease in data transfer and
greater throughput. On the Pulsar server side - the property
``file_cache_dir`` in ``server.ini`` must be set. See Galaxy's  `job_conf.xml
<https://bitbucket.org/galaxy/galaxy-
dist/src/tip/job_conf.xml.sample_advanced?at=default>`_ for information on
configuring the client.

More discussion on this can be found in `this galaxy-dev mailing list thread <http://dev.list.galaxyproject.org/Re-Missing-module-in-the-lwr-repository-tc4664474.html>`_
and future plans and progress can be tracked on `this Trello card <https://trello.com/c/MPlt8DHJ>`_.

Message Queue (Experimental)
----------------------------

Galaxy and the Pulsar can be configured to communicate via a message queue
instead of an Pulsar web server. In this mode, the Pulsar will download files
from and upload files to Galaxy instead of the inverse - this may be very
advantageous if the Pulsar needs to be deployed behind a firewall or if the
Galaxy server is already setup (via proxy web server) for large file
transfers.

To bind the PUlsar server to a message queue, one needs to first ensure the
``kombu`` Python dependency is installed (``pip install kombu``). Once this
available, simply set the ``message_queue_url`` property in ``server.ini`` to
the correct URL of your configured `AMQP <http://en.wikipedia.org/wiki/AMQP>`_
endpoint.

Configuring your AMQP compatible message queue is beyond the scope of this
document - see `RabbitMQ <http://en.wikipedia.org/wiki/RabbitMQ>`_ for instance
for more details (other MQs should work also).

-------
Testing
-------

.. image:: https://travis-ci.org/galaxyproject/pulsar.png?branch=master
    :target: https://travis-ci.org/galaxyproject/pulsar
.. image:: https://coveralls.io/repos/galaxyproject/pulsar/badge.png?branch=master
    :target: https://coveralls.io/r/galaxyproject/pulsar?branch=master

A simple sanity test can be run against a running Pular server by
executing the following command (replace the URL command with the URL
of your running Pulsar application)::

    python run_client_tests.py --url=http://localhost:8913

-----------
Development
-----------

This project is distributed with unit and integration tests (many of
which will not run under Windows), the following command will install
the needed python components to run these tests.::

    pip install -r dev-requirements.txt

The following command will then run these tests::

    make tests

The following command will then produce a coverage report
corresponding to this test and place it in the coverage_html_report
subdirectory of this project.::

    coverage html

Checkout the `Contributing
<https://pulsar.readthedocs.org/en/latest/contributing.html>`_ documentation
for many more details on developing and contributing to Pulsar.
