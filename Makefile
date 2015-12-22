# Default tests run with make test
NOSE_TESTS?=test pulsar
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
VERSION?=$(shell python scripts/print_version_for_release.py $(SOURCE_DIR))
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
	@echo "lint-readme - check README formatting for PyPI"
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
	rm -fr *.egg-info

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
	cp scripts/pre-commit-lint .git/hooks/pre-commit

setup-git-hook-lint-and-test:
	cp scripts/pre-commit-lint-and-test .git/hooks/pre-commit

flake8:
	$(IN_VENV) flake8 --max-complexity 9 $(SOURCE_DIR) $(TEST_DIR)

lint:
	$(IN_VENV) tox -e py27-lint && tox -e py34-lint

lint-readme:
	$(IN_VENV) python setup.py check -r -s

tests:
	$(IN_VENV) nosetests $(NOSE_TESTS)

coverage:
	coverage run --source $(SOURCE_DIR) setup.py $(TEST_DIR)
	coverage report -m
	coverage html
	open htmlcov/index.html || xdg-open htmlcov/index.html


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

open-docs: docs
	open docs/_build/html/index.html || xdg-open docs/_build/html/index.html

open-rtd: docs
	open $(DOC_URL) || xdg-open $(PROJECT_URL)

open-project:
	open $(PROJECT_URL) || xdg-open $(PROJECT_URL)

dist: clean
	$(IN_VENV) python setup.py sdist bdist_egg bdist_wheel
	ls -l dist

release-test: dist
	$(IN_VENV) twine upload -r test dist/*
	open https://testpypi.python.org/pypi/$(PROJECT_NAME) || xdg-open https://testpypi.python.org/pypi/$(PROJECT_NAME)

release: release-test
	@while [ -z "$$CONTINUE" ]; do \
	  read -r -p "Have you executed release-test and reviewed results? [y/N]: " CONTINUE; \
	done ; \
	[ $$CONTINUE = "y" ] || [ $$CONTINUE = "Y" ] || (echo "Exiting."; exit 1;)
	@echo "Releasing"
	$(IN_VENV) twine upload dist/*

commit-version:
	$(IN_VENV) python scripts/commit_version.py $(SOURCE_DIR) $(VERSION)

new-version:
	$(IN_VENV) python scripts/new_version.py $(SOURCE_DIR) $(VERSION)

release-local: commit-version release-aritfacts new-version

push-release:
	git push $(UPSTREAM) master
	git push --tags $(UPSTREAM)

release: release-local push-release
