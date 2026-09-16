import pulsar.client.test.check
import pulsar.main
import pulsar.scripts.chown_working_directory
import pulsar.scripts.drmaa_kill
import pulsar.scripts.drmaa_launch
import pulsar.scripts.submit

MODULES = [
    pulsar.main,
    pulsar.scripts.drmaa_kill,
    pulsar.scripts.drmaa_launch,
    pulsar.scripts.submit,
    pulsar.client.test.check,
]


def test_scripts_have_help():
    for module in MODULES:
        try:
            module.main(["-h"])
        except SystemExit as e:
            assert e.code == 0, module
