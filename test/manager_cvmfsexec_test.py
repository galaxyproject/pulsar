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
        manager = Manager("_default_", self.app, **(manager_kwds or {}))
        job_id = manager.setup_job("300", "tool1", "1.0.0")
        try:
            script_path = manager._setup_job_file(job_id, command, setup_params=setup_params)
            with open(script_path) as fh:
                return fh.read()
        finally:
            manager.clean(job_id)

    def test_disabled_by_default_is_noop(self):
        contents = self._script_for(SINGULARITY_COMMAND)
        assert "CVMFSEXEC_DIR" not in contents
        assert "mountrepo" not in contents
        assert "/cvmfs/singularity.galaxyproject.org/all/img" in contents

    def test_mountrepo_preamble_and_image_rewrite(self):
        contents = self._script_for(SINGULARITY_COMMAND, manager_kwds={"cvmfsexec": MOUNTREPO_CONFIG})
        # Mount preamble generated for every repository.
        assert 'export CVMFSEXEC_DIR="$(dirname "$_GALAXY_JOB_DIR")"' in contents
        assert '"$CVMFSEXEC_DIR/.cvmfsexec/mountrepo" data.galaxyproject.org' in contents
        assert '"$CVMFSEXEC_DIR/.cvmfsexec/mountrepo" singularity.galaxyproject.org' in contents
        # Host-side container image path rewritten to the dist location...
        assert "exec $CVMFSEXEC_DIR/.cvmfsexec/dist/cvmfs/singularity.galaxyproject.org/all/img" in contents
        assert "exec /cvmfs/singularity.galaxyproject.org/all/img" not in contents
        # ...reference-data path (resolved inside the container) left untouched.
        assert "/cvmfs/data.galaxyproject.org/genome.fa" in contents
        # Preamble is injected into the template (after dir prep, before cd), not
        # via the env setup mechanism.
        assert contents.index("export CVMFSEXEC_DIR=") < contents.index("\ncd ")

    def test_setup_params_override_takes_precedence(self):
        override = {
            "path": "/scratch/cvmfsexec",
            "repositories": ["singularity.galaxyproject.org"],
        }
        contents = self._script_for(
            SINGULARITY_COMMAND,
            manager_kwds={"cvmfsexec": MOUNTREPO_CONFIG},
            setup_params={"cvmfsexec": override},
        )
        # Override install path used; the manager-default data repo is not mounted.
        assert 'cp "/scratch/cvmfsexec" "$CVMFSEXEC_DIR/cvmfsexec"' in contents
        assert '"$CVMFSEXEC_DIR/.cvmfsexec/mountrepo" data.galaxyproject.org' not in contents
        assert "exec $CVMFSEXEC_DIR/.cvmfsexec/dist/cvmfs/singularity.galaxyproject.org/all/img" in contents
