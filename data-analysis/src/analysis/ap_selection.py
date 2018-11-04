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
def _rssi(grp_data, macs):
    # the highest rssi at the end of each ap-period
    mac = grp_data[grp_data['scan-period'] == 1].iloc[-1][macs].idxmax(axis = 1)
    grp_data['best'] = mac
    return grp_data

def rssi(input_dir, trace_nr,
    method = 'periodic',
    args = {'periodic' : {'scan_period' : 10.0, 'scan_time' : 1.0}}):

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    if method == 'periodic':
        db_name = ('/%s/%s/%d/%d' % ('best-rssi', 'periodic', int(args['periodic']['scan_period']), int(args['periodic']['scan_time'])))
        if db_name in database.keys():
            sys.stderr.write("""[INFO] %s already in database\n""" % (db_name))
            return
    else:
        sys.stderr.write("""[ERROR] method %s not implemented yet. abort.\n""" % (method))

    # load 'best' 'wlan rssi' data
    db_name = ('/%s/%s' % ('best', 'wlan rssi'))
    if db_name not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (db_name))
        return

    data = database.select(db_name).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
    # FIXME: why do we end up w/ duplicate 'interval-tmstmp' values?
    # get rid of 'best' column
    data = data[[col for col in data.columns if col not in {'best'}]].drop_duplicates(subset = ['interval-tmstmp'])

    macs = [col for col in data.columns if col not in {'interval-tmstmp'}]
    if method == 'periodic':
        
        sp = args['periodic']['scan_period']
        st = args['periodic']['scan_time']

        # divide data in periods of (scan_period + scan_time)
        data['ap-period'] = ((data['interval-tmstmp'] - data.iloc[0]['interval-tmstmp']) / (sp + st)).astype(int)
        # mark scan time portions of scan periods
        data['scan-period'] = (((data.groupby(['ap-period'])['interval-tmstmp'].transform(lambda x : x.diff().cumsum()).fillna(0.0) / (st)).astype(int)) == 0).astype(int)

        # the 'best' mac according to 'wlan rssi': 
        #   - the highest rssi at the end of each ap-period
        #   - it remains for the rest of each scan-period
        data = data.groupby(['ap-period']).apply(_rssi, macs = macs)
        parsing.utils.to_hdf5(data, ('/%s/%s/%d/%d' % ('best-rssi', 'periodic', int(sp), int(st))), database)

    else:
        sys.stderr.write("""[ERROR] method %s not implemented yet. abort.\n""" % (method))

def cell(input_dir, trace_nr,
    metric = 'throughput',
    args = {'cell-size' : 10.0}):

    # objective:
    #   - get a dataframe w/ columns ['interval-tmstmp', 'cell-x', 'cell-y', <thghpt for all macs>, 'best [mac]']
    #   - 'best' is a mac, calculated according to:
    #       - 1) /every-other/no-direction : on lap L, pick ap w/ best mean throughput on the current cell, using data from 
    #                                      laps M, w/ M != L. direction not taken into account.
    #       - 2) 

    # get mac addr info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    clients = mac_addrs[mac_addrs['type'] == 'client']

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    db_name = ('/%s/%s/%s/%s' % ('best-cell', args['cell-size'], 'every-other', 'no-direction'))
    if db_name in database.keys():
        sys.stderr.write("""[INFO] %s already in database\n""" % (db_name))
        return

    # get gps pos of trace
    gps_data, lap_tmstmps = analysis.gps.get_data(input_dir, trace_dir, tag_laps = False)
    gps_data['interval-tmstmp'] = [ (float(ts)) for ts in gps_data['timestamp'] ]
    gps_data = gps_data.sort_values(by = ['interval-tmstmp']).reset_index(drop = True)

    # merge gps data w/ throughput data
    macs = []
    for i, client in clients.iterrows():

        db_name = ('/%s/%s' % ('interval-data', client['mac']))
        if db_name not in database.keys():
            continue

        # load data for a client mac
        data = database.select(db_name)
        if data.empty:
            continue

        data[client['mac']] = data[metric]
        macs.append(client['mac'])

        # update best w/ mac info
        # FIXME: is the use of 'outer' merge correct here?
        gps_data = pd.merge(gps_data, data[ ['interval-tmstmp', client['mac']] ], on = ['interval-tmstmp'], how = 'outer')
        # gps_data = gps_data.sort_values(by = ['interval-tmstmp']).reset_index(drop = True)

    # drop rows w/ undefined throughput values for all mac addrs
    gps_data = gps_data.dropna(subset = macs, how = 'all').drop_duplicates(subset = ['interval-tmstmp']).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
    # keep data of moving period only, i.e. when the bike is moving and getting gps positions
    gps_data = analysis.trace.extract_moving_data(gps_data)
    # fix timestamp gaps
    gps_data.loc[np.isnan(gps_data['timestamp']), 'timestamp'] = gps_data[np.isnan(gps_data['timestamp'])]['interval-tmstmp'].astype(int)
    # fix lat and lon gaps
    analysis.trace.fix_gaps(gps_data, subset = ['lat', 'lon'])

    # add cell ids
    x_cell_num, y_cell_num = analysis.gps.get_cell_num(gps_data, cell_size = args['cell-size'], lat = [LATN, LATS], lon = [LONW, LONE])
    gps_data['cell-x'] = gps_data['lon'].apply(lambda x : int((x - LONW) / (LONE - LONW) * x_cell_num))
    gps_data['cell-y'] = gps_data['lat'].apply(lambda y : int((y - LATS) / (LATN - LATS) * y_cell_num))

    # add lap numbers and direction
    analysis.gps.add_lap_numbers(gps_data, lap_tmstmps)
    # gps_data['interval-tmstmp-str'] = [ (str(ts)) for ts in gps_data['interval-tmstmp'] ]
    # print(gps_data[['interval-tmstmp-str', 'timestamp', 'cell-x', 'cell-y', 'lap-number', 'direction']])

    # now, fill a 'best' column, based on 'method'
    # FIXME: only 1 method so far : /every-other/no-direction
    gps_data['best'] = ''
    laps = gps_data['lap-number'].unique()
    for lap in laps:

        # calculate best mac per cell, cosidering 'every other lap'
        grouped = gps_data[gps_data['lap-number'] != lap].groupby(['cell-x', 'cell-y'])
        for name, group in grouped:
            gps_data.loc[(gps_data['lap-number'] == lap) & (gps_data['cell-x'] == name[0]) & (gps_data['cell-y'] == name[1]), 'best'] = group[macs].mean().idxmax(axis = 1)

    gps_data = gps_data[gps_data['best'] != ''].sort_values(by = ['interval-tmstmp']).reset_index(drop = True).convert_objects(convert_numeric = True)
    gps_data['block'] = ((gps_data['best'].shift(1) != gps_data['best'])).astype(int).cumsum()
    
    parsing.utils.to_hdf5(gps_data, ('/%s/%s/%s/%s' % ('best-cell', args['cell-size'], 'every-other', 'no-direction')), database)
