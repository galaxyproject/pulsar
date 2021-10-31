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
