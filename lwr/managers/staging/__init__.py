""" This module contains the code that allows the LWR to stage file's during
preprocessing (currently this means downloading or copying files) and then unstage
or send results back to client during postprocessing.

:mod:`lwr.managers.staging.preprocess` Module
-------------------------------

.. automodule:: lwr.managers.staging.preprocess

    .. autofunction:: preprocess

:mod:`lwr.managers.staging.postprocess` Module
-------------------------------

.. automodule:: lwr.managers.staging.postprocess

    .. autofunction:: postprocess

"""

from .postprocess import postprocess
from .preprocess import preprocess

__all__ = [preprocess, postprocess]
