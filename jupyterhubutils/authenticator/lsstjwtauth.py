'''LSST Authenticator to use JWT token present in request headers.
'''
import asyncio
from eliot import log_call
from jwtauthenticator.jwtauthenticator import JSONWebTokenAuthenticator
from .lsstauth import LSSTAuthenticator
from .lsstjwtloginhandler import LSSTJWTLoginHandler
from ..utils import make_logger


class LSSTJWTAuthenticator(LSSTAuthenticator, JSONWebTokenAuthenticator):
    auth_refresh_age = 900
    header_name = "X-Portal-Authorization"
    header_is_authorization = True
    username_claim_field = 'uid'

    def __init__(self, *args, **kwargs):
        '''Add LSST Manager structure to hold LSST-specific logic.
        '''
        self.log = make_logger()
        self.log.debug("Creating LSSTJWTAuthenticator")
        super().__init__(*args, **kwargs)

    @log_call
    def get_handlers(self, app):
        '''Install custom handlers.
        '''
        return [
            (r'/login', LSSTJWTLoginHandler),
        ]

    @log_call
    def logout_url(self, base_url):
        '''Returns the logout URL for JWT.
        '''
        return self.lsst_mgr.config.jwt_logout_url

    async def refresh_user(self, user, handler):
        '''Delegate to login handler, if this happens in the login
        '''
        # We don't want to do this anywhere but on the login handler.
        #  It's cheating, but we'll just check to see if there is
        #  a custom method for refresh_user on the handler and call it
        #  if so.  That's true for the LSST JWT Authenticator case.
        with start_action(action_type="refresh_user"):
            retval = await super().refresh_user(user, handler)
            if hasattr(handler, 'refresh_user'):
                return await handler.refresh_user(user, handler)
            else:
                return retval
