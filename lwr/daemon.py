import logging
from logging.config import fileConfig

import os
import functools
import time
import sys
from six.moves import configparser

try:
    from daemonize import Daemonize
except ImportError:
    Daemonize = None

# Vaguely Python 2.6 compatibile ArgumentParser import
try:
    from argparser import ArgumentParser
except ImportError:
    from optparse import OptionParser

    class ArgumentParser(OptionParser):

        def __init__(self, **kwargs):
            self.delegate = OptionParser(**kwargs)

        def add_argument(self, *args, **kwargs):
            if "required" in kwargs:
                del kwargs["required"]
            return self.delegate.add_option(*args, **kwargs)

        def parse_args(self):
            (options, args) = self.delegate.parse_args()
            return options


from paste.deploy.loadwsgi import ConfigLoader

log = logging.getLogger(__name__)

LWR_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_PID = "lwr.pid"
DEFAULT_VERBOSE = True
DESCRIPTION = "Daemonized entry point for LWR services."


def load_lwr_app(
    config_builder,
    config_env=False,
    log=None,
    **kwds
):
    # Allow specification of log so daemon can reuse properly configured one.
    if log is None:
        log = logging.getLogger(__name__)

    # If called in daemon mode, set the ROOT directory and ensure LWR is on
    # sys.path.
    if config_env:
        try:
            os.chdir(LWR_ROOT_DIR)
        except Exception:
            log.exception("Failed to chdir")
            raise
        try:
            sys.path.append(os.path.join(LWR_ROOT_DIR))
        except Exception:
            log.exception("Failed to add LWR to sys.path")
            raise

    config_builder.setup_logging()
    config = config_builder.load()

    config.update(kwds)
    import lwr.core
    lwr_app = lwr.core.LwrApp(**config)
    return lwr_app


def __setup_logging(ini_path):
    raw_config = configparser.ConfigParser()
    raw_config.read([ini_path])
    # https://github.com/mozilla-services/chaussette/pull/32/files
    if raw_config.has_section('loggers'):
        config_file = os.path.abspath(ini_path)
        fileConfig(
            config_file,
            dict(__file__=config_file, here=os.path.dirname(config_file))
        )


def __app_config(ini_path, app_name):
    config = ConfigLoader(ini_path).app_context(app_name).config()
    return config


def app_loop(args):
    try:
        config_builder = LwrConfigBuilder(args)
        lwr_app = load_lwr_app(
            config_builder,
            config_env=True,
            log=log,
        )
    except BaseException:
        log.exception("Failed to initialize LWR application")
        raise
    try:
        # Hmmmm... not sure what to do in here this was example though...
        while True:
            time.sleep(5)
    except Exception:
        pass
    try:
        lwr_app.shutdown()
    except Exception:
        log.exception("Failed to shutdown LWR application")
        raise


class LwrConfigBuilder(object):
    """ Generate paste-like configuration from supplied command-line arguments.
    """

    def __init__(self, args=None, **kwds):
        ini_path = kwds.get("ini_path", None) or args.ini_path
        if ini_path is None:
            ini_path = "server.ini"
        if not os.path.isabs(ini_path):
            ini_path = os.path.join(LWR_ROOT_DIR, ini_path)

        self.ini_path = ini_path
        self.app_name = kwds.get("app") or args.app

    @classmethod
    def populate_options(clazz, arg_parser):
        arg_parser.add_argument("--ini_path", default=None)
        arg_parser.add_argument("--app", default="main")

    def load(self):
        ini_path = self.ini_path
        app_name = self.app_name
        config = ConfigLoader(ini_path).app_context(app_name).config()
        return config

    def setup_logging(self):
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
            ini_path=self.ini_path,
            app=self.app_name
        )


class LwrManagerConfigBuilder(LwrConfigBuilder):

    def __init__(self, args=None, **kwds):
        super(LwrManagerConfigBuilder, self).__init__(args=args, **kwds)
        self.manager = kwds.get("manager", None) or args.manager

    def to_dict(self):
        as_dict = super(LwrManagerConfigBuilder, self).to_dict()
        as_dict["manager"] = self.manager
        return as_dict

    @classmethod
    def populate_options(clazz, arg_parser):
        LwrConfigBuilder.populate_options(arg_parser)
        arg_parser.add_argument("--manager", default="_default_")


def main():
    if Daemonize is None:
        raise ImportError("Attempted to use LWR in daemon mode, but daemonize is unavailable.")

    arg_parser = ArgumentParser(description=DESCRIPTION)
    LwrConfigBuilder.populate_options(arg_parser)
    args = arg_parser.parse_args()

    log.setLevel(logging.DEBUG)
    log.propagate = False
    fh = logging.FileHandler("daemon.log", "w")
    fh.setLevel(logging.DEBUG)
    log.addHandler(fh)
    keep_fds = [fh.stream.fileno()]

    daemon = Daemonize(
        app="lwr",
        pid=DEFAULT_PID,
        action=functools.partial(app_loop, args),
        verbose=DEFAULT_VERBOSE,
        keep_fds=keep_fds,
    )
    daemon.start()

if __name__ == "__main__":
    main()
