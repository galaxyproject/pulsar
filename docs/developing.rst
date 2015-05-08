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
    repository:https://testpypi.python.org/pypi
    username:<username>
    password:<password>


* Review ``git status`` for missing files.
* Verify the latest Travis CI builds pass.
* ``make open-docs`` and review changelog.
* ``make clean && make lint && make tests``
* ``python tools/commit_version.py <new_version>``
* ``make release``
    * Review `Test PyPI site <https://testpypi.python.org/pypi/pulsar-app>`_
      for errors.
    * Test intall ``pip install -i https://testpypi.python.org/pypi pulsar-app``.
* ``python scripts/new_version.py <new_version>``
* ``git push origin master``
* ``git push --tags origin``
