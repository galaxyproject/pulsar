.PHONY: clean-pyc clean-build docs clean

help:
	@echo "clean - remove all build, test, coverage and Python artifacts"
	@echo "clean-build - remove build artifacts"
	@echo "clean-pyc - remove Python file artifacts"
	@echo "clean-test - remove test and coverage artifacts"
	@echo "lint - check style with flake8"
	@echo "test - run tests quickly with the default Python"
	@echo "coverage - check code coverage quickly with the default Python"
	@echo "docs - generate Sphinx HTML documentation, including API docs"

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

lint:
	flake8 --exclude test_tool_deps.py --max-complexity 9 pulsar test

tests:
	nosetests

coverage: tests
	coverage html
	open coverage_html_report/index.html || xdg-open coverage_html_report/index.html

docs:
	rm -f docs/pulsar.rst
	rm -f docs/galaxy.rst
	rm -f docs/modules.rst
	sphinx-apidoc -f -o docs/ pulsar
	sphinx-apidoc -f -o docs/ galaxy
	cp docs/fixed_modules.rst docs/modules.rst
	$(MAKE) -C docs clean
	$(MAKE) -C docs html

open-docs: docs
	open docs/_build/html/index.html || xdg-open docs/_build/html/index.html

open-rtd: docs
	open https://pulsar.readthedocs.org || xdg-open docs/_build/html/index.html

open-project:
	open https://github.com/galaxyproject/pulsar || xdg-open https://github.com/galaxyproject/pulsar

# TODO: Wheel
dist: clean
	python setup.py sdist bdist_egg
	ls -l dist
