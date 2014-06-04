# TODO: Make objects.

PREPROCESSING = "preprocessing"
QUEUED = "queued"
RUNNING = "running"
COMPLETE = "complete"
CANCELLED = "cancelled"
FAILED = "failed"
POSTPROCESSING = "postprocessing"


def is_job_done(status):
    return status in [ COMPLETE, CANCELLED, FAILED ]
