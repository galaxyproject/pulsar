# Update the Galaxy compatibility matrix

> **This command has never been run.** It was written alongside the initial
> matrix, which came from a one-off survey by several research agents. Treat
> it as a starting point: when a step is wrong, missing, or wasteful, fix this
> file as part of the same change. The process should evolve as we mature it.

Bring `docs/compatibility.yml` (rendered to `docs/compatibility.rst`) up to
date with changes in Pulsar and Galaxy since the commits recorded under
`surveyed:` in that file.

## Ground rules

- The matrix records what we *expect*, not a support guarantee. Don't
  promote anything to `tested` without a CI job (or a run you did and can
  cite) that exercised that exact pairing.
- `broken` needs evidence: a commit plus the code path, or a reproduction.
  A behaviour change that only bites when an option is enabled is an issue
  with `severity: conditional` on an `expected` cell, not a `broken` cell.
- Never weaken or delete an existing issue to make the table look better.
  Remove one only when the cells it applies to are gone (e.g. a Galaxy
  release dropped out of support) or a fix has shipped on both sides.
- Cite commits as `<repo>@<sha>` when it isn't obvious which repository a
  hash belongs to.

## Inputs

- Pulsar checkout (this repo), with `origin` fetched.
- A Galaxy checkout with `origin/dev` and every `origin/release_*` branch
  listed in `galaxy_releases`, fetched.
- Optional: a `pulsar-relay` checkout, for relay server questions.

## Steps

1. **Galaxy release rows.** For each `origin/release_*` branch, read the
   `pulsar-galaxy-lib` pin from `lib/galaxy/dependencies/pinned-requirements.txt`
   and update `galaxy_releases`. Add rows for new Galaxy releases (every
   modality's `matrix` needs a row for every release; the test enforces this).
   Keep `pulsar_series` in step with release branches (`release_0.N`).

2. **Diff forward.** Collect changes since `surveyed.pulsar` and
   `surveyed.galaxy_dev`:
   - Pulsar: `git log <surveyed.pulsar>..origin/master` plus the same range on
     any `release_0.*` branch. Pay attention to `pulsar/client/**`,
     `pulsar/web/routes.py`, `pulsar/messaging/**`, `pulsar/managers/staging/**`,
     `pulsar/client/setup_handler.py`, `pulsar/capabilities.py`, and
     `HISTORY.rst`.
   - Galaxy: `git log <surveyed.galaxy_dev>..origin/dev -- lib/galaxy/jobs/runners/pulsar.py`
     plus the pins file and `DEFAULT_PULSAR_CONTAINER`, and the same paths on
     each release branch (backports land there too).

3. **Classify each contract change per modality.** One subagent per modality
   (REST, MQ, relay, coexecution) plus one for cross-cutting concerns keeps the
   main session small. For each change decide:
   - which side it lands on (Galaxy client lib, Pulsar server, sidecar image,
     relay server/client);
   - which direction it affects (old Galaxy → new Pulsar, new Galaxy → old
     Pulsar);
   - break, degraded, or conditional.

   Known traps from the first survey:
   - With `jobs_directory` set (all MQ, relay and coexecution setups),
     Galaxy builds the job config locally, so `pulsar_version` in it is
     Galaxy's own lib version, not the server's. Any Galaxy feature gated on
     that version is suspect.
   - Coexecution's peer is the sidecar image, hardcoded in Galaxy as
     `DEFAULT_PULSAR_CONTAINER`, not the server version. Check whether it moved.
   - Relay also depends on `pulsar-relay-client` and the relay server
     versions (`other_axes`).
   - Servers drop unknown setup keys and query params without error, so
     "new field ignored" usually means a silently missing feature, and
     occasionally (as with `dataset_collector_descriptions`) lost outputs.

4. **Edit the YAML.** Split server ranges where behaviour changes, add or
   update `issues`, and set statuses per the ground rules. Bump `surveyed`
   to the commits you diffed against and today's date.

5. **Regenerate and check.**
   ```sh
   make compatibility-docs
   pytest test/compatibility_doc_test.py
   make lint-docs
   ```

6. **Report.** Summarise new issues, status changes, and anything you could
   not decide (put open questions in the report, not in the YAML). Flag
   changes that look like they need a Pulsar or Galaxy fix rather than just
   a matrix entry. Don't open a PR unless asked.
