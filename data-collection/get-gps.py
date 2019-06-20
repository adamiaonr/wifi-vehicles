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
import threading
import time

from gps import *

# attributes read from gps device
attrs = ['time', 'lon', 'lat', 'alt', 'speed', 'epx', 'epy', 'epv', 'eps']

class GpsPoller(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)
        self.session = gps(mode=WATCH_ENABLE)
        self.current_value = None

    def get_current_value(self):
        return self.current_value

    def run(self):
        try:
            while True:
                self.current_value = self.session.next()

        except StopIteration:
            pass

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
    if isinstance(time_string, int):
        print("warning : unexpected time type")
        return time_string
    else:
        return int(time.mktime(datetime.datetime.strptime(time_string.split(".")[0], "%Y-%m-%dT%H:%M:%S").timetuple()))

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output-dir", 
         help = """dir on which to save .csv files""")

    parser.add_argument(
        "--restart-gpsd", 
         help = """restart gpsd daemon""",
         action = 'store_true')

    args = parser.parse_args()

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # gps log file (0 buffering)
    file_timestamp = str(time.time()).split('.')[0]
    filename = os.path.join(args.output_dir, 'gps-log.' + file_timestamp + '.csv')

    gps_log = csv.writer(open(filename, 'wb+', 0))
    gps_log.writerow(['timestamp'] + attrs)

    # restart gpsd
    if args.restart_gpsd:
        restart_gpsd(args.dev_file)

    gpsp = GpsPoller()
    gpsp.start()

    while 1:
        time.sleep(1)
        gps_out = gpsp.get_current_value()

        timestamp = str(time.time())
        keys = [str(x) for x in gps_out.keys()]

        if not all(e in keys for e in ['time', 'lat', 'lon']):
            print("error : not enough keys. continuing.")
            continue

        for e in ['alt', 'speed', 'epx', 'epy', 'epv', 'eps']:
            if e not in keys:
                gps_out[e] = -1.0

        # convert time to unix timestamp format
        gps_out['time'] = convert_to_unix(gps_out['time'])
        # write new row to .csv log
        line = [timestamp] + [gps_out[attr] for attr in attrs]
        gps_log.writerow(line)
        print(line)
