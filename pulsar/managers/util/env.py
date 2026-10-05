from typing_extensions import TypedDict

RAW_VALUE_BY_DEFAULT = False
VALID_ENV_OPTIONS = ("file", "execute", "name/value")


class EnvVar(TypedDict, total=False):
    """An environment definition: a name/value pair, a file to source, or a command to execute."""

    name: str
    value: str
    raw: bool
    file: str
    execute: str


def env_to_statement(env: EnvVar) -> str:
    """Return the abstraction description of an environment variable definition
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
    """
    source_file = env.get("file")
    if source_file:
        return f". {__escape(source_file, env)}"
    execute = env.get("execute")
    if execute:
        return execute
    name = env.get("name")
    value = env.get("value")
    if name and value is not None:
        return f"{name}={__escape(str(value), env)}; export {name}"
    raise RuntimeError(f"Invalid env definition, must be one of {VALID_ENV_OPTIONS}: {env}")


def __escape(value: str, env: EnvVar) -> str:
    raw = env.get("raw", RAW_VALUE_BY_DEFAULT)
    if not raw:
        value = '"' + value.replace('"', '\\"') + '"'
    return value
