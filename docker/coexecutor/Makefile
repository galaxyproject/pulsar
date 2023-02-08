

dist:
	cd ../..; make dist; cp dist/pulsar*whl docker/coexecutor

docker-image:
	docker build -t 'galaxy/pulsar-pod-staging:0.15.0.2' .

all: dist docker-image
