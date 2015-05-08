.. :changelog:

History
-------

.. to_doc

------------------------
0.5.0 (2015-05-08)
------------------------

* Allow cURL downloader to resume transfers during staging in (thanks to
  @natefoo). 0c61bd9_
* Fix to cURL downloaders status code handling (thanks to @natefoo). 86f95ce_
* Fix non-wheel installs from PyPI. `Issue 72`_
* Fix mesos imports for newer versions of mesos (thanks to @kellrott). fe3e919_
* More, better logging. 2b3942d_, fa2b6dc_

------------------------
0.4.0 (2015-04-20)
------------------------

* Python 3 support. `Pull Request 62`_
* Fix bug encountered when running ``pulsar-main`` and ``pulsar-config`` commands as scripts. 9d43ae0_
* Add ``pulsar-run`` script for issues commands against a Pulsar server (experimental). 3cc7f74_

------------------------
0.3.0 (2015-04-12)
------------------------

* Changed the name of project to Pulsar, moved to Github.
* New RESTful web services interface.
* SCP and Rsync file staging options added by Eric Rasche. `Pull 
  Request <https://github.com/galaxyproject/pulsar/pull/34>`__
* Allow YAML based configuration.
* Support for more traditional ``pip``/``setup.py``-style
  installs.
* Dozens of smaller bugfixes and documentation updates.

---------------------
0.2.0
---------------------

* Last version named the LWR - found on `BitBucket <https://bitbucket.org/jmchilton/lwr>`__.
* Still supported in Galaxy as of 15.03 the release.
* Introduced support for submitting to various queueing systems,
  operation as a Mesos framework, Docker support, and
  various other advanced deployment options.
* Message queue support.
* Framework for configurable file actions introduced.

---------------------
0.1.0
---------------------

* Simple support for running jobs managed by the Python LWR
  web process.
* https://bitbucket.org/jmchilton/lwr/branch/0.1

---------------------
0.0.1
---------------------

* See the original `announcement <http://dev.list.galaxyproject.org/New-Remote-Job-Runner-td4138951.html>`__
  and `initial commit <https://github.com/galaxyproject/pulsar/commit/163ed48d5a1902ceb84c38f10db8cbe5a0c1039d>`__.


.. github_links
.. _fe3e919: https://github.com/galaxyproject/pulsar/commit/fe3e919
.. _2b3942d: https://github.com/galaxyproject/pulsar/commit/2b3942d
.. _fa2b6dc: https://github.com/galaxyproject/pulsar/commit/fa2b6dc
.. _0c61bd9: https://github.com/galaxyproject/pulsar/commit/0c61bd9
.. _86f95ce: https://github.com/galaxyproject/pulsar/commit/86f95ce
.. _Issue 72: https://github.com/galaxyproject/pulsar/issues/72
.. _3cc7f74: https://github.com/galaxyproject/pulsar/commit/3cc7f74
.. _9d43ae0: https://github.com/galaxyproject/pulsar/commit/9d43ae0
.. _Pull Request 62: https://github.com/galaxyproject/pulsar/pull/62
