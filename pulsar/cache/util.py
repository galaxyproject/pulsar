
import os
import shutil

from datetime import datetime


def atomicish_move(source, destination, tmp_suffix="_TMP"):
    """Move source to destination without risk of partial moves.

    > from tempfile import mkdtemp
    > from os.path import join, exists
    > temp_dir = mkdtemp()
    > source = join(temp_dir, "the_source")
    > destination = join(temp_dir, "the_dest")
    > open(source, "wb").write(b"Hello World!")
    > assert exists(source)
    > assert not exists(destination)
    > atomicish_move(source, destination)
    > assert not exists(source)
    > assert exists(destination)
    """
    destination_dir = os.path.dirname(destination)
    destination_name = os.path.basename(destination)
    temp_destination = os.path.join(destination_dir, "%s%s" % (destination_name, tmp_suffix))
    shutil.move(source, temp_destination)
    os.rename(temp_destination, destination)


class Time:
    """Time utilities of now that can be instrumented for testing."""

    @classmethod
    def now(cls):
        """Return the current datetime."""
        return datetime.utcnow()
