from pulsar.managers.util.tes import tes_resources


def test_tes_resources_from_xml():
    resources = tes_resources({
        "tes_cpu_cores": "2",
        "tes_preemptible": "true",
        "tes_ram_gb": "128.0",
        "tes_disk_gb": "512.0",
        "tes_zones": "us-west-1,us-east-1",
    })
    assert resources.cpu_cores == 2
    assert resources.preemptible is True
    assert resources.ram_gb == 128.0
    assert resources.disk_gb == 512.0
    assert resources.zones == ["us-west-1", "us-east-1"]
    assert resources.backend_parameters is None
    assert resources.backend_parameters_strict is None


def test_tes_resources_from_yaml():
    resources = tes_resources({
        "tes_cpu_cores": 4,
        "tes_ram_gb": 127.0,
        "tes_disk_gb": 513.0,
        "tes_zones": ["us-west-1", "us-east-1"],
        "tes_backend_parameters": {"moo": "cow"},
    })
    assert resources.cpu_cores == 4
    assert resources.preemptible is None
    assert resources.ram_gb == 127.0
    assert resources.disk_gb == 513.0
    assert resources.zones == ["us-west-1", "us-east-1"]
    assert resources.backend_parameters == {"moo": "cow"}
    assert resources.backend_parameters_strict is None
