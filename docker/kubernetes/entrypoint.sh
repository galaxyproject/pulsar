#!/bin/bash
set -e

export PATH=/usr/bin:$PATH
export XDG_RUNTIME_DIR=/home/dockeruser/.docker/run
export DOCKER_HOST=unix:///home/dockeruser/.docker/run/docker.sock

PULSAR_DATA_ROOT=/pulsar/files
DOCKER_DATA_ROOT=$PULSAR_DATA_ROOT/docker
DOCKER_LOG_FILE=$DOCKER_DATA_ROOT/docker-daemon.log

mkdir -p $DOCKER_DATA_ROOT
chown pulsar:pulsar $PULSAR_DATA_ROOT
chown dockeruser:dockeruser $DOCKER_DATA_ROOT

# Check if rootless is already set up
if [ ! -d /home/dockeruser/.docker ]; then
    echo "[INFO] Running rootless setup at runtime"
    gosu dockeruser dockerd-rootless-setuptool.sh install --skip-iptables
fi

# Start rootless Docker daemon
gosu dockeruser dockerd-rootless.sh --data-root="$DOCKER_DATA_ROOT" > "$DOCKER_LOG_FILE" 2>&1 &

# Wait for Docker to become ready
echo "[INFO] Waiting for Docker to be ready..."
until gosu dockeruser docker info >/dev/null 2>&1; do
    echo "[INFO] Still waiting..."
    sleep 2
done

echo "[INFO] Docker is ready."

# Change socket permissions so pular can access it
chmod g+rx /home/dockeruser/.docker/run

# Start Pulsar
exec gosu pulsar "$@"
