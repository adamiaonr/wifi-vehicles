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

# for acessing the gps device
from gps import *
from gps3 import gps3
from socket import error as socket_error

gpsd = None # setting the global variable

attrs = ['time', 'lon', 'lat', 'alt', 'speed', 'epx', 'epy', 'epv', 'eps']

# taken from https://gist.githubusercontent.com/wolfg1969/4653340/raw/142eb5746619257b0cd4e317fd8f5fd63ddf2022/gpsdData.py
class GpsPoller(threading.Thread):
    
    def __init__(self):
        threading.Thread.__init__(self)
        global gpsd # bring it in scope
        gpsd = gps(mode = WATCH_ENABLE) # starting the stream of info
        self.current_value = None
        self.running = True # setting the thread running to true

    def run(self):
        global gpsd
        while gpsp.running:
            gpsd.next() # this will continue to loop and grab EACH set of gpsd info to clear the buffer

def reset_gpsd(dev_file = '/dev/ttyUSB0'):

    # sudo killall gpsd
    cmd = ["pkill", "-f", "gpsd"]
    proc = subprocess.call(cmd)

    # sudo gpsd /dev/ttyUSB0 -F -b /var/run/gpsd.sock
    cmd = ["gpsd", dev_file, "-F -b", "/var/run/gpsd.sock"]
    proc = subprocess.call(cmd)

def convert_to_unix(time_string):
    # 2017-11-01T16:46:52.000Z
    return int(time.mktime(datetime.datetime.strptime(time_string.split(".")[0], "%Y-%m-%dT%H:%M:%S").timetuple()))

def capture(iface, output_file, mode = 'ap'):
    # tcpdump -i <iface> -y IEEE802_11_RADIO -s0 -w <file>
    cmd = ''
    if mode == 'ap':
        cmd = ["tcpdump", "-i", iface, "-s0", "-w", output_file, "&"]
    elif mode == 'monitor':
        cmd = ["tcpdump", "-i", iface, "-y", "IEEE802_11_RADIO", "-s0", "-w", output_file, '&']

    proc = subprocess.call(cmd)

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
        "--monitor-iface", 
         help = """wifi iface in monitor mode. e.g.: '--monitor-iface wlx24050f9e2cb1'""")

    parser.add_argument(
        "--ap-iface", 
         help = """wifi iface in 'ap' (master) mode. e.g.: '--ap-iface wlx24050f7d57c1'""")

    parser.add_argument(
        "--restart-gpsd", 
         help = """restart gpsd daemon (use carefully)""",
         action = 'store_true')

    args = parser.parse_args()

    if not args.dev_file:
        args.dev_file = '/dev/ttyUSB0'

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # gps log file (0 buffering)
    file_timestamp = str(time.time()).split('.')[0]
    filename = os.path.join(args.output_dir, 'gps-log.' + file_timestamp + '.csv')
    #if os.path.exists(filename):
    #    gps_log = csv.writer(open(filename, 'a', 0))
    #else:
    gps_log = csv.writer(open(filename, 'wb+', 0))
    gps_log.writerow(attrs)

    # reset gpsd, just in case...
    if args.restart_gpsd:
        reset_gpsd(args.dev_file)

    # # this code uses the gps module (not gps3)
    # gpsp = GpsPoller() # create the thread
    
    # try:
    #     gpsp.start() # start it up
    
    #     while True:
    #         # it may take a second or two to get good data
    #         # print
    #         # print ' GPS reading'
    #         # print '----------------------------------------'
    #         # print 'latitude    ' , gpsd.fix.latitude
    #         # print 'longitude   ' , gpsd.fix.longitude
    #         # print 'time utc    ' , gpsd.utc,' + ', gpsd.fix.time
    #         # print 'altitude (m)' , gpsd.fix.altitude
    #         # print 'eps         ' , gpsd.fix.eps
    #         # print 'epx         ' , gpsd.fix.epx
    #         # print 'epv         ' , gpsd.fix.epv
    #         # print 'ept         ' , gpsd.fix.ept
    #         # print 'speed (m/s) ' , gpsd.fix.speed
    #         # print 'climb       ' , gpsd.fix.climb
    #         # print 'track       ' , gpsd.fix.track
    #         # print 'mode        ' , gpsd.fix.mode
    #         # print
    #         # print 'sats        ' , gpsd.satellites

    #         # attrs = ['time', 'lon', 'lat', 'alt', 'speed', 'epx', 'epy', 'epv', 'eps']
    #         if not (gpsd.utc).encode("utf-8"):
    #             continue

    #         gpsr = {
    #             'time' : convert_to_unix((gpsd.utc).encode("utf-8")),
    #             'lon' : gpsd.fix.longitude,
    #             'lat' : gpsd.fix.latitude,
    #             'alt' : gpsd.fix.altitude,
    #             'speed' : gpsd.fix.speed,
    #             'epx' : gpsd.fix.epx,
    #             'epy' : gpsd.fix.epy,
    #             'epv' : gpsd.fix.epv,
    #             'eps' : gpsd.fix.eps
    #         }

    #         if not gpsr['lon']:
    #             continue

    #         print(gpsr)
    #         time.sleep(1.0) # set to whatever

    # except (KeyboardInterrupt, SystemExit): # when you press ctrl+c
    #     print "\nkilling thread..."
    #     gpsp.running = False
    #     gpsp.join() # wait for the thread to finish what it's doing

    # start reading gps data
    gps_socket = gps3.GPSDSocket()
    data_stream = gps3.DataStream()

    # connect to gps device and start listening
    gps_socket.connect()
    gps_socket.watch()

    # start packet captures
    if args.ap_iface:
        capture_file = os.path.join(args.output_dir, ("ap." + args.ap_iface + "." + file_timestamp + ".pcap"))
        capture(args.ap_iface, capture_file, mode = 'ap')

    if args.monitor_iface:
        capture_file = os.path.join(args.output_dir, ("monitor." + args.monitor_iface + "." + file_timestamp + ".pcap"))
        capture(args.monitor_iface, capture_file, mode = 'monitor')

    try:
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

                print([data_stream.TPV[attr] for attr in attrs])
                data_stream.TPV['time'] = convert_to_unix(data_stream.TPV['time'])
                last_timestamp = data_stream.TPV['time']

                # write new row to .csv log
                gps_log.writerow([data_stream.TPV[attr] for attr in attrs])

            time.sleep(1.0)

    except (KeyboardInterrupt, SystemExit):
        cmd = ["pkill", "-f", "tcpdump"]
        proc = subprocess.call(cmd)
        sys.exit(0)
