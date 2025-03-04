FROM python:3.13-slim AS builder

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

#======================================================
# Builder - Create virtualenv for Pulsar
#======================================================
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

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libcurl4-openssl-dev \
        bzip2 virtualenv \
    && adduser --disabled-password --gecos '' pulsar \
    && mkdir /pulsar \
    && chown pulsar:pulsar /pulsar

WORKDIR /pulsar
COPY --chown=pulsar:pulsar --from=builder /pulsar .

USER pulsar

EXPOSE 8913

CMD [".venv/bin/pulsar"]
