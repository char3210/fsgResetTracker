from twitchAPI import Twitch
from twitchAPI.helper import first
from twitchAPI.types import AuthScope, TwitchAPIException
from twitchAPI.chat import Chat
from twitchauth import ImplicitAuthenticator
import asyncio
from datetime import datetime, timedelta
from Settings import settings, write_settings, DEFAULT_SETTINGS

enabled = False
dirty = False
chat: Chat = None
room: str = None

blinds = [0] * 4
ees = 0
completions = 0
blindtimes = []
eetimes = []
completiontimes = []


def ms_to_string(ms):
    time = int(ms) // 1000
    hr = time // 3600
    min = (time % 3600) // 60
    sec = time % 60
    res = ''
    if hr > 0:
        res += f'{hr}:'
    res += f'{min:02d}:' if hr > 0 else f'{min}:'
    res += f'{sec:02d}'
    return res


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
    blindtimes.append(ms_to_string(time))
    dirty = True


def enter_end(time):
    global dirty, ees
    ees += 1
    eetimes.append(ms_to_string(time))
    dirty = True


def completion(time):
    global dirty, completions
    completions += 1
    completiontimes.append(ms_to_string(time))
    dirty = True


def reset():
    global dirty, blinds, ees, completions
    blinds = [0] * 4
    ees = 0
    completions = 0
    dirty = True


def setcounters(counts):
    global dirty, blinds, ees, completions
    blinds[0] = counts[0]
    blinds[1] = counts[1]
    blinds[2] = counts[2]
    blinds[3] = counts[3]
    ees = counts[4]
    completions = counts[5]

def updatecounter(counter, values):
    global dirty, ees, completions, blindtimes, eetimes, completiontimes
    if counter == "blinds":
        blinds[0] = values[0]
    elif counter == "sub4":
        blinds[1] = values[0]
    elif counter == "sub330":
        blinds[2] = values[0]
    elif counter == "sub3":
        blinds[3] = values[0]
    elif counter == "ees":
        ees = values[0]
    elif counter == "completions":
        completions = values[0]
    elif counter == "blindtimes":
        blindtimes = values
    elif counter == "eetimes":
        eetimes = values
    elif counter == "completiontimes":
        completiontimes = values
    else:
        return False
    dirty = True
    return True


async def update_command():
    global dirty
    if enabled and dirty:
        dirty = False
        await chat.send_message(room, get_update_command())

def get_update_command():
    command = settings['twitch']['command']
    format = settings['twitch']['format']
    
    return format.format(
        command=command,
        blinds=blinds[0], 
        sub4=blinds[1], 
        sub330=blinds[2], 
        sub3=blinds[3], 
        ees=ees, 
        completions=completions, 
        blindtimes=tostring(blindtimes), 
        eetimes=tostring(eetimes),
        completiontimes=tostring(completiontimes)
    )

def tostring(list):
    if len(list) == 0:
        return ""
    return f"[{', '.join(list)}]"

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
    
    if 'format' not in twitchsettings:
        twitchsettings['format'] = DEFAULT_SETTINGS['twitch']['format']
        write_settings(settings)
        
    if 'command' not in twitchsettings:
        twitchsettings['command'] = input('What twitch command should be updated? (leave blank for "!today") ') or "!today"
        write_settings(settings)


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
