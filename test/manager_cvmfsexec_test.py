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
        assert "cvmfsexec" not in contents
        assert "mountrepo" not in contents
        assert "/cvmfs/singularity.galaxyproject.org/all/img" in contents

    def test_mountrepo_preamble(self):
        contents, job_dir = self._script_for(SINGULARITY_COMMAND, manager_kwds={"cvmfsexec": MOUNTREPO_CONFIG})
        # Mount preamble uses the absolute job directory (no $CVMFSEXEC_DIR).
        assert f'cp "/opt/cvmfsexec" "{job_dir}/cvmfsexec"' in contents
        assert f'"{job_dir}/.cvmfsexec/mountrepo" data.galaxyproject.org' in contents
        assert f'"{job_dir}/.cvmfsexec/mountrepo" singularity.galaxyproject.org' in contents
        assert "CVMFSEXEC_DIR" not in contents
        # The container image path is NOT rewritten here - in mountrepo mode that
        # is a Galaxy file_actions rewrite rule. The command passes through as-is.
        assert SINGULARITY_COMMAND in contents
        assert ".cvmfsexec/dist/cvmfs/singularity" not in contents
        # Preamble is injected into the template (after dir prep, before cd).
        assert contents.index('cp "/opt/cvmfsexec"') < contents.index("\ncd ")

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
        assert f'cp "/scratch/cvmfsexec" "{job_dir}/cvmfsexec"' in contents
        assert f'"{job_dir}/.cvmfsexec/mountrepo" data.galaxyproject.org' not in contents
        assert f'"{job_dir}/.cvmfsexec/mountrepo" singularity.galaxyproject.org' in contents
