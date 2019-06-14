

docker-image:
	find . -regex './pulsar_app-.*.whl' -delete
	cd ../..; make dist; cp dist/pulsar*whl docker/coexecutor

all: docker-image
	docker build -t 'galaxy/pulsar-pod-staging:0.12.0' .
