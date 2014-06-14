import time
import json

from lwr.daemon import ArgumentParser
from lwr.lwr_client.util import from_base64_json
from lwr.daemon import load_lwr_app
from lwr.manager_endpoint_util import submit_job
from lwr.managers.status import is_job_done

import logging
log = logging.getLogger(__name__)

DESCRIPTION = "Submit a job and wait for it."
DEFAULT_POLL_TIME = 2


def main():
    arg_parser = ArgumentParser(description=DESCRIPTION)
    arg_parser.add_argument("--file", default=None)
    arg_parser.add_argument("--base64", default=None)
    populate_manager_args(arg_parser)
    args = arg_parser.parse_args()

    manager, app = manager_from_args(args)
    try:
        job_config = __load_job_config(args)
        submit_job(manager, job_config)
        job_id = job_config.get('job_id')
        __wait_for_job_id(manager, job_id)
    except BaseException:
        log.exception("Failure submitting or waiting on job.")
    finally:
        app.shutdown()


def __wait_for_job_id(manager, job_id, poll_time=DEFAULT_POLL_TIME):
    while True:
        status = manager.get_status(job_id)
        if is_job_done(status):
            break
        time.sleep(poll_time)


def __load_job_config(args):
    if args.base64:
        base64_job_config = args.base64
        job_config = from_base64_json(base64_job_config)
    else:
        job_config = json.load(open(args.file, "r"))
    return job_config


def populate_manager_args(arg_parser):
    arg_parser.add_argument("--manager", default="_default_")
    arg_parser.add_argument("--app", default="main")
    arg_parser.add_argument("--ini_path", default=None)


def manager_from_args(args):
    manager_name = args.manager
    app_name = args.app
    ini_path = args.ini_path

    lwr_app = load_lwr_app(
        ini_path=ini_path,
        app_name=app_name,
        # Set message_queue_consume so this LWR app doesn't try to consume
        # setup/kill messages and only publishes status updates to configured
        # queue.
        message_queue_consume=False,
    )
    manager = lwr_app.managers[manager_name]
    return manager, lwr_app

if __name__ == "__main__":
    main()
