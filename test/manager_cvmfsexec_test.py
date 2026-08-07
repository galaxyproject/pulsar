"""Manager-level tests for cvmfsexec integration.

Exercises job-script generation (``_setup_job_file``) directly rather than
launching jobs, so the assertions are deterministic and do not depend on the
execution environment.
"""
from pulsar.managers.unqueued import Manager

from .test_utils import BaseManagerTestCase

MOUNTREPO_CONFIG = {
    "path": "/opt/cvmfsexec",
    "repositories": ["data.galaxyproject.org", "singularity.galaxyproject.org"],
}
NAMESPACE_CONFIG = {
    "mode": "namespace",
    "path": "/opt/cvmfsexec",
    "repositories": ["data.galaxyproject.org", "singularity.galaxyproject.org"],
}
SINGULARITY_COMMAND = (
    "singularity exec /cvmfs/singularity.galaxyproject.org/all/img "
    "tool --ref /cvmfs/data.galaxyproject.org/genome.fa"
)


class CvmfsExecManagerTest(BaseManagerTestCase):

    def _script_for(self, command, manager_kwds=None, setup_params=None):
        """Return (script_contents, absolute_job_directory)."""
        manager = Manager("_default_", self.app, **(manager_kwds or {}))
        job_id = manager.setup_job("300", "tool1", "1.0.0")
        job_dir = manager.job_directory(job_id).job_directory
        try:
            script_path = manager._setup_job_file(job_id, command, setup_params=setup_params)
            with open(script_path) as fh:
                return fh.read(), job_dir
        finally:
            manager.clean(job_id)

    def test_disabled_by_default_is_noop(self):
        contents, _ = self._script_for(SINGULARITY_COMMAND)
        # No cvmfsexec machinery, no EXIT handler, and no wrap when unconfigured.
        assert "mountrepo" not in contents  # also covers umountrepo
        assert "_galaxy_on_exit() {" not in contents  # no EXIT handler defined
        assert "trap _galaxy_on_exit EXIT" not in contents  # no EXIT trap set
        assert "-- /bin/bash -c" not in contents  # no namespace wrap
        assert "/opt/cvmfsexec" not in contents  # no configured install copied
        assert "/cvmfs/singularity.galaxyproject.org/all/img" in contents

    def test_mountrepo_preamble(self):
        contents, job_dir = self._script_for(SINGULARITY_COMMAND, manager_kwds={"cvmfsexec": MOUNTREPO_CONFIG})
        # Mount preamble uses the absolute job directory (no $CVMFSEXEC_DIR).
        assert f"cp /opt/cvmfsexec {job_dir}/cvmfsexec" in contents
        assert f"{job_dir}/.cvmfsexec/mountrepo data.galaxyproject.org" in contents
        assert f"{job_dir}/.cvmfsexec/mountrepo singularity.galaxyproject.org" in contents
        assert "CVMFSEXEC_DIR" not in contents
        # Unmount runs from the single generation-time EXIT handler.
        assert "_galaxy_on_exit() {" in contents
        assert f"{job_dir}/.cvmfsexec/umountrepo -a" in contents
        assert "trap _galaxy_on_exit EXIT" in contents
        # Mounts abort the job with a diagnostic on failure.
        assert "|| { echo 'cvmfsexec: failed to mount data.galaxyproject.org' >&2; exit 1; }" in contents
        # The container image path is NOT rewritten here - in mountrepo mode that
        # is a Galaxy file_actions rewrite rule. The command passes through as-is.
        assert SINGULARITY_COMMAND in contents
        assert ".cvmfsexec/dist/cvmfs/singularity" not in contents
        # Preamble is injected into the template (after dir prep, before cd).
        assert contents.index("cp /opt/cvmfsexec") < contents.index("\ncd ")

    def test_namespace_exports_and_wraps(self):
        contents, _ = self._script_for(SINGULARITY_COMMAND, manager_kwds={"cvmfsexec": NAMESPACE_CONFIG})
        # Namespace preamble exports the shell state the wrap would otherwise drop.
        assert "export TMP TEMP TMPDIR" in contents
        assert "export -f _galaxy_setup_environment" in contents
        # The whole job command is wrapped to run under cvmfsexec.
        assert (
            "/opt/cvmfsexec data.galaxyproject.org singularity.galaxyproject.org -- /bin/bash -c '"
        ) in contents
        # No bind-mount preamble in namespace mode.
        assert "mountrepo" not in contents

    def test_setup_params_override_takes_precedence(self):
        override = {
            "path": "/scratch/cvmfsexec",
            "repositories": ["singularity.galaxyproject.org"],
        }
        contents, job_dir = self._script_for(
            SINGULARITY_COMMAND,
            manager_kwds={"cvmfsexec": MOUNTREPO_CONFIG},
            setup_params={"cvmfsexec": override},
        )
        # Override install path used; the manager-default data repo is not mounted.
        assert f"cp /scratch/cvmfsexec {job_dir}/cvmfsexec" in contents
        assert f"{job_dir}/.cvmfsexec/mountrepo data.galaxyproject.org" not in contents
        assert f"{job_dir}/.cvmfsexec/mountrepo singularity.galaxyproject.org" in contents
