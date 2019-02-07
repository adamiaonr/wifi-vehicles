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
import timeit
import geopandas as gp
import shapely.geometry

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

# wifi net operators
operators = {
    1 : {'name' : 'eduroam', 'match-str' : 'eduroam', 'public' : ''},
    2 : {'name' : 'zon', 'match-str' : 'FON_ZON_FREE_INTERNET|ZON-|Optimus|NOS', 'public' : 'FON_ZON_FREE_INTERNET'},
    3 : {'name' : 'meo', 'match-str' : 'MEO-|Thomson|MEO-WiFi|PT-WIFI|SAPO|2WIRE-', 'public' : 'MEO-WiFi|PT-WIFI'},
    4 : {'name' : 'vodafone', 'match-str' : 'Vodafone-|VodafoneFibra-|VodafoneMobileWiFi-|Huawei', 'public' : 'VodafoneMobileWiFi-'},
    5 : {'name' : 'porto digital', 'match-str' : 'WiFi Porto Digital', 'public' : 'WiFi Porto Digital'}
}

# FIXME: something wrong here...
auth_types = {
    0 : {'name' : 'unknown', 'types' : [0], 'operators' : []},
    1 : {'name' : 'open', 'types' : [1], 'operators' : [0, 1]},
    2 : {'name' : 'commer.', 'types' : [1], 'operators' : [2, 3, 4, 5]},
    3 : {'name' : 'WPA-x', 'types' : [2, 3, 4], 'operators' : []},
    4 : {'name' : '802.11x', 'types' : [5], 'operators' : []}}

# gps coords for a 'central' pin on porto, portugal
LAT  = 41.163158
LON = -8.6127137
# north, south, west, east limits of map, in terms of geo coordinates
LATN = LAT + 0.03
LATS = LAT - 0.03
LONE = LON + 0.06
LONW = LON - 0.06

def get_road_intersection(data, road_data, columns = []):

    # create a geopandas dataframe out of data (w/ 'lat' and 'lon' columns)
    geodf = gp.GeoDataFrame(data)
    # add 'geometry' column, built with Point objects from 'lat' and 'LON'
    geodf['geometry'] = [ shapely.geometry.Point(tuple(x)) for x in geodf[['lon' ,'lat']].values ]
    if geodf.empty:
        return

    # intersection between road cells and data 
    start_time = timeit.default_timer()
    intersection = gp.sjoin(road_data, geodf, how = 'inner', op = 'intersects')[['index', 'geometry', 'cell_id'] + columns]
    print("%s::extract_road_data() : [INFO] intersection in %.3f sec" % (sys.argv[0], timeit.default_timer() - start_time))
    return intersection.drop_duplicates(subset = ['cell_id'])[['cell_id']]

def rebrand_auth(data):
    for at in sorted(auth_types.keys()):
        data.loc[(data['auth'].isin(auth_types[at]['types'])) & ((not auth_types[at]['operators']) | (data['operator'].isin(auth_types[at]['operators']))), 're_auth'] = at
    return data

# def add_cells(data, cell_size):

#     # extract nr. of cells in the designated area
#     xx, yy = analysis.gps.get_cell_num(cell_size = cell_size, lat = [LATN, LATS], lon = [LONW, LONE])
#     # add cell ids to data, based on [new_lat, new_lon]
#     data['cell_x'] = data['lon'].apply(lambda x : int((x - LONW) / (LONE - LONW) * xx)).astype(int)
#     data['cell_y'] = data['lat'].apply(lambda y : int((y - LATS) / (LATN - LATS) * yy)).astype(int)
#     # drop rows with out-of-bounds cell coords
#     data.drop(data[(data['cell_y'] < 0) | (data['cell_x'] < 0) | (data['cell_y'] > (yy - 1)) | (data['cell_x'] > (xx - 1))].index, inplace = True)
#     # it will be useful to get a single integer id
#     data['cell_id'] = (data['cell_y'].apply(lambda y : (y * xx)) + data['cell_x']).astype(int)

def add_band(data):
    # add 'band' column for '2.4' and '5.0'
    data['band'] = -1
    data.loc[(data['frequency'].astype(int) >= 2412) & (data['frequency'].astype(int) <= 2484), 'band'] = 0
    data.loc[(data['frequency'].astype(int) >= 5160) & (data['frequency'].astype(int) <= 5825), 'band'] = 1
    data['band'] = data['band'].astype(int)

def get_operator(essid):
    for op in operators:
        if any(ss in essid for ss in operators[op]['match-str'].split('|')):
            return op

    return 0

def get_public(essid, operator):

    if operator == 0:
        return 0

    if any(ss in essid for ss in operators[operator]['public'].split('|')):
        return 1

    return 0    

def get_db(input_dir):

    db_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(db_dir):
        os.makedirs(db_dir)

    database = pd.HDFStore(os.path.join(db_dir, "smc.hdf5"))
    return database

def calc_dist(data):
    data['dist'] = mapping.utils.gps_to_dist(data['new_lat'], data['new_lon'], data['new_lat'].shift(1), data['new_lon'].shift(1))
    return data

def mark_size(data):
    data['block-size'] = len(data.drop_duplicates(subset = ['seconds']))
    return data
