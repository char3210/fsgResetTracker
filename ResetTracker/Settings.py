import json
import datetime
import os

settings = {}

DEFAULT_SETTINGS = {
    "path": "PATH",
    "sheets": {
        "spreadsheet-link": "LINK"
    },
    "delete-old-records": True,
    "break-offset": 20,
    "twitch": {
        "format": "!editcom {command} Blinds: {blinds} {blindtimes} | End Enters: {ees} {eetimes} | Completions: {completions} {completiontimes}"
    },
    "detect-coop": True
}

def write_settings(settings):
    settings_file = open("settings.json", "w")
    json.dump(settings, settings_file, indent=2)
    settings_file.close()

def read_settings():
    try:
        settings_file = open("settings.json")
        settings = json.load(settings_file)
        settings_file.close()
    except FileNotFoundError:
        print(
            "Could not find settings.json, writing default settings..."
        )
        settings = json.loads(json.dumps(DEFAULT_SETTINGS))
        write_settings(DEFAULT_SETTINGS)
    except json.decoder.JSONDecodeError as e:
        print("Error when reading settings.json:", e)
        print(
            "Creating backup and writing default settings..."
        )
        settings_file.close()
        backup_name = "settings_backup_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".json"
        os.rename("settings.json", backup_name)
        settings = json.loads(json.dumps(DEFAULT_SETTINGS))
        write_settings(DEFAULT_SETTINGS)
    return settings
