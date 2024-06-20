# Default tests run with make test
PYTEST_TESTS?=test pulsar
# Default environment for make tox
ENV?=py27
# Extra arguments supplied to tox command
ARGS?=
# Location of virtualenv used for development.
VENV?=.venv
# Source virtualenv to execute command (flake8, sphinx, twine, etc...)
IN_VENV=if [ -f $(VENV)/bin/activate ]; then . $(VENV)/bin/activate; fi;
# TODO: add this upstream as a remote if it doesn't already exist.
UPSTREAM?=galaxyproject
SOURCE_DIR?=pulsar
BUILD_SCRIPTS_DIR=tools
DEV_RELEASE?=0
VERSION?=$(shell DEV_RELEASE=$(DEV_RELEASE) python $(BUILD_SCRIPTS_DIR)/print_version_for_release.py $(SOURCE_DIR) $(DEV_RELEASE))
DOC_URL?=https://pulsar.readthedocs.org
PROJECT_URL?=https://github.com/galaxyproject/pulsar
PROJECT_NAME?=pulsar-app
TEST_DIR?=test

.PHONY: clean-pyc clean-build docs clean

help:
	@echo "clean - remove all build, test, coverage and Python artifacts"
	@echo "clean-build - remove build artifacts"
	@echo "clean-pyc - remove Python file artifacts"
	@echo "clean-test - remove test and coverage artifacts"
	@echo "setup-venv - setup a development virutalenv in current directory."
	@echo "lint - check style with flake8"
	@echo "lint-dist - twine check dist results, including validating README content"
	@echo "lint-docs - check sphinx docs for warnings"
	@echo "tests - run tests quickly with the default Python"
	@echo "coverage - check code coverage quickly with the default Python"
	@echo "docs - generate Sphinx HTML documentation, including API docs"
	@echo "dist - package project for PyPI distribution"
	@echo "open-docs - open docs built locally with make docs"
	@echo "open-rtd - open docs at pulsar.readthedocs.org"
	@echo "open-project - open project on github"
	@echo "setup-git-hook-lint - setup precommit hook for linting project"
	@echo "setup-git-hook-lint-and-test - setup precommit hook for linting and testing project"

clean: clean-build clean-pyc clean-tests

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr pulsar.*.egg-info
	rm -rf docker/coexecutor/*whl

clean-pyc:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-tests:
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/

setup-venv:
	if [ ! -d $(VENV) ]; then virtualenv $(VENV); exit; fi;
	$(IN_VENV) pip install -r requirements.txt && pip install -r dev-requirements.txt

setup-git-hook-lint:
	cp $(BUILD_SCRIPTS_DIR)/pre-commit-lint .git/hooks/pre-commit

setup-git-hook-lint-and-test:
	cp $(BUILD_SCRIPTS_DIR)/pre-commit-lint-and-test .git/hooks/pre-commit

flake8:
	$(IN_VENV) flake8 --max-complexity 9 $(SOURCE_DIR) $(TEST_DIR)

lint:
	$(IN_VENV) tox -e py37-lint

_lint-dist:
	$(IN_VENV) twine check dist/*

lint-dist: dist _lint-dist

tests:
	$(IN_VENV) pytest $(PYTEST_TESTS)

test-install-pypi:
	bash install_test/test_install_conda.bash

test-install-wheel: dist
	PULSAR_INSTALL_TARGET=$(wildcard $(shell pwd)/dist/pulsar_app*.whl)[web] bash install_test/test_install_conda.bash

coverage:
	coverage run --source $(SOURCE_DIR) setup.py $(TEST_DIR)
	coverage report -m
	coverage html
	open htmlcov/index.html || xdg-open htmlcov/index.html

develop:
	python setup.py develop

develop-galaxy:
	PULSAR_GALAXY_LIB=1 python setup.py develop

ready-docs:
	rm -f docs/$(SOURCE_DIR).rst
	rm -f docs/modules.rst
	$(IN_VENV) sphinx-apidoc -f -o docs/ $(SOURCE_DIR)

docs: ready-docs
	$(IN_VENV) $(MAKE) -C docs clean
	$(IN_VENV) $(MAKE) -C docs html

lint-docs: ready-docs
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; $(MAKE) -C docs clean
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; ! (make -C docs html 2>&1 | grep -v 'nonlocal image URI found\|included in any toctree' | grep WARNING)

_open-docs:
	open docs/_build/html/index.html || xdg-open docs/_build/html/index.html

open-docs: docs _open-docs

open-rtd: docs
	open $(DOC_URL) || xdg-open $(PROJECT_URL)

open-project:
	open $(PROJECT_URL) || xdg-open $(PROJECT_URL)

format:  ## Format Python code base
	$(IN_VENV) isort .

dist: clean-build clean-pyc
	$(IN_VENV) python setup.py sdist bdist_wheel
	ls -l dist

_release-test-artifacts:
	$(IN_VENV) twine upload -r test dist/*
	open https://testpypi.python.org/pypi/$(PROJECT_NAME) || xdg-open https://testpypi.python.org/pypi/$(PROJECT_NAME)

dist-all: dist _dist-lib _lint-dist

release-test-artifacts: dist-all _release-test-artifacts

_release-artifacts:
	@while [ -z "$$CONTINUE" ]; do \
	  read -r -p "Have you executed release-test and reviewed results? [y/N]: " CONTINUE; \
	done ; \
	[ $$CONTINUE = "y" ] || [ $$CONTINUE = "Y" ] || (echo "Exiting."; exit 1;)
	@echo "Releasing"
	$(IN_VENV) twine upload dist/*

release-artifacts: release-test-artifacts _release-artifacts

commit-version:
	$(IN_VENV) DEV_RELEASE=$(DEV_RELEASE) python $(BUILD_SCRIPTS_DIR)/commit_version.py $(SOURCE_DIR) $(VERSION)

new-version:
	$(IN_VENV) DEV_RELEASE=$(DEV_RELEASE) python $(BUILD_SCRIPTS_DIR)/new_version.py $(SOURCE_DIR) $(VERSION)

release-local: commit-version release-artifacts new-version

push-release:
	git push $(UPSTREAM) master
	git push --tags $(UPSTREAM)

release: release-local push-release

add-history:
	$(IN_VENV) python $(BUILD_SCRIPTS_DIR)/bootstrap_history.py $(ITEM)

_dist-lib:
	$(IN_VENV) PULSAR_GALAXY_LIB=1 python setup.py sdist bdist_wheel
	ls -l dist

dist-lib: clean-pyc clean-build _dist-lib

build-coexecutor-container:
	$(MAKE) -C docker/coexecutor all

#release-test-lib-artifacts: dist-lib _release-test-artifacts
#release-lib-artifacts: release-test-lib-artifacts _release-artifacts
