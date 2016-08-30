import collections
import logging
import os

from pulsar.client.util import to_base64_json
from pulsar.main import (
    PULSAR_ROOT_DIR,
)
from pulsar.mesos import (
    mesos_pb2,
    MesosSchedulerDriver,
    Scheduler,
)
from pulsar.messaging import bind_amqp


log = logging.getLogger(__name__)


DEFAULT_FRAMEWORK_USER = ""  # Let Mesos auto-fill this.
DEFAULT_FRAMEWORK_NAME = "Pulsar Framework"
DEFAULT_FRAMEWORK_PRINCIPAL = "Pulsar"

DEFAULT_EXECUTOR_ID = "default"
DEFAULT_EXECUTOR_NAME = "Pulsar Executor"
DEFAULT_EXECUTOR_SOURCE = "Pulsar"


class PulsarScheduler(Scheduler):

    def __init__(self, executor, manager_options, mesos_url):
        self.executor = executor
        self.manager_options = manager_options
        self.mesos_url = mesos_url

        self.taskData = {}
        self.tasksLaunched = 0
        self.tasksFinished = 0
        self.messagesSent = 0
        self.messagesReceived = 0
        # HACK: Storing these messages in a non-persistent queue is a bad idea,
        # obviously. Need something persistent - or possibly better - just not
        # removing them from message queue.
        self.in_memory_queue = collections.deque()

    def registered(self, driver, frameworkId, masterInfo):
        log.info("Registered with Pulsar mesos framework ID %s" % frameworkId.value)

    def resourceOffers(self, driver, offers):
        log.info("Got %d resource offers" % len(offers))
        for offer in offers:
            tasks = self._tasks_for_offer(offer)
            if tasks:
                log.info("Launching tasks %s" % tasks)
            try:
                driver.launchTasks(offer.id, tasks)
            except Exception:
                log.exception("Failed to launch tasks")
                raise

    def _tasks_for_offer(self, offer):
        tasks = []
        log.info("Got resource offer %s" % offer.id.value)
        try:
            next_job = self.in_memory_queue.pop()
        except IndexError:
            log.info("No jobs, skipping iteration")
            return tasks

        # TODO: This is also stupid... if we have any resource offer
        # we are assinging it one job. Should be some attempt here
        # to size jobs and match them to resources.
        tid = self.tasksLaunched
        self.tasksLaunched += 1

        log.info("Accepting offer on %s to start task %d" % (offer.hostname, tid))

        task = mesos_pb2.TaskInfo()
        task.task_id.value = str(tid)
        task.slave_id.value = offer.slave_id.value
        task.name = "task %d" % tid
        task.executor.MergeFrom(self.executor)

        self._populate_task_data_for_job(task, next_job)

        cpus = task.resources.add()
        cpus.name = "cpus"
        cpus.type = mesos_pb2.Value.SCALAR
        cpus.scalar.value = 1

        mem = task.resources.add()
        mem.name = "mem"
        mem.type = mesos_pb2.Value.SCALAR
        mem.scalar.value = 32

        tasks.append(task)
        self.taskData[task.task_id.value] = (
            offer.slave_id,
            task.executor.executor_id
        )
        return tasks

    def statusUpdate(self, driver, update):
        log.info("%s" % update.SerializeToString())
        if update.state == mesos_pb2.TASK_FINISHED:
            self.tasksFinished += 1
            slave_id, executor_id = self.taskData[update.task_id.value]
            self.messagesSent += 1
            driver.sendFrameworkMessage(
                executor_id,
                slave_id,
                'Update'
            )

    def frameworkMessage(self, driver, executorId, slaveId, message):
        self.messagesReceived += 1
        log.info("Received message: %s", repr(str(message)))

    def handle_setup_message(self, body, message):
        try:
            self.__queue_setup_message(body)
        finally:
            message.ack()

    def _populate_task_data_for_job(self, task, job):
        if "env" not in job:
            job["env"] = []

        job["env"].extend(self._mesos_env_vars())

        # In case job itself wants to utilize Mesos
        # populate environment variables.
        task_data = dict(
            job=job,
            manager=self.manager_options
        )
        task.data = to_base64_json(
            task_data
        )

    def __queue_setup_message(self, body):
        self.in_memory_queue.appendleft(body)

    def _mesos_env_vars(self):
        return [
            dict(name="MESOS_URL", value=self.mesos_url),
        ]


def run(master, manager_options, config):
    executor = mesos_pb2.ExecutorInfo()
    executor.executor_id.value = DEFAULT_EXECUTOR_ID
    executor.command.value = os.path.join(
        PULSAR_ROOT_DIR,
        "scripts",
        "mesos_executor"
    )
    executor.name = DEFAULT_EXECUTOR_NAME
    executor.source = DEFAULT_EXECUTOR_SOURCE

    framework = mesos_pb2.FrameworkInfo()
    framework.user = DEFAULT_FRAMEWORK_USER
    framework.name = DEFAULT_FRAMEWORK_NAME

    # TODO: Handle authenticate...
    framework.principal = DEFAULT_FRAMEWORK_PRINCIPAL

    scheduler = PulsarScheduler(
        executor,
        manager_options=manager_options,
        mesos_url=master,
    )
    driver = MesosSchedulerDriver(
        scheduler,
        framework,
        master
    )
    message_queue_url = config.get("message_queue_url", None)
    exchange = bind_amqp.get_exchange(
        message_queue_url,
        manager_name=manager_options["manager"],
        conf=config,
    )

    def drain():
        exchange.consume("setup", callback=scheduler.handle_setup_message, check=True)

    log.info("Binding to Pulsar framework to queue.")
    bind_amqp.start_setup_consumer(
        exchange,
        drain,
    )
    try:
        log.info("Starting Mesos driver")
        if driver.run() != mesos_pb2.DRIVER_STOPPED:
            raise Exception("Driver did not run properly")
    except Exception:
        log.exception("Problem running mesos scheduler")
        raise
    finally:
        driver.stop()
