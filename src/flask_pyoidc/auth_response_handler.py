import collections
import logging

logger = logging.getLogger(__name__)

AuthenticationResult = collections.namedtuple('AuthenticationResult',
                                              ['access_token', 'id_token_claims', 'id_token_jwt', 'userinfo_claims'])


class AuthResponseProcessError(ValueError):
    pass


class AuthResponseUnexpectedStateError(AuthResponseProcessError):
    pass


class AuthResponseUnexpectedNonceError(AuthResponseProcessError):
    pass


class AuthResponseMismatchingSubjectError(AuthResponseProcessError):
    pass


class AuthResponseErrorResponseError(AuthResponseProcessError):
    def __init__(self, error_response):
        """
        Args:
            error_response (Mapping[str, str]): OAuth error response containing 'error' and 'error_description'
        """
        self.error_response = error_response


class AuthResponseHandler:
    def __init__(self, client):
        """
        Args:
            client (flask_pyoidc.pyoidc_facade.PyoidcFacade): Client proxy to make requests to the provider
        """
        self._client = client

    def process_auth_response(self, auth_response, expected_state, expected_nonce=None):
        """
        Args:
            auth_response (Union[AuthorizationResponse, AuthorizationErrorResponse]): parsed OIDC auth response
            expected_state (str): state value included in the OIDC auth request
            expected_nonce (str): nonce value included in the OIDC auth request
        Returns:
            AuthenticationResult: All relevant data associated with the authenticated user
        """
        if 'error' in auth_response:
            raise AuthResponseErrorResponseError(auth_response.to_dict())

        if auth_response['state'] != expected_state:
            raise AuthResponseUnexpectedStateError()

        # implicit/hybrid flow may return tokens in the auth response
        access_token = auth_response.get('access_token', None)
        id_token_claims = auth_response['id_token'].to_dict() if 'id_token' in auth_response else None
        id_token_jwt = auth_response.get('id_token_jwt', None) if 'id_token_jwt' in auth_response else None

        if 'code' in auth_response:
            token_resp = self._client.token_request(auth_response['code'])

            if 'error' in token_resp:
                raise AuthResponseErrorResponseError(token_resp.to_dict())

            access_token = token_resp['access_token']

            if 'id_token' in token_resp:
                id_token = token_resp['id_token']
                logger.debug('received id token: %s', id_token.to_json())

                if id_token['nonce'] != expected_nonce:
                    raise AuthResponseUnexpectedNonceError()

                id_token_claims = id_token.to_dict()
                id_token_jwt = token_resp.get('id_token_jwt')

        # do userinfo request
        userinfo = self._client.userinfo_request(access_token)
        userinfo_claims = None
        if userinfo:
            userinfo_claims = userinfo.to_dict()

        if id_token_claims and userinfo_claims and userinfo_claims['sub'] != id_token_claims['sub']:
            raise AuthResponseMismatchingSubjectError('The \'sub\' of userinfo does not match \'sub\' of ID Token.')

        return AuthenticationResult(access_token, id_token_claims, id_token_jwt, userinfo_claims)
