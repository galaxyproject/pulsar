import pulsar.scripts.chown_working_directory
import pulsar.scripts.drmaa_kill
import pulsar.scripts.drmaa_launch
import pulsar.scripts.mesos_executor
import pulsar.scripts.mesos_framework
import pulsar.scripts.submit
import pulsar.client.test.check

MODULES = [
    pulsar.scripts.drmaa_kill,
    pulsar.scripts.drmaa_launch,
    pulsar.scripts.mesos_executor,
    pulsar.scripts.mesos_framework,
    pulsar.scripts.submit,
    pulsar.client.test.check,
]


def test_scripts_have_help():
    for module in MODULES:
        try:
            module.main(["-h"])
        except SystemExit as e:
            assert e.code == 0, module
