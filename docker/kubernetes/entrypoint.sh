#!/bin/bash
set -e

# Handle docker.sock safely
if [ -S /var/run/docker.sock ]; then
    echo "[INFO] docker.sock detected"

    DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)

    # Check if a group with this GID already exists
    EXISTING_GROUP=$(getent group "$DOCKER_GID" | cut -d: -f1)

    if [ -z "$EXISTING_GROUP" ]; then
        groupadd -g "$DOCKER_GID" dockerhost
        TARGET_GROUP=dockerhost
        echo "[INFO] Created group dockerhost with GID $DOCKER_GID"
    else
        TARGET_GROUP=$EXISTING_GROUP
        echo "[INFO] Reusing existing group $TARGET_GROUP with GID $DOCKER_GID"
    fi

    usermod -aG "$TARGET_GROUP" pulsar

    echo "[INFO] Added pulsar to group $TARGET_GROUP ($DOCKER_GID)"
else
    echo "[WARN] docker.sock not found, Docker commands may fail"
fi

# Drop to pulsar user and start Pulsar
exec gosu pulsar "$@"
