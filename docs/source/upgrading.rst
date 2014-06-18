----------------------
Upgrading from the LWR
----------------------

Pulsar was born out of the previously, poorly named project the ``LWR``. The tenative plan is to allow Galaxy to support both targets for sometime - but at some point LWR servers should be upgraded to the Pulsar servers.

Rough plan:

- Download/clone Pulsar.
- Rebuild dependencies (and/or virtualenv) if needed.
- Copy the LWR's server.ini to Pulsar's root directory.
- Update ``app_factory`` property: ``paste.app_factory = pulsar.web.wsgi:app_factory``
