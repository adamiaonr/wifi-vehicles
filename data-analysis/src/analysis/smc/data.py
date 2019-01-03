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
import hashlib
import timeit

# for parallel processing of sessions
import multiprocessing as mp 
# for maps
import pdfkit
# for MySQL & pandas
import MySQLdb as mysql
import sqlalchemy
import shapely.geometry

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

import analysis.smc.utils

import parsing.utils
import mapping.utils

import geopandas as gp

def to_sql(input_dir, cell_size = 20):

    output_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    # connect to SMC mysql database
    conn = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')
    # conn = mysql.connect(host = "localhost", user = "root", passwd = "xpto12x1", db = "smc")

    filename = os.path.join(input_dir, "all_wf.grid.csv")
    chunksize = 10 ** 5
    for chunk in pd.read_csv(filename, chunksize = chunksize):

        start_time = timeit.default_timer()

        # to speed up computation, filter out values which don't matter
        # - filter out low RSS
        chunk = chunk[chunk['snr'] > -80.0].reset_index(drop = True)
        if chunk.empty:
            continue

        analysis.smc.utils.add_band(chunk)
        #   - filter unknown bands (we consider 2.4 GHz and 5.0 GHz)
        chunk = chunk[chunk['band'] >= 0].reset_index(drop = True)
        if chunk.empty:
            continue

        # add cell ids
        # FIXME : this is wrong, since cell ids depend on cell size
        analysis.smc.utils.add_cells(chunk, cell_size)

        # rename columns
        chunk.rename(
            index = str, 
            columns = {
                'seconds' : 'timestamp', 
                'session_id' : 'session_id', 
                'encode' : 'bssid', 
                'snr' : 'rss', 
                'new_lat' : 'lat', 'new_lon' : 'lon', 'new_err' : 'gps_error',
                'cell-x' : 'cell_x',
                'cell-y' : 'cell_y'}, inplace = True)

        chunk = chunk[['timestamp', 'session_id', 'essid', 'bssid', 'rss', 'auth', 'frequency', 'band', 'cell_x', 'cell_y', 'lat', 'lon', 'gps_error']]
        # fill operator field
        chunk['operator'] = [ analysis.smc.utils.get_operator(s) for s in chunk['essid'].astype(str).tolist() ]
        chunk['operator_known'] = chunk['operator'].apply(lambda op : 0 if (op == 'unknown') else 1)
        # rebrand auth
        chunk['re_auth'] = 0
        chunk = analysis.smc.utils.rebrand_auth(chunk).reset_index(drop = True)
        # change essid to a fixed sized hash value
        chunk['essid'] = [ hashlib.md5(s).hexdigest() for s in chunk['essid'].astype(str).tolist() ]

        # data types
        for c in ['bssid', 'essid']:
            chunk[c] = chunk[c].astype(str)
        for c in ['cell_x', 'cell_y', 'timestamp', 'session_id', 'rss', 'frequency', 'band', 'auth']:
            chunk[c] = [str(s).split(',')[0] for s in chunk[c]]
            chunk[c] = chunk[c].astype(int)
        for c in ['lat', 'lon', 'gps_error']:
            chunk[c] = chunk[c].astype(float)

        chunk.to_sql(con = conn, name = 'original', if_exists = 'append')

        print("%s::to_sql() : [INFO] duration : %.3f sec" % (sys.argv[0], timeit.default_timer() - start_time))