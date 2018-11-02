import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import os
import argparse
import sys
import glob
import math
import gmplot
import time
# for parallel processing of sessions
import multiprocessing as mp 
import hashlib

from random import randint
from collections import defaultdict
from collections import OrderedDict

import datetime

from prettytable import PrettyTable

import mapping.utils
import analysis.metrics

# north, south, west, east limits of map, in terms of geo coordinates
LATN = 41.176796
LATS = 41.179283
LONE = -8.593912
LONW = -8.598336

# gps coords for a 'central' pin on FEUP, Porto, Portugal
LAT  = (41.176796 + 41.179283) / 2.0
LON = (-8.598336 + -8.593912) / 2.0

def get_lap_datetimes(gps_data):

    segments = gps_data.groupby(['lap-number'])['interval-tmstmp'].apply(np.array).reset_index(drop = False)
    timestamps = defaultdict(datetime.datetime)
    for i, segment in segments.iterrows():
        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in [ segment['interval-tmstmp'][0], segment['interval-tmstmp'][-1] ] ]
        timestamps[segment['lap-number']] = dates[0]

    return timestamps

def get_cell_datetimes(gps_data):

    segments = gps_data.groupby(['cell-x', 'cell-y', 'lap-number', 'direction'])['interval-tmstmp'].apply(np.array).reset_index(drop = False)
    timestamps = []
    for i, segment in segments.iterrows():
        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in [ segment['interval-tmstmp'][0], segment['interval-tmstmp'][-1] ] ]
        timestamps.append(dates[0])

    return sorted(timestamps)

def get_cell_num(gps_data, 
    cell_size,
    lat = [LATN, LATS],
    lon = [LONW, LONE]):
    
    # x-axis : longitude
    LAT = (LATN + LATS) / 2.0
    X_CELL_NUM = int(np.ceil((mapping.utils.gps_to_dist(LAT, LONW, LAT, LONE) / cell_size)))
    # y-axis : latitude
    Y_CELL_NUM = int(np.ceil((mapping.utils.gps_to_dist(LATN, 0.0, LATS, 0.0) / cell_size)))

    return X_CELL_NUM, Y_CELL_NUM

def add_lap_numbers(gps_data, lap_timestamps):

    # reset 'lap-number' and 'direction' columns
    gps_data['lap-number'] = -1.0
    gps_data['direction'] = -1.0

    i = 0
    while (i + 1) < len(lap_timestamps['start']):        
        # set lap nr.
        gps_data.loc[(gps_data['timestamp'] > float(lap_timestamps['start'][i])) & (gps_data['timestamp'] <= float(lap_timestamps['start'][i + 1])), 'lap-number'] = i + 1
        # set direction(s) :
        #    1 : East to West
        #   -1 : West to East
        gps_data.loc[(gps_data['timestamp'] > float(lap_timestamps['start'][i])) & (gps_data['timestamp'] <= float(lap_timestamps['turn'][i])), 'direction']  = 1
        gps_data.loc[(gps_data['timestamp'] > float(lap_timestamps['turn'][i])) & (gps_data['timestamp'] <= float(lap_timestamps['start'][i + 1])), 'direction']  = -1

        i += 1

def get_lap_timestamps(gps_data, clients):
    # find 'peaks' of distance of mobile to client @pos0
    # FIXME : this assumes laps always start next to pos2
    pos0 = clients[clients['name'] == 'pos0'].iloc[0]
    gps_pos = [ [row['lat'], row['lon'] ] for index, row in gps_data.iterrows() ]
    gps_data['dist'] = [ mapping.utils.gps_to_dist(pos0['lat'], pos0['lon'], gps[0], gps[1]) for gps in gps_pos ] 

    return analysis.metrics.find_peaks(gps_data, x_metric = 'timestamp', y_metric = 'dist')

def get_data(input_dir, trace_dir, tag_laps = True):

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']

    for filename in sorted(glob.glob(os.path.join(trace_dir, 'mobile/gps-log.*.csv'))):

        gps_data = pd.read_csv(filename)
        gps_data['timestamp'] = gps_data['timestamp'].astype(int)
        gps_data = gps_data.sort_values(by = ['timestamp']).reset_index(drop = True)
        # get lap timestamps
        lap_timestamps = get_lap_timestamps(gps_data, clients)
        # if lap numbers are to be tagged, add them to gps_data
        if tag_laps:
            # add lap numbers and direction
            add_lap_numbers(gps_data, lap_timestamps)

        # sort by unix timestamp
        gps_data = gps_data.sort_values(by = ['timestamp']).reset_index(drop = True)

    return gps_data, lap_timestamps
