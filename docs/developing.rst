==========
Developing
==========

This section contains documentation for maintainers of Pulsar.

Release Checklist
-----------------

This release checklist is based on the `Pocoo Release Management Workflow
<http://www.pocoo.org/internal/release-management/>`_.

This assumes ``~/.pypirc`` file exists with the following fields (variations)
are fine.

::

    [distutils]
    index-servers =
        pypi
        test
    
    [pypi]
    username:<username>
    password:<password>
    
    [test]
    repository:https://test.pypi.org/legacy/
    username:<username>
    password:<password>


* Review ``git status`` for missing files.
* Verify the latest Travis CI builds pass.
* ``make open-docs`` and review changelog.
* Ensure the target release is set correctly in ``pulsar/__init__.py``
  (``version`` will be a ``devN`` variant of target release).
* ``make clean && make lint && make tests``
* ``make release``

  * Review `Test PyPI site <https://testpypi.python.org/pypi/pulsar-app>`_
    for errors.
  * Test intall ``pip install -i https://testpypi.python.org/pypi pulsar-app``.

  This process will push packages to test PyPI, allow review, publish
  to production PyPI, tag the git repository, and push the tag upstream.
  If changes are needed, this can be broken down into steps
  such as:

  * ``make release-local``
  * ``make push-release``
