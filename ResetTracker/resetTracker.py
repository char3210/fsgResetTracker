import time
import json
import math
import csv
import glob
import os
from datetime import datetime, timedelta
import threading
import Sheets
from Sheets import main, setup
from Settings import settings, read_settings, write_settings, DEFAULT_SETTINGS
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from checks import advChecks, statsChecks
import twitchcmds
import asyncio

statsCsv = "stats.csv"

def ms_to_string(ms, returnTime=False):
    if ms is None:
        return None
    ms = int(ms)
    t = datetime(1970, 1, 1) + timedelta(milliseconds=ms)
    if returnTime:
        return t
    return t.strftime("%H:%M:%S")

class NewRecord(FileSystemEventHandler):
    buffer = None
    sessionStart = None
    buffer_observer = None
    prev = None
    src_path = None
    # time of last reset
    prev_datetime = None
    wall_resets = 0
    rta_spent = 0
    splitless_count = 0
    break_rta = 0

    def __init__(self):
        self.path = None
        self.data = None

    def ensure_run(self):
        if self.path is None:
            return False, "Path error"
        if self.data is None:
            return False, "Empty data error"
        # FSG
        # if self.data['run_type'] != 'random_seed':
        #     return False, "Set seed detected, will not track"
        return True, ""

    def on_created(self, evt):
        try:
            self.process_file(evt.src_path)
        except Exception as e:
            print(e)
        
    def process_file(self, path):
        self.this_run = [None] * (len(advChecks) + 2 + len(statsChecks))
        self.path = path
        with open(self.path, "r") as record_file:
            try:
                self.data = json.load(record_file)
            except Exception as e:
                # skip
                return
        if self.data is None:
            print("Record file couldnt be read")
            return
        validation = self.ensure_run()
        if not validation[0]:
            print(validation[1])
            return

        # Update prev_datetime, calculate break_rta
        if self.prev_datetime is not None:
            run_offset = self.prev_datetime + \
                timedelta(milliseconds=self.data["final_rta"])
            self.prev_datetime = datetime.now()
            #RTA between end of last run and start of this run but done badly
            run_differ = self.prev_datetime - run_offset
            if run_differ > timedelta(seconds=settings["break-offset"]):
                self.break_rta += run_differ.total_seconds() * 1000
        else:
            self.prev_datetime = datetime.now()

        #increment wall_resets if wall reset
        if self.data["final_rta"] == 0:
            self.wall_resets += 1
            return
        
        #populate stats, adv, lan
        uids = list(self.data["stats"].keys())
        if len(uids) == 0:
            return
        stats = self.data["stats"][uids[0]]["stats"]
        adv = self.data["advancements"]
        lan = self.data["open_lan"]
        if (lan is not None) and not (settings['detect-coop'] and len(self.data['stats']) > 1):
            lan = int(lan)
        else:
            lan = math.inf

        self.this_run[0] = ms_to_string(self.data["final_rta"])

        #increment completion count
        if self.data["is_completed"] and lan > self.data["final_igt"]:
            twitchcmds.completion(self.data["final_igt"])

        # Advancements
        has_done_something = False # has made an advancement
        for idx in range(len(advChecks)):
            time = None
            check = advChecks[idx]
            # Prefer to read from timelines
            if check[0] == "timelines" and self.this_run[idx + 1] is None: # totally not jank 
                for tl in self.data["timelines"]: #most efficient algorithm
                    if tl["name"] == check[1]:
                        if lan > int(tl["rta"]): # if done legit (before opening to lan)
                            self.this_run[idx + 1] = ms_to_string(tl["igt"])
                            time = tl["igt"]
                            has_done_something = True
            # Read other stuff from advancements
            elif (check[0] in adv and adv[check[0]]["complete"] and self.this_run[idx + 1] is None):
                if lan > int(adv[check[0]]["criteria"][check[1]]["rta"]): #variables are a myth
                    time = adv[check[0]]["criteria"][check[1]]["igt"]
                    self.this_run[idx +
                                  1] = ms_to_string(time)
                    has_done_something = True

            if time is not None:
                #hardcode some cases for twitch commands
                if check[1] == "nether_travel":
                    twitchcmds.blind(int(time))
                elif check[1] == "enter_end":
                    twitchcmds.enter_end(int(time))

        # If nothing was done, just count as reset
        if not has_done_something:
            # From earlier we know that final_rta > 0 so this is a splitless non-wall/bg reset
            self.splitless_count += 1
            # Only account for splitless RTA
            self.rta_spent += self.data["final_rta"]
            return

        # Stats
        self.this_run[len(advChecks) + 1] = ms_to_string(
            self.data["final_igt"])
        self.this_run[len(advChecks) + 2] = ms_to_string(
            self.data["retimed_igt"])
        for idx in range(1, len(statsChecks)):
            if (
                statsChecks[idx][0] in stats
                and statsChecks[idx][1] in stats[statsChecks[idx][0]]
            ):
                self.this_run[len(advChecks) + 2 + idx] = str(
                    stats[statsChecks[idx][0]][statsChecks[idx][1]]
                )

        # Generate other stuff
        # iron source redundant, almost always bastion

        # enter type redundant, always completable RP

        # gold source redundant, always bastion

        spawn_biome = "None"
        if "minecraft:adventure/adventuring_time" in adv:
            for biome in adv["minecraft:adventure/adventuring_time"]["criteria"]:
                if adv["minecraft:adventure/adventuring_time"]["criteria"][biome]["igt"] == 0:
                    spawn_biome = biome.split(":")[1]

        iron_time = adv["minecraft:story/smelt_iron"]["igt"] if "minecraft:story/smelt_iron" in adv else None

        # Push to csv
        d = ms_to_string(int(self.data["date"]), returnTime=True)
        data = ([str(d), spawn_biome] + self.this_run +
                [ms_to_string(iron_time), str(self.wall_resets), str(self.splitless_count),
                 ms_to_string(self.rta_spent), ms_to_string(self.break_rta)])

        with open(statsCsv, "r") as infile:
            reader = list(csv.reader(infile))
            reader.insert(0, data)

        with open(statsCsv, "w", newline="") as outfile:
            writer = csv.writer(outfile)
            for line in reader:
                writer.writerow(line)

        # update twitch command
        asyncio.run(twitchcmds.update_command())

        # Reset all counters/sums
        self.wall_resets = 0
        self.rta_spent = 0
        self.splitless_count = 0
        self.break_rta = 0

if __name__ == "__main__":    
    settings.update(read_settings())
    write_settings(settings)

    while 'path' not in settings or not os.path.exists(settings['path']):
        print("Records directory could not be found")
        
        default_path = os.path.expanduser(os.path.join('~', 'speedrunigt', 'records'))
        settings["path"] = input(
            f"Path to SpeedrunIGT records folder (leave blank for \"{default_path}\"): "
        ) or default_path # if input() is blank, use default
        write_settings(settings)

    # create empty stats.csv if nonexistant
    if not os.path.exists(statsCsv):
        f = open(statsCsv, "w", newline="")
        f.close()
    
    # init record observer (required)
    newRecordObserver = Observer()
    event_handler = NewRecord()
    newRecordObserver.schedule(
        event_handler, settings["path"], recursive=False)
    print("tracking: ", settings["path"])
    newRecordObserver.start()

    if 'delete-old-records' not in settings:
        settings['delete-old-records'] = DEFAULT_SETTINGS['delete-old-records']
        write_settings(settings)
    
    if settings["delete-old-records"]:
        files = glob.glob(f'{settings["path"]}\\*.json')
        for f in files:
            os.remove(f)
            
    if 'detect-coop' not in settings:
        settings['detect-coop'] = DEFAULT_SETTINGS['detect-coop']
        write_settings(settings)
        
    if 'break-offset' not in settings:
        settings['break-offset'] = DEFAULT_SETTINGS['break-offset']
        write_settings(settings)
    
    # init sheets
    setup()
        
    # init twitch
    twitchcmds.setup()

    print("Tracking...")
    print("Type 'help' for help, 'quit' when you are done")
    live = True

    try:
        while live:
            try:
                val = input("% ")
            except:
                val = ""
            args = val.split(' ')
            if (val == "help") or (val == "?"):
                print('help - print this help message')
                print("quit - quit")
                print("reset - resets twitch counters")
                print('update <counter> <value> - updates specified twitch counter. counter can be "blinds", "sub4", "sub330", "sub3", "ees", "completions", "blindtimes", "eestimes", "completiontimes". for lists (e.g. blindtimes), value should be a space-separated list of times')
                print('undo - deletes latest entry')
                print('eval <python code> - evaluates python code')
            elif (val == "stop") or (val == "quit"):
                print("Stopping...")
                live = False
            elif (val == "reset"):
                print("Resetting counters...")
                twitchcmds.reset()
                asyncio.run(twitchcmds.update_command())
                print("...done")
            elif args[0] == 'update':
                if twitchcmds.updatecounter(args[1], args[2:]):
                    asyncio.run(twitchcmds.update_command())
                    print("Counter set")
                else:
                    print("unknown counter", args[1])
            elif val == 'undo':
                with open(statsCsv, "r") as infile:
                    reader = list(csv.reader(infile))
                if len(reader) != 0:
                    print('Deleting latest entry from stats.csv', reader.pop(0))
                    with open(statsCsv, "w", newline="") as outfile:
                        writer = csv.writer(outfile)
                        for line in reader:
                            writer.writerow(line)
                else:
                    if settings['sheets']['enabled']:
                        print('Deleting latest entry from Google Sheets')
                        Sheets.dataSheet.delete_rows(2)
            elif args[0] == 'eval':
                try:
                    r = eval(' '.join(args[1:]))
                    if r is not None:
                        print(r)
                except Exception as e:
                    print(str(type(e))[8:-2] + ":", e)
            elif val == '':
                pass
            else:
                print("Invalid command. Type 'help' for help")
            time.sleep(0.05)
    finally:
        newRecordObserver.stop()
        twitchcmds.stop()
        newRecordObserver.join()
