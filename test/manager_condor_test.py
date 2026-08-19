from unittest import mock

from .test_utils import BaseManagerTestCase


class CondorManagerTest(BaseManagerTestCase):
    """Coverage for the ``condor_submit``-based manager.

    Everything HTCondor-side is faked - see ``manager_htcondor_test`` for the
    bindings-based manager, which is exercised against a fake ``htcondor2``.
    """

    def setUp(self):
        super().setUp()
        from pulsar.managers.queued_condor import CondorQueueManager

        self.manager_class = CondorQueueManager
        self.submit_descriptions = []

    def _manager(self, **kwds):
        return self.manager_class('_default_', self.app, **kwds)

    def _launch(self, manager, external_job_id, **launch_kwds):
        job_id = manager.setup_job(external_job_id, "tool1", "1.0.0")
        with mock.patch("pulsar.managers.queued_condor.condor_submit", side_effect=self._fake_submit):
            manager.launch(job_id, "true", **launch_kwds)
        return job_id

    def _fake_submit(self, submit_file):
        with open(submit_file) as handle:
            self.submit_descriptions.append(handle.read())
        return str(100 + len(self.submit_descriptions)), None

    def test_submission_params_do_not_leak_between_managers(self):
        # launch() takes submit_params={} as a default, so updating it in place
        # would carry one manager's configuration into the next job.
        self._launch(self._manager(submit_request_memory="32"), "123")
        self._launch(self._manager(submit_universe="standard"), "124")
        first, second = self.submit_descriptions
        assert "request_memory = 32" in first
        assert "request_memory" not in second
        assert "universe = standard" in second

    def test_submit_params_argument_is_not_mutated(self):
        submit_params = {}
        self._launch(self._manager(submit_request_memory="32"), "123", submit_params=submit_params)
        assert submit_params == {}

    def test_manager_params_override_job_params(self):
        manager = self._manager(submit_request_memory="32")
        self._launch(manager, "123", submit_params=dict(request_memory="64"))
        assert "request_memory = 32" in self.submit_descriptions[0]
