from pulsar.managers import stateful
import datetime


def test_ensure_minimum_runtime():
    before = datetime.datetime.now()
    with stateful.ensure_minimum_runtime(datetime.timedelta(0, .1)):
        pass
    after = datetime.datetime.now()
    td = after - before
    total_seconds = stateful.total_seconds(td)
    print total_seconds
    assert total_seconds >= .1
