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

# for maps
import pdfkit

from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict

# geodesic distance
from geopy.distance import geodesic

# for ap location estimation
from shapely.geometry import Point

# custom imports
import analysis.metrics
import analysis.trace
import analysis.gps
import analysis.ap_selection.rssi
import analysis.ap_selection.gps

import parsing.utils

import mapping.utils

# gps coords for a 'central' pin on porto, portugal
LAT  = 41.163158
LON = -8.6127137
# north, south, west, east limits of map, in terms of geo coordinates
LATN = LAT + 0.03
LATS = LAT - 0.03
LONE = LON + 0.06
LONW = LON - 0.06

def add_cells(chunk, cell_size):

    # extract nr. of cells in the designated area
    xx, yy = analysis.gps.get_cell_num(cell_size = cell_size, lat = [LATN, LATS], lon = [LONW, LONE])

    # add cell ids to chunk, based on [new_lat, new_lon]
    chunk['cell-x'] = chunk['new_lon'].apply(lambda x : int((x - LONW) / (LONE - LONW) * xx))
    chunk['cell-y'] = chunk['new_lat'].apply(lambda y : int((y - LATS) / (LATN - LATS) * yy))

def add_band(chunk):
    # add 'band' column for '2.4' and '5.0'
    chunk['band'] = -1
    chunk.loc[(chunk['frequency'].astype(int) >= 2412) & (chunk['frequency'].astype(int) <= 2484), 'band'] = 0
    chunk.loc[(chunk['frequency'].astype(int) >= 5160) & (chunk['frequency'].astype(int) <= 5825), 'band'] = 1
    chunk['band'] = chunk['band'].astype(int)

# def calc_speed(chunk):
#     # remove multiple readings for the same timestamp
#     sessions = chunk.drop_duplicates(subset = ['session_id', 'seconds'])
#     # distance & time between readings
#     sessions['dist'] = mapping.utils.gps_to_dist(sessions['new_lat'], sessions['new_lon'], sessions['new_lat'].shift(1), sessions['new_lon'].shift(1))
#     sessions['time'] = sessions['seconds'] - sessions['seconds'].shift(1)
#     # speed
#     sessions['speed'] = (sessions['dist'] / sessions['time']).astype(float).fillna(0.0)

#     return sessions.groupby(['session_id']).agg({'speed' : ['median', 'mean', 'count'], 'dist' : 'sum'}).reset_index(drop = False)

def calc_dist(data):
    data['dist'] = mapping.utils.gps_to_dist(data['new_lat'], data['new_lon'], data['new_lat'].shift(1), data['new_lon'].shift(1))
    return data

def mark_size(data):
    data['block-size'] = len(data.drop_duplicates(subset = ['seconds']))
    return data

def extract_bands(data, database):

    # if no data points in one of the bands, abort
    if data[data['band'] == 1].empty:
        return

    # find cells w/ 5.0 GHz data points
    data['cell'] = data['cell-x'].astype(str) + '.' + data['cell-y'].astype(str)
    cells = data[data['band'] == 1]['cell']

    # # FIXME: a cell size of 5.0 m will result in 2010 x 1335 ~ 3M cells
    # bands = data.groupby(['session_id', 'encode', 'cell-x', 'cell-y', 'band']).agg({'snr' : 'median', 'seconds' : 'count'}).reset_index(drop = False)
    # bands.rename(index = str, columns = {'seconds' : 'count'}, inplace = True)
    # bands['snr'] = bands['snr'].apply(analysis.metrics.custom_round)
    # bands['session_id'] = bands['session_id'].astype(int)
    # bands = bands[['session_id', 'encode', 'cell-x', 'cell-y', 'band', 'snr', 'count']].reset_index(drop = True)

    # print(bands)
    # parsing.utils.to_hdf5(bands, ('/bands/snr'), database)

    # FIXME: cells w/ 5.0 GHz data are so rare, that we can simply save the full rows
    raw = data[data['cell'].isin(cells)].reset_index(drop = True)[['seconds', 'session_id', 'encode', 'snr', 'auth', 'frequency', 'new_lat', 'new_lon', 'new_err', 'ds', 'acc_scan', 'band', 'cell-x', 'cell-y']]
    raw['session_id'] = raw['session_id'].astype(str).apply(lambda x : x.split(',')[0]).astype(int)
    raw['encode'] = raw['encode'].astype(str)
    print(raw)
    parsing.utils.to_hdf5(raw, ('/bands/raw'), database)
    
def extract_coverage(data, processed_data):

    # distances while under coverage, per block
    distances = data.groupby(['session_id', 'encode', 'band', 'time-block']).apply(calc_dist).reset_index(drop = True).fillna(0.0)
    distances = distances.groupby(['session_id', 'encode', 'band', 'time-block'])['dist'].sum().reset_index(drop = False).sort_values(by = ['session_id', 'encode', 'band', 'time-block'])

    # times, distance & speed while under coverage, per block
    aps = data.groupby(['session_id', 'encode', 'band', 'time-block'])['seconds'].apply(np.array).reset_index(drop = False).sort_values(by = ['session_id', 'encode', 'band', 'time-block'])
    aps['time'] = aps['seconds'].apply(lambda x : x[-1] - x[0])
    aps['dist'] = distances['dist']
    aps['speed'] = (aps['dist'] / aps['time'].astype(float)).fillna(0.0)
    aps['speed'] = aps['speed'].apply(analysis.metrics.custom_round)

    # - filter out low speeds (e.g., < 1.0 m/s)
    aps = aps[aps['speed'] > 1.0].reset_index(drop = True)

    if aps.empty:
        return

    for cat in ['time', 'speed']:
        processed_data[cat] = pd.concat([processed_data[cat], aps.groupby(['band', cat]).size().reset_index(drop = False, name = 'count')], ignore_index = True)
        processed_data[cat] = processed_data[cat].groupby(['band', cat]).sum().reset_index(drop = False)

def extract(input_dir, cell_size = 5.0):

    output_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    # processed data 
    processed_data = defaultdict(pd.DataFrame)

    # load .hdfs database
    database = pd.HDFStore(os.path.join(output_dir, "smc.hdf5"))
    # remove '/band' data from database
    if ('/bands/snr') in database.keys():
        database.remove('/bands/snr')
    if ('/bands/raw') in database.keys():
        database.remove('/bands/raw')

    # read .csv dataset by chunks (> 3GB file)
    filename = os.path.join(input_dir, "all_wf.grid.csv")
    chunksize = 2.5 * (10 ** 4)
    for chunk in pd.read_csv(filename, chunksize = chunksize):

        print("""%s: [INFO] handling %s sessions in chunk""" % (sys.argv[0], len(chunk['session_id'].unique())))

        # order by session id & timestamp
        chunk = chunk.sort_values(by = ['session_id', 'seconds']).reset_index(drop = True)

        # to speed up computation, filter out values which don't matter
        # - filter out low snrs
        chunk = chunk[chunk['snr'] > -75.0].reset_index(drop = True)
        # - filter out invalid freq. bands
        add_band(chunk)
        chunk = chunk[chunk['band'] >= 0].reset_index(drop = True)
        
        if chunk.empty:
            continue

        # - filter out consecutive time blocks with too few data points
        chunk['time-block'] = ((chunk['seconds'] - chunk['seconds'].shift(1)) > 1.0).astype(int).cumsum()
        # to make computation lighter, get rid of time blocks w/ less than n entries
        chunk = chunk.groupby(['session_id', 'encode', 'time-block']).apply(mark_size)
        chunk = chunk[chunk['block-size'] > 2].reset_index(drop = True)

        # abort if chunk is empty
        if chunk.empty:
            continue

        # add cell info
        add_cells(chunk, cell_size)

        extract_bands(chunk, database)
        extract_coverage(chunk, processed_data)

    # save on database
    for cat in ['time', 'speed']:
    
        db = ('/coverage/%s' % (cat))
        if db in database.keys():
            database.remove(db)

        parsing.utils.to_hdf5(processed_data[cat], db, database)
