# TODO: Make objects.

PREPROCESSING = "preprocessing"
QUEUED = "queued"
RUNNING = "running"
COMPLETE = "complete"
CANCELLED = "cancelled"
FAILED = "failed"
POSTPROCESSING = "postprocessing"


def is_job_done(status):
    """ Does the supplied status correspond to a finished
    job (done processing).
    """
    return status in [COMPLETE, CANCELLED, FAILED]
