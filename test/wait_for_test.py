import itertools

import pytest

from .test_utils import wait_for


def test_wait_for_returns_first_truthy_value():
    values = iter([None, 0, "ready"])
    assert wait_for(lambda: next(values), "a value") == "ready"


def test_wait_for_returns_polled_value_once_until_holds():
    counter = itertools.count()
    assert wait_for(lambda: next(counter), "the counter", until=lambda n: n >= 3) == 3


def test_wait_for_timeout_names_what_it_waited_for():
    with pytest.raises(AssertionError, match=r"^Timed out after 0\.05s waiting for the thing\.$"):
        wait_for(lambda: False, "the thing", timeout=0.05)


def test_wait_for_timeout_with_until_reports_last_value():
    with pytest.raises(AssertionError, match=r"waiting for completion, last value: \{'complete': 'false'\}"):
        wait_for(lambda: {"complete": "false"}, "completion", until=lambda s: s["complete"] == "true", timeout=0.05)
