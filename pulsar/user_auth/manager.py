from abc import ABC

import inspect


class UserAuthManager(ABC):
    """
    Authorization/Authentication manager.
    """

    def __init__(self, config):
        self._authorization_methods = []
        self._authentication_methods = []

        try:
            user_auth = config.get("user_auth", None)
            if not user_auth:
                return
            authentications = user_auth.pop("authentication", [])
            authorizations = user_auth.pop("authorization", [])

            for authorization in authorizations:
                authorization.update(user_auth)
                obj = get_object("pulsar.user_auth.methods." + authorization["type"], "auth_type",
                                 authorization["type"])
                self._authorization_methods.append(obj(authorization))

            for authentication in authentications:
                authentication.update(user_auth)
                obj = get_object("pulsar.user_auth.methods." + authentication["type"], "auth_type",
                                 authentication["type"])
                self._authentication_methods.append(obj(authentication))
        except Exception as e:
            raise Exception("cannot read auth configuration") from e

    def authorize(self, job_id, job_directory):
        authentication_info = self.__authenticate(job_id, job_directory)

        if len(self._authorization_methods) == 0:
            return True
        for method in self._authorization_methods:
            res = method.authorize(authentication_info)
            if res:
                return True

        raise Exception("Could not authorize job execution on remote resource")

    def __authenticate(self, job_id, job_directory):
        if len(self._authentication_methods) == 0:
            return {}
        for method in self._authentication_methods:
            res = method.authenticate(job_directory)
            if res:
                return res

        raise Exception("Could not authenticate job %s" % job_id)


def get_object(module_name, attribute_name, attribute_value):
    module = __import__(module_name)
    for comp in module_name.split(".")[1:]:
        module = getattr(module, comp)
    for _, obj in inspect.getmembers(module):
        if inspect.isclass(obj) and hasattr(obj, attribute_name) and getattr(obj, attribute_name) == attribute_value:
            return obj
    raise Exception("Cannot find object %s with attribute %s=%s " % (module_name, attribute_name, attribute_value))
