============
Contributing
============

Please note that this project is released with a `Contributor Code of Conduct
<https://pulsar.readthedocs.org/en/latest/conduct.html>`. By participating in
this project you agree to abide by its terms.

Contributions are welcome, and they are greatly appreciated! Every
little bit helps, and credit will always be given.

You can contribute in many ways:

Types of Contributions
----------------------

Report Bugs
~~~~~~~~~~~

Report bugs at https://github.com/galaxyproject/pulsar/issues.

If you are reporting a bug, please include:

* Your operating system name and version, versions of other relevant software 
  such as Galaxy or Docker.
* Links to relevant tools.
* Any details about your local setup that might be helpful in troubleshooting.
* Detailed steps to reproduce the bug.

Fix Bugs
~~~~~~~~

Look through the GitHub issues for bugs. Most things there are up for grabs
but the tag "Help Wanted" may be particulary good places to start.

Implement Features
~~~~~~~~~~~~~~~~~~

Look through the GitHub issues for features (tagged with "enhancement").
Again, most things there are up for grabs but the tag "Help Wanted" may be
particulary good places to start.

Write Documentation
~~~~~~~~~~~~~~~~~~~

Pulsar is cronically under documented, whether as part of the
official Pulsar docs, in docstrings, or even on the web in blog posts,
articles, and such.

Submit Feedback
~~~~~~~~~~~~~~~

The best way to send feedback is to file an issue at https://github.com/galaxyproject/pulsar/issues.

If you are proposing a feature:

* Explain in detail how it would work.
* Keep the scope as narrow as possible, to make it easier to implement.
* This will hopefully become a community-driven project and contributions
  are welcome :)

Get Started!
------------

Ready to contribute? Here's how to set up `pulsar` for local development.

1. Fork the `pulsar` repo on GitHub.
2. Clone your fork locally::

    $ git clone git@github.com:your_name_here/pulsar.git

3. Install your local copy into a virtualenv. Assuming you have ``virtualenv`` installed, this is how you set up your fork for local development::

    $ cd pulsar/
    $ virtualenv .venv
    $ . .venv/bin/activate
    $ pip install -r requirements.txt 
    $ pip install -r dev-requirements.txt

   If you have something like Slurm or Grid Engine configured on your local machine - you should also install ``drmaa`` with ``pip install drmaa``.

4. Create a branch for local development::

    $ git checkout -b name-of-your-bugfix-or-feature

   Now you can make your changes locally.

5. When you're done making changes, check that your changes lint::

    $ make lint

and ensure the tests look good. The easiest way to test is with Docker if it is
available (given the need to test commands with DRMAA, condor, sudo, etc...).::

    $ docker run -v `pwd`:/pulsar -t jmchilton/pulsar_testing

This will mount your copy of `pulsar` in a Docker container preconfigured with all
optional dependencies needed to run a wide range of integration tests. If Docker
is to much of an ordeal many of Pulsar's tests can be executed by simply running 
``nosetests`` from within an ``virtualenv`` configured as explained above.::

    $ make tests

6. Commit your changes and push your branch to GitHub::

    $ git add .
    $ git commit -m "Your detailed description of your changes."
    $ git push origin name-of-your-bugfix-or-feature

7. Submit a pull request through the GitHub website.

Pull Request Guidelines
-----------------------

Before you submit a pull request, check that it meets these guidelines:

1. If the pull request adds functionality, the docs should ideally be updated.
   Put your new functionality into a function with a docstring. (Until the
   @jmchilton learns to do this consistently this is only a suggestion though.)
2. The pull request should work for Python 2.6, 2.7, and 3.4. Check
   https://travis-ci.org/galaxyproject/planemo/pull_requests
   and make sure that the tests pass for all supported Python versions. The
   tests are imperfect and Travis sometimes fails in a transient fashion so
   this also isn't strictly required to pass.
