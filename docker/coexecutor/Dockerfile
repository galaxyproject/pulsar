# Staging image for Pulsar coexecution (Galaxy's Kubernetes, TES and GCP Batch
# runners). It runs pulsar-submit / pulsar-finish next to the tool container
# and, for jobs without a tool container, the tool itself with Conda
# dependencies. Build with `make -C docker/coexecutor all` from the repo root.
FROM python:3.12-slim-trixie

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Pulsar's wheel is pure Python and its dependencies ship wheels (pycurl's
# manylinux wheel bundles libcurl) or pure Python sdists, so no compiler is
# needed. Unlike --no-cache-dir, PIP_NO_CACHE_DIR also reaches the pip that
# installs those sdists' build dependencies. Remote transfer staging uses
# pycurl whenever it imports, whatever PULSAR_CURL_TRANSPORT says. Without it
# staging falls back to requests, which reads each uploaded output fully into
# memory and can't resume downloads.
RUN --mount=type=bind,target=/context \
    PIP_NO_CACHE_DIR=1 pip install "$(ls /context/pulsar_app-*.whl)[amqp,galaxy_extended_metadata]" pycurl

# Containerless jobs resolve tool requirements with Conda under
# /pulsar_dependencies/conda (see Client.get_pulsar_app_config). Installing
# Conda here saves a download per job; pass --build-arg CONDA_INIT=false for an
# image that is only used with tool containers.
ARG CONDA_INIT=true
RUN if [ "$CONDA_INIT" = "true" ]; then \
        _pulsar-conda-init --conda_prefix=/pulsar_dependencies/conda \
        && /pulsar_dependencies/conda/bin/conda clean --all --yes; \
    fi

# pulsar-submit and pulsar-finish build a dependency manager at startup. Its
# default tool_dependency_dir is "dependencies" relative to the working
# directory, which is / for TES and Kubernetes executors, and galaxy-tool-util
# creates it. On a read-only root filesystem (Funnel's default docker run
# template) that mkdir kills the app before the job is staged. Point it at a
# directory that already exists; app config still takes precedence.
ENV PULSAR_CONFIG_TOOL_DEPENDENCY_DIR=/pulsar_dependencies
RUN mkdir -p /pulsar_dependencies
