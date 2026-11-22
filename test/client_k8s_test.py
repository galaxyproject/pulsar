from types import SimpleNamespace
from unittest import mock

from pulsar.client import kubernetes
from pulsar.managers import status
from pulsar.managers.util import runner_states


def _client():
    client = kubernetes.K8sPollingCoexecutionJobClient.__new__(kubernetes.K8sPollingCoexecutionJobClient)
    client.destination_params = {}
    client.job_id = "123"
    return client


def _job(**job_status):
    return SimpleNamespace(obj={"status": job_status})


def _pod(*terminated_reasons):
    return SimpleNamespace(
        obj={"status": {"containerStatuses": [{"state": {"terminated": {"reason": r}}} for r in terminated_reasons]}}
    )


def _full_status(job, pod=None, pod_error=None):
    client_class = kubernetes.K8sPollingCoexecutionJobClient
    with mock.patch.object(client_class, "_k8s_job_name", "job-name"):
        with mock.patch.object(client_class, "_pykube_client", object()):
            with mock.patch.object(kubernetes, "find_job_object_by_name", return_value=job):
                with mock.patch.object(
                    kubernetes, "find_pod_object_by_name", return_value=pod, side_effect=pod_error
                ) as find_pod:
                    return _client().full_status(), find_pod


def test_oom_killed_container_reports_memory_limit():
    response, _ = _full_status(_job(failed=1), _pod("Completed", "OOMKilled"))
    assert response["status"] == status.FAILED
    assert response["runner_state"] == runner_states.MEMORY_LIMIT_REACHED


def test_deadline_exceeded_reports_walltime():
    conditions = [{"type": "Failed", "reason": "DeadlineExceeded"}]
    response, find_pod = _full_status(_job(failed=1, conditions=conditions))
    assert response["runner_state"] == runner_states.WALLTIME_REACHED
    find_pod.assert_not_called()


def test_other_failure_has_no_reason():
    response, _ = _full_status(_job(failed=1), _pod("Error"))
    assert response["status"] == status.FAILED
    assert "runner_state" not in response


def test_missing_pod_has_no_reason():
    response, _ = _full_status(_job(failed=1), None)
    assert "runner_state" not in response


def test_running_job_does_not_look_up_pod():
    response, find_pod = _full_status(_job(active=1))
    assert response["status"] == status.RUNNING
    assert "runner_state" not in response
    find_pod.assert_not_called()


def test_failing_pod_lookup_still_reports_failure():
    response, _ = _full_status(_job(failed=1), pod_error=Exception("api down"))
    assert response["status"] == status.FAILED
    assert "runner_state" not in response
