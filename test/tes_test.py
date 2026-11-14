import pytest

from pulsar.client.coexecution import PULSAR_CONTAINER_IMAGE
from pulsar.client.setup_handler import KNOWN_PULSAR_CONTAINER_VERSIONS
from pulsar.client.tes import (
    tes_state_is_complete,
    tes_state_to_pulsar_status,
)
from pulsar.client.tes_job_config import (
    parse_tes_job_params,
    tes_resources,
)
from pulsar.managers.util.tes import TesState


def test_tes_resources_from_xml():
    resources = tes_resources(parse_tes_job_params({
        "tes_url": "http://moo",
        "tes_cpu_cores": "2",
        "tes_preemptible": "true",
        "tes_ram_gb": "128.0",
        "tes_disk_gb": "512.0",
        "tes_zones": "us-west-1,us-east-1",
    }))
    assert resources.cpu_cores == 2
    assert resources.preemptible is True
    assert resources.ram_gb == 128.0
    assert resources.disk_gb == 512.0
    assert resources.zones == ["us-west-1", "us-east-1"]
    assert resources.backend_parameters is None
    assert resources.backend_parameters_strict is False


def test_tes_resources_from_yaml():
    resources = tes_resources(parse_tes_job_params({
        "tes_url": "http://moo",
        "tes_cpu_cores": 4,
        "tes_ram_gb": 127.0,
        "tes_disk_gb": 513.0,
        "tes_zones": ["us-west-1", "us-east-1"],
        "tes_backend_parameters": {"moo": "cow"},
    }))
    assert resources.cpu_cores == 4
    assert resources.preemptible is None
    assert resources.ram_gb == 127.0
    assert resources.disk_gb == 513.0
    assert resources.zones == ["us-west-1", "us-east-1"]
    assert resources.backend_parameters == {"moo": "cow"}
    assert resources.backend_parameters_strict is False


def test_default_staging_image_is_published():
    # KNOWN_PULSAR_CONTAINER_VERSIONS lists the tags on Docker Hub.
    assert PULSAR_CONTAINER_IMAGE in KNOWN_PULSAR_CONTAINER_VERSIONS


def test_queued_tes_task_is_queued_not_failed():
    pytest.importorskip("pydantictes")
    assert tes_state_to_pulsar_status(TesState.QUEUED) == "queued"
    assert tes_state_is_complete(TesState.QUEUED) is False
