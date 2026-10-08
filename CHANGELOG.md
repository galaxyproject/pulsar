
# History

<!-- towncrier release notes start -->

## 0.15.16 (2026-10-08)

- Send tool stdout and stderr to Galaxy while the job is running, enabled with
  `send_stdout_update` and tuned with `stdout_update_interval`,
  `stdout_update_timeout` and `stdout_update_chunk_size` (thanks to
  [@gecage952](https://github.com/gecage952)). [Pull Request 503](https://github.com/galaxyproject/pulsar/pull/503)
- Recover jobs that were postprocessing when Pulsar restarted instead of losing
  them. [Issue 354](https://github.com/galaxyproject/pulsar/issues/354), [Issue 393](https://github.com/galaxyproject/pulsar/issues/393), [Pull Request 519](https://github.com/galaxyproject/pulsar/pull/519)
- Support configuring the AMQP heartbeat interval with `amqp_heartbeat`, or
  disabling heartbeats with `false` or `0` (thanks to [@natefoo](https://github.com/natefoo)).
  [Pull Request 502](https://github.com/galaxyproject/pulsar/pull/502)
- Allow a `user_mapping_script` for the `queued_external_drmaa` manager,
  mapping the client-supplied user name to a local user when submitting as the
  real user (thanks to [@bernt-matthias](https://github.com/bernt-matthias)). [Pull Request 451](https://github.com/galaxyproject/pulsar/pull/451)
- Add native `cvmfsexec` support to Pulsar managers (`mountrepo` and
  `namespace` modes), configured via a `cvmfsexec` manager option or a
  per-job override, for accessing CVMFS repositories (and CVMFS-hosted
  container images) on hosts without a system-wide `/cvmfs` (thanks to
  [@natefoo](https://github.com/natefoo)). [Pull Request 475](https://github.com/galaxyproject/pulsar/pull/475)
- Add a dedicated `container` file-action path type for rewriting resolved
  container image paths (e.g. a Singularity/Apptainer image on CVMFS) via a
  `rewrite` action, without overloading the `unstructured` tool-parameter
  path type. **Note:** `path_types: "*any*"` now also matches container image
  paths. [Pull Request 475](https://github.com/galaxyproject/pulsar/pull/475)
- Size GCP Batch jobs from the requested `cores` and `mem`, selecting a
  machine type when `machine_type` is not configured (thanks to
  [@ksuderman](https://github.com/ksuderman)). [Pull Request 493](https://github.com/galaxyproject/pulsar/pull/493)
- Support a custom GCP Batch VM boot disk image (`custom_vm_image`) and size
  (`boot_disk_size_gb`) (thanks to [@ksuderman](https://github.com/ksuderman)). [Pull Request 472](https://github.com/galaxyproject/pulsar/pull/472)
- Report DRM-side job failures as `failed` instead of `complete` (thanks to
  [@gkr0110](https://github.com/gkr0110)), and make `failed` terminal in `StatefulManagerProxy` so such
  jobs are deactivated, staged back, and reported to the client.
  [Pull Request 485](https://github.com/galaxyproject/pulsar/pull/485)
- Fail the job instead of reporting success with missing outputs when an
  infrastructure error (disk full, I/O error, transport error) blocks output
  collection or working directory stage out (thanks to [@ksuderman](https://github.com/ksuderman)).
  [Pull Request 467](https://github.com/galaxyproject/pulsar/pull/467), [Pull Request 505](https://github.com/galaxyproject/pulsar/pull/505)
- Fix a job recovery startup race where the monitor could poll recovered jobs
  before their external IDs were restored, without losing the `lost` status
  notification when recovery fails (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 496](https://github.com/galaxyproject/pulsar/pull/496)
- Follow redirects in the curl transport, restart downloads the server cannot
  resume, and keep TUS uploads when Pulsar rebuilds a `remote_transfer_tus`
  action. **Note:** `remote_transfer_tus` now really uses TUS, so servers
  without `tuspy` fail stage out instead of silently falling back to a POST
  (thanks to [@nuwang](https://github.com/nuwang)). [Pull Request 526](https://github.com/galaxyproject/pulsar/pull/526)
- Send `MessageJobClient.get_status()` requests to the `status` queue
  instead of `setup`, and publish `failed` statuses when setup fails before
  the job directory is readable. [Pull Request 532](https://github.com/galaxyproject/pulsar/pull/532)
- Cap tool stdout and stderr in status responses at 64 KiB, so a large
  `maximum_stream_size` cannot produce an oversized completion message
  (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 499](https://github.com/galaxyproject/pulsar/pull/499)
- Keep the end of tool and job stdout/stderr when trimming them to
  `maximum_stream_size` and to the 64 KiB completion-status limit, instead of
  only the start. The end is usually where a failing tool explains why.
  Document `maximum_stream_size` in `app.yml.sample`. [Issue 158](https://github.com/galaxyproject/pulsar/issues/158),
  [Pull Request 524](https://github.com/galaxyproject/pulsar/pull/524)
- Use the task ID recorded by TES for polling and cancellation instead of the
  Galaxy job ID. [Pull Request 491](https://github.com/galaxyproject/pulsar/pull/491)
- Close leaked file, pycurl and requests handles (thanks to [@mvdbeek](https://github.com/mvdbeek)).
  [Pull Request 500](https://github.com/galaxyproject/pulsar/pull/500)
- Report malformed `env` entries in job destinations clearly instead of
  crashing while building environment statements (thanks to [@natefoo](https://github.com/natefoo)).
  [Pull Request 504](https://github.com/galaxyproject/pulsar/pull/504)
- `pulsar-chown-working-directory` runs `chown` without a shell and exits
  non-zero when it fails. Previously a failed `chown` went unnoticed by the
  `queued_external_drmaa` manager, which checks the script's exit status.
- Honor daemon-control arguments in `--mode webless`, preserve daemon logs
  in `pulsar.log`, and add a `daemon` installation extra (thanks to
  [@gkr0110](https://github.com/gkr0110)). [Pull Request 494](https://github.com/galaxyproject/pulsar/pull/494)
- Remove the `__PULSAR_JOBS_DIRECTORY__` destination token, which never
  worked. Substitution only ever reached the job's command line, so staged
  config files, metadata and tool scripts kept the literal token. The command
  line was broken too: Galaxy re-derives the job and tool directories from the
  working directory with `os.path.abspath`, which on a relative token path
  splices in Galaxy's own working directory, so a single command mixed a
  correct `/staging/<id>/working` with a `/galaxy/cwd//staging/<id>`
  job directory and tool_files path. `tool_script.sh` lives in the job
  directory, so little could run. Set `jobs_directory` to the staging path
  configured on the Pulsar side instead. The per-job
  `__PULSAR_JOB_DIRECTORY__` token used by `rewrite` file actions is
  unaffected. [Pull Request 515](https://github.com/galaxyproject/pulsar/pull/515)
- Remove the experimental Apache Mesos framework and executor. Apache Mesos has
  been retired to the Apache Attic, the `mesos.native` bindings the code
  imported were only ever distributed with a Mesos build, and nothing here has
  had a functional change since 2015. [Pull Request 511](https://github.com/galaxyproject/pulsar/pull/511)
- Bind Pulsar to the manager name Galaxy returns from compute-resource
  registration rather than to the relay `sub` claim. `pulsar-config register-with-galaxy` wrote the wrong name into `app.yml`, so registration
  reported success while jobs stayed queued (thanks to [@dSizovs](https://github.com/dSizovs)).
  [Pull Request 514](https://github.com/galaxyproject/pulsar/pull/514)
- Require that manager name: `register-with-galaxy` no longer falls back to
  the relay `sub` and no longer proposes a name in the registration payload
  (Galaxy mints its own and ignores ours). A registration response without a
  manager name now fails loudly instead of writing an `app.yml` bound to a
  guessed name (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 516](https://github.com/galaxyproject/pulsar/pull/516)
- Document Galaxy and Pulsar compatibility per modality (REST, message queue,
  relay, coexecution) in a new `Galaxy Compatibility` docs page generated
  from `docs/compatibility.yml`. [Pull Request 536](https://github.com/galaxyproject/pulsar/pull/536)
- Document the release-branch process (`master` carries the next minor,
  `release_0.N` its point releases) and replace the old release targets with
  `make release-check`, `make release`, `make release-branch`, and
  `make push-release`. Backfill this section with every PR merged since
  0.15.15. [Pull Request 540](https://github.com/galaxyproject/pulsar/pull/540), [Pull Request 543](https://github.com/galaxyproject/pulsar/pull/543)
- Document `min_polling_interval` in `app.yml.sample` (thanks to
  [@martenson](https://github.com/martenson)). [Pull Request 379](https://github.com/galaxyproject/pulsar/pull/379)
- Documentation fixes for running jobs as the real user, AMQP queue
  durability, and typos and grammar (thanks to [@bernt-matthias](https://github.com/bernt-matthias),
  [@mvdbeek](https://github.com/mvdbeek), and [@martincarrere](https://github.com/martincarrere)). [Pull Request 424](https://github.com/galaxyproject/pulsar/pull/424),
  [Pull Request 474](https://github.com/galaxyproject/pulsar/pull/474), [Pull Request 495](https://github.com/galaxyproject/pulsar/pull/495), [Pull Request 497](https://github.com/galaxyproject/pulsar/pull/497)
- Add type annotations to the job managers (thanks to [@bernt-matthias](https://github.com/bernt-matthias)).
  [Pull Request 427](https://github.com/galaxyproject/pulsar/pull/427)
- Replace flake8 with ruff, check import order with isort in CI, and type check
  with Pyrefly alongside mypy (`tox -e pyrefly`), pinning both checkers in
  `dev-requirements.txt`. [Pull Request 489](https://github.com/galaxyproject/pulsar/pull/489), [Pull Request 507](https://github.com/galaxyproject/pulsar/pull/507),
  [Pull Request 539](https://github.com/galaxyproject/pulsar/pull/539)
- Harden GitHub workflows following zizmor recommendations and move CI to
  `ubuntu-24.04` (thanks to [@nsoranzo](https://github.com/nsoranzo)). [Pull Request 478](https://github.com/galaxyproject/pulsar/pull/478),
  [Pull Request 506](https://github.com/galaxyproject/pulsar/pull/506), [Pull Request 508](https://github.com/galaxyproject/pulsar/pull/508)
- Fix the resilience harness readiness checks, move it into `pulsar.testing`,
  and make the persistence and WSGI tests poll instead of sleeping (thanks to
  [@nuwang](https://github.com/nuwang)). [Pull Request 487](https://github.com/galaxyproject/pulsar/pull/487), [Pull Request 488](https://github.com/galaxyproject/pulsar/pull/488), [Pull Request 509](https://github.com/galaxyproject/pulsar/pull/509),
  [Pull Request 525](https://github.com/galaxyproject/pulsar/pull/525), [Pull Request 528](https://github.com/galaxyproject/pulsar/pull/528), [Pull Request 531](https://github.com/galaxyproject/pulsar/pull/531),
  [Pull Request 534](https://github.com/galaxyproject/pulsar/pull/534)

## 0.15.15 (2026-07-13)
- Bump up minimum Python versions for tests (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 437](https://github.com/galaxyproject/pulsar/pull/437)
- Drop use of `distutils`, `pkg_resources`, and `stopit` (thanks to
  [@nsoranzo](https://github.com/nsoranzo)). [Pull Request 438](https://github.com/galaxyproject/pulsar/pull/438)
- Paste to Gunicorn (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 440](https://github.com/galaxyproject/pulsar/pull/440)
- Fail fast on permanent HTTP errors during staging (thanks to [@mvdbeek](https://github.com/mvdbeek)).
  [Pull Request 444](https://github.com/galaxyproject/pulsar/pull/444)
- Add Python 3.12, 3.13, and 3.14 support (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 446](https://github.com/galaxyproject/pulsar/pull/446)
- Force-copy input metadata files when `default_file_action` is `none`
  (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 449](https://github.com/galaxyproject/pulsar/pull/449)
- Harden Pulsar's job lifecycle against restart, broker, and Galaxy outages
  (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 448](https://github.com/galaxyproject/pulsar/pull/448)
- Make sudo calls return stdout as `str` (thanks to [@bernt-matthias](https://github.com/bernt-matthias)).
  [Pull Request 450](https://github.com/galaxyproject/pulsar/pull/450)
- Drop poster, default to requests-based transport (thanks to [@natefoo](https://github.com/natefoo)).
  [Pull Request 453](https://github.com/galaxyproject/pulsar/pull/453)
- Pin the Bookworm Docker image and restrict the wheel glob to Python 3
  (thanks to [@martincarrere](https://github.com/martincarrere)). [Pull Request 455](https://github.com/galaxyproject/pulsar/pull/455)
- Use `sphinx_rtd_theme` for documentation (thanks to [@natefoo](https://github.com/natefoo)). [Pull Request 456](https://github.com/galaxyproject/pulsar/pull/456)
- Update Galaxy job configuration documentation to use YAML syntax (thanks to
  [@natefoo](https://github.com/natefoo)). [Pull Request 457](https://github.com/galaxyproject/pulsar/pull/457)
- Bootstrap pulsar-relay credentials through the OIDC device flow (thanks to
  [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 454](https://github.com/galaxyproject/pulsar/pull/454)
- Publish capability snapshots to the relay for Galaxy BYOC (thanks to
  [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 458](https://github.com/galaxyproject/pulsar/pull/458)
- Sync Galaxy BYOC bootstrap URLs with the `compute_resources` rename
  (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 459](https://github.com/galaxyproject/pulsar/pull/459)
- Block on Kombu producer-pool acquisition rather than raising
  `LimitExceeded` (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 461](https://github.com/galaxyproject/pulsar/pull/461)
- Fix pytest 9.1 duplicate parametrization error (thanks to [@ksuderman](https://github.com/ksuderman)).
  [Pull Request 464](https://github.com/galaxyproject/pulsar/pull/464)
- Fix queued_cli Slurm completion detection (thanks to [@dSizovs](https://github.com/dSizovs)). [Pull Request 460](https://github.com/galaxyproject/pulsar/pull/460)
- Fix documentation typos (thanks to [@jeis4wpi](https://github.com/jeis4wpi)). [Pull Request 462](https://github.com/galaxyproject/pulsar/pull/462)
- Fix GCP Batch co-execution deadlocks (thanks to [@ksuderman](https://github.com/ksuderman)). [Pull Request 466](https://github.com/galaxyproject/pulsar/pull/466)
- Drain relay poll waiters on stop or kill (thanks to [@ksuderman](https://github.com/ksuderman)). [Pull Request 470](https://github.com/galaxyproject/pulsar/pull/470)

## 0.15.14 (2025-01-20)
- Fix install_wheel test by switching to docker and disabling
  `outputs_to_working_directory` (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 436](https://github.com/galaxyproject/pulsar/pull/436)
- Add no-op BaseAction.write_from_path for actions that don't need staging
  (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 435](https://github.com/galaxyproject/pulsar/pull/435)

## 0.15.13 (2026-01-12)
- Restrict collection of dynamic working dir output to specified directory
  (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 432](https://github.com/galaxyproject/pulsar/pull/432)
- Documentation fixes (thanks to [@nsoranzo](https://github.com/nsoranzo)). [Pull Request 433](https://github.com/galaxyproject/pulsar/pull/433)
- Implement pulsar-relay retry handling, improve message resume (thanks to
  [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 421](https://github.com/galaxyproject/pulsar/pull/421)
- Better cleanup after external DRMAA and condor jobs (thanks to [@bernt-matthias](https://github.com/bernt-matthias)).
  [Pull Request 429](https://github.com/galaxyproject/pulsar/pull/429)

## 0.15.12 (2025-11-28)

- Avoid pastescript for config file parsing (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 426](https://github.com/galaxyproject/pulsar/pull/426)
- Fix relay docs (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 420](https://github.com/galaxyproject/pulsar/pull/420)
- Add pulsar relay mode (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 419](https://github.com/galaxyproject/pulsar/pull/419)
- CI improvements and type annotations (thanks to [@nsoranzo](https://github.com/nsoranzo)). [Pull Request 418](https://github.com/galaxyproject/pulsar/pull/418)

## 0.15.11 (2025-09-30)

- Support collecting dirs via `from_work_dir` (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 410](https://github.com/galaxyproject/pulsar/pull/410)
- Enable dependabot version updates for GitHub actions (thanks to
  [@nsoranzo](https://github.com/nsoranzo)). [Pull Request 411](https://github.com/galaxyproject/pulsar/pull/411)
- Update release information docs. [Pull Request 409](https://github.com/galaxyproject/pulsar/pull/409)

## 0.15.10 (2025-09-04)

- Implement GCP Batch co-execution job runner.
  [Pull Request 404](https://github.com/galaxyproject/pulsar/pull/404)
- Customizable Pulsar test file server port and files endpoint
  (thanks to [@kysrpex](https://github.com/kysrpex)). [Pull Request 406](https://github.com/galaxyproject/pulsar/pull/406)

## 0.15.9 (2025-07-17)
- Support HTCondor in CLUSTER_SLOTS_STATEMENT.sh (thanks to [@kysrpex](https://github.com/kysrpex)).
  [Pull Request 405](https://github.com/galaxyproject/pulsar/pull/405)
- BasicAuth for PulsarTesRunner (thanks to [@BorisYourich](https://github.com/BorisYourich)). [Pull Request 391](https://github.com/galaxyproject/pulsar/pull/391)
- Move `get_pulsar_app_config()` and `_ensure_manager_config()`  (thanks to
  [@jmchilton](https://github.com/jmchilton)). [Pull Request 402](https://github.com/galaxyproject/pulsar/pull/402)

## 0.15.8 (2025-06-09)
- Add a deploy CI workflow (thanks to [@nsoranzo](https://github.com/nsoranzo)). [Pull Request 387](https://github.com/galaxyproject/pulsar/pull/387)
- Fix staging location of legacy tool files (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 398](https://github.com/galaxyproject/pulsar/pull/398)
- Add procps so we can inspect running processes from within pulsar (thanks to
  [@nuwang](https://github.com/nuwang)). [Pull Request 397](https://github.com/galaxyproject/pulsar/pull/397)
- Share docker group between pulsar and dind (thanks to [@nuwang](https://github.com/nuwang)). [Pull Request 396](https://github.com/galaxyproject/pulsar/pull/396)
- Add dind and apptainer support (thanks to [@nuwang](https://github.com/nuwang)). [Pull Request 395](https://github.com/galaxyproject/pulsar/pull/395)
- Docker image for kubernetes helm chart (thanks to [@nuwang](https://github.com/nuwang)). [Pull Request 378](https://github.com/galaxyproject/pulsar/pull/378)

## 0.15.7 (2025-03-13)
- Fix transfer of remote directories (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 385](https://github.com/galaxyproject/pulsar/pull/385)
- Add health check endpoint (thanks to [@nuwang](https://github.com/nuwang)). [Pull Request 382](https://github.com/galaxyproject/pulsar/pull/382)
- Prepare dirs from Galaxy, to properly recover resubmitted jobs (thanks to
  [@natefoo](https://github.com/natefoo)). [Pull Request 380](https://github.com/galaxyproject/pulsar/pull/380)
- Replace obsolete package types-pkg-resources with types-setuptools (thanks
  to [@nuwang](https://github.com/nuwang)). [Pull Request 383](https://github.com/galaxyproject/pulsar/pull/383)
- Drop nose (thanks to [@neoformit](https://github.com/neoformit)). [Pull Request 333](https://github.com/galaxyproject/pulsar/pull/333)
- Open tool file contents in `rb` (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 372](https://github.com/galaxyproject/pulsar/pull/372)
- Do not attempt to complete pre- or post-process if jobs are cancelled in the
  middle of either stage (thanks to [@natefoo](https://github.com/natefoo)). [Pull Request 365](https://github.com/galaxyproject/pulsar/pull/365)
- Update job_managers.rst (thanks to [@peterg1t](https://github.com/peterg1t)). [Pull Request 360](https://github.com/galaxyproject/pulsar/pull/360)
- Send accept-encoding: identity to get correct content-length on head …
  (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 361](https://github.com/galaxyproject/pulsar/pull/361)

## 0.15.6 (2024-01-15)
- Allow tus uploads to Galaxy.
  [Pull Request 351](https://github.com/galaxyproject/pulsar/pull/351)

## 0.15.5 (2023-09-15)
- Add catchall OSError to recoverable exceptions (thanks to [@mvdbeek](https://github.com/mvdbeek)).
  [Pull Request 338](https://github.com/galaxyproject/pulsar/pull/338)

## 0.15.4 (2023-08-29)
- Add .readthedocs.yaml (thanks to [@natefoo](https://github.com/natefoo)). [Pull Request 332](https://github.com/galaxyproject/pulsar/pull/332)
- Add explicit TimeoutError catching (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 337](https://github.com/galaxyproject/pulsar/pull/337)
- Update galaxy-job-metrics requirement (thanks to [@cat-bro](https://github.com/cat-bro)). [Pull Request 334](https://github.com/galaxyproject/pulsar/pull/334)

## 0.15.3 (2023-07-20)
- Fix Pulsar consumer state after `ConnectionResetError`. [Pull Request 331](https://github.com/galaxyproject/pulsar/pull/331)
- User auth plugins (thanks to [@SergeyYakubov](https://github.com/SergeyYakubov)). [Pull Request 321](https://github.com/galaxyproject/pulsar/pull/321)

## 0.15.2 (2023-05-02)
- Fix Pulsar and Pulsar client reconnection to AMQP server. [Pull Request 324](https://github.com/galaxyproject/pulsar/pull/324)
- Reduce verbosity of timeout exception catching. [Pull Request 325](https://github.com/galaxyproject/pulsar/pull/325)

## 0.15.1 (2023-04-13)
- No changes, working around pypi isssue.

## 0.15.0 (2023-04-13)

- Updated Galaxy+Pulsar container. [Pull Request 306](https://github.com/galaxyproject/pulsar/pull/306)
- Rework container execution - generalize Kubernetes execution to allow it to work without a
  message queue and to allow TES execution based on pydantic-tes (https://github.com/jmchilton/pydantic-tes). [Pull Request 302](https://github.com/galaxyproject/pulsar/pull/302)
- Add documentation and diagrams for container execution scenarios. [Pull Request 302](https://github.com/galaxyproject/pulsar/pull/302)
- Rework integration tests to use pytest more aggressively.
- Fixes to CI to run more tests that weren't being executed because Tox was not sending
  environment variables through to pytest.
- Add option `amqp_key_prefix` to direct task queue naming while retaining simple
  default manager names and such in container scheduling deployments. [Pull Request 315](https://github.com/galaxyproject/pulsar/pull/315)
- Various typing and CI fixes. [Pull Request 312](https://github.com/galaxyproject/pulsar/pull/312), [Pull Request 319](https://github.com/galaxyproject/pulsar/pull/319)
- Fixes for extra_file handling. [Pull Request 318](https://github.com/galaxyproject/pulsar/pull/318)
- Separate tool_stdio and job_stdio handling. [Pull Request 318](https://github.com/galaxyproject/pulsar/pull/318)
- Re-import MEMORY_STATEMENT.sh from Galaxy. [Pull Request 297](https://github.com/galaxyproject/pulsar/pull/297)
- Add support for logging to sentry. [Pull Request 322](https://github.com/galaxyproject/pulsar/pull/322)

## 0.14.16 (2022-10-04)

- Fix small regression related to building URLs for client action mapping.

## 0.14.15 (2022-10-03)

- Fix small regressions bugs in 0.14.14 - updating runner util code was bigger swap over
  than it seemed.

## 0.14.14 (2022-10-30)

- Bring in updated Galaxy runner util code. [Pull Request 303](https://github.com/galaxyproject/pulsar/pull/303)
- Fix recovering "lost" jobs where the job directory does not exist at
  startup/recovery time (thanks to [@natefoo](https://github.com/natefoo)). [Pull Request 301](https://github.com/galaxyproject/pulsar/pull/301)
- Use urlencode to encode path (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 299](https://github.com/galaxyproject/pulsar/pull/299)
- Support the k8s_job_ttl_secs_after_finished option as in the Galaxy
  Kubernetes runner (thanks to [@natefoo](https://github.com/natefoo)). [Pull Request 287](https://github.com/galaxyproject/pulsar/pull/287)

## 0.14.13 (2021-12-06)

- Don't pass all environment variables to jobs launched by `Manager` (thanks
  to [@nsoranzo](https://github.com/nsoranzo)).
  [Pull Request 295](https://github.com/galaxyproject/pulsar/pull/295)
- Drop legacy job conf for Galaxy framework tests, test against
  `metadata_strategy: extended` (thanks to [@mvdbeek](https://github.com/mvdbeek)).
  [Pull Request 294](https://github.com/galaxyproject/pulsar/pull/294)

## 0.14.12 (2021-11-10)

- Fixes to bring HOME and temp directory handling closer to Galaxy native runners.
- Enable globbed from_work_dir outputs for remote metadata.

## 0.14.11 (2021-07-19)

- Fix and test for returncode handling in certain cases. [Pull Request 274](https://github.com/galaxyproject/pulsar/pull/274)
- Modernize tox. [Pull Request 271](https://github.com/galaxyproject/pulsar/pull/271)

## 0.14.10 (2021-07-17)

- Don't error out if annotated galaxy.json is absent. [Pull Request 270](https://github.com/galaxyproject/pulsar/pull/270)

## 0.14.9 (2021-07-16)

- Implement dynamic file sources abstraction for parsing files to transfer
  from `galaxy.json` files. [Pull Request 269](https://github.com/galaxyproject/pulsar/pull/269)
- Use tool classes to only test remote Galaxy tools. [Pull Request 266](https://github.com/galaxyproject/pulsar/pull/266)
- Run Galaxy framework tests against dev and master branches of Galaxy (thanks
  to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 264](https://github.com/galaxyproject/pulsar/pull/264)

## 0.14.8 (2021-07-14)

- Fix Galaxy composite input references. [Pull Request 262](https://github.com/galaxyproject/pulsar/pull/262)
- Run galaxy's tool framework tests against this repo's pulsar (thanks to
  [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 259](https://github.com/galaxyproject/pulsar/pull/259)
    
## 0.14.7 (2021-07-13)

- Accept description of tool files to transfer from Galaxy.
  [Pull Request 261](https://github.com/galaxyproject/pulsar/pull/261)
- Support globs in from_work_dir outputs (thanks to [@natefoo](https://github.com/natefoo)).
  [Pull Request 257](https://github.com/galaxyproject/pulsar/pull/257)
- Fix loading the Galaxy dependency resolvers config, plus additional config
  directory fixes (thanks to [@natefoo](https://github.com/natefoo)). [Pull Request 256](https://github.com/galaxyproject/pulsar/pull/256)

## 0.14.6 (2021-05-24)

- Fix for newer Galaxy tool profiles having isolated home directories.

## 0.14.5 (2021-04-15)

- Potential fix for setting file actions via job destination parameters.

## 0.14.4 (2021-04-14)

- Re-attempt release process - published wrong branch with 0.14.3.

## 0.14.3 (2021-04-13)

- Allow transferring fewer files from Pulsar when using extended metadata with
  Galaxy.

## 0.14.2 (2021-02-15)

- Fix the use of requests, limits, and walltime with coexecution pods. [Pull Request 246](https://github.com/galaxyproject/pulsar/pull/246)

## 0.14.1 (2021-02-02)

- Fix the use of named managers with coexecution pods. [Pull Request 242](https://github.com/galaxyproject/pulsar/pull/242)

## 0.14.0 (2020-09-17)

- fix the PyYAML "load() deprecation" warning (thanks to [@gmauro](https://github.com/gmauro)). [Pull Request 232](https://github.com/galaxyproject/pulsar/pull/232)
- Set the DRMAA workingDirectory to the job's working directory
  [Pull Request 230](https://github.com/galaxyproject/pulsar/pull/230)
- Fix a unicode issue and polish a bit of variables (thanks to [@gmauro](https://github.com/gmauro)).
  [Pull Request 229](https://github.com/galaxyproject/pulsar/pull/229)
- Respond to MQ messages requesting status updates. [Pull Request 228](https://github.com/galaxyproject/pulsar/pull/228)
- Fix REST connections broken with Py3 using standard transport [Issue 227](https://github.com/galaxyproject/pulsar/issues/227)
  [Pull Request 231](https://github.com/galaxyproject/pulsar/pull/231)
- Drop Python 2.7 support in standard transport, drop Python 2.7 tests and fix
  Python 3.7 wheel install test, general test debugging enhancements.
  [Pull Request 231](https://github.com/galaxyproject/pulsar/pull/231)
- drop python 2.6 and add 3.7 and update the testing infrastructure to a more
  recent Ubuntu setup (thanks to [@bgruening](https://github.com/bgruening)). [Pull Request 226](https://github.com/galaxyproject/pulsar/pull/226)
- Use is_alive in favour of isAlive for Python 3.9 compatibility (thanks to
  [@tirkarthi](https://github.com/tirkarthi)). [Issue 224](https://github.com/galaxyproject/pulsar/issues/224) [Pull Request 225](https://github.com/galaxyproject/pulsar/pull/225)
- Request and register ports for Galaxy ITs when using Kubernetes.
  [Pull Request 223](https://github.com/galaxyproject/pulsar/pull/223)
- Implement killing k8s jobs. [Pull Request 221](https://github.com/galaxyproject/pulsar/pull/221)
- Respond to MQ messages requesting status updates.
  [Pull Request 228](https://github.com/galaxyproject/pulsar/pull/228)
- Drop python 2.6 and add 3.7 and update the testing infrastructure to a more
  recent Ubuntu setup (thanks to [@bgruening](https://github.com/bgruening)). [Pull Request 226](https://github.com/galaxyproject/pulsar/pull/226)
- Add a more descriptive message in case of error parsing an external id
  (thanks to [@gmauro](https://github.com/gmauro)). [Pull Request 213](https://github.com/galaxyproject/pulsar/pull/213)
- Use requests (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 216](https://github.com/galaxyproject/pulsar/pull/216)
- Use is_alive in favour of isAlive for Python 3.9 compatibility (thanks to
  [@tirkarthi](https://github.com/tirkarthi)). [Pull Request 225](https://github.com/galaxyproject/pulsar/pull/225)
- Debug connection string for AMQP.
  [Pull Request 217](https://github.com/galaxyproject/pulsar/pull/217)
- Various small Kubernetes fixes and enhancements.
  [Pull Request 218](https://github.com/galaxyproject/pulsar/pull/218), [Pull Request 219](https://github.com/galaxyproject/pulsar/pull/219)
- Improvements and fixes to container handling.
  [Pull Request 202](https://github.com/galaxyproject/pulsar/pull/202)
- Fix a typo in exception logging thanks to @erasche.
  [Pull Request 203](https://github.com/galaxyproject/pulsar/pull/203)
- Cleanup config file handling a bit by removing branch for very
  old Pulsar servers likely no longer supported.
  [Pull Request 201](https://github.com/galaxyproject/pulsar/pull/201)

## 0.13.1 (2020-09-16)

- Pinned all listed requirements. This is the final version of Pulsar to support Python 2.

## 0.13.0 (2019-06-25)

- Various improvements and simplifications to Kubernetes job execution.

## 0.12.1 (2019-06-03)

- Retry botched release that didn't include all relevant commits.

## 0.12.0 (2019-06-03)

- Revise Python Galaxy dependencies to use newer style Galaxy decomposition.
  galaxy-lib can no longer be installed in Pulsar's environment, so you will
  likely need to rebuild your Pulsar virtualenv for this release.
  [Pull Request 187](https://github.com/galaxyproject/pulsar/pull/187)
- Add a `Dockerfile` for Pulsar with CVMFS (thanks to [@nuwang](https://github.com/nuwang) and [@afgane](https://github.com/afgane)).
  [Pull Request 166](https://github.com/galaxyproject/pulsar/pull/166)
- Various small improvements to Kubernetes pod execution environment.
  [Pull Request 190](https://github.com/galaxyproject/pulsar/pull/190)
- Improve readme linting.
  [Pull Request 186](https://github.com/galaxyproject/pulsar/pull/186)
- Update example docs for Condor (thanks to [@bgruening](https://github.com/bgruening)).
  [Pull Request 189](https://github.com/galaxyproject/pulsar/pull/189)

## 0.11.0 (2019-05-16)

- Implement staging Galaxy metadata input files in the client.
  39de377_
- Fix 'amqp_ack_republish_time' in sample (thanks to [@dannon](https://github.com/dannon)).
  [Pull Request 185](https://github.com/galaxyproject/pulsar/pull/185)
- Updated amqp_url in job_conf_sample_mq_rsync.xml (thanks to [@AndreasSko](https://github.com/AndreasSko)).
  [Pull Request 184](https://github.com/galaxyproject/pulsar/pull/184)
- Use wildcard char for pulsar version (thanks to [@VJalili](https://github.com/VJalili)).
  [Pull Request 181](https://github.com/galaxyproject/pulsar/pull/181)
- Refactor toward more structured inputs. f477bc4_
- Refactor toward passing objectstore identifying information around.
  [Pull Request 180](https://github.com/galaxyproject/pulsar/pull/180)
- Rework imports for new Galaxy library structure. da086c9_
- Revert empty input testing, it really probably should cause a failure
  to transfer a non-existent file.
  8bd5511_
- Better client mapper documentation. b6278b4_

## 0.10.0 (2019-05-06)

- Implement support for Kubernetes two container pod jobs - staging and
  tool execution as separate containers in the same job's pod.
  [Pull Request 176](https://github.com/galaxyproject/pulsar/pull/176), [Pull Request 178](https://github.com/galaxyproject/pulsar/pull/178)

## 0.9.1 (2019-05-01)

- Fix duplicate inputs being a problem when staging Galaxy files.
  [Pull Request 175](https://github.com/galaxyproject/pulsar/pull/175)
- Fix deprecated `assertEquals()` (thanks to @nsoranzo). [Pull Request 173](https://github.com/galaxyproject/pulsar/pull/173)
- Fix a method missing problem. [Pull Request 174](https://github.com/galaxyproject/pulsar/pull/174)
- Sync "recent" galaxy runner util changes. [Pull Request 177](https://github.com/galaxyproject/pulsar/pull/177)

## 0.9.0 (2019-04-12)
    
- Add configuration parameter to limit stream size read from disk. [Pull Request 157](https://github.com/galaxyproject/pulsar/pull/157)
- Pass full job status for failed and lost jobs. [Pull Request 159](https://github.com/galaxyproject/pulsar/pull/159)
- Improve message handling if problems occur during job setup/staging. [Pull Request 160](https://github.com/galaxyproject/pulsar/pull/160)
- Rework preprocessing job state to improve restartability and reduce job loss.
  **This change should be applied while no jobs are running.**
  [Pull Request 164](https://github.com/galaxyproject/pulsar/pull/164)
- Add support for overriding config through environment variables (thanks to
  @nuwang). [Pull Request 165](https://github.com/galaxyproject/pulsar/pull/165)
- Minor docs updates (thanks to @afgane). [Pull Request 170](https://github.com/galaxyproject/pulsar/pull/170)
- Python 3 fixes in Pulsar client (thanks to [@mvdbeek](https://github.com/mvdbeek)). [Pull Request 172](https://github.com/galaxyproject/pulsar/pull/172)

## 0.8.3 (2018-02-08)

- Create universal wheels to enable Python 3 support when installing from PyPI
  (thanks to @nsoranzo).
  [Pull Request 156](https://github.com/galaxyproject/pulsar/pull/156)

## 0.8.1 (2018-02-08)

- Update link for logo image. [Pull Request 145](https://github.com/galaxyproject/pulsar/pull/145)
- Minor error and log message typos (thanks to @blankenberg).
  [Pull Request 146](https://github.com/galaxyproject/pulsar/pull/146), [Pull Request 153](https://github.com/galaxyproject/pulsar/pull/153)
- Fixes/improvements for catching quoted tool files. [Pull Request 148](https://github.com/galaxyproject/pulsar/pull/148)
- Fix config sample parsing so run.sh works out of the box.
  [Pull Request 149](https://github.com/galaxyproject/pulsar/pull/149)

## 0.8.0 (2017-09-21)

- Support new features in Galaxy job running/scripting so that Pulsar respects
  `$GALAXY_VIRTUAL_ENV` and `$PRESERVE_GALAXY_ENVIRONMENT`. Fix remote
  metadata in cases where the tool environment changes the `python` on
  `$PATH`. [Pull Request 137](https://github.com/galaxyproject/pulsar/pull/137)
- Precreate Galaxy tool outputs on the remote before executing (fixes a bug
  related to missing output files on stage out). [Pull Request 141](https://github.com/galaxyproject/pulsar/pull/141)
- Support the remote_transfer file action without setting the
  `jobs_directory` destination param [Pull Request 136](https://github.com/galaxyproject/pulsar/pull/136)
- Fix invalid character in job managers documentation (thanks to @mapa17).
  [Pull Request 130](https://github.com/galaxyproject/pulsar/pull/130)
- Fix `conda_auto_*` option resolution and include a sample
  `dependency_resolvers_conf.xml` (thanks to @mapa17). [Pull Request 132](https://github.com/galaxyproject/pulsar/pull/132)
- Fix tox/Travis tests. [Pull Request 138](https://github.com/galaxyproject/pulsar/pull/138), [Pull Request 139](https://github.com/galaxyproject/pulsar/pull/139),
  [Pull Request 140](https://github.com/galaxyproject/pulsar/pull/140)
- Fix a bug with AMQP acknowledgement. [Pull Request 143](https://github.com/galaxyproject/pulsar/pull/143)

## 0.7.4 (2017-02-07)

- Fix Conda resolution and add a test case. 11ce744_
- Style fixes for updated flake8 libraries. 93ab8a1_, 3573341_
- Remove unused script. 929bffa_
- Fixup README. 629fdea_
    

## 0.7.3 (2016-10-31)

- Fix  "AttributeError" when submitting a job as a real user.
  [Pull Request 124](https://github.com/galaxyproject/pulsar/pull/124), [Issue 123](https://github.com/galaxyproject/pulsar/issues/123)

## 0.7.2 (2016-08-31)

- Fix bug causing loops on in response to preprocessing error conditions.

## 0.7.1 (2016-08-29)

- Do a release to circumvent a tool version logic error in Galaxy (
  released Galaxy versions think 0.7.0 < 0.7.0.dev3).

## 0.7.0 (2016-08-26)

- Update Makefile to allow release pulsar as an application and a library 
  for Galaxy at the same time.
- Small update to test scripts for TravisCI changes.
- Improvements for embedded Galaxy runner. (TODO: fill this out)
- Remove support for Python 2.6. 60bf962_
- Update docs to describe project goverance and reuse Galaxy's
  Code of Conduct. 7e23d43_, dc47140_
- Updated cluster slots detection for SLURM from Galaxy. cadfc5a_
- Various changes to allow usage within Galaxy as a library. ce9d4f9_
- Various changes to allow embedded Pulsar managers within Galaxy.
  ce9d4f9_, d262323_, 8f7c04a_
- Introduce a separate working and metadata directory as required for
  Galaxy 16.04 that requires this separation. 6f4328e_
- Improve logging and comments. 38953f3_, a985107_, ad33cb9_
- Add Tox target for Python 2.7 unit testing. d7c524e_
- Add `Makefile` command for setup.py develop. fd82d00_

## 0.6.1 (2015-12-23)

- Tweak release process that left 0.6.0 with an incorrect PyPI description page.

## 0.6.0 (2015-12-23)

- Pulsar now depends on the new `galaxy-lib` Python package instead of
  manually synchronizing Python files across Pulsar and Galaxy.
- Numerous build and testing improvements.
- Fixed a documentation bug in the code (thanks to @erasche). e8814ae_
- Remove galaxy.eggs stuff from Pulsar client (thanks to @natefoo). 00197f2_
- Add new logo to README (thanks to @martenson). abbba40_
- Implement an optional awknowledgement system on top of the message queue
  system (thanks to @natefoo). [Pull Request 82](https://github.com/galaxyproject/pulsar/pull/82) 431088c_
- Documentation fixes thanks to @remimarenco. [Pull Request 78](https://github.com/galaxyproject/pulsar/pull/78), [Pull Request 80](https://github.com/galaxyproject/pulsar/pull/80)
- Fix project script bug introduced this cycle (thanks to @nsoranzo). 140a069_
- Fix config.py on Windows (thanks to @ssorgatem). [Pull Request 84](https://github.com/galaxyproject/pulsar/pull/84)
- Add a job manager for XSEDE jobs (thanks to @natefoo). 1017bc5_
- Fix pip dependency installation (thanks to @afgane) [Pull Request 73](https://github.com/galaxyproject/pulsar/pull/73)

## 0.5.0 (2015-05-08)

- Allow cURL downloader to resume transfers during staging in (thanks to
  @natefoo). 0c61bd9_
- Fix to cURL downloaders status code handling (thanks to @natefoo). 86f95ce_
- Fix non-wheel installs from PyPI. [Issue 72](https://github.com/galaxyproject/pulsar/issues/72)
- Fix mesos imports for newer versions of mesos (thanks to @kellrott). fe3e919_
- More, better logging. 2b3942d_, fa2b6dc_

## 0.4.0 (2015-04-20)

- Python 3 support. [Pull Request 62](https://github.com/galaxyproject/pulsar/pull/62)
- Fix bug encountered when running `pulsar-main` and `pulsar-config` commands as scripts. 9d43ae0_
- Add `pulsar-run` script for issues commands against a Pulsar server (experimental). 3cc7f74_

## 0.3.0 (2015-04-12)

- Changed the name of project to Pulsar, moved to Github.
- New RESTful web services interface.
- SCP and Rsync file staging options added by E. Rasche. [Pull Request](https://github.com/galaxyproject/pulsar/pull/34)
- Allow YAML based configuration.
- Support for more traditional `pip`/`setup.py`-style
  installs.
- Dozens of smaller bugfixes and documentation updates.

## 0.2.0

- Last version named the LWR - found on [BitBucket](https://bitbucket.org/jmchilton/lwr).
- Still supported in Galaxy as of 15.03 the release.
- Introduced support for submitting to various queueing systems,
  operation as a Mesos framework, Docker support, and
  various other advanced deployment options.
- Message queue support.
- Framework for configurable file actions introduced.

## 0.1.0

- Simple support for running jobs managed by the Python LWR
  web process.
- https://bitbucket.org/jmchilton/lwr/branch/0.1

## 0.0.1

- See the original [announcement](http://dev.list.galaxyproject.org/New-Remote-Job-Runner-td4138951.html)
  and [initial commit](https://github.com/galaxyproject/pulsar/commit/163ed48d5a1902ceb84c38f10db8cbe5a0c1039d).
