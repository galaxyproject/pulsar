Collection acknowledgment
=========================

Collection acknowledgment optionally protects Pulsar staging until its client
has imported the returned outputs and metadata. The facility applies to ordinary
managers independently of their execution backend. Existing clients retain
their current cleanup behavior.

Supporting servers advertise ``system_properties.collection_ack`` with
``schema: 1``. A compatible client explicitly opts a job into the protocol:

.. code-block:: python

    configuration = client.setup(require_collection_ack=True)
    client.launch(command_line, job_config=configuration)
    # Wait for terminal execution and import the returned outputs/metadata.
    client.acknowledge_collection()
    client.clean()

Setup confirms opt-in with ``require_collection_ack: true``. New clients reject
an unconfirmed remote request. For local/asynchronous setup, pass the returned
job configuration to launch so its opt-in reaches the server. Configure such
clients against a server supporting the advertised protocol.

For an opted-in job, cleanup requests before acknowledgment retain staging and
record a pending cleanup request. Acknowledgment records the client's successful
collection; if cleanup was already requested, it then performs that cleanup.
Acknowledgment alone does not delete an otherwise retained directory. Repeated
acknowledgment and cleanup are safe. Debug mode continues retaining files.

The HTTP acknowledgment operation is ``PUT /jobs/{job_id}/collection`` and
returns ``{"acknowledged": true}``. It uses the same authorization as other job
operations. Acknowledgment expresses client intent and belongs after terminal
execution and successful import. It does not itself validate imported data.

Jobs failing or being stopped before launch still have a cleanup path: after
recording their outcome and applying the client's retention policy, acknowledge
and clean them through the same API. No execution manifest is required.

Independent server processes coordinate acknowledgment and cleanup through one
stable lock outside individual job directories. The lock survives directory
deletion; it does not serialize job execution. Clients should keep diagnostics
when import fails rather than acknowledge collection prematurely.
