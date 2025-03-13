.. :changelog:

History
-------

.. to_doc

---------------------
0.15.7 (2025-03-13)
---------------------
* Fix transfer of remote directories (thanks to `@mvdbeek`_). `Pull Request 385`_
* Add health check endpoint (thanks to `@nuwang`_). `Pull Request 382`_
* Prepare dirs from Galaxy, to properly recover resubmitted jobs (thanks to
  `@natefoo`_). `Pull Request 380`_
* Replace obsolete package types-pkg-resources with types-setuptools (thanks
  to `@nuwang`_). `Pull Request 383`_
* Drop nose (thanks to `@neoformit`_). `Pull Request 333`_
* Open tool file contents in `rb` (thanks to `@mvdbeek`_). `Pull Request 372`_
* Do not attempt to complete pre- or post-process if jobs are cancelled in the
  middle of either stage (thanks to `@natefoo`_). `Pull Request 365`_
* Update job_managers.rst (thanks to `@peterg1t`_). `Pull Request 360`_
* Send accept-encoding: identity to get correct content-length on head …
  (thanks to `@mvdbeek`_). `Pull Request 361`_

---------------------
0.15.6 (2024-01-15)
---------------------
* Allow tus uploads to Galaxy.
  `Pull Request 351`_

---------------------
0.15.5 (2023-09-15)
---------------------
* Add catchall OSError to recoverable exceptions (thanks to `@mvdbeek`_).
  `Pull Request 338`_

---------------------
0.15.4 (2023-08-29)
---------------------
* Add .readthedocs.yaml (thanks to `@natefoo`_). `Pull Request 332`_
* Add explicit TimeoutError catching (thanks to `@mvdbeek`_). `Pull Request 337`_
* Update galaxy-job-metrics requirement (thanks to `@cat-bro`_). `Pull Request 334`_

---------------------
0.15.3 (2023-07-20)
---------------------
* Fix Pulsar consumer state after ``ConnectionResetError``. `Pull Request 331`_
* User auth plugins (thanks to `@SergeyYakubov`_). `Pull Request 321`_

---------------------
0.15.2 (2023-05-02)
---------------------
* Fix Pulsar and Pulsar client reconnection to AMQP server. `Pull Request 324`_
* Reduce verbosity of timeout exception catching. `Pull Request 325`_

---------------------
0.15.1 (2023-04-13)
---------------------
* No changes, working around pypi isssue.

---------------------
0.15.0 (2023-04-13)
---------------------

* Updated Galaxy+Pulsar container. `Pull Request 306`_
* Rework container execution - generalize Kubernetes execution to allow it to work without a
  message queue and to allow TES execution based on pydantic-tes (https://github.com/jmchilton/pydantic-tes). `Pull Request 302`_
* Add documentation and diagrams for container execution scenarios. `Pull Request 302`_
* Rework integration tests to use pytest more aggressively.
* Fixes to CI to run more tests that weren't being executed because Tox was not sending
  environment variables through to pytest.
* Add option ``amqp_key_prefix`` to direct task queue naming while retaining simple
  default manager names and such in container scheduling deployments. `Pull Request 315`_
* Various typing and CI fixes. `Pull Request 312`_, `Pull Request 319`_
* Fixes for extra_file handling. `Pull Request 318`_
* Separate tool_stdio and job_stdio handling. `Pull Request 318`_
* Re-import MEMORY_STATEMENT.sh from Galaxy. `Pull Request 297`_
* Add support for logging to sentry. `Pull Request 322`_

---------------------
0.14.16 (2022-10-04)
---------------------

* Fix small regression related to building URLs for client action mapping.

---------------------
0.14.15 (2022-10-03)
---------------------

* Fix small regressions bugs in 0.14.14 - updating runner util code was bigger swap over
  than it seemed.

---------------------
0.14.14 (2022-10-30)
---------------------

* Bring in updated Galaxy runner util code. `Pull Request 303`_
* Fix recovering "lost" jobs where the job directory does not exist at
  startup/recovery time (thanks to `@natefoo`_). `Pull Request 301`_
* Use urlencode to encode path (thanks to `@mvdbeek`_). `Pull Request 299`_
* Support the k8s_job_ttl_secs_after_finished option as in the Galaxy
  Kubernetes runner (thanks to `@natefoo`_). `Pull Request 287`_

---------------------
0.14.13 (2021-12-06)
---------------------

* Don't pass all environment variables to jobs launched by `Manager` (thanks
  to `@nsoranzo`_).
  `Pull Request 295`_
* Drop legacy job conf for Galaxy framework tests, test against
  ``metadata_strategy: extended`` (thanks to `@mvdbeek`_).
  `Pull Request 294`_

---------------------
0.14.12 (2021-11-10)
---------------------

* Fixes to bring HOME and temp directory handling closer to Galaxy native runners.
* Enable globbed from_work_dir outputs for remote metadata.

---------------------
0.14.11 (2021-07-19)
---------------------

* Fix and test for returncode handling in certain cases. `Pull Request 274`_
* Modernize tox. `Pull Request 271`_

---------------------
0.14.10 (2021-07-17)
---------------------

* Don't error out if annotated galaxy.json is absent. `Pull Request 270`_

---------------------
0.14.9 (2021-07-16)
---------------------

* Implement dynamic file sources abstraction for parsing files to transfer
  from ``galaxy.json`` files. `Pull Request 269`_
* Use tool classes to only test remote Galaxy tools. `Pull Request 266`_
* Run Galaxy framework tests against dev and master branches of Galaxy (thanks
  to `@mvdbeek`_). `Pull Request 264`_

---------------------
0.14.8 (2021-07-14)
---------------------

* Fix Galaxy composite input references. `Pull Request 262`_
* Run galaxy's tool framework tests against this repo's pulsar (thanks to
  `@mvdbeek`_). `Pull Request 259`_
    
---------------------
0.14.7 (2021-07-13)
---------------------

* Accept description of tool files to transfer from Galaxy.
  `Pull Request 261`_
* Support globs in from_work_dir outputs (thanks to `@natefoo`_).
  `Pull Request 257`_
* Fix loading the Galaxy dependency resolvers config, plus additional config
  directory fixes (thanks to `@natefoo`_). `Pull Request 256`_

---------------------
0.14.6 (2021-05-24)
---------------------

* Fix for newer Galaxy tool profiles having isolated home directories.

---------------------
0.14.5 (2021-04-15)
---------------------

* Potential fix for setting file actions via job destination parameters.

---------------------
0.14.4 (2021-04-14)
---------------------

* Re-attempt release process - published wrong branch with 0.14.3.

---------------------
0.14.3 (2021-04-13)
---------------------

* Allow transferring fewer files from Pulsar when using extended metadata with
  Galaxy.

---------------------
0.14.2 (2021-02-15)
---------------------

* Fix the use of requests, limits, and walltime with coexecution pods. `Pull Request 246`_

---------------------
0.14.1 (2021-02-02)
---------------------

* Fix the use of named managers with coexecution pods. `Pull Request 242`_

---------------------
0.14.0 (2020-09-17)
---------------------

* fix the PyYAML "load() deprecation" warning (thanks to `@gmauro`_). `Pull
  Request 232`_
* Set the DRMAA workingDirectory to the job's working directory
  `Pull Request 230`_
* Fix a unicode issue and polish a bit of variables (thanks to `@gmauro`_).
  `Pull Request 229`_
* Respond to MQ messages requesting status updates. `Pull Request 228`_
* Fix REST connections broken with Py3 using standard transport `Issue 227`_
  `Pull Request 231`_
* Drop Python 2.7 support in standard transport, drop Python 2.7 tests and fix
  Python 3.7 wheel install test, general test debugging enhancements.
  `Pull Request 231`_
* drop python 2.6 and add 3.7 and update the testing infrastructure to a more
  recent Ubuntu setup (thanks to `@bgruening`_). `Pull Request 226`_
* Use is_alive in favour of isAlive for Python 3.9 compatibility (thanks to
  `@tirkarthi`_). `Issue 224`_ `Pull Request 225`_
* Request and register ports for Galaxy ITs when using Kubernetes.
  `Pull Request 223`_
* Implement killing k8s jobs. `Pull Request 221`_
* Respond to MQ messages requesting status updates.
  `Pull Request 228`_
* Drop python 2.6 and add 3.7 and update the testing infrastructure to a more
  recent Ubuntu setup (thanks to `@bgruening`_). `Pull Request 226`_
* Add a more descriptive message in case of error parsing an external id
  (thanks to `@gmauro`_). `Pull Request 213`_
* Use requests (thanks to `@mvdbeek`_). `Pull Request 216`_
* Use is_alive in favour of isAlive for Python 3.9 compatibility (thanks to
  `@tirkarthi`_). `Pull Request 225`_
* Debug connection string for AMQP.
  `Pull Request 217`_
* Various small Kubernetes fixes and enhancements.
  `Pull Request 218`_, `Pull Request 219`_
* Improvements and fixes to container handling.
  `Pull Request 202`_
* Fix a typo in exception logging thanks to @erasche.
  `Pull Request 203`_
* Cleanup config file handling a bit by removing branch for very
  old Pulsar servers likely no longer supported.
  `Pull Request 201`_

---------------------
0.13.1 (2020-09-16)
---------------------

* Pinned all listed requirements. This is the final version of Pulsar to support Python 2.

---------------------
0.13.0 (2019-06-25)
---------------------

* Various improvements and simplifications to Kubernetes job execution.

---------------------
0.12.1 (2019-06-03)
---------------------

* Retry botched release that didn't include all relevant commits.

---------------------
0.12.0 (2019-06-03)
---------------------

* Revise Python Galaxy dependencies to use newer style Galaxy decomposition.
  galaxy-lib can no longer be installed in Pulsar's environment, so you will
  likely need to rebuild your Pulsar virtualenv for this release.
  `Pull Request 187`_
* Add a ``Dockerfile`` for Pulsar with CVMFS (thanks to `@nuwang`_ and `@afgane`).
  `Pull Request 166`_
* Various small improvements to Kubernetes pod execution environment.
  `Pull Request 190`_
* Improve readme linting.
  `Pull Request 186`_
* Update example docs for Condor (thanks to `@bgruening`_).
  `Pull Request 189`_

---------------------
0.11.0 (2019-05-16)
---------------------

* Implement staging Galaxy metadata input files in the client.
  39de377_
* Fix 'amqp_ack_republish_time' in sample (thanks to `@dannon`_).
  `Pull Request 185`_
* Updated amqp_url in job_conf_sample_mq_rsync.xml (thanks to `@AndreasSko`_).
  `Pull Request 184`_
* Use wildcard char for pulsar version (thanks to `@VJalili`_).
  `Pull Request 181`_
* Refactor toward more structured inputs. f477bc4_
* Refactor toward passing objectstore identifying information around.
  `Pull Request 180`_
* Rework imports for new Galaxy library structure. da086c9_
* Revert empty input testing, it really probably should cause a failure
  to transfer a non-existent file.
  8bd5511_
* Better client mapper documentation. b6278b4_

---------------------
0.10.0 (2019-05-06)
---------------------

* Implement support for Kubernetes two container pod jobs - staging and
  tool execution as separate containers in the same job's pod.
  `Pull Request 176`_, `Pull Request 178`_

---------------------
0.9.1 (2019-05-01)
---------------------

* Fix duplicate inputs being a problem when staging Galaxy files.
  `Pull Request 175`_
* Fix deprecated ``assertEquals()`` (thanks to @nsoranzo). `Pull Request 173`_
* Fix a method missing problem. `Pull Request 174`_
* Sync "recent" galaxy runner util changes. `Pull Request 177`_

---------------------
0.9.0 (2019-04-12)
---------------------
    
* Add configuration parameter to limit stream size read from disk. `Pull
  Request 157`_
* Pass full job status for failed and lost jobs. `Pull Request 159`_
* Improve message handling if problems occur during job setup/staging. `Pull
  Request 160`_
* Rework preprocessing job state to improve restartability and reduce job loss.
  **This change should be applied while no jobs are running.**
  `Pull Request 164`_
* Add support for overriding config through environment variables (thanks to
  @nuwang). `Pull Request 165`_
* Minor docs updates (thanks to @afgane). `Pull Request 170`_
* Python 3 fixes in Pulsar client (thanks to `@mvdbeek`_). `Pull Request 172`_

---------------------
0.8.3 (2018-02-08)
---------------------

* Create universal wheels to enable Python 3 support when installing from PyPI
  (thanks to @nsoranzo).
  `Pull Request 156`_

---------------------
0.8.1 (2018-02-08)
---------------------

* Update link for logo image. `Pull Request 145`_
* Minor error and log message typos (thanks to @blankenberg).
  `Pull Request 146`_, `Pull Request 153`_
* Fixes/improvements for catching quoted tool files. `Pull Request 148`_
* Fix config sample parsing so run.sh works out of the box.
  `Pull Request 149`_

---------------------
0.8.0 (2017-09-21)
---------------------

* Support new features in Galaxy job running/scripting so that Pulsar respects
  ``$GALAXY_VIRTUAL_ENV`` and ``$PRESERVE_GALAXY_ENVIRONMENT``. Fix remote
  metadata in cases where the tool environment changes the ``python`` on
  ``$PATH``. `Pull Request 137`_
* Precreate Galaxy tool outputs on the remote before executing (fixes a bug
  related to missing output files on stage out). `Pull Request 141`_
* Support the remote_transfer file action without setting the
  ``jobs_directory`` destination param `Pull Request 136`_
* Fix invalid character in job managers documentation (thanks to @mapa17).
  `Pull Request 130`_
* Fix ``conda_auto_*`` option resolution and include a sample
  ``dependency_resolvers_conf.xml`` (thanks to @mapa17). `Pull Request 132`_
* Fix tox/Travis tests. `Pull Request 138`_, `Pull Request 139`_,
  `Pull Request 140`_
* Fix a bug with AMQP acknowledgement. `Pull Request 143`_

---------------------
0.7.4 (2017-02-07)
---------------------

* Fix Conda resolution and add a test case. 11ce744_
* Style fixes for updated flake8 libraries. 93ab8a1_, 3573341_
* Remove unused script. 929bffa_
* Fixup README. 629fdea_
    

---------------------
0.7.3 (2016-10-31)
---------------------

* Fix  "AttributeError" when submitting a job as a real user.
  `Pull Request 124`_, `Issue 123`_

---------------------
0.7.2 (2016-08-31)
---------------------

* Fix bug causing loops on in response to preprocessing error conditions.

---------------------
0.7.1 (2016-08-29)
---------------------

* Do a release to circumvent a tool version logic error in Galaxy (
  released Galaxy versions think 0.7.0 < 0.7.0.dev3).

---------------------
0.7.0 (2016-08-26)
---------------------

* Update Makefile to allow release pulsar as an application and a library 
  for Galaxy at the same time.
* Small update to test scripts for TravisCI changes.
* Improvements for embedded Galaxy runner. (TODO: fill this out)
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
* SCP and Rsync file staging options added by E. Rasche. `Pull 
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
.. _Pull Request 385: https://github.com/galaxyproject/pulsar/pull/385
.. _Pull Request 382: https://github.com/galaxyproject/pulsar/pull/382
.. _Pull Request 380: https://github.com/galaxyproject/pulsar/pull/380
.. _Pull Request 383: https://github.com/galaxyproject/pulsar/pull/383
.. _Pull Request 333: https://github.com/galaxyproject/pulsar/pull/333
.. _Pull Request 372: https://github.com/galaxyproject/pulsar/pull/372
.. _Pull Request 365: https://github.com/galaxyproject/pulsar/pull/365
.. _Pull Request 360: https://github.com/galaxyproject/pulsar/pull/360
.. _Pull Request 361: https://github.com/galaxyproject/pulsar/pull/361

.. _Pull Request 351: https://github.com/galaxyproject/pulsar/pull/351
.. _Pull Request 338: https://github.com/galaxyproject/pulsar/pull/338
.. _Pull Request 332: https://github.com/galaxyproject/pulsar/pull/332
.. _Pull Request 337: https://github.com/galaxyproject/pulsar/pull/337
.. _Pull Request 334: https://github.com/galaxyproject/pulsar/pull/334
.. _Pull Request 331: https://github.com/galaxyproject/pulsar/pull/331
.. _Pull Request 321: https://github.com/galaxyproject/pulsar/pull/321
.. _Pull Request 325: https://github.com/galaxyproject/pulsar/pull/325
.. _Pull Request 324: https://github.com/galaxyproject/pulsar/pull/324
.. _Pull Request 322: https://github.com/galaxyproject/pulsar/pull/322
.. _Pull Request 318: https://github.com/galaxyproject/pulsar/pull/318
.. _Pull Request 319: https://github.com/galaxyproject/pulsar/pull/319
.. _Pull Request 312: https://github.com/galaxyproject/pulsar/pull/312
.. _Pull Request 315: https://github.com/galaxyproject/pulsar/pull/315
.. _Pull Request 306: https://github.com/galaxyproject/pulsar/pull/306
.. _Pull Request 297: https://github.com/galaxyproject/pulsar/pull/297
.. _Pull Request 302: https://github.com/galaxyproject/pulsar/pull/302
.. _Pull Request 303: https://github.com/galaxyproject/pulsar/pull/303
.. _Pull Request 301: https://github.com/galaxyproject/pulsar/pull/301
.. _Pull Request 299: https://github.com/galaxyproject/pulsar/pull/299
.. _Pull Request 295: https://github.com/galaxyproject/pulsar/pull/295
.. _Pull Request 294: https://github.com/galaxyproject/pulsar/pull/294
.. _Pull Request 287: https://github.com/galaxyproject/pulsar/pull/287
.. _Pull Request 271: https://github.com/galaxyproject/pulsar/pull/271
.. _Pull Request 274: https://github.com/galaxyproject/pulsar/pull/274
.. _Pull Request 270: https://github.com/galaxyproject/pulsar/pull/270
.. _Pull Request 269: https://github.com/galaxyproject/pulsar/pull/269
.. _Pull Request 266: https://github.com/galaxyproject/pulsar/pull/266
.. _Pull Request 264: https://github.com/galaxyproject/pulsar/pull/264
.. _Pull Request 262: https://github.com/galaxyproject/pulsar/pull/262
.. _Pull Request 259: https://github.com/galaxyproject/pulsar/pull/259
.. _Pull Request 261: https://github.com/galaxyproject/pulsar/pull/261
.. _Pull Request 257: https://github.com/galaxyproject/pulsar/pull/257
.. _Pull Request 256: https://github.com/galaxyproject/pulsar/pull/256
.. _Pull Request 246: https://github.com/galaxyproject/pulsar/pull/246
.. _Pull Request 242: https://github.com/galaxyproject/pulsar/pull/242
.. _Pull Request 232: https://github.com/galaxyproject/pulsar/pull/232
.. _Pull Request 230: https://github.com/galaxyproject/pulsar/pull/230
.. _Pull Request 229: https://github.com/galaxyproject/pulsar/pull/229
.. _Pull Request 228: https://github.com/galaxyproject/pulsar/pull/228
.. _Pull Request 231: https://github.com/galaxyproject/pulsar/pull/231
.. _Issue 227: https://github.com/galaxyproject/pulsar/issues/227
.. _Pull Request 226: https://github.com/galaxyproject/pulsar/pull/226
.. _Pull Request 225: https://github.com/galaxyproject/pulsar/pull/225
.. _Issue 224: https://github.com/galaxyproject/pulsar/issues/224
.. _Pull Request 228: https://github.com/galaxyproject/pulsar/pull/228
.. _Pull Request 226: https://github.com/galaxyproject/pulsar/pull/226
.. _Pull Request 213: https://github.com/galaxyproject/pulsar/pull/213
.. _Pull Request 216: https://github.com/galaxyproject/pulsar/pull/216
.. _Pull Request 225: https://github.com/galaxyproject/pulsar/pull/225
.. _Pull Request 223: https://github.com/galaxyproject/pulsar/pull/223
.. _Pull Request 217: https://github.com/galaxyproject/pulsar/pull/217
.. _Pull Request 218: https://github.com/galaxyproject/pulsar/pull/218
.. _Pull Request 219: https://github.com/galaxyproject/pulsar/pull/219
.. _Pull Request 221: https://github.com/galaxyproject/pulsar/pull/221
.. _Pull Request 202: https://github.com/galaxyproject/pulsar/pull/202
.. _Pull Request 203: https://github.com/galaxyproject/pulsar/pull/203
.. _Pull Request 201: https://github.com/galaxyproject/pulsar/pull/201
.. _Pull Request 190: https://github.com/galaxyproject/pulsar/pull/190
.. _Pull Request 166: https://github.com/galaxyproject/pulsar/pull/166
.. _Pull Request 186: https://github.com/galaxyproject/pulsar/pull/186
.. _Pull Request 187: https://github.com/galaxyproject/pulsar/pull/187
.. _Pull Request 189: https://github.com/galaxyproject/pulsar/pull/189
.. _Pull Request 185: https://github.com/galaxyproject/pulsar/pull/185
.. _Pull Request 184: https://github.com/galaxyproject/pulsar/pull/184
.. _Pull Request 181: https://github.com/galaxyproject/pulsar/pull/181
.. _Pull Request 180: https://github.com/galaxyproject/pulsar/pull/180
.. _da086c9: https://github.com/galaxyproject/pulsar/commit/da086c9
.. _8bd5511: https://github.com/galaxyproject/pulsar/commit/8bd5511
.. _b6278b4: https://github.com/galaxyproject/pulsar/commit/b6278b4
.. _39de377: https://github.com/galaxyproject/pulsar/commit/39de377
.. _f477bc4: https://github.com/galaxyproject/pulsar/commit/f477bc4
.. _Pull Request 178: https://github.com/galaxyproject/pulsar/pull/178
.. _Pull Request 176: https://github.com/galaxyproject/pulsar/pull/176
.. _Pull Request 173: https://github.com/galaxyproject/pulsar/pull/173
.. _Pull Request 174: https://github.com/galaxyproject/pulsar/pull/174
.. _Pull Request 175: https://github.com/galaxyproject/pulsar/pull/175
.. _Pull Request 177: https://github.com/galaxyproject/pulsar/pull/177
.. _Pull Request 172: https://github.com/galaxyproject/pulsar/pull/172
.. _Pull Request 170: https://github.com/galaxyproject/pulsar/pull/170
.. _Pull Request 165: https://github.com/galaxyproject/pulsar/pull/165
.. _Pull Request 164: https://github.com/galaxyproject/pulsar/pull/164
.. _Pull Request 160: https://github.com/galaxyproject/pulsar/pull/160
.. _Pull Request 159: https://github.com/galaxyproject/pulsar/pull/159
.. _Pull Request 157: https://github.com/galaxyproject/pulsar/pull/157
.. _Pull Request 156: https://github.com/galaxyproject/pulsar/pull/156
.. _Pull Request 145: https://github.com/galaxyproject/pulsar/pull/145
.. _Pull Request 146: https://github.com/galaxyproject/pulsar/pull/146
.. _Pull Request 148: https://github.com/galaxyproject/pulsar/pull/148
.. _Pull Request 149: https://github.com/galaxyproject/pulsar/pull/149
.. _Pull Request 153: https://github.com/galaxyproject/pulsar/pull/153
.. _Pull Request 143: https://github.com/galaxyproject/pulsar/pull/143
.. _Pull Request 141: https://github.com/galaxyproject/pulsar/pull/141
.. _Pull Request 136: https://github.com/galaxyproject/pulsar/pull/136
.. _Pull Request 137: https://github.com/galaxyproject/pulsar/pull/137
.. _Pull Request 140: https://github.com/galaxyproject/pulsar/pull/140
.. _Pull Request 139: https://github.com/galaxyproject/pulsar/pull/139
.. _Pull Request 138: https://github.com/galaxyproject/pulsar/pull/138
.. _Pull Request 132: https://github.com/galaxyproject/pulsar/pull/132
.. _Pull Request 130: https://github.com/galaxyproject/pulsar/pull/130
.. _11ce744: https://github.com/galaxyproject/pulsar/commit/11ce744
.. _3573341: https://github.com/galaxyproject/pulsar/commit/3573341
.. _93ab8a1: https://github.com/galaxyproject/pulsar/commit/93ab8a1
.. _929bffa: https://github.com/galaxyproject/pulsar/commit/929bffa
.. _629fdea: https://github.com/galaxyproject/pulsar/commit/629fdea
.. _Pull Request 124: https://github.com/galaxyproject/pulsar/pull/124
.. _Issue 123: https://github.com/galaxyproject/pulsar/issues/123
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
.. _@dannon: https://github.com/dannon
.. _@AndreasSko: https://github.com/AndreasSko
.. _@VJalili: https://github.com/VJalili
.. _@nuwang: https://github.com/nuwang
.. _@afgane: https://github.com/afgane
.. _@bgruening: https://github.com/bgruening
.. _@gmauro: https://github.com/gmauro
.. _@mvdbeek: https://github.com/mvdbeek
.. _@tirkarthi: https://github.com/tirkarthi
.. _@natefoo: https://github.com/natefoo
.. _@nsoranzo: https://github.com/nsoranzo
.. _@SergeyYakubov: https://github.com/SergeyYakubov
.. _@cat-bro: https://github.com/cat-bro
.. _@peterg1t: https://github.com/peterg1t
.. _@neoformit: https://github.com/neoformit
