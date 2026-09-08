
``pulsar-main``
======================================

**Usage**::

    pulsar-main [-h] [-c CONFIG_DIR] [--ini_path INI_PATH]
                [--app_conf_path APP_CONF_PATH]
                [--app_conf_base64 APP_CONF_BASE64] [--app APP] [-d]
                [--log-file DAEMON_LOG_FILE] [--pid PID_FILE] [--stop-daemon]

**Help**

Stand-alone entry point for running Pulsar without a web server.

In its simplest form, this method will check the current directory for an
app.yml and run the corresponding configuration as a standalone application.
This makes sense when ``app.yml`` contains a ``message_queue_url`` option so
Pulsar is configured to listen to a message queue and doesn't require a web
server.

The following commands can be used to bootstrap such a setup.::

    mkdir pulsar-mq-config
    cd pulsar-mq-config
    pulsar-config --mq
    pulsar-main

This script can be used in a standalone fashion, but it is generally better to
run the ``pulsar`` script with ``--mode webless`` - which will in turn
delegate to this script.

**Options**::


      -h, --help            show this help message and exit
      -c CONFIG_DIR, --config_dir CONFIG_DIR
                            Default directory to search for relevant Pulsar
                            configuration files (e.g. app.yml, server.ini).
      --ini_path INI_PATH   Specify an explicit path to Pulsar's server.ini
                            configuration file.
      --app_conf_path APP_CONF_PATH
                            Specify an explicit path to Pulsar's app.yml
                            configuration file.
      --app_conf_base64 APP_CONF_BASE64
                            Specify an application configuration as a base64
                            encoded JSON blob.
      --app APP
      -d, --daemon, --daemonize
                            Run as a daemon process.
      --log-file, --daemon-log-file DAEMON_LOG_FILE
                            Log file for daemon (default is pulsar.log).
      --pid, --pid-file PID_FILE
                            Pid file for daemon (default is pulsar.pid).
      --stop-daemon         Stop a running daemon by reading the PID file.
