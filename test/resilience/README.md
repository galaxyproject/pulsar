# Pulsar Resilience Test Framework

End-to-end test suite that exercises the *operational* failure modes Pulsar
must survive without losing jobs:

- Pulsar SIGKILL / restart at every lifecycle phase
- AMQP broker outage / partition / restart
- pulsar-relay outage / partition
- Galaxy HTTP file-server transient failures, persistent failures, partitions
- Combinations of all of the above

The single guarantee every scenario asserts is: **for every submitted job, a
terminal status (`complete` or `failed`) is delivered exactly once and is
preceded only by valid intermediate states**, within a bounded time after the
fault clears.

## Stack

`docker-compose.yml` brings up:

| Service        | Role                                                               |
|----------------|--------------------------------------------------------------------|
| `rabbitmq`     | Real RabbitMQ for AMQP-mode tests                                  |
| `valkey`       | Backing store for `pulsar-relay`                                   |
| `relay`        | The `pulsar-relay/` HTTP long-poll service                         |
| `toxiproxy`    | Network fault injection in front of all three                      |
| `mock-galaxy`  | FastAPI app with file-server endpoints + AMQP/relay status recorder |
| `pulsar`       | Pulsar built from local source (mode selected via `PULSAR_MODE`)    |

Pulsar reaches every other service through toxiproxy, so the harness can
disable connections, blackhole packets, add latency, or reset peers
mid-scenario.

## Running locally

```bash
# from repo root
docker compose -f test/resilience/docker-compose.yml up -d --build
pytest test/resilience -v
docker compose -f test/resilience/docker-compose.yml down -v
```

Or via the smoke test:

```bash
pytest test/resilience/scenarios/test_happy_path.py -v
```

The session fixture (`compose_up`) brings the stack up if it's not already
running and tears it down afterwards. Pass `--keep-stack` to leave the stack
running between sessions when iterating locally.

## Layout

```
test/resilience/
├── docker-compose.yml      # service stack
├── Dockerfile.pulsar       # builds Pulsar from local source
├── entrypoint.sh           # selects amqp / amqp_ack / relay mode at startup
├── config/                 # app_*.yml + server.ini + toxiproxy.json
├── mock_galaxy/            # FastAPI app wrapping pulsar.testing.recorder
├── conftest.py             # pytest fixtures + parametrized mq_mode
└── scenarios/              # the actual test cases
```

The drivers and assertions the scenarios import are not in this directory.
They ship inside the distribution as `pulsar.testing`:

```
pulsar/testing/
├── recorder.py             # StatusRecorder — stdlib only, embedded in mock_galaxy
└── resilience/             # PulsarControl, ToxiproxyControl, job factory, assertions
```

so they are importable by name from anywhere rather than by an accident of
`sys.path`. The split is deliberate: `recorder` makes no assumptions about how
the status events reached it and is reusable anywhere — downstream projects that
install `pulsar-galaxy-lib` get it for free — while everything under
`resilience/` is wired to this compose stack's service names and host ports.

## Adding a scenario

1. Pick a fixture set: `pulsar`, plus one of `rabbitmq_proxy` / `relay_proxy`
   / `galaxy_proxy` for fault injection.
2. Build a setup payload with `pulsar.testing.resilience.job_factory.make_setup_message`.
3. Submit it via `requests.post(GALAXY_BASE + "/_publish_setup", json=...)`.
4. Inject the fault you care about with the appropriate proxy fixture.
5. Restore connectivity and assert with
   `pulsar.testing.resilience.assertions.await_terminal` and
   `assert_exactly_once_terminal`.

To act at a point *inside* a phase rather than after it, open a
`pulsar.watch_logs()` before submitting and wait on a marker the phase logs
(`test_postprocess_restart.py` waits for `collecting output` to kill Pulsar
mid-upload). Open the watch first: `_publish_setup` is reached through
toxiproxy, so a toxic that stalls the phase stalls the submitting call too,
and the marker can be logged before that call returns.

## Mode matrix

`mq_mode` is parametrized over `amqp`, `amqp_ack`, and `relay`. Tests that
should run in every mode just take the `pulsar` fixture (which depends on
`mq_mode`); tests that only make sense in one mode pin via `pytest.mark.parametrize`.

## Why docker-compose

The bugs we care about are operational: process death, partition, broker
restart. Existing in-process tests (`test/integration_test_state.py`) use
the in-memory kombu transport and cannot reproduce them. docker-compose +
toxiproxy is the standard way to inject these faults, runs the same on a dev
laptop and in CI, and keeps the harness reproducible.
