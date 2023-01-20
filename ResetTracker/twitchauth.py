import aiohttp

from twitchAPI import Twitch
from twitchAPI.helper import build_url, build_scope, get_uuid, TWITCH_AUTH_BASE_URL, fields_to_enum, first
from twitchAPI.types import AuthScope, InvalidRefreshTokenException, UnauthorizedException, TwitchAPIException
from twitchAPI.chat import Chat
from typing import Optional, Callable
import webbrowser
from aiohttp import web
import asyncio
from threading import Thread
from time import sleep
from concurrent.futures._base import CancelledError
from logging import getLogger, Logger

from typing import List, Union

class ImplicitAuthenticator:
    """Simple to use client for the Twitch implicit authentication flow.
       """

    def __init__(self,
                 twitch: 'Twitch',
                 scopes: List[AuthScope],
                 force_verify: bool = False,
                 url: str = 'http://localhost:17563'):
        """

        :param twitch: A twitch instance
        :param scopes: List of the desired Auth scopes
        :param force_verify: If this is true, the user will always be prompted for authorization by twitch |default| :code:`False`
        :param url: The reachable URL that will be opened in the browser. |default| :code:`http://localhost:17563`
        """
        self.__twitch: 'Twitch' = twitch
        self.__client_id: str = twitch.app_id
        self.scopes: List[AuthScope] = scopes
        self.force_verify: bool = force_verify
        self.logger: Logger = getLogger('twitchAPI.oauth')
        """The logger used for OAuth related log messages"""
        self.url = url
        self.redirect_document: str = """<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>pyTwitchAPI OAuth</title>
        </head>
        <body>
            <h1>Redirecting you...</h1>
            <script>
            window.location = "http://localhost:17563/" + "?" + document.location.hash.substring(1)
            </script>
        </body>
        </html>"""
        self.document: str = """<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>pyTwitchAPI OAuth</title>
        </head>
        <body>
            <h1>Thanks for Authenticating with pyTwitchAPI!</h1>
        This page closes itself after 5 seconds.
            <script>
            setTimeout(function() {
                window.close();
                }, 5000);
            </script>
        </body>
        </html>"""
        """The document that will be rendered at the end of the flow"""
        self.port: int = 17563
        """The port that will be used. |default| :code:`17653`"""
        self.host: str = '0.0.0.0'
        """the host the webserver will bind to. |default| :code:`0.0.0.0`"""
        self.state: str = str(get_uuid())
        self.__callback_func = None
        self.__server_running: bool = False
        self.__loop: Union[asyncio.AbstractEventLoop, None] = None
        self.__runner: Union[web.AppRunner, None] = None
        self.__thread: Union[Thread, None] = None
        self.__user_token: Union[str, None] = None
        self.__can_close: bool = False
        self.__is_closed = False

    def __build_auth_url(self):
        params = {
            'client_id': self.__twitch.app_id,
            'redirect_uri': self.url,
            'response_type': 'token',
            'scope': build_scope(self.scopes),
            'force_verify': str(self.force_verify).lower(),
            'state': self.state
        }
        return build_url(TWITCH_AUTH_BASE_URL + 'oauth2/authorize', params)

    def __build_runner(self):
        app = web.Application()
        app.add_routes([web.route('*', '/', self.__handle_callback)])
        return web.AppRunner(app)

    async def __run_check(self):
        while not self.__can_close:
            await asyncio.sleep(0.1)
        await self.__runner.shutdown()
        await self.__runner.cleanup()
        self.logger.info('shutting down oauth Webserver')
        self.__is_closed = True

    def __run(self, runner: web.AppRunner):
        self.__runner = runner
        self.__loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.__loop)
        self.__loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, self.host, self.port)
        self.__loop.run_until_complete(site.start())
        self.__server_running = True
        self.logger.info('running oauth Webserver')
        try:
            self.__loop.run_until_complete(self.__run_check())
        except (CancelledError, asyncio.CancelledError):
            pass

    def __start(self):
        self.__thread = Thread(target=self.__run, args=(self.__build_runner(),))
        self.__thread.start()

    def stop(self):
        """Manually stop the flow

        :rtype: None
        """
        self.__can_close = True

    async def __handle_callback(self, request: web.Request):
        # http://localhost:17563/?access_token=xtk0fb6z1283nwigggw1nr61yc6zig&scope=chat%3Aread+chat%3Aedit&state=4abfbded-b7e8-4f1a-a4ff-3ff6e2fc1a0f&token_type=bearer

        val = request.rel_url.query.get('state')
        if val is None:
            return web.Response(text=self.redirect_document, content_type='text/html')

        self.logger.debug(f'got callback with state {val}')
        # invalid state!
        if val != self.state:
            return web.Response(status=401)
        self.__user_token = request.rel_url.query.get('access_token')
        if self.__user_token is None:
            # must provide code
            return web.Response(status=400)
        if self.__callback_func is not None:
            self.__callback_func(self.__user_token)
        return web.Response(text=self.document, content_type='text/html')

    def return_auth_url(self):
        """Returns the URL that will authenticate the app, used for headless server environments."""
        return self.__build_auth_url()

    async def authenticate(self,
                           callback_func: Optional[Callable[[str, str], None]] = None,
                           user_token: Optional[str] = None,
                           browser_name: Optional[str] = None,
                           browser_new: int = 2):
        """Start the user authentication flow\n
        If callback_func is not set, authenticate will wait till the authentication process finished and then return
        the access_token and the refresh_token
        If user_token is set, it will be used instead of launching the webserver and opening the browser

        :param callback_func: Function to call once the authentication finished.
        :param user_token: Code obtained from twitch to request the access and refresh token.
        :param browser_name: The browser that should be used, None means that the system default is used.
                            See `the webbrowser documentation <https://docs.python.org/3/library/webbrowser.html#webbrowser.register>`__ for more info
                            |default|:code:`None`
        :param browser_new: controls in which way the link will be opened in the browser.
                            See `the webbrowser documentation <https://docs.python.org/3/library/webbrowser.html#webbrowser.open>`__ for more info
                            |default|:code:`2`
        :return: None if callback_func is set, otherwise access_token
        :raises ~twitchAPI.types.TwitchAPIException: if authentication fails
        :rtype: None or (str, str)
        """
        self.__callback_func = callback_func
        self.__can_close = False
        self.__user_token = None
        self.__is_closed = False

        if user_token is None:
            self.__start()
            # wait for the server to start up
            while not self.__server_running:
                sleep(0.01)
            # open in browser
            browser = webbrowser.get(browser_name)
            toopenurl = self.__build_auth_url()
            print("opening url " + toopenurl)
            browser.open(toopenurl, new=browser_new)
            
            while self.__user_token is None:
                sleep(0.01)
            # now we need to actually get the correct token
        else:
            self.__user_token = user_token
            self.__is_closed = True
        self.stop()
        while not self.__is_closed:
            await asyncio.sleep(0.1)
        return self.__user_token #lol


async def twitch_example():
    # initialize the twitch instance, this will by default also create a app authentication for you
    twitch = await Twitch('cy0wkkzf69rj7gsvypb6tjxdvdoif3', authenticate_app=False)
    twitch.auto_refresh_auth = False

    scope = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT]
    
    auth = ImplicitAuthenticator(twitch, scope, force_verify=False)
    token = await auth.authenticate()
    await twitch.set_user_authentication(token, scope)

    thisuser = await first(twitch.get_users())

    chat = await Chat(twitch)
    chat.start()

    room = thisuser.login
    await chat.join_room(room)
    await chat.send_message(room, "!commands")

    chat.stop()

if __name__ == "__main__":
    # run this example
    asyncio.run(twitch_example())

