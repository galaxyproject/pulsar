from abc import ABC, abstractmethod


class AuthMethod(ABC):
    """
    Defines the interface to various authentication/authorization methods.
    """

    @abstractmethod
    def authorize(self, authentication_info):
        raise NotImplementedError("a concrete class should implement this")

    @abstractmethod
    def authenticate(self, job_directory):
        raise NotImplementedError("a concrete class should implement this")
