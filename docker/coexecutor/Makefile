# Build the coexecution staging image from a wheel of this checkout.
#   make -C docker/coexecutor all IMAGE=galaxy/pulsar-pod-staging:<tag>
# When publishing a tag, add it to KNOWN_PULSAR_CONTAINER_VERSIONS in
# pulsar/client/setup_handler.py.
PULSAR_VERSION := $(shell sed -n "s/^__version__ = '\(.*\)'/\1/p" ../../pulsar/__init__.py)
IMAGE ?= galaxy/pulsar-pod-staging:$(PULSAR_VERSION)
DOCKER_BUILD_ARGS ?=

dist:
	cd ../..; $(MAKE) dist; cp dist/pulsar_app-*.whl docker/coexecutor

docker-image:
	docker build $(DOCKER_BUILD_ARGS) -t '$(IMAGE)' .

all: dist docker-image

.PHONY: dist docker-image all
