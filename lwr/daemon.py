import logging
from logging.config import fileConfig

import os
import time
import sys
from six.moves import configparser

try:
    from daemonize import Daemonize
except ImportError:
    Daemonize = None

from paste.deploy.loadwsgi import ConfigLoader

logger = logging.getLogger(__name__)

LWR_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_PID = "lwr.pid"
DEFAULT_VERBOSE = True


def paste_like_app(ini_path="server.ini", app_name="main"):
    if not os.path.isabs(ini_path):
        ini_path = os.path.join(LWR_ROOT_DIR, ini_path)

    raw_config = configparser.ConfigParser()
    raw_config.read([ini_path])
    # https://github.com/mozilla-services/chaussette/pull/32/files
    if raw_config.has_section('loggers'):
        config_file = os.path.abspath(ini_path)
        fileConfig(
            config_file,
            dict(__file__=config_file, here=os.path.dirname(config_file))
        )

    config = ConfigLoader(ini_path).app_context(app_name).config()
    import lwr.core
    lwr_app = lwr.core.LwrApp(**config)
    return lwr_app


def app_loop():
    try:
        os.chdir(LWR_ROOT_DIR)
    except Exception:
        logger.exception("Failed to chdir")
        raise
    try:
        sys.path.append(os.path.join(LWR_ROOT_DIR))
    except Exception:
        logger.exception("Failed to add LWR to sys.path")
        raise
    try:
        lwr_app = paste_like_app()
    except BaseException:
        logger.exception("Failed to initialize LWR application")
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
        logger.exception("Failed to shutdown LWR application")
        raise


def main():
    if Daemonize is None:
        raise ImportError("Attempted to use LWR in daemon mode, but daemonize is unavailable.")

    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    fh = logging.FileHandler("daemon.log", "w")
    fh.setLevel(logging.DEBUG)
    logger.addHandler(fh)
    keep_fds = [fh.stream.fileno()]

    daemon = Daemonize(
        app="lwr",
        pid=DEFAULT_PID,
        action=app_loop,
        verbose=DEFAULT_VERBOSE,
        keep_fds=keep_fds,
    )
    daemon.start()

if __name__ == "__main__":
    main()
