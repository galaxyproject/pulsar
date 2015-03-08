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

clean: clean-build clean-pyc clean-tests

clean-build:
	rm -fr build/
	rm -fr dist/
	rm -fr pulsar*.egg-info

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
	if [ -f .venv ]; then virtualenv .venv; fi;
	. .venv/bin/activate && pip install -r requirements.txt && pip install -r dev-requirements.txt

lint:
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; flake8 --exclude test_tool_deps.py --max-complexity 9 pulsar test

lint-readme:
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; python setup.py check -r -s

tests:
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; nosetests

coverage: tests
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; coverage html
	open coverage_html_report/index.html || xdg-open coverage_html_report/index.html

ready-docs:
	rm -f docs/pulsar.rst
	rm -f docs/galaxy.rst
	rm -f docs/modules.rst
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; sphinx-apidoc -f -o docs/ pulsar
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; sphinx-apidoc -f -o docs/ galaxy
	cp docs/fixed_modules.rst docs/modules.rst

docs: ready-docs
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; $(MAKE) -C docs clean
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; $(MAKE) -C docs html

lint-docs: ready-docs
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; $(MAKE) -C docs clean
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; ! (make -C docs html 2>&1 | grep -v 'nonlocal image URI found\|included in any toctree' | grep WARNING)

open-docs: docs
	open docs/_build/html/index.html || xdg-open docs/_build/html/index.html

open-rtd: docs
	open https://pulsar.readthedocs.org || xdg-open docs/_build/html/index.html

open-project:
	open https://github.com/galaxyproject/pulsar || xdg-open https://github.com/galaxyproject/pulsar

dist: clean
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; python setup.py sdist bdist_egg bdist_wheel
	ls -l dist

release-test: dist
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; twine upload -r test dist/*
	open https://testpypi.python.org/pypi/pulsar-app || https://testpypi.python.org/pypi/pulsar-app

release:
	@while [ -z "$$CONTINUE" ]; do \
	  read -r -p "Have you executed release-test and reviewed results? [y/N]: " CONTINUE; \
	done ; \
	[ $$CONTINUE = "y" ] || [ $$CONTINUE = "Y" ] || (echo "Exiting."; exit 1;)
	@echo "Releasing"
	if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; twine upload dist/*
