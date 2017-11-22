import os
import argparse
import sys
import glob
import math
import time

# to access gps device
from gps3 import gps3

# gps coords for a 'central' pin on porto, portugal
PORTO_LATITUDE  = 41.163158
PORTO_LONGITUDE = -8.6127137
# north, south, west, east limits of porto map, in terms of geo coordinates
PORTO_LATITUDE_LIMIT_NORTH = PORTO_LATITUDE  + 0.03
PORTO_LATITUDE_LIMIT_SOUTH = PORTO_LATITUDE  - 0.03
PORTO_LONGITUDE_LIMIT_EAST = PORTO_LONGITUDE + 0.06
PORTO_LONGITUDE_LIMIT_WEST = PORTO_LONGITUDE - 0.06
# x and y span (in meters) of the map, derived from geo coordinate limits
# NOTE : y is the vertical axis (latitude), x is the horizontal axis (longitude)
Y_SPAN = gps_to_dist(PORTO_LATITUDE_LIMIT_NORTH, 0.0, PORTO_LATITUDE_LIMIT_SOUTH, 0.0)
# FIXME : an x span depends on the latitude, and we're assuming a fixed latitude
X_SPAN = gps_to_dist(PORTO_LONGITUDE_LIMIT_WEST, PORTO_LATITUDE, PORTO_LONGITUDE_LIMIT_EAST, PORTO_LATITUDE)

# attributes reported by gps sensor
gps_stream_attrs = ['time', 'lon', 'lat', 'alt', 'speed', 'epx', 'epy', 'epv', 'eps']

# get (x,y) coords of cell w/ side cell_size
def calc_cell(lat, lon, cell_size = 10.0):
    # calc y (latitude) and x (longitude) coords of cell
    y = ((lat - PORTO_LATITUDE_LIMIT_SOUTH) / (PORTO_LATITUDE_LIMIT_NORTH - PORTO_LATITUDE_LIMIT_SOUTH)) * (Y_SPAN / cell_size)
    x = ((lon - PORTO_LONGITUDE_LIMIT_WEST) / (PORTO_LONGITUDE_LIMIT_EAST - PORTO_LONGITUDE_LIMIT_WEST)) * (X_SPAN / cell_size)
    return int(x), int(y)

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

    # connect to gps device and start listening to 
    # gps data
    # sudo killall gpsd; sudo gpsd /dev/ttyUSB0 -F -b /var/run/gpsd.sock
    gps_socket = gps3.GPSDSocket()
    gps_socket.connect()
    gps_socket.watch()

    # start reading gps data into a gps3 datastream
    gps_stream = gps3.DataStream()
    for new_data in gps_socket:
        if new_data:
            # extract data from gps reading 
            gps_stream.unpack(new_data)
            # check if data is meaningful
            if (gps_stream.TPV['lon'] == 'n/a') and (gps_stream.TPV['lat'] == 'n/a'):
                continue

            # get cell id
            cell = calc_cell(gps_stream.TPV['lat'], gps_stream.TPV['lon'])
            # connect to aps in the cell
            conn_manager.manage_connections(cell)

            time.sleep(0.5)