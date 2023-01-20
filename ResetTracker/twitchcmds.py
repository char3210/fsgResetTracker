from twitchAPI import Twitch
from twitchAPI.helper import first
from twitchAPI.types import AuthScope, TwitchAPIException
from twitchAPI.chat import Chat
from twitchauth import ImplicitAuthenticator
import asyncio
from Settings import settings, write_settings

enabled = False
dirty = False
chat: Chat = None
room: str = None

blinds = [0] * 4
ees = 0
completions = 0

def blind(time):
    """
    called when user gets a run that blinds at a time (in ms) 
    """
    global dirty
    blinds[0] += 1
    if time < 4*60*1000: # sub 4
        blinds[1] += 1
    if time < (3*60+30)*1000: # sub 3:30
        blinds[2] += 1
    if time < 3*60*1000: # sub 3
        blinds[3] += 1
    dirty = True

def enter_end():
    global dirty, ees
    ees += 1
    dirty = True

def completion():
    global dirty, completions
    completions += 1
    dirty = True

def reset():
    global dirty, blinds, ees, completions
    blinds = [0] * 4
    ees = 0
    completions = 0
    dirty = True

async def update_command():
    global dirty
    if enabled and dirty:
        dirty = False
        await chat.send_message(room, get_update_command())

def get_update_command():
    return f"!editcom !today Blinds: {blinds[0]} [Sub 4: {blinds[1]}] [Sub 3:30: {blinds[2]}] [Sub 3: {blinds[3]}] | " \
        f"Enter Ends: {ees} | Completions: {completions}"

def setup():
    if 'twitch' not in settings:
        settings['twitch'] = {}
    twitchsettings = settings['twitch']

    if "enabled" not in twitchsettings:
        yesno = input("Would you like to enable Twitch integration? (y/n) ")
        twitchsettings["enabled"] = yesno.lower() == "y"
        write_settings(settings)
    
    if not twitchsettings['enabled']:
        print('Skipping twitch integration')
        return

    print("Enabling twitch integration...")

    asyncio.run(enable())

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

    global chat, room, enabled
    chat = await Chat(twitch)
    chat.start()

    room = thisuser.login
    await chat.join_room(room)

    enabled = True

def stop():
    if enabled:
        chat.stop()
