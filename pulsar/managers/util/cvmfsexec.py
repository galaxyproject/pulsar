"""Generate job-script shell for running under `cvmfsexec`.

`cvmfsexec <https://github.com/cvmfs/cvmfsexec>`_ provides access to CVMFS
repositories without root. Pulsar supports two execution modes, selected via a
``cvmfsexec`` manager option (or a per-job override delivered in
``setup_params``):

``namespace``
    ``cvmfsexec`` mounts the requested repositories into a mount namespace so
    they are available at the real ``/cvmfs``. The job command is run under
    ``cvmfsexec`` and no path rewriting is needed. Requires unprivileged user
    namespaces (or a suitable setuid/fusermount fallback) on the execution host.

``mountrepo``
    For hosts where the mount namespace cannot be created, ``mountrepo``
    bind-mounts each repository under
    ``<job_directory>/.cvmfsexec/dist/cvmfs/<repo>`` instead of the real
    ``/cvmfs``. Because Galaxy resolves Singularity containers against the real
    ``/cvmfs`` on the Galaxy host and bakes that path into the job command, the
    host-side container image path must be remapped to the ``dist`` location.
    That rewrite is *not* done here: it is an ordinary path rewrite handled by
    Galaxy via a destination ``file_actions``/``file_action_config`` ``rewrite``
    rule (source ``/cvmfs/<repo>``, destination
    ``__PULSAR_JOB_DIRECTORY__/.cvmfsexec/dist/cvmfs/<repo>``). The
    ``__PULSAR_JOB_DIRECTORY__`` token is substituted by the Pulsar server with
    the absolute job directory (it survives ``shlex.quote`` on the client, unlike
    a ``$VAR``). This module only owns the cvmfsexec runtime setup (mount
    preamble and, for namespace mode, wrapping the command).

This module only generates strings; it performs no I/O so it is trivially
unit-testable.
"""
import shlex
from typing import (
    List,
    Optional,
)

from galaxy.util import listify

MODE_MOUNTREPO = "mountrepo"
MODE_NAMESPACE = "namespace"
VALID_MODES = (MODE_MOUNTREPO, MODE_NAMESPACE)
DEFAULT_MODE = MODE_MOUNTREPO


class CvmfsExecConfig:

    def __init__(
        self,
        mode: str,
        path: str,
        repositories: List[str],
    ):
        self.mode = mode
        self.path = path
        self.repositories = repositories


def parse(raw) -> Optional[CvmfsExecConfig]:
    """Build a :class:`CvmfsExecConfig` from a raw mapping (or ``None``).

    Returns ``None`` when cvmfsexec is not configured.

    >>> parse(None) is None
    True
    >>> c = parse({"path": "/opt/cvmfsexec", "repositories": ["singularity.galaxyproject.org", "data.galaxyproject.org"]})
    >>> c.mode
    'mountrepo'
    >>> c.repositories
    ['singularity.galaxyproject.org', 'data.galaxyproject.org']
    >>> parse({"repositories": ["a"]})
    Traceback (most recent call last):
    ...
    ValueError: cvmfsexec configuration requires a 'path'
    >>> parse({"mode": "bogus", "path": "/x", "repositories": ["a"]})
    Traceback (most recent call last):
    ...
    ValueError: Invalid cvmfsexec mode 'bogus', must be one of: mountrepo, namespace
    """
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise ValueError("cvmfsexec configuration must be a mapping")

    mode = raw.get("mode") or DEFAULT_MODE
    if mode not in VALID_MODES:
        raise ValueError(
            "Invalid cvmfsexec mode '%s', must be one of: %s" % (mode, ", ".join(VALID_MODES))
        )

    path = raw.get("path")
    if not path:
        raise ValueError("cvmfsexec configuration requires a 'path'")

    repositories = listify(raw.get("repositories"))
    if not repositories:
        raise ValueError("cvmfsexec configuration requires at least one repository")

    return CvmfsExecConfig(
        mode=mode,
        path=path,
        repositories=repositories,
    )


# Shell state the job-script template sets but does not export, which the
# namespace-mode wrap (a fresh ``/bin/bash -c``) would otherwise lose. The
# ``TMP*`` vars are read by the ``singularity`` invocation (``SINGULARITYENV_*``
# pass-through); the ``GALAXY_*`` vars and the ``_galaxy_setup_environment``
# function are used by the in-job (remote) metadata segment. ``export -f`` is a
# bash builtin (the wrap uses ``/bin/bash``).
NAMESPACE_EXPORT_COMMANDS = [
    "export TMP TEMP TMPDIR",
    "export GALAXY_VIRTUAL_ENV _GALAXY_VIRTUAL_ENV GALAXY_LIB GALAXY_PYTHON",
    "export -f _galaxy_setup_environment",
]


def _guarded(command: str, message: str) -> str:
    """Abort the job script with ``message`` if ``command`` exits non-zero."""
    return "%s || { echo %s >&2; exit 1; }" % (command, shlex.quote(message))


def setup_commands(config: CvmfsExecConfig, job_directory: str) -> List[str]:
    """Shell statements that prepare cvmfsexec before the job command runs.

    For ``mountrepo`` mode this reproduces the previously hand-maintained
    destination ``env``/``execute`` block: install the cvmfsexec launcher into
    the (absolute) per-job directory, bootstrap the ``.cvmfsexec`` dist tree, and
    mount each repository. Each step aborts the job script with a diagnostic on
    failure rather than letting the job continue and die later on a missing image
    path. The matching unmount is registered separately as an EXIT handler (see
    :func:`add_exit_handlers`).

    For ``namespace`` mode the command is wrapped instead (see
    :func:`wrap_command`); the preamble only exports the shell state that wrap
    would otherwise drop across the ``/bin/bash -c`` boundary
    (:data:`NAMESPACE_EXPORT_COMMANDS`).

    ``job_directory`` is the absolute job directory (Pulsar knows it at
    job-script generation time), used directly instead of a ``$CVMFSEXEC_DIR``
    shell variable so the mount location matches the ``__PULSAR_JOB_DIRECTORY__``
    the client rewrites the container image path to.

    >>> c = parse({"path": "/opt/cvmfsexec", "repositories": ["singularity.galaxyproject.org"]})
    >>> setup_commands(c, "/jobs/7")  # doctest: +NORMALIZE_WHITESPACE
    ["cp /opt/cvmfsexec /jobs/7/cvmfsexec || { echo 'cvmfsexec: failed to install launcher' >&2; exit 1; }",
     "/jobs/7/cvmfsexec -v >/dev/null || { echo 'cvmfsexec: failed to bootstrap dist tree' >&2; exit 1; }",
     "/jobs/7/.cvmfsexec/mountrepo singularity.galaxyproject.org || { echo 'cvmfsexec: failed to mount singularity.galaxyproject.org' >&2; exit 1; }"]

    >>> ns = parse({"mode": "namespace", "path": "/opt/cvmfsexec", "repositories": ["data.galaxyproject.org"]})
    >>> setup_commands(ns, "/jobs/7")
    ['export TMP TEMP TMPDIR', 'export GALAXY_VIRTUAL_ENV _GALAXY_VIRTUAL_ENV GALAXY_LIB GALAXY_PYTHON', 'export -f _galaxy_setup_environment']
    """
    if config.mode == MODE_NAMESPACE:
        return list(NAMESPACE_EXPORT_COMMANDS)
    if config.mode != MODE_MOUNTREPO:
        return []
    launcher = "%s/cvmfsexec" % job_directory
    dist = "%s/.cvmfsexec" % job_directory
    mountrepo = "%s/mountrepo" % dist
    commands = [
        _guarded(
            "cp %s %s" % (shlex.quote(config.path), shlex.quote(launcher)),
            "cvmfsexec: failed to install launcher",
        ),
        _guarded(
            "%s -v >/dev/null" % shlex.quote(launcher),
            "cvmfsexec: failed to bootstrap dist tree",
        ),
    ]
    for repository in config.repositories:
        commands.append(
            _guarded(
                "%s %s" % (shlex.quote(mountrepo), shlex.quote(repository)),
                "cvmfsexec: failed to mount %s" % repository,
            )
        )
    return commands


def add_exit_handlers(exit_handlers, config: CvmfsExecConfig, job_directory: str) -> None:
    """Add cvmfsexec cleanup to the job script's exit handlers.

    For ``mountrepo`` mode this unmounts everything mounted by
    :func:`setup_commands` when the job script exits. ``namespace`` mode needs no
    cleanup (the mount namespace is torn down with the wrapped process).

    ``exit_handlers`` is a ``pulsar.managers.util.job_script.ExitHandlers`` (the
    generic collector); cvmfsexec only contributes to it rather than owning the
    EXIT-handling machinery.

    >>> from pulsar.managers.util.job_script import ExitHandlers
    >>> handlers = ExitHandlers()
    >>> c = parse({"path": "/opt/cvmfsexec", "repositories": ["singularity.galaxyproject.org"]})
    >>> add_exit_handlers(handlers, c, "/jobs/7")
    >>> handlers.commands
    ['/jobs/7/.cvmfsexec/umountrepo -a']
    >>> ns = parse({"mode": "namespace", "path": "/opt/cvmfsexec", "repositories": ["a"]})
    >>> add_exit_handlers(handlers, ns, "/jobs/7")
    >>> handlers.commands
    ['/jobs/7/.cvmfsexec/umountrepo -a']
    """
    if config.mode != MODE_MOUNTREPO:
        return
    exit_handlers.add("%s -a" % shlex.quote("%s/.cvmfsexec/umountrepo" % job_directory))


def wrap_command(config: CvmfsExecConfig, command: str) -> str:
    """Wrap the job command to run under cvmfsexec for ``namespace`` mode.

    The whole command is executed under ``cvmfsexec <repos> -- /bin/bash -c
    ...`` so the real ``/cvmfs`` is available throughout. ``mountrepo`` mode
    returns the command unchanged (its repositories are mounted by the preamble).

    The shell state the wrapped command needs (``TMP*``, ``GALAXY_*``, and the
    ``_galaxy_setup_environment`` function) is exported by the namespace-mode
    preamble (:func:`setup_commands`) so it crosses into the wrapped shell.
    Namespace mode should still be validated on a namespace-capable host before
    production use.

    >>> c = parse({"mode": "namespace", "path": "/opt/cvmfsexec", "repositories": ["data.galaxyproject.org"]})
    >>> wrap_command(c, "run_tool --flag")
    "/opt/cvmfsexec data.galaxyproject.org -- /bin/bash -c 'run_tool --flag'"
    """
    if config.mode != MODE_NAMESPACE:
        return command
    repositories = " ".join(shlex.quote(repository) for repository in config.repositories)
    return "%s %s -- /bin/bash -c %s" % (shlex.quote(config.path), repositories, shlex.quote(command))
