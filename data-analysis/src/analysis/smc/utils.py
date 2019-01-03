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

# wifi net operators
operators = {
    'eduroam'   : {'match-str' : 'eduroam'},
    'zon'       : {'match-str' : 'FON_ZON_FREE_INTERNET|ZON-|Optimus'},
    'meo'       : {'match-str' : 'MEO-|Thomson|MEO-WiFi|PT-WIFI'},
    'vodafone'  : {'match-str' : 'Vodafone-|VodafoneFibra-|VodafoneMobileWiFi-'}
}

auth_types = {
    0 : {'name' : 'unknown', 'types' : [0], 'operators' : ['unknown']},
    1 : {'name' : 'open', 'types' : [1], 'operators' : ['unknown']},
    2 : {'name' : 'commer.', 'types' : [0, 1], 'operators' : ['meo', 'vodafone', 'zon']},
    3 : {'name' : 'WPA-x', 'types' : [2, 3, 4], 'operators' : []},
    4 : {'name' : '802.11x', 'types' : [5], 'operators' : []},
    5 : {'name' : '802.11x', 'types' : [0, 1], 'operators' : ['eduroam']}}

# gps coords for a 'central' pin on porto, portugal
LAT  = 41.163158
LON = -8.6127137
# north, south, west, east limits of map, in terms of geo coordinates
LATN = LAT + 0.03
LATS = LAT - 0.03
LONE = LON + 0.06
LONW = LON - 0.06

def rebrand_auth(data):
    for at in sorted(auth_types.keys()):
        # FIXME: this is to fix a mutual exclusivity issue w/ auth types [0,1] and operator 'eduroam'
        _at = at
        if at == 5:
            _at = 4

        data.loc[(data['auth'].isin(auth_types[at]['types'])) & ((not auth_types[at]['operators']) | (data['operator'].isin(auth_types[at]['operators']))), 're_auth'] = _at

    return data

def add_cells(data, cell_size):

    # extract nr. of cells in the designated area
    xx, yy = analysis.gps.get_cell_num(cell_size = cell_size, lat = [LATN, LATS], lon = [LONW, LONE])
    # add cell ids to data, based on [new_lat, new_lon]
    data['cell-x'] = data['new_lon'].apply(lambda x : int((x - LONW) / (LONE - LONW) * xx))
    data['cell-y'] = data['new_lat'].apply(lambda y : int((y - LATS) / (LATN - LATS) * yy))

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

    return 'unknown'

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
