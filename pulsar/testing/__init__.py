"""Test-support code for exercising Pulsar over its real wire protocols.

Shipped inside the distribution, alongside :mod:`pulsar.client.test`, so it is
importable by name rather than by an accident of ``sys.path``.

``pulsar.testing.recorder``
    A pure-stdlib accumulator for the job-status events Galaxy would receive,
    with the ordering rules Galaxy's own job-state processor enforces. It makes
    no assumptions about how those events were produced, which is why it sits
    here rather than under a suite-specific subpackage -- ``docs/error_handling``
    points at it as the reference implementation of those rules.

``pulsar.testing.resilience``
    The docker-compose harness that drives ``test/resilience``: build setup
    messages, steer the Pulsar and broker containers, inject faults, and wait on
    recorded status transitions. Needs only ``requests``, already a Pulsar
    dependency, but it is wired to that specific stack -- service names, host
    port mappings and the compose file's own layout -- so treat it as this
    suite's support code rather than a general-purpose API.

Downstream consumers -- Galaxy included, via ``pulsar-galaxy-lib`` -- get these
without vendoring a copy.
"""
