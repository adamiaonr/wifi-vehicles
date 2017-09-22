import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.pylab as pl
import os
import argparse
import sys
import glob
import math
import gmplot
import time

# for parallel processing of sessions
import multiprocessing as mp 

# for maps
import pdfkit

from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict

# for ap location estimation
from shapely.geometry import Point

from random import randint

# custom imports
from plot_utils import *

matplotlib.rcParams.update({'font.size': 16})

# gps coords for a 'central' pin on porto, portugal
PORTO_LATITUDE  = 41.163158
PORTO_LONGITUDE = -8.6127137

# limits for map plotting
PORTO_LATITUDE_LIMIT_NORTH = PORTO_LATITUDE  + 0.03
PORTO_LATITUDE_LIMIT_SOUTH = PORTO_LATITUDE  - 0.03
PORTO_LONGITUDE_LIMIT_EAST = PORTO_LONGITUDE + 0.06
PORTO_LONGITUDE_LIMIT_WEST = PORTO_LONGITUDE - 0.06

GRID_SIZE = 50.0

# in order to save time, we save the post-processed data used in plots 
# on .csv files 
OUTPUT_DIR = '/home/adamiaonr/workbench/wifi-authentication/data-analysis/graphs'

WIFI_AUTH = {0: 'unknown', 1: 'open', 2: 'wep', 3: 'wpa', 4: 'wpa2', 5: 'wpa2-enter'}

file_lock = mp.Lock()

# info about the sense-my-city dataset
#   ds : distance travelled by the user during the scanning period
#   acc_scan : mean accuracy from the GPS during the scanning period
#   new_err : mean error related to the map matching process (was conducted by others)
#   new_lat | new_lot : location where the scan was associated
#   g_lat | g_lon : cell location
#   auth : authentication mode (0 - Unknown, 1 - Open, 2 - WEP, 3 - WPA, 4 - WPA2, 5 - Enterprise (RADIUS/.11x/Other).)
#   session_id : identifies the trip

def to_radians(degrees):
    return (degrees * math.pi / 180.0)

def to_degrees(radians):
    return (radians / (math.pi / 180.0))

def gps_to_dist(lat_start, lon_start, lat_end, lon_end):

    # we use the haversine formula to calculate the great-circle distance between two points. 
    # in other words, this calculates the lenght of the shortest arch in-between 2 points, in 
    # a 'great' circle of radius equal to 6371 (the radius of the earth) 
    # source : http://www.movable-type.co.uk/scripts/latlong.html

    # earth radius, in m
    earth_radius = 6371000

    delta_lat = to_radians(lat_end - lat_start)
    delta_lon = to_radians(lon_end - lon_start)

    lat_start = to_radians(lat_start)
    lat_end = to_radians(lat_end)

    a = (np.sin(delta_lat / 2.0) * np.sin(delta_lat / 2.0)) + (np.sin(delta_lon / 2.0) * np.sin(delta_lon / 2.0)) * np.cos(lat_start) * np.cos(lat_end)
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))

    return earth_radius * c

def central_angle(dist):

    # earth radius, in m
    earth_radius = 6371000

    return to_degrees(dist / earth_radius)

def extract_median_speeds(data, session_id):

    median_speeds = defaultdict()

    # get start and end latitudes and longitudes of the scans
    #   - we measure the distance in-between data points. 
    #   - we use the .shift(-1) method to align the start and end columns, and feed them directly to 
    #     the gps_to_dist() method
    lat_start   = np.array(data['new_lat'])
    lon_start   = np.array(data['new_lon'])
    lat_end     = np.array(data['new_lat'].shift(-1))
    lon_end     = np.array(data['new_lon'].shift(-1))

    # get start and end timestamps (using the .shift(-1) method as above)
    time_start = np.array(data['seconds'])
    time_end = np.array(data['seconds'].shift(-1))

    # calculate and extract (valid) median speeds for the session
    speeds = gps_to_dist(lat_start[:-1], lon_start[:-1], lat_end[:-1], lon_end[:-1]) / (time_end[:-1] - time_start[:-1])
    # print("session_analysis::extract_median_speeds() : speeds[%s] = %s" % (session_id, str([s for s in np.sort(speeds) if not math.isnan(s)])))
    median_speed = float(np.nanpercentile(speeds, 50))

    if (median_speed > 0.0) and (not math.isnan(median_speed)) and (median_speed < 41.0):
        # print("median = %f, 50 = %f, 25 = %f" % (median_speed, float(np.nanpercentile(speeds, 50)), float(np.nanpercentile(speeds, 25))))
        median_speeds[session_id] = median_speed
    else:
        median_speeds[session_id] = -1.0

    return median_speeds

def print_grid(ap_grid, grid_side = 10.0):

    # the map object centered in porto, portugal
    gmap = gmplot.GoogleMapPlotter(PORTO_LATITUDE, PORTO_LONGITUDE, 14.50)

    # get latitude and longitude grid limits
    lat_ticks = np.arange(PORTO_LATITUDE_LIMIT_SOUTH, PORTO_LATITUDE_LIMIT_NORTH, 
        (PORTO_LATITUDE_LIMIT_NORTH - PORTO_LATITUDE_LIMIT_SOUTH) / (gps_to_dist(PORTO_LATITUDE_LIMIT_NORTH, 0.0, PORTO_LATITUDE_LIMIT_SOUTH, 0.0) / grid_side))
    lon_ticks = np.arange(PORTO_LONGITUDE_LIMIT_WEST, PORTO_LONGITUDE_LIMIT_EAST, 
        (PORTO_LONGITUDE_LIMIT_EAST - PORTO_LONGITUDE_LIMIT_WEST) / (gps_to_dist(PORTO_LONGITUDE_LIMIT_WEST, PORTO_LATITUDE, PORTO_LONGITUDE_LIMIT_EAST, PORTO_LATITUDE) / grid_side))    

    color_map = plt.get_cmap('Reds')
    colors = [color_map(i) for i in np.linspace(0, 1, 6)]

    # show the hex codes
    for i, color in enumerate(colors):
        print("color[%d] : %s" % (i, matplotlib.colors.rgb2hex(color[:3]).lstrip('#')))

    for i in xrange(len(lat_ticks) - 1):
        for j in xrange(len(lon_ticks) - 1):

            # get nr. of aps in grid cell
            nr_aps = float(len(ap_grid['counts'][i][j]))
            # if no aps have been found, continue
            if nr_aps == 0:
                continue

            # else, find if in these intervals:
            #   0-5, 5-10, 10-15, 15-20, 20-25, 25+
            color = None

            nr_aps = min(int(nr_aps / 5.0), 5)
            rgb = colors[nr_aps][:3]
            color = matplotlib.colors.rgb2hex(rgb)

            gmap.polygon(
                (lat_ticks[i], lat_ticks[i + 1], lat_ticks[i + 1], lat_ticks[i]), 
                (lon_ticks[j], lon_ticks[j], lon_ticks[j + 1], lon_ticks[j + 1]),
                edge_color = "black", edge_width = 0.5, face_color = color, face_alpha = 0.25)

    gmap.draw('example.html')

def init_grid(ap_grid, grid_side = 10.0):

    lat_ticks = np.arange(PORTO_LATITUDE_LIMIT_SOUTH, PORTO_LATITUDE_LIMIT_NORTH, 
        (PORTO_LATITUDE_LIMIT_NORTH - PORTO_LATITUDE_LIMIT_SOUTH) / (gps_to_dist(PORTO_LATITUDE_LIMIT_NORTH, 0.0, PORTO_LATITUDE_LIMIT_SOUTH, 0.0) / grid_side))
    lon_ticks = np.arange(PORTO_LONGITUDE_LIMIT_WEST, PORTO_LONGITUDE_LIMIT_EAST, 
        (PORTO_LONGITUDE_LIMIT_EAST - PORTO_LONGITUDE_LIMIT_WEST) / (gps_to_dist(PORTO_LONGITUDE_LIMIT_WEST, PORTO_LATITUDE, PORTO_LONGITUDE_LIMIT_EAST, PORTO_LATITUDE) / grid_side))

    ap_grid['lat-slots'] = len(lat_ticks)
    ap_grid['lon-slots'] = len(lon_ticks)

    ap_grid['counts'] = defaultdict()
    for i in xrange(len(lat_ticks) - 1):
        ap_grid['counts'][i] = defaultdict(set)

def calc_grid(latitude, longitude):

    x = (latitude - PORTO_LATITUDE_LIMIT_SOUTH) / (PORTO_LATITUDE_LIMIT_NORTH - PORTO_LATITUDE_LIMIT_SOUTH)
    y = (longitude - PORTO_LONGITUDE_LIMIT_WEST) / (PORTO_LONGITUDE_LIMIT_EAST - PORTO_LONGITUDE_LIMIT_WEST)

    return x,y

def extract_grid_counts(session_data, ap_grid, ap_stats, grid_side = 10.0):

    for index, row in session_data.iterrows():

        ap_mac = row['encode']

        if ap_mac not in ap_stats:
            
            ap_stats[ap_mac] = defaultdict()
            ap_stats[ap_mac]['essid'] = row['essid']
            ap_stats[ap_mac]['auth']  = WIFI_AUTH[int(row['auth'])]

        x, y = calc_grid(row['new_lat'], row['new_lon'])

        if x >= 1.0 or y >= 1.0:
            continue

        x = int(x * ap_grid['lat-slots'])
        y = int(y * ap_grid['lon-slots'])
        ap_grid['counts'][x][y].add(ap_mac)

        # print("session_analysis::extract_grid_counts() : grid [%d,%d] w/ %d macs" % (x, y, len(ap_grid['counts'][x][y])))

    return len(session_data['ds'].unique())

def analyze_sessions(file_name, out_dir, median_speed_thrshld = 5.5):

    session_ids = set()

    nr_scans = 0
    ap_grid = defaultdict()
    ap_stats = defaultdict()
    init_grid(ap_grid, grid_side = GRID_SIZE)

    # given the large size of the input data file (> 3 GB), we read the file in chunks
    chunksize = 10 ** 5
    prev_chunk = None

    for chunk in pd.read_csv(file_name, chunksize = chunksize):

        # find unique session ids on this chunk
        chunk_session_ids = chunk['session_id'].unique()

        # find if any of the session ids overlaps, update the median scanning dist value 
        # if that's the case
        intersection = list(session_ids & set(chunk_session_ids))

        if len(intersection) > 0:
            print("session_analysis::analyze_sessions() : found %d intersections : %s" % (len(intersection), str(intersection)))

        print("session_analysis::analyze_sessions() : %d sessions found in chunk" % (len(chunk_session_ids)))

        # for each session:
        #   - add nr. of visible aps to a grid of a x b meters
        #   - nr. of scans
        #   - nr. of diff. visible aps
        #   - nr. of diff. ssids
        #   - size of wifi networks (# of macs per ssid)
        #   - visible auth. types
        for session_id in chunk_session_ids:

            # print("session_analysis::analyze_sessions() : analyzing session_id %s" % (session_id))

            # to make it easier, extract session data first
            session_data = chunk.loc[chunk['session_id'] == session_id]
            # extract median speeds for the session
            median_speeds = extract_median_speeds(session_data, session_id)

            # if the median speed is less than threshold, skip it
            if (median_speeds[session_id] < median_speed_thrshld):
                # print("session_analysis::analyze_sessions() : median-speed[%s] = %f < %f. skipping it." 
                #     % (session_id, median_speeds[session_id], median_speed_thrshld))
                continue

            # add session id to list of processed sessions
            session_ids.add(session_id)

            # collect required statistics
            # 1) collect grid counts
            nr_scans += extract_grid_counts(session_data, ap_grid, ap_stats, grid_side = GRID_SIZE)

        if len(session_ids) > 10:
            break

        # keep track of pervious chunk to keep track of overlapping 
        # sessions in-between chunks
        prev_chunk = chunk

    # print statistics
    print("nr. scans : %d" % (nr_scans))
    print("nr. aps : %d" % (len(ap_stats)))
    # convert dict to pandas dataframe
    ap_stats = pd.DataFrame.from_dict(ap_stats, orient = 'index')
    # nr. essids
    essids = ap_stats['essid'].unique()
    print("nr. essids : %d" % (len(essids)))
    # nr. macs per ssid (intervals of 5):
    #   0 : [0-4], 1 : [5-9], 2 : [10-14], ..., 45-50, 50+
    essid_sizes = defaultdict(int)
    essid_large = defaultdict(int)
    print("nr. macs per essid :")
    for essid in essids:
        # extract nr. of macs w/ essid x
        nr_macs = len(ap_stats.loc[ap_stats['essid'] == essid])
        # add it to the correct bucket
        essid_sizes[min(int(nr_macs / 5.0), 10.0)] += 1

        if min(int(nr_macs / 5.0), 10.0) == 10.0:
            essid_large[essid] = nr_macs

    total = 0
    for size in essid_sizes:
        print("\t[%d-%d] : %d" % ((size * 5), ((size + 1) * 5) - 1, essid_sizes[size]))
        total += essid_sizes[size]
    print("\n\t[total] : %d\n" % (total))

    for essid in essid_large:
        print("\t[%s] : %d" % (essid, essid_large[essid]))

    print("\nnr. auths :")
    total = 0
    for key, auth in WIFI_AUTH.iteritems():
        nr_aps = len(ap_stats.loc[ap_stats['auth'] == auth])
        print("\t[%s] : %d" % (auth, nr_aps))
        total += nr_aps
    print("\n\t[total] : %d" % (total))


    print_grid(ap_grid, grid_side = GRID_SIZE)

def plot(file_name, out_dir):

    """extracts bunch of stats from 'sense my city' sessions"""

    analyze_sessions(file_name, out_dir)
