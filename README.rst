.. figure:: https://galaxyproject.org/images/galaxy-logos/pulsar_transparent.png
   :alt: Pulsar Logo

.. image:: https://readthedocs.org/projects/pulsar/badge/?version=latest
   :target: http://pulsar.readthedocs.io/en/latest/?badge=latest
   :alt: Documentation Status
.. image:: https://badge.fury.io/py/pulsar-app.svg
   :target: https://pypi.python.org/pypi/pulsar-app/
   :alt: Pulsar on the Python Package Index (PyPI)
.. image:: https://travis-ci.org/galaxyproject/pulsar.png?branch=master
   :target: https://travis-ci.org/galaxyproject/pulsar
   :alt: Build Status
.. image:: https://coveralls.io/repos/galaxyproject/pulsar/badge.png?branch=master
   :target: https://coveralls.io/r/galaxyproject/pulsar?branch=master
   :alt: Test Coverage

This project is a Python server application that allows a `Galaxy
<http://galaxyproject.org>`_ server to run jobs on remote systems (including
Windows) without requiring a shared mounted file systems. Unlike traditional
Galaxy job runners - input files, scripts, and config files may be transferred
to the remote system, the job is executed, and the results are transferred back
to the Galaxy server - eliminating the need for a shared file system.

Full documentation for the project can be found on `Read The Docs
<https://pulsar.readthedocs.io/>`_.

------------------
Configuring Galaxy
------------------

Galaxy job runners are configured in Galaxy's ``job_conf.xml`` file. Some small
examples of how to configure this can be found `here
<https://pulsar.readthedocs.org/en/latest/galaxy_conf.html>`__, but be sure
to check out ``job_conf.xml.sample_advanced`` in your Galaxy code base or on
`Github
<https://github.com/galaxyproject/galaxy/blob/master/config/job_conf.xml.sample_advanced>`_
for complete information.

------------------
Quickstart
------------------

Full details on different ways to install Pulsar can be found in the `install
section <https://pulsar.readthedocs.org/en/latest/install.html>`__ of the
documentaiton, but if your machine has the proper Python dependencies
available it can be quickly download and a test job run with::

    $ mkdir pulsar
    $ cd pulsar
    $ python3 -m venv venv
    $ . venv/bin/activate    # venv\Scripts\activate.bat on Windows
    $ pip install 'pulsar-app[web]'
    $ pulsar-config
    $ pulsar --daemon        # just `pulsar` on Windows
    $ pulsar-check           # runs a test job

Please note that as of the 0.14.0 release, Pulsar no longer supports any version
of Python 2. The minimum supported Python version is 3.5.

The `configuration documentation
<https://pulsar.readthedocs.org/en/latest/configure.html>`__
has many details on securing your Pulsar server and enabling advanced features
such as cluster integration and message queue communication.

-----------------------
Development and Testing
-----------------------

The recommended approach to setting up a development environment for Pulsar on
Linux or macOS is rougly as follows::

    $ git clone https://github.com/galaxyproject/pulsar
    $ cd pulsar
    $ python3 -m venv .venv
    $ . .venv/bin/activate    # .venv\Scripts\activate on Windows
    $ pip install -e '.[web]'
    $ pip install -r dev-requirements.txt

The ``-e`` flag to ``pip`` installs Pulsar in "editable" mode, meaning that
changes you make to the source code will be reflected when running the pulsar
commands installed in the virtual environment.

This project is distributed with unit and integration tests (many of which will
not run under Windows), the following command will install the needed python
components to run these tests. The following command will then run these tests::

    $ make tests

The following command will then produce a coverage report corresponding to this
test and place it in the ``coverage_html_report`` subdirectory of this
project.::

    $ coverage html

Check out the `Contributing
<https://pulsar.readthedocs.org/en/latest/contributing.html>`_ documentation
for many more details on developing and contributing to Pulsar.

Please note that this project is released with a `Contributor Code of Conduct 
<https://pulsar.readthedocs.org/en/latest/conduct.html>`__. By participating
in this project you agree to abide by its terms.

-----------------------
Support
-----------------------

This documentation is an incomplete work in progress. There are more ways to
configure and use Pulsar than are documented, and a growing number of Pulsar
experts who would be more than happy to answer your questions and help with any
problems you may run in to while setting up a Pulsar deployment. Please do not
hesitate to reach out on the `Galaxy Admins Gitter Channel`_

.. _Galaxy Admins Gitter Channel: https://gitter.im/galaxyproject/admins
