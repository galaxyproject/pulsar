import re
import ast
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


readme = open('README.rst').read()
history = open('HISTORY.rst').read().replace('.. :changelog:', '')

requirements = [
    'six',
    'webob',
    'psutil',
    'paste',
    'PasteScript',
]

test_requirements = [
    # TODO: put package test requirements here
]


_version_re = re.compile(r'__version__\s+=\s+(.*)')

with open('pulsar/__init__.py', 'rb') as f:
    version = str(ast.literal_eval(_version_re.search(
        f.read().decode('utf-8')).group(1)))

setup(
    name='pulsar-app',
    version=version,
    description='Distributed job execution application built for Galaxy (http://galaxyproject.org/).',
    long_description=readme + '\n\n' + history,
    author='Galaxy Project',
    author_email='jmchilton@gmail.com',
    url='https://github.com/galaxyproject/pulsar',
    packages=[
        'pulsar',
        'pulsar.cache',
        'pulsar.client',
        'pulsar.client.test',
        'pulsar.client.staging',
        'pulsar.client.transport',
        'pulsar.managers',
        'pulsar.managers.base',
        'pulsar.managers.staging',
        'pulsar.managers.util',
        'pulsar.managers.util.cli',
        'pulsar.managers.util.cli.job',
        'pulsar.managers.util.cli.shell',
        'pulsar.managers.util.condor',
        'pulsar.managers.util.drmaa',
        'pulsar.managers.util.job_script',
        'pulsar.mesos',
        'pulsar.messaging',
        'pulsar.scripts',
        'pulsar.tools',
        'pulsar.web',
        'galaxy',
        'galaxy.jobs',
        'galaxy.jobs.metrics',
        'galaxy.jobs.metrics.collectl',
        'galaxy.jobs.metrics.instrumenters',
        'galaxy.objectstore',
        'galaxy.tools',
        'galaxy.tools.linters',
        'galaxy.tools.deps',
        'galaxy.tools.deps.resolvers',
        'galaxy.util',
    ],
    entry_points='''
        [console_scripts]
        pulsar-main=pulsar.main:main
        pulsar-check=pulsar.client.test.check:main
        pulsar-config=pulsar.scripts.config:main
    ''',
    scripts=[
        'scripts/pulsar',
    ],
    package_data={'pulsar': [
        'managers/util/job_script/DEFAULT_JOB_FILE_TEMPLATE.sh',
        'managers/util/job_script/CLUSTER_SLOTS_STATEMENT.sh',
    ]},
    package_dir={'pulsar': 'pulsar',
                 'galaxy': 'galaxy'},
    include_package_data=True,
    install_requires=requirements,
    license="Apache License 2.0",
    zip_safe=False,
    keywords='pulsar',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Environment :: Console',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
    ],
    test_suite='test',
    tests_require=test_requirements
)
