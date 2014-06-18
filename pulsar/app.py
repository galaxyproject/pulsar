""" Deprecated module for wsgi app factory. LWR servers should transition to
``lwr.web.wsgi:app_factory``.
"""
from pulsar.web.wsgi import app_factory

__all__ = ['app_factory']
