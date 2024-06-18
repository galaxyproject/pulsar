""" Pulsar utilities.
"""
from tempfile import NamedTemporaryFile

BUFFER_SIZE = 4096


def copy_to_path(object, path):
    """
    Copy file-like object to path.
    """
    with open(path, 'wb') as output:
        _copy(object, output)


def _copy(object, output):
    while True:
        buffer = object.read(BUFFER_SIZE)
        if not buffer:
            break
        output.write(buffer)


def copy_to_temp(object):
    """
    Copy file-like object to temp file and return
    path.
    """
    with NamedTemporaryFile(delete=False) as temp_file:
        _copy(object, temp_file)
    return temp_file.name


def enum(**enums):
    """
    http://stackoverflow.com/questions/36932/how-can-i-represent-an-enum-in-python
    """
    return type('Enum', (), enums)
