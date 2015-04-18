import sys
import threading

from pulsar.mesos import (
    Executor,
    MesosExecutorDriver,
    mesos_pb2,
    ensure_mesos_libs,
)
from pulsar.client.util import from_base64_json
from pulsar.scripts.submit_util import (
    manager_from_args,
    wait_for_job
)
from pulsar.manager_endpoint_util import submit_job

from pulsar.main import (
    ArgumentParser,
    PulsarManagerConfigBuilder,
)

import logging
log = logging.getLogger(__name__)

DESCRIPTION = "Mesos executor for Pulsar"


class PulsarExecutor(Executor):

    def __task_update(self, driver, task, state, data=None):
        try:
            log.debug("Sending status update...")
            update = mesos_pb2.TaskStatus()
            update.task_id.value = task.task_id.value
            update.state = state
            if data:
                update.data = data

            driver.sendStatusUpdate(update)
        except Exception:
            log.exception("Failed to update status of task.")

    def launchTask(self, driver, task):
        # Create a thread to run the task. Tasks should always be run in new
        # threads or processes, rather than inside launchTask itself.
        def run_task():
            try:
                log.info("Running task %s" % task.task_id.value)
                task_data = from_base64_json(task.data)
                manager_options = task_data["manager"]
                config_builder = PulsarManagerConfigBuilder(**manager_options)
                manager, pulsar_app = manager_from_args(config_builder)
                job_config = task_data["job"]
                submit_job(manager, job_config)
                self.__task_update(driver, task, mesos_pb2.TASK_RUNNING)
                wait_for_job(manager, job_config)
                self.__task_update(driver, task, mesos_pb2.TASK_FINISHED)
                pulsar_app.shutdown()
            except Exception:
                log.exception("Failed to run, update, or monitor task %s" % task)
                raise

        thread = threading.Thread(target=run_task)
        thread.start()

    def frameworkMessage(self, driver, message):
        # Send it back to the scheduler.
        driver.sendFrameworkMessage(message)


def run_executor(argv=None):
    arg_parser = ArgumentParser(description=DESCRIPTION)
    arg_parser.parse_args(argv)

    ensure_mesos_libs()
    log.info("Starting Pulsar executor")
    driver = MesosExecutorDriver(PulsarExecutor())
    exit_code = 0
    if not driver.run() == mesos_pb2.DRIVER_STOPPED:
        exit_code = 1
    return exit_code


def main(argv=None):
    sys.exit(run_executor(argv))


if __name__ == "__main__":
    main()
