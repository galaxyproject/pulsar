#!/usr/bin/env bash
# Pulsar entrypoint for resilience tests. Selects an app config based on
# $PULSAR_MODE so the same image can run any of the AMQP / AMQP-ack / relay
# scenarios.

set -euo pipefail

mode="${PULSAR_MODE:-amqp}"
case "$mode" in
    amqp)     src="/etc/pulsar/app_amqp.yml" ;;
    amqp_ack) src="/etc/pulsar/app_amqp_ack.yml" ;;
    relay)    src="/etc/pulsar/app_relay.yml" ;;
    *) echo "Unknown PULSAR_MODE=$mode" >&2; exit 2 ;;
esac

# Stage configs into a writable runtime dir so we can pick the active app.yml
# without touching the read-only mount.
runtime=/tmp/pulsar-runtime
mkdir -p "$runtime"
cp /etc/pulsar/server.ini "$runtime/server.ini"
cp "$src" "$runtime/app.yml"

export PULSAR_CONFIG_DIR="$runtime"
# No --port: webless mode binds no port, so the flag is not one of the
# pulsar-main arguments this mode accepts.
exec pulsar --mode webless --config_dir "$runtime"
