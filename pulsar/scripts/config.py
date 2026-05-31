#!/usr/bin/env python

import os
import string
import sys

from pulsar.client.galaxy_byoc import (
    GalaxyBYOCRegistrationError,
    register_with_galaxy,
)
from pulsar.main import (
    ArgumentParser,
    DEFAULT_APP_YAML,
    DEFAULT_INI,
)

try:
    import pip  # type: ignore[import-not-found,unused-ignore]
except ImportError:
    pip = None  # type: ignore

try:
    import virtualenv
except ImportError:
    virtualenv = None

IS_WINDOWS = os.environ.get("MOCK_WINDOWS", None) or sys.platform.startswith('win')

CONFIGURE_URL = "https://pulsar.readthedocs.org/en/latest/configure.html"

DESCRIPTION = "Initialize a directory with a minimal pulsar config."
HELP_DIRECTORY = "Directory containing the configuration files for Pulsar."
HELP_MQ = ("Write configuration files for message queue server deployment "
           "instead of more traditional RESTful web based pulsar.")
HELP_AUTO_CONDA = ("Auto initialize Conda for tool resolution and auto install "
                   "dependencies on demand.")
HELP_NO_LOGGING = ("Do not write Pulsar's default logging configuration to server.ini "
                   "and if uwsgi is configured do not configure its logging either.")
HELP_SUPERVISOR = ("Write a supervisord configuration file for "
                   "managing pulsar out as well.")
HELP_FORCE = "Overwrite existing files if they already exist."
HELP_WSGI_SERVER = ("Web server stack used to host Pulsar wsgi application.")
HELP_LIBDRMAA = ("Configure Pulsar to submit jobs to a cluster via DRMAA by "
                 "supplying the path to a libdrmaa .so file using this argument.")
HELP_INSTALL = ("Install optional dependencies required by specified configuration "
                "(e.g. drmaa, supervisor, uwsgi, etc...).")
HELP_LOGIN = ("Scaffold a relay-flavoured config directory (app.yml, "
              "local_env.sh, ...) and bootstrap pulsar-relay credentials via "
              "the device-authorization flow. Implies --mq. Refuses to "
              "overwrite an existing app.yml without --force; if you already "
              "have a config and only want the credentials file, use "
              "--login-only.")
HELP_LOGIN_ONLY = ("Bootstrap pulsar-relay credentials via the device-"
                   "authorization flow only — do not write or modify "
                   "app.yml. Use this when you already have a relay config.")
HELP_RELAY_URL = ("Base URL of the pulsar-relay server. Required with --login "
                  "or --login-only; also written into app.yml when --mq is set.")

HELP_HOST = ("Host to bind Pulsar to - defaults to localhost. Specify 0.0.0.0 "
             "to listen on all interfaces.")
HELP_TOKEN = ("Private token used to authorize clients. If Pulsar is not protected "
              "via firewall, this should be specified and SSL should be enabled. See "
              "%s for more information on security.") % CONFIGURE_URL
HELP_PORT = ("Port to bind Pulsar to (ignored if --mq is specified).")
HELP_PIP_INSTALL_ARGS_HELP = ("Arguments to pip install (defaults to pulsar-app) - unimplemented")

DEFAULT_HOST = "localhost"

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
port = ${port}
host = ${host}
## pem file to use to enable SSL.
# ssl_pem = host.pem

[app:main]
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
    dependencies = []
    arg_parser = PlatformArgumentParser(description=DESCRIPTION)
    arg_parser.add_argument("--directory",
                            default=".",
                            help=HELP_DIRECTORY)
    arg_parser.add_argument("--auto_conda",
                            action="store_true",
                            default=False,
                            help=HELP_AUTO_CONDA)
    arg_parser.add_argument("--mq",
                            action="store_true",
                            default=False,
                            help=HELP_MQ)
    arg_parser.add_argument("--login",
                            action="store_true",
                            default=False,
                            help=HELP_LOGIN)
    arg_parser.add_argument("--login-only",
                            dest="login_only",
                            action="store_true",
                            default=False,
                            help=HELP_LOGIN_ONLY)
    arg_parser.add_argument("--relay-url",
                            dest="relay_url",
                            default=None,
                            help=HELP_RELAY_URL)
    arg_parser.add_argument("--no_logging",
                            dest="logging",
                            action="store_false",
                            default=True,
                            help=HELP_NO_LOGGING)
    arg_parser.add_argument("--supervisor",
                            action="store_true",
                            default=False,
                            help=HELP_SUPERVISOR,
                            skip_on_windows=True)
    arg_parser.add_argument("--wsgi_server",
                            choices=["gunicorn", "uwsgi"],
                            default=None,
                            help=HELP_WSGI_SERVER,
                            skip_on_windows=True)
    arg_parser.add_argument("--libdrmaa_path",
                            help=HELP_LIBDRMAA,
                            skip_on_windows=True)
    arg_parser.add_argument("--host",
                            default=DEFAULT_HOST,
                            help=HELP_HOST)
    arg_parser.add_argument("--private_token",
                            default=None,
                            help=HELP_TOKEN)
    arg_parser.add_argument("--port",
                            default="8913",
                            help=HELP_PORT)
    arg_parser.add_argument("--install",
                            action="store_true",
                            help=HELP_INSTALL)
    arg_parser.add_argument("--force",
                            action="store_true",
                            default=False,
                            help=HELP_FORCE)
    arg_parser.add_argument("--register-with-galaxy",
                            dest="register_with_galaxy",
                            default=None,
                            metavar="GALAXY_URL",
                            help=(
                                "Bootstrap a BYOC Pulsar registration against a Galaxy "
                                "server. Drives the relay device flow with pair-issuance "
                                "and hands the secondary refresh token to Galaxy at "
                                "/api/compute_resources/registrations/complete. Requires "
                                "--relay-url and --galaxy-token (the one-shot token returned "
                                "by POST /api/compute_resources/registrations)."
                            ))
    arg_parser.add_argument("--galaxy-token",
                            dest="galaxy_token",
                            default=None,
                            help="One-shot bootstrap token from /api/compute_resources/registrations.")
    # arg_parser.add_argument("--pip_install_args",
    #                         default="pulsar-app",
    #                         help=HELP_PIP_INSTALL_ARGS_HELP)
    args = arg_parser.parse_args(argv)
    directory = args.directory
    relative_directory = directory
    directory = os.path.abspath(directory)

    _validate_relay_args(args, arg_parser, directory)

    # --login-only: just run the device flow, no scaffolding.
    if args.login_only:
        if not os.path.exists(directory):
            os.makedirs(directory)
        return _run_relay_login(args, directory)

    # --register-with-galaxy: pair-issuance device flow + Galaxy callback.
    # Scaffolds app.yml using the relay-supplied manager_name so the user's
    # Pulsar binds to the same topics Galaxy publishes to.
    if args.register_with_galaxy:
        if not os.path.exists(directory):
            os.makedirs(directory)
        return _run_register_with_galaxy(args, directory)

    mode = _determine_mode(args)
    if mode == "uwsgi":
        dependencies.append("uwsgi")

    if not os.path.exists(directory):
        os.makedirs(directory)

    default_dependencies_dir = os.path.join(directory, "dependencies")
    if not os.path.exists(default_dependencies_dir):
        os.makedirs(default_dependencies_dir)

    print("Bootstrapping pulsar configuration into directory %s" % relative_directory)
    _handle_app_yaml(args, directory)
    _handle_server_ini(args, directory)
    if not IS_WINDOWS:
        _handle_local_env(args, directory, dependencies)
        _handle_supervisor(args, mode, directory, dependencies)
    _handle_install(args, dependencies)
    _print_config_summary(args, mode, relative_directory)

    # If the operator asked to also sign in, run the device flow now so the
    # credentials file lands next to the freshly-scaffolded app.yml.
    if args.login:
        return _run_relay_login(args, directory)


def _validate_relay_args(args, arg_parser, directory):
    if args.login and args.login_only:
        arg_parser.error("--login and --login-only are mutually exclusive")
    if (args.login or args.login_only) and not args.relay_url:
        arg_parser.error("--login / --login-only require --relay-url")
    if args.register_with_galaxy:
        if not args.relay_url:
            arg_parser.error("--register-with-galaxy requires --relay-url")
        if not args.galaxy_token:
            arg_parser.error("--register-with-galaxy requires --galaxy-token")

    # --login implies --mq (relay is a message queue). Set it here so the
    # downstream scaffold writes a relay-flavoured app.yml.
    if args.login:
        args.mq = True
        # Refuse to clobber an existing app.yml unless --force is set —
        # this is almost certainly the operator's hand-rolled config and
        # they want --login-only instead.
        existing_app_yaml = os.path.join(directory, DEFAULT_APP_YAML)
        if os.path.isfile(existing_app_yaml) and not args.force:
            arg_parser.error(
                "{path} already exists. Use --login-only to bootstrap relay "
                "credentials without touching app.yml, or --force to "
                "regenerate the scaffold from scratch.".format(path=existing_app_yaml)
            )


def _print_config_summary(args, mode, relative_directory):
    print(" - app.yml created, update to configure Pulsar application.")
    _print_server_ini_info(args, mode)
    if not IS_WINDOWS:
        print(" - local_env.sh created, update to configure environment.")
    print("\n")
    print("Start pulsar by running the command from directory [%s]:" % relative_directory)
    _print_pulsar_run(mode)
    _print_pulsar_check(args, mode)


def _print_server_ini_info(args, mode):
    if not args.mq:
        print(" - server.ini created, update to configure web server.")
        print("   * Target web server %s" % mode)
        if args.host == DEFAULT_HOST:
            print("   * Binding to host localhost, remote clients will not be able to connect.")
        elif args.private_token:
            print("   * Binding to host [%s] with a private token, please configure SSL if network is not firewalled off.", args.host)
        else:
            print("   * Binding to host [%s], configure a private token and SSL if network is not firewalled off.", args.host)
        print("   * Target web server %s" % mode)


def _print_pulsar_run(mode):
    if IS_WINDOWS:
        print("    pulsar")
    elif mode == "uwsgi":
        print("    pulsar --mode %s" % mode)
        print("Any extra commands passed to pulsar will be forwarded along to uwsgi.")
    elif mode != "gunicorn":
        print("    pulsar --mode %s" % mode)
    else:
        print("    pulsar")


def _print_pulsar_check(args, mode):
    if not mode == "webless":
        # TODO: Implement pulsar-check for mq
        return

    print("Run a test job against your Pulsar server using the command:")
    command = "pulsar-check --url http://{}:{}".format(args.host, args.port)
    if args.private_token:
        command += '--private_token %s' % args.private_token
    print("  %s" % command)
    print("If it reports no problems, your pulsar server is running properly.")


def _determine_mode(args):
    if not IS_WINDOWS and args.wsgi_server:
        mode = args.wsgi_server
    elif args.mq:
        mode = "webless"
    else:
        mode = "gunicorn"
    return mode


RELAY_CREDENTIALS_FILENAME = "relay_credentials.json"


def _run_register_with_galaxy(args, directory):
    """Drive ``pulsar-config --register-with-galaxy`` end-to-end."""
    credentials_path = os.path.join(directory, RELAY_CREDENTIALS_FILENAME)
    try:
        result = register_with_galaxy(
            galaxy_url=args.register_with_galaxy,
            bootstrap_token=args.galaxy_token,
            relay_url=args.relay_url,
            credentials_path=credentials_path,
        )
    except GalaxyBYOCRegistrationError as exc:
        print("BYOC registration failed: {}".format(exc), file=sys.stderr)
        return 1

    # Write a minimal app.yml that binds Pulsar to the manager_name the
    # relay handed us (= the JWT ``sub``), via the credentials file we
    # just wrote.
    manager_name = result["manager_name"]
    app_yaml_path = os.path.join(directory, DEFAULT_APP_YAML)
    if os.path.exists(app_yaml_path) and not args.force:
        print(
            " - {path} already exists; not overwriting. Configure your Pulsar to "
            "use manager.name='{m}' and message_queue_credentials_file='{c}'.".format(
                path=app_yaml_path, m=manager_name, c=credentials_path
            )
        )
    else:
        contents = (
            "---\n"
            "managers:\n"
            "  {m}: {{}}\n"
            'message_queue_url: "{url}"\n'
            'message_queue_credentials_file: "{c}"\n'
        ).format(m=manager_name, url=args.relay_url, c=credentials_path)
        with open(app_yaml_path, "w") as fh:
            fh.write(contents)
        print(" - {path} written (manager.name='{m}').".format(path=app_yaml_path, m=manager_name))

    print(
        " - registered with Galaxy at {url} as manager '{m}'.".format(
            url=args.register_with_galaxy, m=manager_name
        )
    )
    print(" - relay credentials at {p} (primary refresh token).".format(p=credentials_path))
    return 0


def _run_relay_login(args, directory):
    """Bootstrap a refresh-token credentials file via the device flow.

    Imported lazily so that ``pulsar-config`` without ``--login`` does not
    pay the import cost (and works even if ``requests`` is unavailable, which
    matters for some bootstrap scripts).
    """
    from pulsar_relay_client import (
        CredentialsFile,
        DeviceFlowError,
        RelayDeviceFlowAuthenticator,
    )

    credentials_path = os.path.join(directory, RELAY_CREDENTIALS_FILENAME)
    cred_file = CredentialsFile(credentials_path)

    print(
        "Beginning pulsar-relay device-flow login against {url}.".format(url=args.relay_url)
    )
    print(
        "If your terminal is on a different machine than your browser, "
        "open the URL printed below in any browser and enter the user code shown."
    )

    flow = RelayDeviceFlowAuthenticator(
        relay_url=args.relay_url,
        credentials_file=cred_file,
        client_hint="pulsar-config on {host}".format(host=os.uname().nodename),
    )
    try:
        flow.run()
    except DeviceFlowError as exc:
        print("Login failed: {}".format(exc), file=sys.stderr)
        return 1
    print(" - relay credentials written to {path}".format(path=credentials_path))
    if not args.mq:
        # The app.yml scaffold was skipped (operator ran --login alone).
        # Print the keys they need to add by hand.
        print(
            "Set ``message_queue_credentials_file: {path}`` (and "
            "``message_queue_url: {url}``) in app.yml.".format(
                path=credentials_path, url=args.relay_url
            )
        )
    return 0


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
    if args.private_token:
        contents += 'private_token: %s\n' % args.private_token
    if args.mq:
        if args.relay_url:
            # pulsar-relay (HTTP) mode. Use a refresh-token credentials file
            # bootstrapped by `pulsar-config --login`, falling back to legacy
            # username/password placeholders the operator can fill in by hand.
            contents += 'message_queue_url: "{}"\n'.format(args.relay_url)
            contents += 'message_queue_credentials_file: "{}"\n'.format(
                os.path.join(directory, RELAY_CREDENTIALS_FILENAME)
            )
            contents += '## Or, for legacy password-based relay auth:\n'
            contents += '#message_queue_username: admin\n'
            contents += '#message_queue_password: changeme\n'
        else:
            contents += 'message_queue_url: "amqp://guest:guest@localhost:5672//"\n'
    auto_conda = 'true' if args.auto_conda else 'false'
    contents += 'conda_auto_init: {}\n'.format(auto_conda)
    contents += 'conda_auto_install: {}\n'.format(auto_conda)
    if not IS_WINDOWS and args.libdrmaa_path:
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
        if pip is None:
            raise ImportError("Bootstrapping Pulsar dependencies requires pip library.")

        pip.main(["install"] + dependencies)


# def _install_pulsar_in_virtualenv(venv):
#     if virtualenv is None:
#         raise ImportError("Bootstrapping Pulsar into a virtual environment, requires virtualenv.")
#     if IS_WINDOWS:
#         bin_dir = "Scripts"
#     else:
#         bin_dir = "bin"
#     virtualenv.create_environment(venv)
#     # TODO: Remove --pre on release.
#     subprocess.call([os.path.join(venv, bin_dir, 'pip'), 'install', "--pre", "pulsar-app"])


def _check_file(path, force):
    if os.path.exists(path) and not force:
        print("File %s exists, exiting. Run with --force to replace configuration." % path, file=sys.stderr)
        sys.exit(1)


class PlatformArgumentParser(ArgumentParser):

    def add_argument(self, *args, **kwds):
        if "skip_on_windows" in kwds:
            skip_on_windows = kwds["skip_on_windows"]
            if skip_on_windows and IS_WINDOWS:
                return
            del kwds["skip_on_windows"]

        return ArgumentParser.add_argument(self, *args, **kwds)
