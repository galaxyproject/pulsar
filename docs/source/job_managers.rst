-------------------------------
Job Managers
-------------------------------

By default the LWR will maintain its own queue of jobs. Alternatively, the LWR
can be configured to maintain multiple such queues with different properties
or to delegate to external job queues (via DRMAA, qsub/qstat CLI commands, or
Condor).

To change the default configuration, rename the file
``job_managers.ini.sample`` distributed with the LWR to ``job_managers.ini``
and modify it to reflect your desired configuration, and finally uncomment the
line ``#job_managers_config = job_managers.ini`` in ``server.ini``.

Likely the cleanest way to interface with an external queueing system is going
to be DRMAA. In this case, one should likely copy ``local_env.sh.sample`` to
``local_env.sh`` and update it to set ``DRMAA_LIBRARY_PATH`` to point to the
correct ``libdrmaa.so`` file. Also, the Python ``drmaa`` module must be
installed (see more information about `drmaa dependency <https://lwr.readthedocs.org/#job-managers>`).

Sample Configuration
--------------------

.. literalinclude:: ../../job_managers.ini.sample


Running Jobs As External User
-----------------------------

TODO: Fill out this section with information from `this thread <http://dev.list.galaxyproject.org/Managing-Data-Locality-tp4662438.html>`.
