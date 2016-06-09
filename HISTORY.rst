.. :changelog:

History
-------

.. to_doc

---------------------
0.7.0.dev5
---------------------

* Improvements for embedded Galaxy runner. (TODO: fill this out)

---------------------
0.7.0.dev4
---------------------

* Improvements for embedded Galaxy runner. (TODO: fill this out and fix date)

---------------------
0.7.0.dev3
---------------------

* Remove support for Python 2.6. 60bf962_
* Update docs to describe project goverance and reuse Galaxy's
  Code of Conduct. 7e23d43_, dc47140_
* Updated cluster slots detection for SLURM from Galaxy. cadfc5a_
* Various changes to allow usage within Galaxy as a library. ce9d4f9_
* Various changes to allow embedded Pulsar managers within Galaxy.
  ce9d4f9_, d262323_, 8f7c04a_
* Introduce a separate working and metadata directory as required for
  Galaxy 16.04 that requires this separation. 6f4328e_
* Improve logging and comments. 38953f3_, a985107_, ad33cb9_
* Add Tox target for Python 2.7 unit testing. d7c524e_
* Add ``Makefile`` command for setup.py develop. fd82d00_

---------------------
0.6.1 (2015-12-23)
---------------------

* Tweak release process that left 0.6.0 with an incorrect PyPI description page.

---------------------
0.6.0 (2015-12-23)
---------------------

* Pulsar now depends on the new ``galaxy-lib`` Python package instead of
  manually synchronizing Python files across Pulsar and Galaxy.
* Numerous build and testing improvements.
* Fixed a documentation bug in the code (thanks to @erasche). e8814ae_
* Remove galaxy.eggs stuff from Pulsar client (thanks to @natefoo). 00197f2_
* Add new logo to README (thanks to @martenson). abbba40_
* Implement an optional awknowledgement system on top of the message queue
  system (thanks to @natefoo). `Pull Request 82`_ 431088c_
* Documentation fixes thanks to @remimarenco. `Pull Request 78`_, `Pull Request 80`_
* Fix project script bug introduced this cycle (thanks to @nsoranzo). 140a069_
* Fix config.py on Windows (thanks to @ssorgatem). `Pull Request 84`_
* Add a job manager for XSEDE jobs (thanks to @natefoo). 1017bc5_
* Fix pip dependency installation (thanks to @afgane) `Pull Request 73`_

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
.. _ad33cb9: https://github.com/galaxyproject/pulsar/commit/ad33cb9
.. _d7c524e: https://github.com/galaxyproject/pulsar/commit/d7c524e
.. _fd82d00: https://github.com/galaxyproject/pulsar/commit/fd82d00
.. _a985107: https://github.com/galaxyproject/pulsar/commit/a985107
.. _38953f3: https://github.com/galaxyproject/pulsar/commit/38953f3
.. _6f4328e: https://github.com/galaxyproject/pulsar/commit/6f4328e
.. _8f7c04a: https://github.com/galaxyproject/pulsar/commit/8f7c04a
.. _cadfc5a: https://github.com/galaxyproject/pulsar/commit/cadfc5a
.. _d262323: https://github.com/galaxyproject/pulsar/commit/d262323
.. _ce0636a: https://github.com/galaxyproject/pulsar/commit/ce0636a
.. _ce9d4f9: https://github.com/galaxyproject/pulsar/commit/ce9d4f9
.. _dc47140: https://github.com/galaxyproject/pulsar/commit/dc47140
.. _7e23d43: https://github.com/galaxyproject/pulsar/commit/7e23d43
.. _60bf962: https://github.com/galaxyproject/pulsar/commit/60bf962
.. _Pull Request 73: https://github.com/galaxyproject/pulsar/pull/73
.. _1017bc5: https://github.com/galaxyproject/pulsar/commit/1017bc5
.. _Pull Request 84: https://github.com/galaxyproject/pulsar/pull/84
.. _140a069: https://github.com/galaxyproject/pulsar/commit/140a069
.. _Pull Request 78: https://github.com/galaxyproject/pulsar/pull/78
.. _Pull Request 80: https://github.com/galaxyproject/pulsar/pull/80
.. _Pull Request 82: https://github.com/galaxyproject/pulsar/pull/82
.. _abbba40: https://github.com/galaxyproject/pulsar/commit/abbba40
.. _00197f2: https://github.com/galaxyproject/pulsar/commit/00197f2
.. _431088c: https://github.com/galaxyproject/pulsar/commit/431088c
.. _e8814ae: https://github.com/galaxyproject/pulsar/commit/e8814ae
.. _fe3e919: https://github.com/galaxyproject/pulsar/commit/fe3e919
.. _2b3942d: https://github.com/galaxyproject/pulsar/commit/2b3942d
.. _fa2b6dc: https://github.com/galaxyproject/pulsar/commit/fa2b6dc
.. _0c61bd9: https://github.com/galaxyproject/pulsar/commit/0c61bd9
.. _86f95ce: https://github.com/galaxyproject/pulsar/commit/86f95ce
.. _Issue 72: https://github.com/galaxyproject/pulsar/issues/72
.. _3cc7f74: https://github.com/galaxyproject/pulsar/commit/3cc7f74
.. _9d43ae0: https://github.com/galaxyproject/pulsar/commit/9d43ae0
.. _Pull Request 62: https://github.com/galaxyproject/pulsar/pull/62
