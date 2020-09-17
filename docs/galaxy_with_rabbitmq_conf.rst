.. _galaxy_with_rabbitmq_conf:

Message Queues with Galaxy and Pulsar
=====================================

Message Queues (MQs) allow securely connecting Galaxy to Pulsar servers.
MQs provide a transport method to allow the producer (Galaxy) to publish
messages (jobs) which consumers consume (Pulsar).

Message Queue Overview
----------------------

In brief terms, an MQ is simply a queue of arbitrary messages. The
messages themselves don't conform to any particular specification, and
require the service author to do the validation/parsing. This allows MQs
to be very efficient, lightweight services. There are a couple of key
concepts to understand MQs which will be covered here. If you're not
interested in the background terminology and an overview of
functionality in MQs, skip this section.

Galaxy and Pulsar both make use of the
`Kombu <http://pypi.python.org/pypi/kombu>`__ library for accessing MQs.
Kombu is an abstraction layer over a number of different queues,
allowing the deployer some choice in which service they'd like to use to
provide the Galaxy/Pulsar interaction. The `Kombu
introduction <http://kombu.readthedocs.org/en/latest/introduction.html>`__
is an excellent resource for those interested in a basic introduction to
building services with MQs. For the purpose of this documentation, we'll
be using AMQP urls.

AMQP Urls look like the following:

::

    amqp://guest:password@localhost:5672//

There is user/pass information supplied ahead of the server URL. It is
important to note the trailing ``/`` at the end, it's the **virtual
host**. By default, it is ``/``, but more can be configured. Within a
virtual host there can be several **exchanges**. Exchanges manage the
routing of messages from producers to consumers. Within an exchange,
there are one or more queues. For visual reference:

::

    AMQP Server -> Virtual Host -> Exchange -> Queue

Within a queue, **routing keys** are used to identify groups of
messages. Depending on the exchange type, the routing key helps
determine which consumer picks up a message. We are only concerned with
*direct exchanges* which require that the consumer and producer have
identical routing keys. Pulsar constructs the routing names with the
following snippet:

::

    pulsar%s__kill          # Job kill commands
    pulsar%s__setup         # Job submissions
    pulsar%s__status_update # Informs of job completions

where ``%s`` is the "Manager name", in Pulsar parlance.

Deploying RabbitMQ
------------------

For Ubuntu,

::

    $ sudo apt-get install rabbitmq-server

This will provide the command ``rabbitmqctl`` which can be run as root
to handle configuration. If you're new to MQs in general, you may be
interested in enabling the web GUI with:

::

    $ rabbitmq-plugins enable rabbitmq_management

This will listen on ``http://fqdn:15672`` and provide access to manage
and view queue/exchange/vhost information. The default username and
password are both "guest". This user is generally only allowed to login
on ``localhost``, though this restriction is disabled on the web
interface. (This is a security risk, in case that wasn't clear. Please
do not leave this up, unsecured!)

Locking it Down
~~~~~~~~~~~~~~~

As someone new to RabbitMQ, this may not be the best way to do this, but
it works for me. Seeing that ``guest:guest`` could access everything in
``/``, and not wanting to break other things that might depend on that
access, I created a separate virtual host without ``guest`` access.

.. code:: bash

    # Add a user specific to galaxy, allows us to restrict/manage logins
    sudo rabbitmqctl add_user galaxy some_long_password
    # Add the virtualhost
    sudo rabbitmqctl add_vhost galaxy
    # Grant permissions, allow configure/read/write to ALL exchanges in the galaxy virtualhost
    sudo rabbitmqctl set_permissions -p galaxy .* .* .*

Alternatively this can be done in the default virtual host:

.. code:: bash

    # Add a user specific to galaxy, allows us to restrict/manage logins
    sudo rabbitmqctl add_user galaxy some_long_password
    # Set permissions for the galaxy user, allow conf, read, and write on ONLY the "pulsar" exchange
    sudo rabbitmqctl set_permissions -p / galaxy pulsar pulsar pulsar

Configuring Galaxy
------------------

The Galaxy configuration portion is covered in :ref:`galaxy_conf`.

Configuring Pulsar
------------------

The Pulsar configuration portion is covered in :ref:`job_managers`.
