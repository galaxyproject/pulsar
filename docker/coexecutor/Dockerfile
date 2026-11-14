# Staging image for Pulsar coexecution (Galaxy's Kubernetes, TES and GCP Batch
# runners). It runs pulsar-submit / pulsar-finish next to the tool container
# and, for jobs without a tool container, the tool itself with Conda
# dependencies. Build with `make -C docker/coexecutor all` from the repo root.
ARG PYTHON_IMAGE=python:3.12-slim-trixie
FROM ${PYTHON_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

# Pulsar's wheel is pure Python and its dependencies ship wheels (pycurl's
# manylinux wheel bundles libcurl), so no compiler is needed. Remote transfer
# staging uses pycurl whenever it imports, whatever PULSAR_CURL_TRANSPORT says.
# Without it staging falls back to requests, which reads each uploaded output
# fully into memory and can't resume downloads. drmaa is left out: coexecution
# never talks to a DRM.
COPY pulsar_app-*.whl /tmp/
RUN pip install "$(ls /tmp/pulsar_app-*.whl)[amqp,galaxy_extended_metadata]" pycurl \
    && rm /tmp/pulsar_app-*.whl

# Containerless jobs resolve tool requirements with Conda under
# /pulsar_dependencies/conda (see Client.get_pulsar_app_config). Installing
# Conda here saves a download per job; pass --build-arg CONDA_INIT=false for an
# image that is only used with tool containers.
ARG CONDA_INIT=true
RUN if [ "$CONDA_INIT" = "true" ]; then \
        _pulsar-conda-init --conda_prefix=/pulsar_dependencies/conda \
        && /pulsar_dependencies/conda/bin/conda clean --all --yes; \
    fi
