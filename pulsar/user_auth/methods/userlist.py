from pulsar.user_auth.methods.interface import AuthMethod


class UserListAuth(AuthMethod):
    """
    Defines authorization user by username
    """

    def __init__(self, config):
        try:
            self._allowed_users = config["userlist_allowed_users"]
        except Exception as e:
            raise Exception("cannot read UsernameAuth configuration") from e

    auth_type = "userlist"

    def authorize(self, authentication_info):
        return authentication_info["username"] in self._allowed_users

    def authenticate(self, job_directory):
        raise NotImplementedError("authentication not implemented for this class")
