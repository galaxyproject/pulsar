import pytest

from pulsar.client.container_job_config import (
    _validate_ssd_size,
    DEFAULT_GCP_WALLTIME_LIMIT,
    gcp_job_template,
    GcpJobParams,
    parse_gcp_job_params,
    TesJobParams,
)
from pulsar.managers.util.gcp_util import compute_machine_type


def test_docs():
    print(GcpJobParams.model_json_schema())
    print(TesJobParams.model_json_schema())


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


@pytest.mark.parametrize(
    "cores,mem,expected_cpu_milli,expected_memory_mib,expected_machine_type",
    [
        ("2", "4", 2000, 4096, "n2-standard-2"),
        ("4", "4", 4000, 4096, "n2-highcpu-4"),
        ("4", "20", 4000, 20480, "n2-highmem-4"),
        (None, "8", 1000, 8192, "n2-highmem-2"),
        ("8", None, 8000, 2048, "n2-highcpu-8"),
    ],
)
def test_gcp_dynamic_resources(cores, mem, expected_cpu_milli, expected_memory_mib, expected_machine_type):
    params = parse_gcp_job_params({"project_id": "moo", "cores": cores, "mem": mem})

    assert params.cpu_milli == expected_cpu_milli
    assert params.memory_mib == expected_memory_mib
    assert params.machine_type == expected_machine_type


def test_gcp_resources_do_not_override_explicit_machine_type():
    params = parse_gcp_job_params(
        {"project_id": "moo", "cores": "4", "mem": "8", "machine_type": "n2-custom-4-8192"}
    )

    assert params.machine_type == "n2-custom-4-8192"
    assert params.cpu_milli == 4000
    assert params.memory_mib == 8192


def test_gcp_job_template_uses_one_resource_contract():
    params = parse_gcp_job_params({"project_id": "moo", "cores": "4", "mem": "8"})
    task = gcp_job_template(params).task_groups[0].task_spec

    assert task.compute_resource.cpu_milli == 4000
    assert task.compute_resource.memory_mib == 8192
    assert task.environment.variables["GALAXY_SLOTS"] == "4"
    assert task.environment.variables["GALAXY_MEMORY_MB"] == "8192"


def test_gcp_job_template_keeps_legacy_resource_defaults_when_unspecified():
    task = gcp_job_template(parse_gcp_job_params({"project_id": "moo"})).task_groups[0].task_spec

    assert not task.compute_resource
    assert "GALAXY_SLOTS" not in task.environment.variables
    assert "GALAXY_MEMORY_MB" not in task.environment.variables


@pytest.mark.parametrize(
    "cpu_milli,memory_mib,expected",
    [
        (2000, 4096, "n2-standard-2"),
        (4000, 4096, "n2-highcpu-4"),
        (4000, 8192, "n2-standard-4"),
        (16000, 131072, "n2-highmem-16"),
    ],
)
def test_compute_n2_machine_type(cpu_milli, memory_mib, expected):
    assert compute_machine_type(cpu_milli, memory_mib) == expected


def test_compute_machine_type_rejects_unsupported_requirements():
    with pytest.raises(ValueError, match="cannot satisfy"):
        compute_machine_type(129000, 128 * 1024)


@pytest.mark.parametrize(
    "disk_size,machine_type,expected",
    [
        (375, "n2-standard-2", 375),
        (375, "n2-standard-16", 750),
        (750, "n2-standard-32", 1500),
        (2250, "n2-standard-16", 3000),
        (376, "n1-standard-4", 750),
    ],
)
def test_validate_ssd_size_uses_machine_specific_allowed_counts(disk_size, machine_type, expected):
    assert _validate_ssd_size(disk_size, machine_type) == expected


def test_validate_ssd_size_rejects_more_than_supported():
    with pytest.raises(ValueError, match="does not support"):
        _validate_ssd_size(25 * 375, "n2-standard-16")
