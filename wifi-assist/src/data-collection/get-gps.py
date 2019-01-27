import csv
import json
import argparse
import os
import sys
import time
import datetime
import subprocess
import errno
import threading
import signal

# for acessing the gps device
from gps import *
from gps3 import gps3
from socket import error as socket_error

# attributes read from gps device
attrs = ['time', 'lon', 'lat', 'alt', 'speed', 'epx', 'epy', 'epv', 'eps']

def signal_handler(signal, frame):
    global stop_loop
    stop_loop = True

# this required a bit of tweaking to work:
#   - altered /etc/default/gpsd to not start gpsd on boot
#   - altered /lib/systemd/system/gpsd.service to not require gpsd.socket options
#   - when reseting gpsd, we stop and disable gpsd and gpsd.socket first
def restart_gpsd(dev_file = '/dev/ttyUSB0'):
    # simply run the start-gps script
    cmd = ["start-gps", dev_file]
    proc = subprocess.call(cmd)

def convert_to_unix(time_string):
    # 2017-11-01T16:46:52.000Z
    return int(time.mktime(datetime.datetime.strptime(time_string.split(".")[0], "%Y-%m-%dT%H:%M:%S").timetuple()))

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--dev-file", 
         help = """gps device file. default is '/dev/ttyUSB0'""")

    parser.add_argument(
        "--output-dir", 
         help = """dir on which to save .csv files""")

    parser.add_argument(
        "--restart-gpsd", 
         help = """restart gpsd daemon""",
         action = 'store_true')

    args = parser.parse_args()

    if not args.dev_file:
        args.dev_file = '/dev/ttyUSB0'

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # register CTRL+C catcher
    signal.signal(signal.SIGINT, signal_handler)

    # gps log file (0 buffering)
    file_timestamp = str(time.time()).split('.')[0]
    filename = os.path.join(args.output_dir, 'gps-log.' + file_timestamp + '.csv')

    gps_log = csv.writer(open(filename, 'wb+', 0))
    gps_log.writerow(['timestamp'] + attrs)

    # restart gpsd
    if args.restart_gpsd:
        restart_gpsd(args.dev_file)

    # start reading gps data
    gps_socket = gps3.GPSDSocket()
    data_stream = gps3.DataStream()

    # connect to gps device and start listening
    gps_socket.connect()
    gps_socket.watch()

    stop_loop = False
    last_timestamp = 0
    for new_data in gps_socket:

        if new_data:

            # extract data from gps reading 
            data_stream.unpack(new_data)

            # check if data is meaningful
            if data_stream.TPV['lon'] == 'n/a':
                continue

            # convert time to unix timestamp format
            if data_stream.TPV['time'] == last_timestamp:
                continue

            data_stream.TPV['time'] = convert_to_unix(data_stream.TPV['time'])
            last_timestamp = data_stream.TPV['time']

            # write new row to .csv log
            line = [str(time.time())] + [data_stream.TPV[attr] for attr in attrs]
            gps_log.writerow(line)
            print(line)

        time.sleep(1.0)

        # keep collecting data till a CTRL+C is caught...
        if stop_loop:
            break

    sys.exit(0)
