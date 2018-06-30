.. _install:

--------------------
Installing Pulsar
--------------------

There are two primary ways to deploy Pulsar. The newer and preferred
method is to install Pulsar from `PyPI <pypi.python.org/pypi/pulsar-app>`__
using the standard Python tools of pip_ and virtualenv_.

The older method also requires these tools to install Pulsar's dependencies
but Pulsar itself is served directly from a clone of the Pulsar source tree -
this mirrors how `Galaxy`_ is most typically deployed. This may be beneficial
during Pulsar development and is required for certain experimental features such
as Mesos support.

Both methods presented here require a pip_ installation availabe for Windows,
Linux, and Mac OS X in addition to a Python 2 runtime (`Windows
<http://docs.python-guide.org/en/latest/starting/install/win/>`__,
`Linux <http://docs.python-guide.org/en/latest/starting/install/linux/>`__,
`Mac OS X
<http://docs.python-guide.org/en/latest/starting/install/osx>`__).

These instructions also require virtualenv_. Open a console on your machine and
type ``virtualenv`` - if the command is missing you will need to install it. It
can be installed using ``[sudo] pip install virtualenv``.

From PyPI
----------------------

Start by creating a directory for the pulsar configuration files and setting
up a virtualenv to install Pulsar into using the following three commands.::

    mkdir pulsar
    cd pulsar
    virtualenv venv

Next, activate this newly created virtualenv. From a Linux or MacOS X terminal
this can be done with the command ``. venv/bin/activate`` and in Windows you can
type ``venv\Scripts\activate``.

Next install pulsar using ``pip``.::

    pip install pulsar-app

Next setup required this directory for use with Pulsar by running the following
command.::

    pulsar-config

The ``pulsar-config`` script can bootstrap various Pulsar deployment options,
run ``pulsar-config --help`` for full details. For instance, Pulsar can be
configured to monitor a message queue and skip the web server configuration -
enable this by passing ``--mq`` to ``pulsar-config``. Another useful option is
``--supervisor`` which will generate a Supervisord_ configuration for this
directory and install Supervisord_.

.. TODO a full page of documentation on supervisor - perhaps auto-generated
   from --help.
.. TODO a page on operating pulsar via supervisord

``pulsar-config`` installs a few files into this directory. ``app.yml``
contains Pulsar configuration options and ``server.ini`` contains web server
related information (it will not exist if configured ``--mq``).::

    pulsar [--daemon]

Under Linux and Mac OS X the ``--daemon`` argument can be supplied to run
Pulsar as a daemon and ``pulsar --stop-daemon``. If ``start`` is not supplied,
Pulsar will just run in the foreground (the only option for Windows).

The Pulsar deployment can be tested by running the following command, which will
submit an example job and wait for its completion.::

    pulsar-check

If Pulsar is not running on the default port ``8913``, ``pulsar-check`` should
be called with an explicit URL using the argument
``--url=http://localhost:8913``. Likewise if a private token has been configured
it can be supplied using ``--private_token=<token>``.

From Source
----------------------

Alternatively, Pulsar can be obtained from GitHub_ using the following command
and ran directly from the source tree (like Galaxy is traditionally
deployed)::

    git clone https://github.com/galaxyproject/pulsar


The following section will assume your current working directory is the newly
created ``pulsar`` directory.

    cd pulsar

~~~~~~~~~~~~~~~~~~~
Pulsar Dependencies
~~~~~~~~~~~~~~~~~~~

Several Python packages must be installed to run the Pulsar server. These can
either be installed into a Python ``virtualenv`` or into your system wide
Python environment either using ``pip`` or ``easy_install``. Combining the
``virtualenv`` approach with ``pip`` based installation works fine most of the
time, but in the past ``easy_install``-based installation was slightly more
robust under Windows and requires only a Python installation so those
instructions are included as well.

This section describes setting up the minimal dependencies required for
running a standalone Pulsar web server. Additional dependencies are required
for features such submitting to a cluster (``drmaa``), communicating via
message queue (``kombu``), etc.... Most of the time these can just be
installed with ``pip install <dependency_name>``. Pulsar's documentation about
these functionality

virtualenv
~~~~~~~~~~~~~~~~~~~

1. Install virtualenv_ (if not already available)::

    [sudo] pip install virtualenv

2. Create a new Python virtual environment called ``.venv`` in the ``pulsar`` root directory::

    virtualenv .venv

3. Activate environment (varies by OS).

From a Linux or MacOS terminal::

    . .venv/bin/activate

From a Windows terminal::

    .venv\Scripts\activate

4. Install required dependencies into this virtual environment::

    pip install -r requirements.txt

easy_install
~~~~~~~~~~~~~~~~~~~

Install python setuptools for your platform, more details on how to do
this can be found `here <http://pypi.python.org/pypi/setuptools>`__.

The ``easy_install`` command line application will be installed as
part of setuptools. Use the following command to install the needed
packages via ``easy_install``::

    easy_install paste wsgiutils PasteScript PasteDeploy webob six psutil pyyaml

Launching Pulsar
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Before launching Pulsar, it may make sense to copy over the sample
configuration files. ``server.ini`` is used to describe web server related
properties and ``app.yml`` is used for Pulsar application-related
configuration files.

    cp server.ini.sample server.ini
    cp app.yml.sample app.yml

Pulsar should now be launchable via the ``run.sh`` script under Linux or Mac
OS X or using the ``run.bat`` script under Windows. So under Linux or Mac OS
X, Pulsar can be launched in daemon mode as::

    ./run.sh --daemon

This daemon can be stopped using ``./run.sh --stop-daemon``. When run as a
daemon, Pulsar will log to the file ``paster.log``.

Under Windows, Pulsar can be started using::

    run.bat

and will run as long as that process is alive and log to standard output.

    python run_client_tests.py

If Pulsar's ``server.ini`` has been modified and it is not running on the
default port ``8913``, ``run_client_tests.py`` should be called with an
explicit URL using the argument ``--url=http://localhost:8913``. Likewise if a
private token has been configured it can be supplied using
``--private_token=<token>``. ``server.ini`` settings can be overridden by
setting environment variables, just as with Galaxy, by prefixing the config
setting name with ``PULSAR_CONFIG_OVERRIDE``. For example
``PULSAR_CONFIG_OVERRIDE_PRIVATE_TOKEN``. Defaults can also be set via
environment variables by just prefixing with ``PULSAR_CONFIG``. For example,
``PULSAR_CONFIG_PRIVATE_TOKEN``.

A Note on ``run.sh``
~~~~~~~~~~~~~~~~~~~~~~~~~~~

If any of `circus <http://circus.readthedocs.org/en/0.9.2/>`_, `chassuette
<https://chaussette.readthedocs.org/>`_, or `uWSGI
<http://uwsgi-docs.readthedocs.org/>`_ are installed into Pulsar's virtual 
environment more sophisticated web servers will launched via this ``run.sh``
command. See the script for more details.

.. _Galaxy: http://galaxyproject.org/
.. _GitHub: https://github.com/
.. _virtualenv: https://virtualenv.pypa.io/
.. _pip: https://pip.pypa.io/
.. _Supervisord: http://supervisord.org/
