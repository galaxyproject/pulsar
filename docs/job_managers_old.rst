.. _job-managers-old:

-------------------------------
Job Managers
-------------------------------

By default the Pulsar will maintain its own queue of jobs. Under Linux
however, Pulsar can be configured to maintain multiple such queues with
different properties or to delegate to external job queues (via DRMAA,
qsub/qstat CLI commands, or Condor).

``app.yml.sample`` demonstrates an 

Likely the cleanest way to interface with an external queueing system is going
to be DRMAA. In this case, one should likely copy ``local_env.sh.sample`` to
``local_env.sh`` and update it to set ``DRMAA_LIBRARY_PATH`` to point to the
correct ``libdrmaa.so`` file. Also, the Python ``drmaa`` module must be
installed (e.g. via ``pip install drmaa``).

Sample Configuration
--------------------

.. literalinclude:: old_job_managers.ini.sample


Running Jobs As External User
-----------------------------

TODO: Fill out this section with information from `this thread
<http://dev.list.galaxyproject.org/Managing-Data-Locality-tp4662438.html>`_.
