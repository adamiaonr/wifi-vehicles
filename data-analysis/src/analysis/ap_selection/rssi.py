import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import os
import re
import argparse
import sys
import glob
import math
import gmplot
import time
import timeit
import subprocess
import csv
# for parallel processing of sessions
import multiprocessing as mp 
import hashlib
import datetime
import json

import mapping.utils
import mapping.openstreetmap

import geopandas as gp

import parsing.utils

import analysis.metrics
import analysis.gps
import analysis.channel
import analysis.trace

import shapely.geometry

from random import randint

from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple

from prettytable import PrettyTable

from sklearn import linear_model

# north, south, west, east limits of map, in terms of geo coordinates
LATN = 41.176796
LATS = 41.179283
LONE = -8.593912
LONW = -8.598336
# gps coords for a 'central' pin on FEUP, Porto, Portugal
LAT  = (41.176796 + 41.179283) / 2.0
LON = (-8.598336 + -8.593912) / 2.0

# source : https://medium.com/@sean.turner026/applying-custom-functions-to-groupby-objects-in-pandas-61af58955569
def _rssi(data, macs, mode = 'periodic'):

    if mode == 'periodic':
        # the highest rssi at the end of each ap-period
        mac = data[data['scan-period'] == 1].iloc[-1][macs].idxmax(axis = 1)
        data['best'] = mac

    elif mode == 'band-steering':

        mac = ''
        if data[(data['scan-period'] == 1)].iloc[-1]['band-steering'] == 1:
            mac = data[(data['scan-period'] == 1)].iloc[-1][macs['5.0']].astype(float).idxmax(axis = 1)
        if (data[(data['scan-period'] == 1)].iloc[-1]['band-steering'] == 0) or ((type(mac) == float) and (np.isnan(mac))):
            mac = data[(data['scan-period'] == 1)].iloc[-1][macs['2.4']].astype(float).idxmax(axis = 1)

        data['best'] = mac

    return data

def periodic(input_dir, trace_nr,
    method = 'periodic',
    args = {'scan_period' : 10.0, 'scan_time' : 1.0},
    force_calc = False):

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    periodic_db = ('/%s/%s/%d/%d' % ('best-rssi', method, int(args['scan_period']), int(args['scan_time'])))
    if periodic_db in database.keys():
        if force_calc:
            database.remove(periodic_db)
        else:
            sys.stderr.write("""[INFO] %s already in database. skipping data extraction.\n""" % (periodic_db))
            return

    # load 'best' 'wlan rssi' data
    best_db = ('/%s/%s' % ('best', 'wlan rssi'))
    if best_db not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (best_db))
        return

    data = database.select(best_db).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
    # FIXME: why do we end up w/ duplicate 'interval-tmstmp' values?
    # get rid of 'best' column
    data = data[[col for col in data.columns if col not in {'best'}]].drop_duplicates(subset = ['interval-tmstmp'])

    macs = [col for col in data.columns if col not in {'interval-tmstmp'}]
    if method == 'periodic':
        
        sp = args['scan_period']
        st = args['scan_time']

        # divide data in periods of (scan_period + scan_time)
        data['ap-period'] = ((data['interval-tmstmp'] - data.iloc[0]['interval-tmstmp']) / (sp + st)).astype(int)
        # mark scan time portions of scan periods
        # FIXME: 0.5 intervals should not be hardcoded
        if (st < .5):
            st = .5

        data['scan-period'] = (((data.groupby(['ap-period'])['interval-tmstmp'].transform(lambda x : x.diff().cumsum()).fillna(0.0) / (st)).astype(int)) == 0).astype(int)

        # the 'best' mac according to 'wlan rssi': 
        #   - the highest rssi at the end of each ap-period
        #   - it remains for the rest of each scan-period
        data = data.groupby(['ap-period']).apply(_rssi, macs = macs)
        parsing.utils.to_hdf5(data, periodic_db, database)

    else:
        sys.stderr.write("""[ERROR] method %s not implemented yet. abort.\n""" % (method))

def _band_steering(data):
    return int(len(data[data['band'] == 5.0]) > len(data[data['band'] == 2.4]))

def band_steering(input_dir, trace_nr,
    method = 'band-steering',
    args = {'scan_period' : 10.0, 'scan_time' : 1.0, 'cell-size' : 10.0, 'aid-metric' : 'throughput'},
    force_calc = False):

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    band_steer_db = ('/%s/%s/%s/%s/%s/%s' % ('best-rssi', method, args['scan_period'], args['scan_time'], args['cell-size'], args['aid-metric']))
    if band_steer_db in database.keys():
        if force_calc:
            database.remove(band_steer_db)
        else:
            sys.stderr.write("""[INFO] %s already in database. skipping data extraction.\n""" % (band_steer_db))
            return

    # we need 3 data collections to do this:
    #   1) lat & lon data (on /dist-data)
    #   2) rssi data (on /best/wlan rssi)
    #   3) aid-metric data (on /best/<aid-metric>)
    
    # (1) load dist data
    loc_db = ('/%s' % ('dist-data'))
    if loc_db not in database.keys():
        sys.stderr.write("""[INFO] %s already in database. skipping data extraction.\n""" % (loc_db))
        return

    loc_data = database.select(loc_db).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)[['interval-tmstmp', 'lat', 'lon', 'lap-number', 'direction']]

    # (2) load wlan rssi data
    rssi_db = ('/%s/%s' % ('best', 'wlan rssi'))
    if rssi_db not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (rssi_db))
        return

    rssi_data = database.select(rssi_db).drop_duplicates(subset = ['interval-tmstmp']).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)

    # (3) load aid-metric data
    aid_db = ('/%s/%s' % ('best', args['aid-metric']))
    if aid_db not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (rssi_db))
        return

    aid_data = database.select(aid_db).drop_duplicates(subset = ['interval-tmstmp']).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)

    # classify data in aid-data as 2.4 GHz or 5 GHz
    aid_data['band'] = ''
    for i, client in clients.iterrows():
        aid_data.loc[aid_data['best'] == client['mac'], 'band'] = client['band']

    # add cell ids to loc_data
    x_cell_num, y_cell_num = analysis.gps.get_cell_num(loc_data, cell_size = args['cell-size'], lat = [LATN, LATS], lon = [LONW, LONE])
    loc_data['cell-x'] = loc_data['lon'].apply(lambda x : int((x - LONW) / (LONE - LONW) * x_cell_num))
    loc_data['cell-y'] = loc_data['lat'].apply(lambda y : int((y - LATS) / (LATN - LATS) * y_cell_num))
    
    # merge aid_data and loc_data
    aid_data = pd.merge(aid_data, loc_data, on = ['interval-tmstmp'], how = 'left')

    # mark <lap, <cell-id>> tuples as 'band-steering' (1) or 'no band-steer' (0)
    aid_data['band-steering'] = 0
    laps = aid_data['lap-number'].unique()

    for lap in laps:

        # <cell-x, cell-y> pairs for 'every other lap'
        other = aid_data[aid_data['lap-number'] != lap].groupby(['cell-x', 'cell-y'])
        # <cell-x, cell-y> pairs for 'this' lap
        this = aid_data[aid_data['lap-number'] == lap].groupby(['cell-x', 'cell-y'])

        for name, group in this:
            other_name = name
            if other_name not in other.groups:
                closest = analysis.gps.get_closest_cell(name, other.groups.keys())
                other_name = (closest['cell-x'], closest['cell-y'])

            other_data = aid_data.iloc[other.groups[other_name].tolist()]
            aid_data.loc[(aid_data['lap-number'] == lap) & (aid_data['cell-x'] == name[0]) & (aid_data['cell-y'] == name[1]), 'band-steering'] = _band_steering(other_data[['band']])

    # merge [bad-steering] with rssi data
    rssi_data = pd.merge(rssi_data, aid_data[ ['interval-tmstmp', 'band-steering'] ], on = ['interval-tmstmp'], how = 'left').convert_objects(convert_numeric = True)
    rssi_data = rssi_data[ [ col for col in rssi_data.columns if col not in ['best'] ] ]
    # pick the conditional best rssi 
    macs = defaultdict(list)
    macs['2.4'] = [ col for col in rssi_data.columns if col not in ['interval-tmstmp', 'band-steering'] ]
    macs['5.0'] = list(set(clients[clients['band'] == 5.0]['mac'].tolist()) & set(macs['2.4']))
    sp = args['scan_period']
    st = args['scan_time']
    # divide data in periods of (scan_period + scan_time)
    rssi_data['ap-period'] = ((rssi_data['interval-tmstmp'] - rssi_data.iloc[0]['interval-tmstmp']) / (sp + st)).astype(int)
    # mark scan time portions of scan periods
    # FIXME: 0.5 intervals should not be hardcoded
    if (st < .5):
        st = .5

    rssi_data['scan-period'] = (((rssi_data.groupby(['ap-period'])['interval-tmstmp'].transform(lambda x : x.diff().cumsum()).fillna(0.0) / (st)).astype(int)) == 0).astype(int)
    rssi_data['best'] = ''
    rssi_data = rssi_data.groupby(['ap-period']).apply(_rssi, macs = macs, mode = 'band-steering')
    parsing.utils.to_hdf5(rssi_data, band_steer_db, database)
