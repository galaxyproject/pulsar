""" This module contains the code that allows the LWR to stage file's during
preprocessing (currently this means downloading or copying files) and then unstage
or send results back to client during postprocessing.

:mod:`pulsar.managers.staging.preprocess` Module
-------------------------------

.. automodule:: pulsar.managers.staging.preprocess

    .. autofunction:: preprocess

:mod:`pulsar.managers.staging.postprocess` Module
-------------------------------

.. automodule:: pulsar.managers.staging.postprocess

    .. autofunction:: postprocess

"""

from .postprocess import postprocess
from .preprocess import preprocess

__all__ = [preprocess, postprocess]
