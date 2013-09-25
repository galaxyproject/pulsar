try:
    from argparser import ArgumentParser
except ImportError:
    from optparse import OptionParser

    class ArgumentParser(OptionParser):

        def __init__(self, **kwargs):
            self.delegate = OptionParser(**kwargs)

        def add_argument(self, *args, **kwargs):
            if "required" in kwargs:
                del kwargs["required"]
            return self.delegate.add_option(*args, **kwargs)

        def parse_args(self):
            (options, args) = self.delegate.parse_args()
            return options


__all__ = [ArgumentParser]
