==========
Developing
==========

This section contains documentation for maintainers of Pulsar.

Branches and Versions
---------------------

Each Galaxy release pins a ``pulsar-galaxy-lib`` minor series (see
:ref:`compatibility`). Pulsar keeps a release branch per minor series, named
like Galaxy's:

* ``master`` carries the next minor series as a ``.dev0`` version (e.g.
  ``0.16.0.dev0``). Features and behavior changes land here only.
* ``release_0.N`` carries the ``0.N.x`` point releases for the Galaxy releases
  that pin that series.

Open a bug fix against the oldest supported release branch it applies to. After
it merges, merge that branch forward through the newer release branches and
into ``master``.

Packages
--------

One tag publishes two packages built from the same tree: ``pulsar-app`` (the
server) and ``pulsar-galaxy-lib`` (the client half Galaxy depends on, built with
``PULSAR_GALAXY_LIB=1``). Pushing a version tag to ``galaxyproject/pulsar``
triggers ``.github/workflows/deploy.yaml``, which builds both with
``make dist-all`` and uploads them to PyPI using trusted publishing. Nothing
else is needed to publish. Tags pushed to a fork do not publish.

PyPI's trusted publisher is bound to ``deploy.yaml``; renaming or moving that
workflow requires updating the publisher on PyPI for both projects.

Preparing a Release
-------------------

Releases are cut from the branch that owns the series: ``master`` for a new
minor series, ``release_0.N`` for a point release.

Each PR adds a changelog entry, ``changes/<PR number>.<type>.md``, where the
type is ``change`` (behavior changes and removals), ``feature``, ``bugfix`` or
``misc``; ``changes/README.md`` describes them. The ``changelog`` workflow fails
PRs without one, or that edit ``CHANGELOG.md`` directly, unless they are labeled
``no changelog`` (dependabot PRs are exempt). Label PRs that merge a release
branch forward ``no changelog``; they carry its released sections. ``make add-change PR=526 TYPE=bugfix`` writes one from the PR title,
crediting outside contributors. Edit the result into a user-facing description,
and credit the original authors of rescued PRs. ``make release`` collects the
entries into ``CHANGELOG.md`` with `towncrier <https://towncrier.readthedocs.io/>`__.

``make release-check`` reports whether the current branch is ready:

* on ``master`` or the ``release_0.N`` matching the version, which is a
  ``.dev0`` version, with a clean tree in sync with ``galaxyproject/pulsar``;
* every PR merged since the previous tag has a ``changes/`` entry, is already
  in ``CHANGELOG.md``, or is labeled ``no changelog``, and the entries build;
* the tag does not exist yet, and CI passed on the commit (requires ``gh``;
  without it this is a warning).

``ALLOW_MISSING_CHANGES=1`` or ``SKIP_CI=1`` turn those failures into warnings
for ``make release-check`` and ``make release``.

Cutting a Release
-----------------

1. ``make release`` runs the checks, then commits ``Create pulsar release
   X.Y.Z`` (moves the ``changes/`` entries into a dated ``CHANGELOG.md``
   section, drops ``.dev0``), tags it, and commits ``Start work on X.Y.Z+1``.
   On ``master``, pass ``NEXT=0.16.0`` to start a different version.
2. ``make push-release`` shows the push and asks for confirmation, then
   pushes the branch and tag to ``galaxyproject/pulsar`` in one atomic push.
3. Watch the ``Deploy`` workflow run for the tag, then confirm both
   ``pulsar-app`` and ``pulsar-galaxy-lib`` show the new version on PyPI.
4. Create the GitHub release (``push-release`` prints the ``gh release
   create`` command).

Nothing is pushed until step 2. To abandon a release before then, delete the
tag and reset the two commits.

Cutting a Release Branch
------------------------

When Galaxy branches a new release, cut the last release of the current series
from ``master`` and start the next minor there::

    make release NEXT=0.16.0
    make release-branch
    make push-release

``make release-branch`` creates ``release_0.15`` from the ``0.15.16`` tag and
commits ``Start work on 0.15.17`` on it. ``make push-release`` then pushes
``master``, ``release_0.15`` and the tag together.

After a point release on a release branch, merge the branch into ``master``.
The point release's ``CHANGELOG.md`` section comes along; on a
``pulsar/__init__.py`` conflict keep ``master``'s version.

After a Release
---------------

* Bump ``pulsar-galaxy-lib`` in ``lib/galaxy/dependencies/pinned-requirements.txt``
  on each Galaxy branch that should pick up the release.
* Update ``docs/compatibility.yml`` (and regenerate with
  ``make compatibility-docs``) when a series is added, a Galaxy pin changes,
  or a release fixes or introduces a known break.
  ``.agents/commands/update_compat_matrix.md`` describes the survey.
