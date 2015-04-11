
``${script}``
======================================

**Usage**::

    pulsar-config [options]

**Help**


Initialize a directory with a minimal pulsar config.

**Options**::


      -h, --help            show this help message and exit
      --directory=DIRECTORY
                            Directory containing the configuration files for
                            Pulsar.
      --mq                  Write configuration files for message queue server
                            deployment instead of more traditional RESTful web
                            based pulsar.
      --no_logging          Do not write Pulsar's default logging configuration to
                            server.ini and if uwsgi is configured do not configure
                            its logging either.
      --supervisor          Write a supervisord configuration file for managing
                            pulsar out as well.
      --wsgi_server=WSGI_SERVER
                            Web server stack used to host Pulsar wsgi application.
      --libdrmaa_path=LIBDRMAA_PATH
                            Configure Pulsar to submit jobs to a cluster via DRMAA
                            by supplying the path to a libdrmaa .so file using
                            this argument.
      --host=HOST           Host to bind Pulsar to - defaults to localhost.
                            Specify 0.0.0.0 to listen on all interfaces.
      --private_token=PRIVATE_TOKEN
                            Private token used to authorize clients. If Pulsar is
                            not protected via firewall, this should be specified
                            and SSL should be enabled. See https://pulsar.readthed
                            ocs.org/en/latest/configure.html for more information
                            on security.
      --port=PORT           Port to bind Pulsar to (ignored if --mq is specified).
      --install             Install optional dependencies required by specified
                            configuration (e.g. drmaa, supervisor, uwsgi, etc...).
      --force               Overwrite existing files if they already exist.
    
