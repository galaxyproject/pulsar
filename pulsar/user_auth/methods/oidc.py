import requests
import base64
import json
import jwt
import re
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import load_der_x509_certificate

from pulsar.user_auth.methods.interface import AuthMethod

import logging

log = logging.getLogger(__name__)


def get_token(job_directory, provider):
    log.debug("Getting OIDC token for provider " + provider + " from Galaxy")
    endpoint = job_directory.load_metadata("launch_config")["token_endpoint"]
    endpoint = endpoint + "&provider=" + provider
    r = requests.get(url=endpoint)
    return r.text


class OIDCAuth(AuthMethod):
    """
    Authorization based on OIDC tokens
    """
    auth_type = "oidc"

    def __init__(self, config):
        try:
            self._provider = config["oidc_provider"]
            self._jwks_url = config["oidc_jwks_url"]
            self._username_in_token = config["oidc_username_in_token"]
            self._username_template = config["oidc_username_template"]

        except Exception as e:
            raise Exception("cannot read OIDCAuth configuration") from e

    def _verify_token(self, token):
        try:
            # Obtain appropriate cert from JWK URI
            key_set = requests.get(self._jwks_url, timeout=5)
            encoded_header, rest = token.split('.', 1)
            headerobj = json.loads(base64.b64decode(encoded_header + '==').decode('utf8'))
            key_id = headerobj['kid']
            for key in key_set.json()['keys']:
                if key['kid'] == key_id:
                    x5c = key['x5c'][0]
                    break
            else:
                raise jwt.DecodeError('Cannot find kid ' + key_id)
            cert = load_der_x509_certificate(base64.b64decode(x5c), default_backend())
            # Decode token (exp date is checked automatically)
            decoded_token = jwt.decode(
                token,
                key=cert.public_key(),
                algorithms=['RS256'],
                options={'exp': True, 'verify_aud': False}
            )
            return decoded_token
        except Exception as error:
            raise Exception("Error verifying jwt token") from error

    def authorize(self, authentication_info):
        raise NotImplementedError("authorization not implemented for this class")

    def authenticate(self, job_directory):
        token = get_token(job_directory, self._provider)

        decoded_token = self._verify_token(token)
        user = decoded_token[self._username_in_token]
        user = re.match(self._username_template, user).group(0)
        return {"username": user}
