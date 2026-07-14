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
    ``$CVMFSEXEC_DIR/.cvmfsexec/dist/cvmfs/<repo>`` instead of the real
    ``/cvmfs``. Because Galaxy resolves Singularity containers against the real
    ``/cvmfs`` on the Galaxy host and bakes that path into the job command, the
    host-side container image path must be remapped to the ``dist`` location.
    That rewrite is *not* done here: it is an ordinary path rewrite handled by
    Galaxy via a destination ``file_actions``/``file_action_config`` ``rewrite``
    rule (source ``/cvmfs/<repo>``, destination
    ``$CVMFSEXEC_DIR/.cvmfsexec/dist/cvmfs/<repo>``). This module only owns the
    cvmfsexec runtime setup (mount preamble and, for namespace mode, wrapping
    the command).

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

# Expression evaluated in the job script to locate the per-job cvmfsexec
# directory. ``_GALAXY_JOB_DIR`` is set to the working directory near the top of
# the job script template, so its parent is the job directory that Pulsar stages
# under - the same value the previous hand-written destination config computed.
DEFAULT_CVMFSEXEC_DIR_EXPR = '$(dirname "$_GALAXY_JOB_DIR")'


class CvmfsExecConfig:

    def __init__(
        self,
        mode: str,
        path: str,
        repositories: List[str],
        cvmfsexec_dir_expr: str = DEFAULT_CVMFSEXEC_DIR_EXPR,
    ):
        self.mode = mode
        self.path = path
        self.repositories = repositories
        self.cvmfsexec_dir_expr = cvmfsexec_dir_expr


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

    cvmfsexec_dir_expr = raw.get("cvmfsexec_dir") or DEFAULT_CVMFSEXEC_DIR_EXPR

    return CvmfsExecConfig(
        mode=mode,
        path=path,
        repositories=repositories,
        cvmfsexec_dir_expr=cvmfsexec_dir_expr,
    )


def setup_commands(config: CvmfsExecConfig) -> List[str]:
    """Shell statements that prepare cvmfsexec before the job command runs.

    For ``mountrepo`` mode this reproduces the previously hand-maintained
    destination ``env``/``execute`` block: locate ``CVMFSEXEC_DIR``, install the
    cvmfsexec launcher, bootstrap the ``.cvmfsexec`` dist tree, register cleanup,
    and mount each repository. ``namespace`` mode needs no preamble - the command
    is wrapped instead (see :func:`wrap_command`).

    >>> c = parse({"path": "/opt/cvmfsexec", "repositories": ["singularity.galaxyproject.org"]})
    >>> setup_commands(c)  # doctest: +NORMALIZE_WHITESPACE
    ['export CVMFSEXEC_DIR="$(dirname "$_GALAXY_JOB_DIR")"',
     'cp "/opt/cvmfsexec" "$CVMFSEXEC_DIR/cvmfsexec"',
     '"$CVMFSEXEC_DIR/cvmfsexec" -v >/dev/null',
     'trap "$CVMFSEXEC_DIR/.cvmfsexec/umountrepo -a" EXIT',
     '"$CVMFSEXEC_DIR/.cvmfsexec/mountrepo" singularity.galaxyproject.org']
    """
    if config.mode != MODE_MOUNTREPO:
        return []
    commands = [
        'export CVMFSEXEC_DIR="%s"' % config.cvmfsexec_dir_expr,
        'cp "%s" "$CVMFSEXEC_DIR/cvmfsexec"' % config.path,
        '"$CVMFSEXEC_DIR/cvmfsexec" -v >/dev/null',
        'trap "$CVMFSEXEC_DIR/.cvmfsexec/umountrepo -a" EXIT',
    ]
    for repository in config.repositories:
        commands.append('"$CVMFSEXEC_DIR/.cvmfsexec/mountrepo" %s' % repository)
    return commands


def wrap_command(config: CvmfsExecConfig, command: str) -> str:
    """Wrap the job command to run under cvmfsexec for ``namespace`` mode.

    The whole command is executed under ``cvmfsexec <repos> -- /bin/bash -c
    ...`` so the real ``/cvmfs`` is available throughout. ``mountrepo`` mode
    returns the command unchanged (its repositories are mounted by the preamble).

    Note: exported environment and the working directory are inherited by the
    wrapped shell, but non-exported shell variables set earlier in the job
    script are not visible inside it. Namespace mode should be validated on a
    namespace-capable host before production use.

    >>> c = parse({"mode": "namespace", "path": "/opt/cvmfsexec", "repositories": ["data.galaxyproject.org"]})
    >>> wrap_command(c, "run_tool --flag")
    '"/opt/cvmfsexec" data.galaxyproject.org -- /bin/bash -c \\'run_tool --flag\\''
    """
    if config.mode != MODE_NAMESPACE:
        return command
    repositories = " ".join(config.repositories)
    return '"%s" %s -- /bin/bash -c %s' % (config.path, repositories, shlex.quote(command))
