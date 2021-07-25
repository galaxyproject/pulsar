
RAW_VALUE_BY_DEFAULT = False
VALID_ENV_OPTIONS = ('file', 'execute', 'name/value')


def env_to_statement(env):
    ''' Return the abstraction description of an environment variable definition
    into a statement for shell script.

    >>> env_to_statement(dict(name='X', value='Y'))
    'X="Y"; export X'
    >>> env_to_statement(dict(name='X', value='Y', raw=True))
    'X=Y; export X'
    >>> env_to_statement(dict(name='X', value='"A","B","C"'))
    'X="\\\\"A\\\\",\\\\"B\\\\",\\\\"C\\\\""; export X'
    >>> env_to_statement(dict(file="Y"))
    '. "Y"'
    >>> env_to_statement(dict(file="'RAW $FILE'", raw=True))
    ". 'RAW $FILE'"
    >>> # Source file takes precedence
    >>> env_to_statement(dict(name='X', value='"A","B","C"', file="S"))
    '. "S"'
    >>> env_to_statement(dict(execute="module load java/1.5.1"))
    'module load java/1.5.1'
    '''
    source_file = env.get('file', None)
    if source_file:
        return '. %s' % __escape(source_file, env)
    execute = env.get('execute', None)
    if execute:
        return execute
    name = env.get('name', None)
    if name:
        value = __escape(str(env['value']), env)
        return '%s=%s; export %s' % (name, value, name)
    raise RuntimeError("Invalid env definition, must be one of %s: %s" % (str(VALID_ENV_OPTIONS), str(env)))


def __escape(value, env):
    raw = env.get('raw', RAW_VALUE_BY_DEFAULT)
    if not raw:
        value = '"' + value.replace('"', '\\"') + '"'
    return value
