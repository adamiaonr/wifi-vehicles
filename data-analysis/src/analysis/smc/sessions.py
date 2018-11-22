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

# for ap location estimation
from shapely.geometry import Point

# custom imports
import analysis.metrics
import analysis.trace
import analysis.gps
import analysis.ap_selection.rssi
import analysis.ap_selection.gps

import mapping.utils

# gps coords for a 'central' pin on porto, portugal
LAT  = 41.163158
LON = -8.6127137
# north, south, west, east limits of map, in terms of geo coordinates
LATN = LAT + 0.03
LATS = LAT - 0.03
LONE = LON + 0.06
LONW = LON - 0.06

def extract(input_dir, cell_size = 5.0):

    output_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    # load .hdfs database
    database = pd.HDFStore(os.path.join(output_dir, "smc.hdf5"))
    # extract nr. of cells in the designated area
    xx, yy = analysis.gps.get_cell_num(cell_size = cell_size, lat = [LATN, LATS], lon = [LONW, LONE])

    # read .csv dataset by chunks (> 3GB file)
    filename = os.path.join(input_dir, "all_wf.grid.csv")
    chunksize = 10 ** 5
    i = 0
    for chunk in pd.read_csv(filename, chunksize = chunksize):

        print("""%s: [INFO] handling %s sessions in chunk""" % (sys.argv[0], len(chunk['session_id'].unique())))

        # order by session id & timestamp
        chunk = chunk.sort_values(by = ['session_id', 'seconds']).reset_index(drop = True)

        # add cell ids to chunk, based on [new_lat, new_lon]
        chunk['cell-x'] = chunk['new_lon'].apply(lambda x : int((x - LONW) / (LONE - LONW) * xx))
        chunk['cell-y'] = chunk['new_lat'].apply(lambda y : int((y - LATS) / (LATN - LATS) * yy))
        # add 'band' column
        chunk['band'] = 0.0
        chunk.loc[(chunk['frequency'].astype(int) >= 2412) & (chunk['frequency'].astype(int) <= 2484), 'band'] = 2.4
        chunk.loc[(chunk['frequency'].astype(int) >= 5160) & (chunk['frequency'].astype(int) <= 5825), 'band'] = 5.0

        # filter by valid freq. bands
        chunk = chunk[chunk['band'] > 0.0].reset_index(drop = True)

        # # freq. bands
        # bands = chunk.groupby(['session_id', 'encode', 'cell-x', 'cell-y', 'band'])['snr'].mean().reset_index(drop = False, name = 'rss')
        # bands = bands[['session_id', 'encode', 'cell-x', 'cell-y', 'band', 'rss']]

        # print(bands)
        chunk.drop_duplicates(subset = ['session_id', 'seconds'], inplace = True)
        chunk['dist'] = mapping.utils.gps_to_dist(chunk['new_lat'], chunk['new_lon'], chunk['new_lat'].shift(1), chunk['new_lon'].shift(1))
        chunk['time'] = chunk['seconds'] - chunk['seconds'].shift(1)
        chunk['speed'] = (chunk['dist'] / chunk['time']).astype(float).fillna(0.0)

        print(chunk.groupby(['session_id', 'encode']).agg({'speed' : ['median', 'mean'], 'time' : 'count', 'dist' : ['sum', 'min']}).reset_index(drop = False))

        i += 1
        if i > 20:
            sys.exit(0)