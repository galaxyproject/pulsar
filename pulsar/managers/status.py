# TODO: Make objects.

# Job is staging about will be queued shortly.
PREPROCESSING = "preprocessing"
# Job manager has queued this job for execution.
QUEUED = "queued"
# Job manager believes the job is currently running.
RUNNING = "running"
# Job manager has finished and postprocessing ran successfully.
COMPLETE = "complete"
# Job was cancelled
CANCELLED = "cancelled"
# Problem submitting the job, interfacing with the job manager,
# or postprocessing the job.
FAILED = "failed"
# DRM marked job as complete and job is being unstaged.
POSTPROCESSING = "postprocessing"
# Pulsar believed this job to be active but the job manager
# cannot determine a state for it.
LOST = "lost"


def is_job_done(status):
    """ Does the supplied status correspond to a finished
    job (done processing).
    """
    return status in [COMPLETE, CANCELLED, FAILED, LOST]
