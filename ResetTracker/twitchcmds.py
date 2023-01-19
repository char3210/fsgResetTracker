from twitchAPI import Twitch
from twitchAPI.helper import first
from twitchAPI.types import AuthScope, TwitchAPIException
from twitchAPI.chat import Chat
from twitchauth import ImplicitAuthenticator

enabled = False
dirty = False
chat: Chat = None
room: str = None

def blind(time):
    # if blind is sub 3 increment sub 3 counter, etc.
    dirty = True

def enter_end():
    dirty = True

def completion():
    dirty = True

def reset():
    #things
    dirty = True
    updateCommand()
    pass

async def updateCommand():
    if enabled and dirty:
        dirty = False
        await chat.send_message(room, get_update_command())

def get_update_command():
    return "!commands"

async def enable():
    twitch = await Twitch('cy0wkkzf69rj7gsvypb6tjxdvdoif3', authenticate_app=False)
    twitch.auto_refresh_auth = False

    scope = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT]
    
    auth = ImplicitAuthenticator(twitch, scope, force_verify=False)
    try:
        token = await auth.authenticate()
    except (TwitchAPIException):
        print("Twitch authentication failed! Not enabling twitch chat integration")
        return
    await twitch.set_user_authentication(token, scope)

    thisuser = await first(twitch.get_users())

    global chat
    global room
    chat = await Chat(twitch)
    chat.start()

    room = thisuser.login
    await chat.join_room(room)

    enabled = True

def stop():
    chat.stop()
