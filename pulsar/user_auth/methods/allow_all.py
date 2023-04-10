from pulsar.user_auth.methods.interface import AuthMethod


class AlwaysAllowAuthMethod(AuthMethod):
    """
    Always allow
    """

    def __init__(self, _config):
        pass

    auth_type = "allow_all"

    def authorize(self, authentication_info):
        return True

    def authenticate(self, job_directory):
        return {"username": "anonymous"}
