from string import Template

DEFAULT_JOB_FILE_TEMPLATE = Template("""#!/bin/sh
$headers
$slots_statement
export GALAXY_SLOTS
GALAXY_LIB="$galaxy_lib"
if [ "$GALAXY_LIB" != "None" ]; then
    if [ -n "$PYTHONPATH" ]; then
        PYTHONPATH="$GALAXY_LIB:$PYTHONPATH"
    else
        PYTHONPATH="$GALAXY_LIB"
    fi
    export PYTHONPATH
fi
$env_setup_commands
cd $working_directory
$command
echo $? > $exit_code_path
""")

# SGE: http://www.blog.kubiak.co.uk/post/53
# SLURM: https://computing.llnl.gov/linux/slurm/sbatch.html#lbAF
SLOTS_STATEMENT_CLUSTER_DEFAULT = """
if [ -n "$SLURM_JOB_NUM_NODES" ]; then
    GALAXY_SLOTS="$SLURM_JOB_NUM_NODES"
    GALAXY_SLOTS_CONFIGURED="1"
elif [ -n "$NSLOTS" ]; then
    GALAXY_SLOTS="$NSLOTS"
    GALAXY_SLOTS_CONFIGURED="1"
elif [ -f "$PBS_NODEFILE" ]; then
    GALAXY_SLOTS=`wc -l < $PBS_NODEFILE`
    GALAXY_SLOTS_CONFIGURED="1"
else
    GALAXY_SLOTS="1"
fi
"""

SLOTS_STATEMENT_SINGLE = """
GALAXY_SLOTS="1"
"""

REQUIRED_TEMPLATE_PARAMS = ['working_directory', 'command', 'exit_code_path']
OPTIONAL_TEMPLATE_PARAMS = {
    'galaxy_lib': None,
    'headers': '',
    'env_setup_commands': '',
    'slots_statement': SLOTS_STATEMENT_CLUSTER_DEFAULT,
}


def job_script(template=DEFAULT_JOB_FILE_TEMPLATE, **kwds):
    """

    >>> has_exception = False
    >>> try: job_script()
    ... except Exception as e: has_exception = True
    >>> has_exception
    True
    >>> script = job_script(working_directory='wd', command='uptime', exit_code_path='ec')
    >>> '\\nuptime\\n' in script
    True
    >>> 'echo $? > ec' in script
    True
    >>> 'GALAXY_LIB="None"' in script
    True
    >>> script.startswith('#!/bin/sh\\n#PBS -test\\n')
    False
    >>> script = job_script(working_directory='wd', command='uptime', exit_code_path='ec', headers='#PBS -test')
    >>> script.startswith('#!/bin/sh\\n#PBS -test\\n')
    True
    >>> script = job_script(working_directory='wd', command='uptime', exit_code_path='ec', slots_statement='GALAXY_SLOTS="$SLURM_JOB_NUM_NODES"')
    >>> script.find('GALAXY_SLOTS="$SLURM_JOB_NUM_NODES"\\nexport GALAXY_SLOTS\\n') > 0
    True
    """
    if any([param not in kwds for param in REQUIRED_TEMPLATE_PARAMS]):
        raise Exception("Failed to create job_script, a required parameter is missing.")
    template_params = OPTIONAL_TEMPLATE_PARAMS.copy()
    template_params.update(**kwds)
    if not isinstance(template, Template):
        template = Template(template)
    return template.safe_substitute(template_params)
