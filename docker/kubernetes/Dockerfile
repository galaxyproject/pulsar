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

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV PULSAR_CONFIG_PRIVATE_TOKEN=change_me

RUN apt-get update && apt-get install -y --no-install-recommends \
    libcurl4-openssl-dev \
    bzip2 \
    virtualenv \
    # needed for rootless docker
    uidmap \
    fuse \
    iptables \
    iproute2 \
    dbus-user-session \
    sudo \
    curl \
    squashfs-tools \
    gosu \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash dockeruser \
    && adduser --disabled-password --gecos '' pulsar \
    && usermod -aG dockeruser pulsar \
    && mkdir /pulsar \
    && chown pulsar:pulsar /pulsar

WORKDIR /pulsar

# Copy Pulsar virtualenv + configs
COPY --chown=pulsar:pulsar --from=builder /pulsar .

# Download upstream Docker static binaries (with rootless scripts)
RUN curl -LO https://download.docker.com/linux/static/stable/x86_64/docker-28.1.1.tgz \
    && tar -xvzf docker-28.1.1.tgz \
    && curl -LO https://download.docker.com/linux/static/stable/x86_64/docker-rootless-extras-28.1.1.tgz \
    && tar -xvzf docker-rootless-extras-28.1.1.tgz \
    && mv docker/* /usr/bin/ \
    && mv docker-rootless-extras/* /usr/bin/ \
    && chmod +x /usr/bin/dockerd* /usr/bin/rootless* \
    && rm -rf docker docker-rootless-extras docker-28.1.1.tgz docker-rootless-extras-28.1.1.tgz

# Copy entrypoint script
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8913

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD [".venv/bin/pulsar"]
