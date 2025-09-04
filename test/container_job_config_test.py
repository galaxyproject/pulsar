from pulsar.client.container_job_config import (
    GcpJobParams,
    gcp_job_template,
    parse_gcp_job_params,
    DEFAULT_GCP_WALLTIME_LIMIT,
    TesJobParams,
)


def test_docs():
    print(GcpJobParams.schema())
    print(TesJobParams.schema())


def test_gcp_defaults():
    params = parse_gcp_job_params({"project_id": "moo"})
    assert params.project_id == "moo"
    assert params.credentials_file is None
    assert params.walltime_limit == DEFAULT_GCP_WALLTIME_LIMIT


def test_gcp_job_template():
    params = parse_gcp_job_params({"project_id": "moo"})
    job = gcp_job_template(params)
    assert job is not None
    assert len(job.task_groups) == 1
    task_group = job.task_groups[0]
    task = task_group.task_spec
    assert len(task.volumes) == 1


def test_gcp_custom_walltime():
    custom_walltime = "7200"  # 2 hours in seconds
    params = parse_gcp_job_params(dict(project_id="moo", credentials_file="path/to/credentials.json", walltime_limit=custom_walltime))
    assert params.credentials_file == "path/to/credentials.json"
    assert params.walltime_limit == int(custom_walltime)
