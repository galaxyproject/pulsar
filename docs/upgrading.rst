----------------------
Upgrading from the LWR
----------------------

Pulsar was born out of the poorly named `LWR
<https://bitbucket.org/jmchilton/lwr>`_ developed for the `Galaxy-P
<https://usegalaxyp.org/>`_ project. This section outlines broadly how
to upgrade from an LWR server to a Pulsar one.

The tentative plan is to allow Galaxy to support both targets for
sometime - but at some point LWR servers should be upgraded to the
Pulsar servers.

Rough plan:

- Download/clone Pulsar.
- Rebuild dependencies (and/or virtualenv) if needed.
- Copy the LWR's server.ini to Pulsar's root directory.
- Update ``app_factory`` property: ``paste.app_factory = pulsar.web.wsgi:app_factory``
- Rename ``private_key`` property in ``server.ini`` to ``private_token``.
- Replace logging section with new pulsar logging section from `server.ini.sample`.
- If you were using the default values for ``persistence_directory`` and ``staging_directory`` you may wish to update those to the new defaults as well.


On Galaxy client side:

- Open job_conf.xml and replace all LWR plugin definitions
  (``galaxy.jobs.runners.lwr:LwrJobRunner``) with Pulsar ones
  (``galaxy.jobs.runners.pulsar:PulsarLegacyJobRunner``).
- This plugin should behave largely like the LWR one but a few attributes `param` ids are different. The plugin param `url` has changed to `amqp_url` and the destination param `remote_lwr_directory` has become `remote_pulsar_directory`.
