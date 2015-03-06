#!/usr/bin/env python
from __future__ import print_function

import os
import string
import sys

from pulsar.main import (
    ArgumentParser,
    DEFAULT_APP_YAML,
    DEFAULT_INI
)

DESCRIPTION = "Initialize a directory with a minimal pulsar config."
HELP_DIRECTORY = "Directory containing the configuration files for Pulsar."
HELP_MQ = ("Write configuration files for message queue server deployment "
           "instead of more traditional RESTful web based pulsar.")
HELP_SUPERVISOR = ("Write a supervisord configuration file for "
                   "managing pulsar out as well.")
HELP_FORCE = "Overwrite existing files if they already exist."
HELP_WSGI_SERVER = ("Web server stack used to host Pulsar wsgi application.")
HELP_LIBDRMAA = ("Configure Pulsar to submit jobs to a cluster via DRMAA by "
                 "supplying the path to a libdrmaa .so file using this argument.")
HELP_INSTALL = ("Install optional dependencies required by specified configuration "
                "(e.g. drmaa, supervisor, uwsgi, etc...).")
HELP_HOST = ("Host to bind Pulsar to - defaults to localhost. Set to 0.0.0.0 "
             "to listen on all interfaces.")
HELP_PORT = ("Port to bind Pulsar to (ignored if --mq is specified).")


LOGGING_CONFIG_SECTIONS = """## Configure Python loggers.
[loggers]
keys = root,pulsar

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = INFO
handlers = console

[logger_pulsar]
level = DEBUG
handlers = console
qualname = pulsar
propagate = 0

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = DEBUG
formatter = generic

[formatter_generic]
format = %(asctime)s %(levelname)-5.5s [%(name)s][%(threadName)s] %(message)s
"""

SUPERVISOR_CONFIG_TEMPLATE = string.Template("""[program:pulsar]
user            = ${user}
directory       = ${directory}
command         = pulsar --mode '${mode}' --config '${directory}'
redirect_stderr = true
autorestart     = true
""")

SERVER_CONFIG_TEMPLATE = string.Template("""[server:main]
use = egg:Paste#http
port = ${port}
host = ${host}
## pem file to use to enable SSL.
# ssl_pem = host.pem

[app:main]
paste.app_factory = pulsar.web.wsgi:app_factory
app_config = %(here)s/app.yml

## Configure uWSGI (if used).
[uwsgi]
master = True
paste-logger = ${use_logging}
socket = ${host}:3031
processes = 1
enable-threads = True


## Configure circus and chaussette (if used).
[circus]
endpoint = tcp://127.0.0.1:5555
pubsub_endpoint = tcp://127.0.0.1:5556
#stats_endpoint = tcp://127.0.0.1:5557

[watcher:web]
cmd = chaussette --fd $(circus.sockets.web) paste:server.ini
use_sockets = True
# Pulsar must be single-process for now...
numprocesses = 1

[socket:web]
host = ${host}
port = ${port}

${logging_sections}
""")

LOCAL_ENV_TEMPLATE = string.Template("""## Place local configuration variables used by Pulsar and run.sh in here. For example

## If using the drmaa queue manager, you will need to set the DRMAA_LIBRARY_PATH variable,
## you may also need to update LD_LIBRARY_PATH for underlying library as well.
$libdrmaa_line


## If you wish to use a variety of Galaxy tools that depend on galaxy.eggs being defined,
## set GALAXY_HOME to point to a copy of Galaxy.
#export GALAXY_HOME=/path/to/galaxy-dist
""")


def main(argv=None):
    if argv is None:
        argv = sys.argv
    dependencies = []
    arg_parser = ArgumentParser(description=DESCRIPTION)
    arg_parser.add_argument("--directory",
                            default=".",
                            help=HELP_DIRECTORY)
    arg_parser.add_argument("--mq",
                            action="store_true",
                            default=False,
                            help=HELP_MQ)
    arg_parser.add_argument("--no_logging",
                            dest="logging",
                            action="store_false",
                            default=True,
                            help=HELP_MQ)
    arg_parser.add_argument("--supervisor",
                            action="store_true",
                            default=False,
                            help=HELP_SUPERVISOR)
    arg_parser.add_argument("--wsgi_server",
                            choices=["paste", "uwsgi"],
                            default=None,
                            help=HELP_WSGI_SERVER)
    arg_parser.add_argument("--libdrmaa_path",
                            help=HELP_LIBDRMAA)
    arg_parser.add_argument("--host",
                            default="localhost",
                            help=HELP_HOST)
    arg_parser.add_argument("--port",
                            default="8913",
                            help=HELP_PORT)
    arg_parser.add_argument("--install",
                            help=HELP_INSTALL)
    arg_parser.add_argument("--force",
                            action="store_true",
                            default=False,
                            help=HELP_FORCE)
    args = arg_parser.parse_args(argv)
    directory = args.directory
    directory = os.path.abspath(directory)

    mode = _determine_mode(args)
    if mode == "uwsgi":
        dependencies.append("uwsgi")

    if not os.path.exists(directory):
        os.makedirs(directory)

    _handle_app_yaml(args, directory)
    _handle_server_ini(args, directory)
    _handle_local_env(args, directory, dependencies)
    _handle_supervisor(args, mode, directory, dependencies)
    _handle_install(args, dependencies)


def _determine_mode(args):
    if args.wsgi_server:
        mode = args.wsgi_server
    elif args.mq:
        mode = "webless"
    else:
        mode = "paster"
    return mode


def _handle_server_ini(args, directory):
    force = args.force
    ini_file = os.path.join(directory, DEFAULT_INI)
    if not args.mq:
        _check_file(ini_file, force)
        config_dict = dict(
            port=args.port,
            host=args.host,
        )
        if args.logging:
            config_dict["logging_sections"] = LOGGING_CONFIG_SECTIONS
            config_dict["use_logging"] = "true"
        else:
            config_dict["logging_sections"] = ""
            config_dict["use_logging"] = "false"

        server_config = SERVER_CONFIG_TEMPLATE.safe_substitute(
            **config_dict
        )
        open(ini_file, "w").write(server_config)


def _handle_app_yaml(args, directory):
    force = args.force
    yaml_file = os.path.join(directory, DEFAULT_APP_YAML)
    _check_file(yaml_file, force)
    contents = "---\n"
    if args.mq:
        contents += 'message_queue_url: "amqp://guest:guest@localhost:5672//"\n'
    else:
        if args.libdrmaa_path:
            contents += 'manager:\n  type: queued_drmaa\n'
    open(yaml_file, "w").write(contents)


def _handle_local_env(args, directory, dependencies):
    local_env_file = os.path.join(directory, "local_env.sh")
    if args.libdrmaa_path:
        libdrmaa_line = 'export DRMAA_LIBRARY_PATH=%s' % args.libdrmaa_path
        os.environ["DRMAA_LIBRARY_PATH"] = args.libdrmaa_path
        dependencies.append("drmaa")
    else:
        libdrmaa_line = '#export DRMAA_LIBRARY_PATH=/path/to/libdrmaa.so'

    local_env_contents = LOCAL_ENV_TEMPLATE.safe_substitute(
        libdrmaa_line=libdrmaa_line,
    )
    open(local_env_file, "w").write(local_env_contents)


def _handle_supervisor(args, mode, directory, dependencies):
    if args.supervisor:
        template = SUPERVISOR_CONFIG_TEMPLATE
        config = template.safe_substitute(
            user=os.environ["USER"],
            directory=directory,
            mode=mode,
        )
        conf_path = os.path.join(directory, "supervisor.conf")
        open(conf_path, "w").write(config)
        dependencies.append("supervisor")


def _handle_install(args, dependencies):
    if args.install and dependencies:
        import pip
        pip.main("install", *dependencies)


def _check_file(path, force):
    if os.path.exists(path) and not force:
        print("File %s exists, exiting." % path, file=sys.stderr)
        sys.exit(1)
