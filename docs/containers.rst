.. _containers:

-------------------------------
Containers
-------------------------------

Galaxy and Shared File Systems
-------------------------------

Galaxy can be configured to run Pulsar with traditional job managers and just submit jobs
that launch containers. Simply setting ``docker_enabled`` on the job environment in Galaxy's
job_conf.yml file will accomplish this.

There are limitations to using DRM systems that submit job scripts that launch containers
though. Modern container scheduling environments (AWS Batch or Kubernetes or instance) are
capable of scheduling containers directly. This is conceptually cleaner, persumably scales better,
and side steps all sorts of issues for the deployer and developer such as configuring Docker and
managing the interaction between the DRM and the container host server (i.e. the Docker server).

There are a couple approaches to scheduling containers directly in Galaxy - such as the Galaxy
Kubernetes runner and the Galaxy AWS Batch runner. These approaches require Galaxy be deployed
alongside the compute infrasture (i.e. on Amazon with the same EFS volume or inside of Kubernetes
with the same mounts).

These two scenarios and some of their limitations are described below.

.. figure:: gx_aws_deployment.plantuml.svg

   Deployment diagram for Galaxy's AWS Batch job runner.

.. figure:: gx_k8s_deployment.plantuml.svg

   Deployment diagram for Galaxy's Kubernetes job runner.

The most glaring disadvantage of not using Pulsar in the above scenarios is that Galaxy must
be deployed in the same container with the same mounts as the job execution environment. This
prevents leveraging external cloud compute, multi-cloud compute, and makes it unsuitable for
common Galaxy use cases such as large public instances, Galaxy's leveraging institution non-cloud
storage, etc... Even within the same cloud - a large shared file system can be an expensive prospect
and Pulsar may allow making use of buckets and such more tractable. Finally, Pulsar offers more
options in terms of how to collect metadata which can have big implications in terms of metadata.

Co-execution
-------------------------------

Galaxy job inputs and outputs are very flexible and staging up job inputs, configs, and scripts,
and staging down results doesn't map cleanly to cloud APIs and cannot be fully reasoned about
until job runtime. For this reason, code that needs to know how stage Galaxy jobs up and down needs
to run in the cloud when disk isn't shared and Galaxy cannot do this directly. Galaxy jobs however
are typically executed in Biocontainers that are minimal containers just for the tool being executed
and not appropriate for executing Galaxy code.

For this reason, the Pulsar runners that schedule containers will run a container beside (or before
and after) that is responsible for staging the job up and down, communicating with Galaxy, etc..

Perhaps the most typical potential scenario is using the Kubernetes Job API along with a message queue
for communication with Galaxy and a Biocontainer. A diagram for this deployment would look something
like:

.. figure:: pulsar_k8s_coexecution_mq_deployment.plantuml.svg

The modern Galaxy landscape is much more container driven, but the setup can be simplified to use
Galaxy dependency resolution from within the "pulsar" container. This allows the tool and the staging
code to live side-by-side and results in requesting only one container for the execution from the target
container. The default Pulsar staging container has a conda environment configured out of the box and
has some initial tooling to be connected to a CVM-FS available conda directory.

This one-container approach (staging+conda) is available with or without MQ and on either Kubernetes
or against a GA4GH TES server. The TES version of this with RabbitMQ to mitigate communication looks
like:

.. figure:: pulsar_tes_coexecution_mq_deployment.plantuml.svg

Notice when executing jobs on Kubernetes, the containers of the pod run concurrrently. The Pulsar container
will compute a command-line and write it out, the tool container will wait for it on boot and execute it
when available, while the Pulsar container waits for a return code from the tool container to proceed to
staging out the job. In the GA4GH TES case, 3 containers are used instead of 2, but they run sequentially
one at a time.

Typically, a MQ is needed to communicate between Pulsar and Galaxy even though the status of the job
could potentially be inferred from the container scheduling environment. This is because Pulsar needs
to transfer information about job state, etc. after the job is complete.

More experimentally this shouldn't be needed if extended metadata is being collected because then the
whole job state that needs to be ingested by Galaxy should be populated as part of the job. In this case
it may be possible to get away without a MQ.

.. figure:: pulsar_k8s_coexecution_deployment.plantuml.svg

Deployment Scenarios
-------------------------------

Kubernetes
~~~~~~~~~~

.. figure:: pulsar_k8s_coexecution_mq_deployment.plantuml.svg

   Kuberentes job execution with a biocontainer for the tool and RabbitMQ for communicating with
   Galaxy.

.. figure:: pulsar_k8s_mq_deployment.plantuml.svg

   Kuberentes job execution with Conda dependencies for the tool and RabbitMQ for communicating with
   Galaxy.

.. figure:: pulsar_k8s_coexecution_deployment.plantuml.svg

   Kuberentes job execution with a biocontainer for the tool and no message queue.

.. figure:: pulsar_k8s_deployment.plantuml.svg

   Kuberentes job execution with Conda dependencies for the tool and no message queue.

GA4GH TES
~~~~~~~~~~

.. figure:: pulsar_tes_coexecution_mq_deployment.plantuml.svg

   GA4GH TES job execution with a biocontainer for the tool and RabbitMQ for communicating with
   Galaxy.

.. figure:: pulsar_tes_mq_deployment.plantuml.svg

   GA4GH TES job execution with Conda dependencies for the tool and RabbitMQ for communicating with
   Galaxy.

.. figure:: pulsar_tes_coexecution_deployment.plantuml.svg

   GA4GH TES job execution with a biocontainer for the tool and no message queue.

.. figure:: pulsar_tes_deployment.plantuml.svg

   GA4GH TES job execution with Conda dependencies for the tool and no message queue.

AWS Batch
~~~~~~~~~~

Work in progress.
