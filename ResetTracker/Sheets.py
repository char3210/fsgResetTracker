import gspread
import json
import csv
import time
import threading
from Settings import settings, write_settings

def setup():
    global sh
    global gc

    if 'sheets' not in settings:
        settings['sheets'] = {}
    
    if "enabled" not in settings["sheets"]:
        yesno = input("Would you like to enable Google Sheets integration? (y/n) ")
        settings["sheets"]["enabled"] = yesno.lower() == "y"
        write_settings(settings)
    
    sheetsettings = settings["sheets"]
    
    if not sheetsettings["enabled"]:
        print("Skipping google sheets integration")
        return
    
    print("Enabling google sheets integration...")
    try:
        gc = gspread.service_account(filename="credentials.json")
    except FileNotFoundError as e:
        print(e)
        print(
            "Could not find credentials.json, make sure you have the file in the same directory as the exe, and named exactly 'credentials.json'. "
        )
        print('Cancelling google sheets integration')
        return


    while True:
        try:
            sh = gc.open_by_url(sheetsettings["spreadsheet-link"])
        except:
            creds_file = open("credentials.json", "r")
            creds = json.load(creds_file)
            creds_file.close()
            print("Don't forget to share the google sheet with",
                  creds["client_email"])
            sheetsettings["spreadsheet-link"] = input("Link to your Sheet: ")
            write_settings(settings)
            continue
        else:
            break

    t = threading.Thread(
        target=main, name="sheets"
    )  # < Note that I did not actually call the function, but instead sent it as a parameter
    t.daemon = True
    t.start()  # < This actually starts the thread execution in the background
    
def main():
    try:

        # Setting up constants and verifying
        global dataSheet
        dataSheet = sh.worksheet("Raw Data")
        color = (15.0, 15.0, 15.0)
        global pushedLines
        pushedLines = 1
        statsCsv = "stats.csv"

        def push_data():
            global pushedLines
            with open(statsCsv, newline="") as f:
                reader = csv.reader(f)
                data = list(reader)
                f.close()

            try:
                if len(data) == 0:
                    return
                # print(data)
                dataSheet.insert_rows(
                    data,
                    row=2,
                    value_input_option="USER_ENTERED",
                )
                if pushedLines == 1:
                    endColumn = ord("A") + len(data)
                    endColumn1 = ord("A") + (endColumn // ord("A")) - 1
                    endColumn2 = ord("A") + ((endColumn - ord("A")) % 26)
                    endColumn = chr(endColumn1) + chr(endColumn2)
                    # print("A2:" + endColumn + str(1 + len(data)))
                    dataSheet.format(
                        "A2:" + endColumn + str(1 + len(data)),
                        {
                            "backgroundColor": {
                                "red": color[0],
                                "green": color[1],
                                "blue": color[2],
                            }
                        },
                    )

                pushedLines += len(data)
                f = open(statsCsv, "w+")
                f.close()
            except Exception as e:
                print(e)
        live = True
        while live:
            push_data()
            time.sleep(30)
    except Exception as e:
        print("Error in Sheets thread", e)
        input("")
