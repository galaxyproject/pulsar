

dist:
	cd ../..; make dist; cp dist/pulsar*whl docker/kubernetes; cp requirements.txt docker/kubernetes

docker-image:
	docker build -t 'galaxy/pulsar-kubernetes:0.15.7' .

all: dist docker-image
