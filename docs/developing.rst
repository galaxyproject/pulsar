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

* Check that ``HISTORY.rst`` covers every PR merged since the previous tag.
  For example::

      git log --first-parent --format=%s <previous-tag>..HEAD | grep '^Merge pull request'

  Add a bullet for each user-facing change, crediting outside contributors
  (including the original authors of rescued PRs) and calling out behavior
  changes with **Note:**. Dependabot bumps are not listed. Each PR reference
  needs a link under ``.. github_links``, and each new contributor a link at the
  end of the file::

      * Follow redirects in the curl transport (thanks to `@nuwang`_).
        `Pull Request 526`_

      .. _Pull Request 526: https://github.com/galaxyproject/pulsar/pull/526
      .. _@nuwang: https://github.com/nuwang
* Make sure CI is green on the commit being released.

Cutting a Release
-----------------

Using ``0.15.16`` as the example, with ``master`` at ``0.15.16.dev0``:

1. Create the release commit. In ``HISTORY.rst``, replace the
   ``0.15.16.dev0`` header with ``0.15.16 (YYYY-MM-DD)``. In
   ``pulsar/__init__.py``, set ``__version__ = '0.15.16'``. Commit as
   ``Create pulsar release 0.15.16``.
2. Tag that commit: ``git tag 0.15.16``. The tag must point at the release
   commit, not at the next ``.dev0`` commit.
3. Start the next version. Add a new ``.dev0`` section to the top of
   ``HISTORY.rst`` under ``.. to_doc``, set ``__version__`` to match, and
   commit as ``Start work on <version>``. On a release branch this is the
   next point release (``0.15.17.dev0``). On ``master`` it is either the next
   point release or, when a release branch is being cut (see below), the next
   minor (``0.16.0.dev0``).
4. Push the branch and the tag together to ``galaxyproject/pulsar``::

      git push <galaxyproject-remote> <branch> 0.15.16

5. Watch the ``Deploy`` workflow run for the tag, then confirm both
   ``pulsar-app`` and ``pulsar-galaxy-lib`` show the new version on PyPI.
6. Create a GitHub release for the tag with generated release notes.

``make docs`` and ``make open-docs`` regenerate the API stubs in
``docs/pulsar.*.rst``. Don't let unrelated stub changes ride along in the
release commit.

Cutting a Release Branch
------------------------

When Galaxy branches a new release, cut the matching Pulsar series:

1. Cut the last release of the current series from ``master`` as above, but
   in step 3 bump ``master`` to the next minor (e.g. ``0.16.0.dev0``).
2. Create the release branch from that release's tag and push it::

      git branch release_0.15 0.15.16
      git push <galaxyproject-remote> release_0.15

3. On the release branch, start the next point release (``0.15.17.dev0``).

A point release from a release branch follows `Cutting a Release`_ on that
branch. Afterwards, merge the release branch into ``master``. In
``HISTORY.rst``, keep ``master``'s ``.dev0`` section on top and the point
release's section below it.

After a Release
---------------

* Bump ``pulsar-galaxy-lib`` in ``lib/galaxy/dependencies/pinned-requirements.txt``
  on each Galaxy branch that should pick up the release.
* Update ``docs/compatibility.yml`` (and regenerate with
  ``make compatibility-docs``) when a series is added, a Galaxy pin changes,
  or a release fixes or introduces a known break.
  ``.agents/commands/update_compat_matrix.md`` describes the survey.

The ``release``, ``release-local`` and ``push-release`` Makefile targets and
the ``tools/commit_version.py`` and ``tools/new_version.py`` scripts predate
this process and are not used.
