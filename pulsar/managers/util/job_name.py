"""Job names shared by container schedulers."""

import uuid


def produce_unique_k8s_job_name(app_prefix=None, instance_id=None, job_id=None):
    if job_id is None:
        job_id = str(uuid.uuid4())

    job_name = ""
    if app_prefix:
        job_name += "%s-" % app_prefix

    if instance_id and len(instance_id) > 0:
        job_name += "%s-" % instance_id

    return job_name + job_id
