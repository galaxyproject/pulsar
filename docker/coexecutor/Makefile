

docker-image:
	cd ../..; make dist; cp dist/pulsar*whl docker/coexecutor

all: docker-image
	re='pulsar_app-([0-9]+.[0-9]+.[0-9]+).dev0-py2.py3-none-any.whl'
        f='$(shell ls -1a | egrep '$(re)')'
        version=$(shell if [[ $(f) =~ $(re) ]]; then echo "v${BASH_REMATCH[1]}"; else echo "unknown_version"; fi)
	docker build -t 'galaxy/pulsar-pod-staging:0.1' .
