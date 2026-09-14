from pulsar.managers.util.retry import RetryActionExecutor


def test_retry_defaults():
    action_tracker = ActionTracker()
    assert RetryActionExecutor().execute(action_tracker.execute) == 42
    assert action_tracker.count == 1


def test_exception_passthrough():
    action_tracker = ActionTracker(fail_count=1)
    exception_raised = False
    try:
        RetryActionExecutor().execute(action_tracker.execute)
    except Exception:
        exception_raised = True
    assert action_tracker.count == 1
    assert exception_raised


def test_third_execution_fine():
    action_tracker = ActionTracker(fail_count=2)
    exception_raised = False
    try:
        RetryActionExecutor(max_retries=2, interval_start=.01, interval_step=.01).execute(action_tracker.execute)
    except Exception:
        exception_raised = True
    assert action_tracker.count == 3, action_tracker.count
    assert not exception_raised


def test_should_retry_false_short_circuits():
    """When should_retry returns False the exception must propagate on the
    first failure — no sleep, no further attempts."""
    action_tracker = ActionTracker(fail_count=5, fail_how=PermanentError)
    executor = RetryActionExecutor(
        max_retries=10,
        interval_start=.01,
        interval_step=.01,
        should_retry=lambda exc: not isinstance(exc, PermanentError),
    )
    try:
        executor.execute(action_tracker.execute)
    except PermanentError:
        pass
    else:
        raise AssertionError("PermanentError should have propagated")
    assert action_tracker.count == 1, action_tracker.count


def test_should_retry_true_still_retries():
    """The predicate must not block retries for exceptions it approves."""
    action_tracker = ActionTracker(fail_count=2, fail_how=TransientError)
    executor = RetryActionExecutor(
        max_retries=5,
        interval_start=.01,
        interval_step=.01,
        should_retry=lambda exc: isinstance(exc, TransientError),
    )
    result = executor.execute(action_tracker.execute)
    assert result == 42
    assert action_tracker.count == 3, action_tracker.count


class PermanentError(Exception):
    pass


class TransientError(Exception):
    pass


class ActionTracker:

    def __init__(self, fail_count=0, fail_how=Exception):
        self.fail_count = fail_count
        self.fail_how = fail_how
        self.count = 0

    def execute(self):
        self.count += 1
        if self.fail_count >= self.count:
            raise self.fail_how()
        else:
            return 42
