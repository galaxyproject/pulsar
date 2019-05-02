"""Stand-alone entry point for running Pulsar without a web server.

In its simplest form, this method will check the current directory for an
app.yml and run the corresponding configuration as a standalone applciation.
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
"""
import logging
from logging.config import fileConfig

import os
import functools
import time
import sys
from six.moves import configparser

try:
    import yaml
except ImportError:
    yaml = None

try:
    from daemonize import Daemonize
except ImportError:
    Daemonize = None

from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter

log = logging.getLogger(__name__)

REQUIRES_DAEMONIZE_MESSAGE = "Attempted to use Pulsar in daemon mode, but daemonize is unavailable."

PULSAR_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if "PULSAR_CONFIG_DIR" in os.environ:
    PULSAR_CONFIG_DIR = os.path.abspath(os.environ["PULSAR_CONFIG_DIR"])
else:
    PULSAR_CONFIG_DIR = PULSAR_ROOT_DIR

DEFAULT_INI_APP = "main"
DEFAULT_INI = "server.ini"
DEFAULT_APP_YAML = "app.yml"
DEFAULT_MANAGER = "_default_"

DEFAULT_PID = "pulsar.pid"
DEFAULT_VERBOSE = True
HELP_CONFIG_DIR = "Default directory to search for relevant Pulsar configuration files (e.g. app.yml, server.ini)."
HELP_INI_PATH = "Specify an explicit path to Pulsar's server.ini configuration file."
HELP_APP_CONF_PATH = "Specify an explicit path to Pulsar's app.yml configuration file."
HELP_APP_CONF_BASE64 = "Specify an application configuration as a base64 encoded JSON blob."
HELP_DAEMONIZE = "Daemonzie process (requires daemonize library)."
CONFIG_PREFIX = "PULSAR_CONFIG_"


def load_pulsar_app(
    config_builder,
    config_env=False,
    log=None,
    **kwds
):
    # Allow specification of log so daemon can reuse properly configured one.
    if log is None:
        log = logging.getLogger(__name__)

    # If called in daemon mode, set the ROOT directory and ensure Pulsar is on
    # sys.path.
    if config_env:
        try:
            os.chdir(PULSAR_ROOT_DIR)
        except Exception:
            log.exception("Failed to chdir")
            raise
        try:
            sys.path.append(PULSAR_ROOT_DIR)
        except Exception:
            log.exception("Failed to add Pulsar to sys.path")
            raise

    config_builder.setup_logging()
    config = config_builder.load()

    config.update(kwds)
    import pulsar.core
    pulsar_app = pulsar.core.PulsarApp(**config)
    return pulsar_app


def app_loop(args, log):
    pulsar_app = _app(args, log)
    sleep = True
    while sleep:
        try:
            time.sleep(5)
        except KeyboardInterrupt:
            sleep = False
        except SystemExit:
            sleep = False
        except Exception:
            pass
    try:
        pulsar_app.shutdown()
    except Exception:
        log.exception("Failed to shutdown Pulsar application")
        raise


def _app(args, log):
    try:
        config_builder = PulsarConfigBuilder(args)
        pulsar_app = load_pulsar_app(
            config_builder,
            config_env=True,
            log=log,
        )
    except BaseException:
        log.exception("Failed to initialize Pulsar application")
        raise
    return pulsar_app


def absolute_config_path(path, config_dir):
    if path and not os.path.isabs(path):
        path = os.path.join(config_dir, path)
    return path


def _find_default_app_config(*config_dirs):
    for config_dir in config_dirs:
        app_config_path = os.path.join(config_dir, DEFAULT_APP_YAML)
        if os.path.exists(app_config_path):
            return app_config_path

    return None


def apply_env_overrides_and_defaults(conf):
    override_prefix = "%sOVERRIDE_" % CONFIG_PREFIX
    for key in os.environ:
        if key.startswith(override_prefix):
            config_key = key[len(override_prefix):].lower()
            conf[config_key] = os.environ[key]
        elif key.startswith(CONFIG_PREFIX):
            config_key = key[len(CONFIG_PREFIX):].lower()
            if config_key not in conf:
                conf[config_key] = os.environ[key]
    return conf


def load_app_configuration(ini_path=None, app_conf_path=None, app_name=None, local_conf=None, config_dir=PULSAR_CONFIG_DIR):
    """
    """
    if ini_path and local_conf is None:
        from pulsar.util.pastescript.loadwsgi import ConfigLoader
        local_conf = ConfigLoader(ini_path).app_context(app_name).config()
    local_conf = local_conf or {}
    if app_conf_path is None and "app_config" in local_conf:
        app_conf_path = absolute_config_path(local_conf["app_config"], config_dir)
        if not os.path.exists(app_conf_path) and os.path.exists(app_conf_path + ".sample"):
            app_conf_path = app_conf_path + ".sample"
    elif ini_path:
        # If not explicit app.yml file found - look next to server.ini -
        # be it in pulsar root, some temporary staging directory, or /etc.
        app_conf_path = _find_default_app_config(
            os.path.dirname(ini_path),
        )
    if app_conf_path:
        if yaml is None:
            raise Exception("Cannot load configuration from file %s, pyyaml is not available." % app_conf_path)

        with open(app_conf_path, "r") as f:
            app_conf = yaml.load(f) or {}
            local_conf.update(app_conf)

    return apply_env_overrides_and_defaults(local_conf)


def find_ini(supplied_ini, config_dir):
    if supplied_ini:
        return supplied_ini

    # If not explicitly supplied an ini, check server.ini and then
    # just resort to sample if that has not been configured.
    for guess in ["server.ini", "server.ini.sample"]:
        ini_path = os.path.join(config_dir, guess)
        if os.path.exists(ini_path):
            return ini_path

    return guess


class PulsarConfigBuilder(object):
    """ Generate paste-like configuration from supplied command-line arguments.
    """

    def __init__(self, args=None, **kwds):
        config_dir = kwds.get("config_dir", None) or PULSAR_CONFIG_DIR
        ini_path = kwds.get("ini_path", None) or (args and args.ini_path)
        app_conf_path = kwds.get("app_conf_path", None) or (args and args.app_conf_path)
        app_conf_base64 = args and args.app_conf_base64

        if not app_conf_base64 and not app_conf_path:
            # If given app_conf_path - use that - else we need to ensure we have an
            # ini path.
            ini_path = find_ini(ini_path, config_dir)
            ini_path = absolute_config_path(ini_path, config_dir=config_dir)
        self.config_dir = config_dir
        self.ini_path = ini_path
        self.app_conf_path = app_conf_path
        self.app_conf_base64 = app_conf_base64
        self.app_name = kwds.get("app") or (args and args.app) or DEFAULT_INI_APP

    @classmethod
    def populate_options(cls, arg_parser):
        arg_parser.add_argument("-c", "--config_dir", default=None, help=HELP_CONFIG_DIR)
        arg_parser.add_argument("--ini_path", default=None, help=HELP_INI_PATH)
        arg_parser.add_argument("--app_conf_path", default=None, help=HELP_APP_CONF_PATH)
        arg_parser.add_argument("--app_conf_base64", default=None, help=HELP_APP_CONF_BASE64)
        arg_parser.add_argument("--app", default=DEFAULT_INI_APP)
        # daemon related options...
        arg_parser.add_argument("-d", "--daemonize", default=False, help=HELP_DAEMONIZE, action="store_true")
        arg_parser.add_argument("--daemon-log-file", default=None, help="Log file for daemon, if --daemonize supplied.")
        arg_parser.add_argument("--pid-file", default=DEFAULT_PID, help="Pid file for daemon, if --daemonize supplied (default is %s)." % DEFAULT_PID)

    def load(self):
        load_kwds = dict(
            app_name=self.app_name
        )
        if self.app_conf_base64:
            from pulsar.client.util import from_base64_json
            local_conf = from_base64_json(self.app_conf_base64)
            load_kwds["local_conf"] = local_conf
        else:
            load_kwds.update(dict(
                config_dir=self.config_dir,
                ini_path=self.ini_path,
                app_conf_path=self.app_conf_path,
            ))
        return load_app_configuration(**load_kwds)

    def setup_logging(self):
        if not self.ini_path:
            # TODO: should be possible can configure using dict.
            return
        raw_config = configparser.ConfigParser()
        raw_config.read([self.ini_path])
        # https://github.com/mozilla-services/chaussette/pull/32/files
        if raw_config.has_section('loggers'):
            config_file = os.path.abspath(self.ini_path)
            fileConfig(
                config_file,
                dict(__file__=config_file, here=os.path.dirname(config_file))
            )

    def to_dict(self):
        return dict(
            config_dir=self.config_dir,
            ini_path=self.ini_path,
            app_conf_path=self.app_conf_path,
            app=self.app_name
        )


class PulsarManagerConfigBuilder(PulsarConfigBuilder):

    def __init__(self, args=None, **kwds):
        super(PulsarManagerConfigBuilder, self).__init__(args=args, **kwds)
        self.manager = kwds.get("manager", None) or (args and args.manager) or DEFAULT_MANAGER

    def to_dict(self):
        as_dict = super(PulsarManagerConfigBuilder, self).to_dict()
        as_dict["manager"] = self.manager
        return as_dict

    @classmethod
    def populate_options(cls, arg_parser):
        PulsarConfigBuilder.populate_options(arg_parser)
        arg_parser.add_argument("--manager", default=DEFAULT_MANAGER)


def main(argv=None):
    mod_docstring = sys.modules[__name__].__doc__
    arg_parser = ArgumentParser(
        description=mod_docstring,
        formatter_class=RawDescriptionHelpFormatter,
    )
    PulsarConfigBuilder.populate_options(arg_parser)
    args = arg_parser.parse_args(argv)

    pid_file = args.pid_file

    log.setLevel(logging.DEBUG)
    log.propagate = False

    if args.daemonize:
        if Daemonize is None:
            raise ImportError(REQUIRES_DAEMONIZE_MESSAGE)

        keep_fds = []
        if args.daemon_log_file:
            fh = logging.FileHandler(args.daemon_log_file, "w")
            fh.setLevel(logging.DEBUG)
            log.addHandler(fh)
            keep_fds.append(fh.stream.fileno())
        else:
            fh = logging.StreamHandler(sys.stderr)
            fh.setLevel(logging.DEBUG)
            log.addHandler(fh)

        daemon = Daemonize(
            app="pulsar",
            pid=pid_file,
            action=functools.partial(app_loop, args, log),
            verbose=DEFAULT_VERBOSE,
            logger=log,
            keep_fds=keep_fds,
        )
        daemon.start()
    else:
        app_loop(args, log)


if __name__ == "__main__":
    main()
