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
enable this by passing ``--mq`` to ``pulsar-config``. Another particularly
useful option is ``--supervisor`` which will generate a Supervisord_
configuration for this directory and install Supervisord_.

.. TODO a full page of documentation on supervisor - perhaps auto-generated
   from --help.

.. TODO a page on operating pulsar via supervisord

``pulsar-config`` installs a few files into this directory. ``app.yml``
contains Pulsar configuration options and ``server.ini`` contains web server
related information (it will not exist if configured ``--mq``).::

    pulsar [start]

Under Linux and Mac OS X the ``start`` argument can be supplied to run Pulsar as
a daemon and ``pulsar stop``. If ``start`` is not supplied, Pulsar will just run
in the foreground (the only option for Windows).

The Pulsar deployment can be tested by running the following command, which will
submit an example job and wait for its completion.

    pulsar-check

If Pulsar is not running on the default port ``8913``, ``pulsar-check`` should
be called with an explicit URL using the argument
``--url=http://localhost:8913``. Likewise if a private token has been configured
it can be supplied using ``--private_token=<token>``.

From Source
----------------------

Pulsar can be obtained from GitHub_ using the following command::

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

Installation suitable for \*nix are as follows. These instructions can work for
Windows as well but generally the ``easy_install`` instructions below are more
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



.. _Galaxy: http://galaxyproject.org/
.. _GitHub: https://github.com/
.. _virtualenv: https://virtualenv.pypa.io/
.. _pip: https://pip.pypa.io/
.. _Supervisord: http://supervisord.org/
