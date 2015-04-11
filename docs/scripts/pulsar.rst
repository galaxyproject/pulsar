
``pulsar`` (\*nix)
======================================

Installing Pulsar will install the ``pulsar`` script. It is a lightweight
wrapper abstracting out a few different ways to run Pulsar. Pulsar can easily
be run inside a variety wsgi servers or stand-alone without a web server using
``pulsar-main`` - the ``pulsar`` script shouldn't be considered a best
practice - it merely provides a minimal level of convenience that may be
useful in some deployment scenarios.

Very simply, ``pulsar`` will source ``local_env.sh`` if it is present (to
configure things like ``DRMAA_LIBRARY_PATH``) and then determine which
external application to use to run Pulsar (either a WSGI_ server or ``pulsar-
main``) and delegate to that method.

``pulsar`` can be passed the ``--mode`` argument to explicitly describe which
application should be used to run Pulsar. If ``--mode`` unspecified,
``pulsar``  will check the ``PATH`` and launch look for (in order) ``uwsgi``,
``circusd``, ``chaussette``, and finally ``paster`` to determine which mode to
use.

------------------------
``paster`` mode
------------------------

Paste_ is installed with Pulsar and so is the fallback mode if none of the
other web servers is available.

In this mode, Pulsar can be launched using the command::

    pulsar

This will run the server in your terminal (not as a daemon) and the server
will run as long as this command is running. To run Pulsar as a daemon, use
the command::

    pulsar --daemon

This will run Pulsar in daemon mode (i.e. run in the background). In daemon
mode, paster creates a pid file in the current directory called ``paster.pid``
and a log file ``paster.log``. The daemon can be stopped using the command::

    pulsar --stop-daemon

------------------------
``webless`` mode
------------------------

This mode can be used to launch Pulsar without a web server. This only makes
sense if a ``message_queue_url`` is defined in ``app.yml`` and the client (e.g
Galaxy) configures all staging to be triggered remotely (this is the default for the Galaxy job runner ``galaxy.jobs.runners.pulsar:PulsarMQJobRunner``).

See the documentation for the ``pulsar-main`` for the arguments that may be
supplied to ``pulsar`` in this mode.

------------------------
Other Modes
------------------------

``pulsar-config`` will configure sections in ``server.ini`` that allow Pulsar
to be launched using uWSGI_, Cirucs_, and Chaussette_. ``pulsar`` will launch
these servers when ``--mode`` is specified as ``uwsgi``, ``circus``,
``chaussette`` respectively.

See the documentation for the respective application for a full description of
the arguments that can be used to configure that web server. Presumably each
of these servers is more performant and better maintained than Paste_ but
Paste_ is cross-platform and makes it trivial to configure SSL and so it
remains the default for Pulsar for now.

``pulsar`` (Windows)
======================================

``pulsar`` is a lightweight wrapper around ``paster serve`` (see `docs
<http://pythonpaste.org/script/#paster-serve>`__). It will check the current
directory for a ``server.ini`` file and launch the described Pulsar server using Paste_.


.. _Paste: http://pythonpaste.org/
.. _WSGI: http://en.wikipedia.org/wiki/Web_Server_Gateway_Interface
.. _Cirucs: http://circus.readthedocs.org/
.. _Chaussette: https://chaussette.readthedocs.org/
.. _uWSGI: https://uwsgi-docs.readthedocs.org/


	