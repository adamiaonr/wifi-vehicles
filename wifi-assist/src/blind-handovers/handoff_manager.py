import os
import argparse
import sys
import glob
import math
import time

import zmq
import thread
import json

# to access gps device
from gps3 import gps3

import coverage_map

# attributes reported by gps sensor
gps_stream_attrs = ['time', 'lon', 'lat', 'alt', 'speed', 'epx', 'epy', 'epv', 'eps']

def listen():

    # the handoff_manager listens on port 55555 for cmds
    # from the SESAME controller
    # (zmq.REP is for the server side of a REQ-REP socket pair)
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind('tcp://*:55555')
    
    while True:
    
        # block till next message is received
        req = socket.recv()
        # convert req (encoded in json format) to dict
        req = json.loads(req)

        if 'to_update' in req:

            # do something...

        else:
            print("handoff_manager::listen() [ERROR] unknown key : %s" % (req[0]))

if __name__ == "__main__":

    # use an ArgumentParser for a nice cli
    parser = argparse.ArgumentParser()
    # options (self-explanatory)
    parser.add_argument(
        "--output-dir", 
         help = """dir on which to print graphs""")

    args = parser.parse_args()

    # quit if a dir w/ .tsv files hasn't been provided
    if not args.output_dir:
        args.output_dir = '../data'

    # initialize coverage map
    cmap = coverage_map.CoverageMap()

    # launch thread to listen to updates from SESAME server
    try:
        thread.start_new_thread(listen, (cmap,))
    except:
        print("handoff_manager::init() [ERROR] error while starting thread...")

    # connect to gps device and start listening to gps data
    # sudo killall gpsd; sudo gpsd /dev/ttyUSB0 -F -b /var/run/gpsd.sock
    gps_socket = gps3.GPSDSocket()
    gps_socket.connect()
    gps_socket.watch()

    # start reading gps data into a gps3 datastream
    gps_stream = gps3.DataStream()
    for new_data in gps_socket:
        if new_data:
            
            # abort if coverage map is not available yet
            if cmap.empty():
                continue

            # extract data from gps reading 
            gps_stream.unpack(new_data)
            # check if data is meaningful
            if (gps_stream.TPV['lon'] == 'n/a') and (gps_stream.TPV['lat'] == 'n/a'):
                continue

            # get cell which contails the current gps coords
            cell = cmap.get_cell((gps_stream.TPV['lat'], gps_stream.TPV['lon']))
            # connect to aps in cell
            
            time.sleep(0.5)