.. _install:

--------------------
Installing Pulsar
--------------------

.. tip::

    This documentation covers installing Pulsar by hand. The tutorial
    `Running Jobs on Remote Resources with Pulsar <https://training.galaxyproject.org/training-material/topics/admin/tutorials/pulsar/tutorial.html>`_
    in the `Galaxy Training Network <https://training.galaxyproject.org/>`_
    contains a step-by-step guide for installing Pulsar using `Ansible
    <http://www.ansible.com/>`_.

There are two primary ways to deploy Pulsar. The newer and preferred
method is to install Pulsar from `PyPI <pypi.python.org/pypi/pulsar-app>`__
using the standard pip_ and venv_ Python tools.

The older method also requires these tools to install Pulsar's dependencies
but Pulsar itself is served directly from a clone of the Pulsar source tree -
this mirrors how `Galaxy`_ is most typically deployed. This may be beneficial
during Pulsar development and is required for certain experimental features such
as Mesos support.

Both methods presented here require a Python 3.5 (or later) runtime for either
`Windows <https://docs.python-guide.org/starting/install3/win/>`__,
`Linux <https://docs.python-guide.org/starting/install3/linux/>`__, or
`macOS <https://docs.python-guide.org/starting/install3/osx/>`__. **Python 2 is
no longer supported as of the 0.14.0 release of Pulsar**.

These instructions also require venv_. Open a console on your machine and
type ``python3 -m venv`` - if the module is missing you will need to install it.
It is part of any full Python installation, but some Linux distributions (such
as Debian and its derivatives) package it separately. On Debian systems, you can

From PyPI
----------------------

Start by creating a directory for the Pulsar configuration files and setting
up a venv to install Pulsar into using the following three commands.::

    $ mkdir pulsar
    $ cd pulsar
    $ python3 -m venv venv

Next, activate this newly created venv. From a Linux or macOS terminal, this can
be done with the command ``. venv/bin/activate`` and in Windows you can type
``venv\Scripts\activate``.

Next install Pulsar using ``pip``.::

    $ pip install 'pulsar-app[web]'

If you are planning to use Pulsar in the optional message queue mode rather than
traditional web mode (see the :doc:`configuration docs <configure>`), you can
drop ``[web]`` from the install command (this extra qualifier causes web serving
packages to be installed).

Next, create the required configuration files for use with Pulsar in this
directory by running the following command.::

    $ pulsar-config

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
related information (it will not exist if configured ``--mq``).

Launching Pulsar
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Pulsar server can be started by running::

    $ pulsar [--daemon]

Under Linux and macOS the ``--daemon`` argument can be supplied to run Pulsar as
a daemon, and stopped with ``pulsar --stop-daemon``. If ``--daemon`` is not
supplied, Pulsar will just run in the foreground (the only option for Windows).

The Pulsar deployment can be tested by running the following command, which will
submit an example job and wait for its completion.::

    $ pulsar-check

If Pulsar is not running on the default port ``8913``, ``pulsar-check`` should
be called with an explicit URL using the argument
``--url=http://localhost:8913``. Likewise if a private token has been configured
it can be supplied using ``--private_token=<token>``.

From Source
----------------------

Alternatively, Pulsar can be obtained from GitHub_ using the following command
and ran directly from the source tree (like Galaxy is traditionally
deployed)::

    $ git clone https://github.com/galaxyproject/pulsar


The following steps assume your current working directory is the newly created
``pulsar`` directory.::

    $ cd pulsar

Create a new Python virtual environment called ``.venv`` in the ``pulsar`` root
directory::

    $ python3 -m venv .venv

Activate environment (varies by OS). From a Linux or macOS terminal::

    $ . .venv/bin/activate

Or from a Windows terminal::

    $ .venv\Scripts\activate.bat

Finally, install Pulsar's required dependencies into the virtual environment::

    $ pip install -r requirements.txt

If using the standard webserver, it can be installed with::

    $ pip install Paste PasteScript

Launching Pulsar
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Before launching Pulsar, it may make sense to copy over the sample
configuration files. ``server.ini`` is used to describe web server related
properties and ``app.yml`` is used for Pulsar application-related
configuration files::

    $ cp server.ini.sample server.ini
    $ cp app.yml.sample app.yml

Pulsar should now be launchable via the ``run.sh`` script under Linux or macOS
or using the ``run.bat`` script under Windows. So under Linux or macOS,
Pulsar can be launched with::

    $ ./run.sh [--daemon]

This daemon can be stopped using ``./run.sh --stop-daemon``. When run as a
daemon, Pulsar will log to the file ``paster.log``.  If ``--daemon`` is not
supplied, Pulsar will just run in the foreground.

Under Windows, Pulsar can be started using::

    $ run.bat

and will run as long as that process is alive and log to standard output. A test
job can be submitted using the command::

    $ python run_client_tests.py

If Pulsar's ``server.ini`` has been modified and it is not running on the
default port ``8913``, ``run_client_tests.py`` should be called with an
explicit URL using the argument ``--url=http://localhost:8913``. Likewise if a
private token has been configured it can be supplied using
``--private_token=<token>``.

Pulsar Webservers
----------------------

Pulsar's default webserver (if web dependencies are installed) is `Paste`_.
However, `uWSGI`_ or `circus`_ will be used instead, if found.

A precompiled version of uWSGI can be installed with::

    $ pip install pyuwsgi

Or compiled from source with::

    $ pip install uWSGI

Pulsar Dependencies
--------------------

Several Python packages must be installed to run the Pulsar server. The core set
of required dependencies were installed during the Pulsar installation in the
previous section. Additional dependencies are required for features such
submitting to a cluster (``drmaa``), communicating via message queue
(``kombu``), etc.... Most of the time these can just be installed with ``pip
install <dependency_name>``.

.. TODO better optional dependency handling/docs

.. _Galaxy: http://galaxyproject.org/
.. _GitHub: https://github.com/
.. _venv: https://docs.python.org/3/library/venv.html
.. _pip: https://pip.pypa.io/
.. _Supervisord: http://supervisord.org/
.. _Paste: https://pythonpaste.readthedocs.io/en/latest/
.. _uWSGI: https://uwsgi-docs.readthedocs.io/
.. _circus: http://circus.readthedocs.org/
