.. figure:: https://wiki.galaxyproject.org/Images/GalaxyLogos?action=AttachFile&do=get&target=pulsar_transparent.png
   :alt: Pulsar Logo

.. image:: https://readthedocs.org/projects/pip/badge/?version=latest
        :target: https://pulsar.readthedocs.org.
.. image:: https://travis-ci.org/galaxyproject/pulsar.png?branch=master
        :target: https://travis-ci.org/galaxyproject/pulsar
.. image:: https://coveralls.io/repos/galaxyproject/pulsar/badge.png?branch=master
        :target: https://coveralls.io/r/galaxyproject/pulsar?branch=master

This project is a Python server application that allows a `Galaxy
<http://galaxyproject.org>`_ server to run jobs on remote systems (including
Windows) without requiring a shared mounted file systems. Unlike traditional
Galaxy job runners - input files, scripts, and config files may be transferred
to the remote system, the job is executed, and the results are transfered back
to the Galaxy server - eliminating the need for a shared file system.

Full documentation for the project can be found on `Read The Docs
<https://pulsar.readthedocs.org/>`_.

------------------
Configuring Galaxy
------------------

Galaxy job runners are configured in Galaxy's ``job_conf.xml`` file. Some small
examples of how to configure this can be found `here
<https://pulsar.readthedocs.org/en/latest/galaxy_conf.html>`__, but be sure
to checkout ``job_conf.xml.sample_advanced`` in your Galaxy code base or on
`Github
<https://github.com/galaxyproject/galaxy/blob/master/config/job_conf.xml.sample_advanced>`_
for complete information.

------------------
Quickstart
------------------

Full details on different ways to install Pulsar can be found in the `install
section <https://pulsar.readthedocs.org/en/latest/install.html>`__ of the
documentaiton, but if your machine has the proper Python dependencies
available it can be quickly download and a test job run with.

::

    mkdir pulsar
    cd pulsar
    virtualenv venv
    . venv/bin/activate # .venv\Scripts\activate if Windows
    pip install pulsar-app
    pulsar-config 
    pulsar --daemon # just pulsar if Windows
    pulsar-check # runs a test job

The `configuration documentation
<https://pulsar.readthedocs.org/en/latest/configure.html>`__
has many details on securing your Pulsar server and enabling advanced features
such as cluster integration and message queue communication.

-----------------------
Development and Testing
-----------------------

The recommended approach to setting up a development environment for Pulsar on
Linux or Mac OS X is rougly as follows::

    git clone https://github.com/galaxyproject/pulsar
    cd pulsar
    virtualenv .venv
    . .venv/bin/activate # .venv\Scripts\activate if Windows
    pip install -r requirements.txt
    pip install -r dev-requirements.txt

This project is distributed with unit and integration tests (many of which
will not run under Windows), the following command will install the needed
python components to run these tests. The following command will then run
these tests::

    make tests

The following command will then produce a coverage report
corresponding to this test and place it in the ``coverage_html_report``
subdirectory of this project.::

    coverage html

Checkout the `Contributing
<https://pulsar.readthedocs.org/en/latest/contributing.html>`_ documentation
for many more details on developing and contributing to Pulsar.

Please note that this project is released with a `Contributor Code of Conduct 
<https://pulsar.readthedocs.org/en/latest/conduct.html>`__. By participating
in this project you agree to abide by its terms.
