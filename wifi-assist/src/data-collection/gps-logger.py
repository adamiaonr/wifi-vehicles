import csv
import json
import argparse
import os
import time
import datetime
import subprocess as sp

# for acessing the gps device
from gps3 import gps3

attrs = ['time', 'lon', 'lat', 'alt', 'speed', 'epx', 'epy', 'epv', 'eps']

def convert_to_unix(time_string):
    # 2017-11-01T16:46:52.000Z
    return int(time.mktime(datetime.datetime.strptime(time_string.split(".")[0], "%Y-%m-%dT%H:%M:%S").timetuple()))

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
        args.output_dir = '/home/pi/workbench/wifi-assist/data/logs'

    # gps log file (0 buffering)
    filename = os.path.join(args.output_dir, 'gps-log.csv')
    #if os.path.exists(filename):
    #    gps_log = csv.writer(open(filename, 'a', 0))
    #else:
    gps_log = csv.writer(open(filename, 'wb+', 0))
    gps_log.writerow(attrs)

    # start reading gps data
    gps_socket = gps3.GPSDSocket()
    data_stream = gps3.DataStream()
    # connect to gps device and start listening
    gps_socket.connect()
    gps_socket.watch()

    last_timestamp = 0
    for new_data in gps_socket:

        if new_data:

            print([data_stream.TPV[attr] for attr in attrs])

            # extract data from gps reading 
            data_stream.unpack(new_data)
            # check if data is meaningful
            if data_stream.TPV['speed'] == 'n/a':
                continue

            # convert time to unix timestamp format
            if data_stream.TPV['time'] == last_timestamp:
                continue

            data_stream.TPV['time'] = convert_to_unix(data_stream.TPV['time'])
            last_timestamp = data_stream.TPV['time']

            # write new row to .csv log
            gps_log.writerow([data_stream.TPV[attr] for attr in attrs])

        time.sleep(1.0)
