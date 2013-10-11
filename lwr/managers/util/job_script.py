from string import Template

DEFAULT_JOB_FILE_TEMPLATE = Template("""#!/bin/sh
$headers
GALAXY_SLOTS="$slots_expression"
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

REQUIRED_TEMPLATE_PARAMS = ['working_directory', 'command', 'exit_code_path']
OPTIONAL_TEMPLATE_PARAMS = {
    'galaxy_lib': None,
    'headers': '',
    'env_setup_commands': '',
    'slots_expression': '1',
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
    >>> script = job_script(working_directory='wd', command='uptime', exit_code_path='ec', slots_expression='$SLURM_JOB_NUM_NODES')
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
