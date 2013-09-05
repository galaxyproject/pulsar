"""
Condor helper utilities.
"""

DEFAULT_QUERY_CLASSAD = dict(
    universe='vanilla',
    getenv='true',
    notification='NEVER',
)


def build_submit_description(executable, output, error, user_log, query_params):
    """
    Build up the contents of a condor submit description file.

    >>> submit_args = dict(executable='/path/to/script', output='o', error='e', user_log='ul')
    >>> submit_args['query_params'] = dict()
    >>> default_description = build_submit_description(**submit_args)
    >>> assert 'executable = /path/to/script' in default_description
    >>> assert 'output = o' in default_description
    >>> assert 'error = e' in default_description
    >>> assert 'queue' in default_description
    >>> assert 'universe = vanilla' in default_description
    >>> assert 'universe = standard' not in default_description
    >>> submit_args['query_params'] = dict(universe='standard')
    >>> std_description = build_submit_description(**submit_args)
    >>> assert 'universe = vanilla' not in std_description
    >>> assert 'universe = standard' in std_description
    """
    all_query_params = DEFAULT_QUERY_CLASSAD.copy()
    all_query_params.update(query_params)

    submit_description = []
    for key, value in all_query_params.items():
        submit_description.append('%s = %s' % (key, value))
    submit_description.append('executable = ' + executable)
    submit_description.append('output = ' + output)
    submit_description.append('error = ' + error)
    submit_description.append('log = ' + user_log)
    submit_description.append('queue')
    return '\n'.join(submit_description)
