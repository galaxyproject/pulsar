#!/usr/bin/env python
from __future__ import print_function

import os
import sys

from pulsar.main import (
    ArgumentParser,
    DEFAULT_APP_YAML,
    DEFAULT_INI
)

DESCRIPTION = "Initialize a directory with a minimal pulsar config."


def main():
    arg_parser = ArgumentParser(description=DESCRIPTION)
    arg_parser.add_argument("--directory", default=".")
    arg_parser.add_argument("--mq",
                            action="store_true",
                            default=False,
                            help=("Write configuration files for message queue "
                                  "instead of web based pulsar."))
    arg_parser.add_argument("--force",
                            action="store_true",
                            default=False,
                            help="Overwrite existing files.")
    args = arg_parser.parse_args()
    directory = args.directory
    force = args.force
    directory = os.path.abspath(directory)

    if not os.path.exists(directory):
        os.makedirs(directory)

    yaml_file = os.path.join(directory, DEFAULT_APP_YAML)
    check_file(yaml_file, force)
    if args.mq:
        open(yaml_file, "w").write("""---
message_queue_url: "amqp://guest:guest@localhost:5672//"
""")
    else:
        open(yaml_file, "w").write("""---""")

    ini_file = os.path.join(directory, DEFAULT_INI)
    if not args.mq:
        check_file(ini_file, force)
        open(ini_file, "w").write("""[server:main]
use = egg:Paste#http

[app:main]
paste.app_factory = pulsar.web.wsgi:app_factory
app_config = %(here)s/app.yml

## Configure uWSGI (if used).
[uwsgi]
master = True
paste-logger = True
socket = 127.0.0.1:3031
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
host = localhost
port = 8913

## Configure Python loggers.
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
""")

    local_env_file = os.path.join(directory, "local_env.sh")
    open(local_env_file, "w").write("""## Place local configuration variables used by Pulsar and run.sh in here. For example

## If using the drmaa queue manager, you will need to set the DRMAA_LIBRARY_PATH variable,
## you may also need to update LD_LIBRARY_PATH for underlying library as well.
#export DRMAA_LIBRARY_PATH=/path/to/libdrmaa.so


## If you wish to use a variety of Galaxy tools that depend on galaxy.eggs being defined,
## set GALAXY_HOME to point to a copy of Galaxy.
#export GALAXY_HOME=/path/to/galaxy-dist
""")


def check_file(path, force):
    if os.path.exists(path) and not force:
        print("File %s exists, exiting." % path, file=sys.stderr)
        sys.exit(1)
