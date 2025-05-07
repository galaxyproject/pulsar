#======================================================
# Builder - Create virtualenv for Pulsar
#======================================================
FROM python:3.13-slim AS builder

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends apt-transport-https \
    # Install packages
    && apt-get update \
    && apt-get install -y --no-install-recommends gcc \
        libcurl4-openssl-dev \
        bzip2 virtualenv \
    && mkdir /pulsar

WORKDIR /pulsar

COPY pulsar_app-*-py2.py3-none-any.whl .
COPY requirements.txt .

# Install Pulsar Python requirements
RUN virtualenv .venv \
    && . .venv/bin/activate \
    && pip install wheel pykube-ng \
    && pip install -r requirements.txt Paste \
    && pip install `ls pulsar_app-*-py2.py3-none-any.whl`\[galaxy_extended_metadata,web,amqp\]

# generate default pulsar config
RUN .venv/bin/pulsar-config --host 0.0.0.0

#======================================================
# Final image - Copy virtualenv for Pulsar
#======================================================
FROM python:3.13-slim

ENV LC_ALL=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV PULSAR_CONFIG_PRIVATE_TOKEN=change_me

# -------------------------
# Pulsar and common dependencies
# -------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    locales \
    libcurl4-openssl-dev \
    bzip2 \
    virtualenv \
    && echo "$LANG UTF-8" > /etc/locale.gen \
    && locale-gen $LANG && update-locale LANG=$LANG \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* \
    && adduser --disabled-password --gecos '' pulsar \
    && mkdir /pulsar \
    && chown pulsar:pulsar /pulsar

# -------------------------
# Docker client dependencies
# -------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg lsb-release \
    # needed for rootless docker
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" \
      | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && apt-get purge -y curl gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# -------------------------
# Apptainer (Singularity) dependencies
# -------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libseccomp-dev \
    pkg-config \
    squashfs-tools \
    cryptsetup \
    uidmap \
    fuse2fs \
    fuse3 \
    fuse-overlayfs \
    && curl -LO https://github.com/apptainer/apptainer/releases/download/v1.4.0/apptainer_1.4.0_amd64.deb \
    && apt-get install -y ./apptainer_1.4.0_amd64.deb \
    && rm apptainer_1.4.0_amd64.deb \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /pulsar

# Copy Pulsar virtualenv + configs
COPY --chown=pulsar:pulsar --from=builder /pulsar .

EXPOSE 8913

CMD [".venv/bin/pulsar"]
