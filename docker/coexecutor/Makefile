

dist:
	cd ../..; make dist; cp dist/pulsar*whl docker/coexecutor

docker-image:
	docker build -t 'galaxy/pulsar-pod-staging:0.13.0' .

all: dist docker-image
