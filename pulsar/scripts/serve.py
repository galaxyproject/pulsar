#!/usr/bin/env python
"""Launch Pulsar using gunicorn as the WSGI server.

Reads server configuration from a server.ini file and starts
a gunicorn worker serving the Pulsar WSGI application.
"""

import argparse
import configparser
import os
import signal
import ssl
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description="Serve Pulsar with gunicorn.")
    parser.add_argument("config_file", nargs="?", default=None,
                        help="Path to server.ini configuration file (default: auto-detect)")
    parser.add_argument("--daemon", action="store_true", default=False,
                        help="Run as a daemon process")
    parser.add_argument("--pid", default=None,
                        help="Path to PID file (default: pulsar.pid when daemonized)")
    parser.add_argument("--log-file", default=None,
                        help="Path to log file (default: pulsar.log when daemonized)")
    parser.add_argument("--stop-daemon", action="store_true", default=False,
                        help="Stop a running daemon by reading the PID file")
    args = parser.parse_args(argv)

    config_file = args.config_file
    if config_file is None:
        config_file = _find_config_file()
    if not os.path.isabs(config_file):
        config_file = os.path.abspath(config_file)

    pid_file = args.pid
    log_file = args.log_file

    if args.stop_daemon:
        return _stop_daemon(pid_file or "pulsar.pid")

    # Read server settings from INI
    host, port, ssl_pem = _read_server_config(config_file)

    if args.daemon:
        if pid_file is None:
            pid_file = "pulsar.pid"
        if log_file is None:
            log_file = "pulsar.log"

    _run_gunicorn(config_file, host, port, ssl_pem, args.daemon, pid_file, log_file)


def _find_config_file():
    """Find server.ini, checking PULSAR_CONFIG_DIR then current directory."""
    config_dir = os.environ.get("PULSAR_CONFIG_DIR", ".")
    candidates = [
        os.path.join(config_dir, "server.ini"),
        "server.ini",
        "server.ini.sample",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return "server.ini"


def _read_server_config(config_file):
    """Read host, port, and ssl_pem from [server:main] in the INI file."""
    config = configparser.ConfigParser()
    config.read(config_file)

    section = "server:main"
    host = "localhost"
    port = "8913"
    ssl_pem = None

    if config.has_section(section):
        host = config.get(section, "host", fallback=host)
        port = config.get(section, "port", fallback=port)
        ssl_pem = config.get(section, "ssl_pem", fallback=None)

    return host, port, ssl_pem


def _stop_daemon(pid_file):
    """Stop a daemonized pulsar-serve process."""
    if not os.path.exists(pid_file):
        print("No PID file found at %s" % pid_file, file=sys.stderr)
        return 1

    with open(pid_file) as f:
        pid = int(f.read().strip())

    try:
        os.kill(pid, signal.SIGTERM)
        print("Sent SIGTERM to process %d" % pid)
    except ProcessLookupError:
        print("Process %d not found, removing stale PID file" % pid, file=sys.stderr)
    except PermissionError:
        print("Permission denied sending signal to process %d" % pid, file=sys.stderr)
        return 1

    try:
        os.remove(pid_file)
    except OSError:
        pass

    return 0


def _run_gunicorn(config_file, host, port, ssl_pem, daemon, pid_file, log_file):
    """Start gunicorn with the Pulsar WSGI app."""
    try:
        from gunicorn.app.base import BaseApplication
    except ImportError:
        print("gunicorn is not installed. Install it with: pip install 'pulsar-app[web]'",
              file=sys.stderr)
        sys.exit(1)

    # Set PULSAR_CONFIG_FILE so init_webapp can find it
    os.environ["PULSAR_CONFIG_FILE"] = config_file

    # On macOS, Objective-C runtime crashes when fork() is called after
    # certain frameworks are initialized. This is the standard workaround.
    if sys.platform == "darwin":
        os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

    bind = "%s:%s" % (host, port)

    options = {
        "bind": bind,
        "workers": 1,
        "threads": 4,
        "worker_class": "gthread",
    }

    if daemon:
        options["daemon"] = True
    if pid_file:
        options["pidfile"] = pid_file
    if log_file:
        options["errorlog"] = log_file
        options["accesslog"] = log_file

    if ssl_pem:
        if os.path.exists(ssl_pem):
            options["certfile"] = ssl_pem
            options["keyfile"] = ssl_pem
            options["ssl_version"] = ssl.PROTOCOL_TLS

    class PulsarApplication(BaseApplication):
        def __init__(self, options=None):
            self.options = options or {}
            super().__init__()

        def load_config(self):
            for key, value in self.options.items():
                if key in self.cfg.settings and value is not None:
                    self.cfg.set(key.lower(), value)

        def load(self):
            from pulsar.web.wsgi import init_webapp
            config_dir = os.path.dirname(os.path.abspath(config_file))
            return init_webapp(ini_path=config_file, config_dir=config_dir)

    print("Starting Pulsar on %s" % bind)
    PulsarApplication(options).run()


if __name__ == "__main__":
    main()
