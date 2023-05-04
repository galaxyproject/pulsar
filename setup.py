import ast
import os
import re

try:
    from distutils.util import get_platform
    is_windows = get_platform().startswith("win")
except ImportError:
    # Don't break install if distuils is incompatible in some way
    # probably overly defensive.
    is_windows = False
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

# Set environment variable to 1 to build as library for Galaxy instead
# of as stand-alone app.
DEFAULT_PULSAR_GALAXY_LIB = 0
PULSAR_GALAXY_LIB = os.environ.get("PULSAR_GALAXY_LIB", "%d" % DEFAULT_PULSAR_GALAXY_LIB) == "1"

readme = open('README.rst').read()
history = open('HISTORY.rst').read().replace('.. :changelog:', '')

if os.path.exists("requirements.txt"):
    requirements = [r for r in open("requirements.txt").read().split("\n") if ";" not in r]
else:
    # In tox, it will cover them anyway.
    requirements = []

if PULSAR_GALAXY_LIB:
    requirements = [r for r in requirements if not r.startswith("galaxy-")]


_version_re = re.compile(r'__version__\s+=\s+(.*)')

with open('pulsar/__init__.py', 'rb') as f:
    version = str(ast.literal_eval(_version_re.search(
        f.read().decode('utf-8')).group(1)))

if is_windows:
    scripts = ["scripts/pulsar.bat"]
else:
    scripts = ["scripts/pulsar"]

name = "pulsar-app" if not PULSAR_GALAXY_LIB else "pulsar-galaxy-lib"

setup(
    name=name,
    version=version,
    description='Distributed job execution application built for Galaxy (http://galaxyproject.org/).',
    long_description=readme + '\n\n' + history,
    long_description_content_type='text/x-rst',
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
        'pulsar.user_auth',
        'pulsar.user_auth.methods',
        'pulsar.util',
        'pulsar.util.pastescript',
        'pulsar.web',
    ],
    entry_points='''
        [console_scripts]
        pulsar-main=pulsar.main:main
        pulsar-check=pulsar.client.test.check:main
        pulsar-config=pulsar.scripts.config:main
        pulsar-drmaa-launch=pulsar.scripts.drmaa_launch:main
        pulsar-drmaa-kill=pulsar.scripts.drmaa_kill:main
        pulsar-chown-working-directory=pulsar.scripts.chown_working_directory:main
        pulsar-submit=pulsar.scripts.submit:main
        pulsar-finish=pulsar.scripts.finish:main
        pulsar-run=pulsar.scripts.run:main
        _pulsar-conda-init=pulsar.scripts._conda_init:main
        _pulsar-configure-slurm=pulsar.scripts._configure_slurm:main
        _pulsar-configure-galaxy-cvmfs=pulsar.scripts._configure_galaxy_cvmfs:main
    ''',
    scripts=scripts,
    package_data={'pulsar': [
        'managers/util/job_script/DEFAULT_JOB_FILE_TEMPLATE.sh',
        'managers/util/job_script/CLUSTER_SLOTS_STATEMENT.sh',
        'scripts/cvmfs_data/*',
    ]},
    package_dir={'pulsar': 'pulsar'},
    include_package_data=True,
    install_requires=requirements,
    extras_require={
        'amqp': ['kombu'],
        'web': ['Paste', 'PasteScript'],
        'galaxy_extended_metadata': ['galaxy-job-execution', 'galaxy-util[template]'],
    },
    license="Apache License 2.0",
    zip_safe=False,
    keywords='pulsar',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Environment :: Console',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX',
        'Operating System :: Microsoft :: Windows',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
)
