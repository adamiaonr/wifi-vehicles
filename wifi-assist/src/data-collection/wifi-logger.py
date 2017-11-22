import iwlist
import csv
import json
import argparse
import os
import time
import datetime

attrs = ['time', 'essid', 'mac', 'signal_level_dBm', 'signal_quality', 'channel']

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--output-dir", 
         help = """dir on which to print graphs""")

    args = parser.parse_args()

    # quit if a dir w/ .tsv files hasn't been provided
    if not args.output_dir:
        args.output_dir = '../data'

    # gps log file (0 buffering)
    filename = os.path.join(args.output_dir, 'wifi-log.csv')
    if os.path.exists(filename):
        wifi_log = csv.writer(open(filename, 'a', 0))
    else:
        wifi_log = csv.writer(open(filename, 'wb+', 0))
        wifi_log.writerow(attrs)

    while True:

        curr_timestamp = time.time()

        content = iwlist.scan(interface = 'wlan0')
        # content = ""
        # with open ("scan.txt", "r") as myfile:
        #     content = myfile.read()

        cells = iwlist.parse(content)
        
        for cell in cells:

            # update the 'time' attr, accounting w/ the last_beacon component
            cell['time'] = int(curr_timestamp - float(cell['last_beacon']) / 1000.0)
            # write new row to .csv log
            wifi_log.writerow([cell[attr] for attr in attrs])
