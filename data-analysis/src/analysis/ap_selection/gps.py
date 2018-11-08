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

def get_closest_cell(cell, candidates):
    
    cells = pd.DataFrame()
    
    for c in candidates:
        cells = cells.append({'cell-x' : c[0], 'cell-y' : c[1]}, ignore_index = True)
    cells['diff'] = np.abs(cells['cell-x'] - cell[0]) + np.abs(cells['cell-y'] - cell[1])

    return cells.ix[cells['diff'].idxmin()]

def cell(input_dir, trace_nr,
    metric = 'throughput',
    args = {'cell-size' : 10.0}):

    # objective:
    #   - get a dataframe w/ columns ['interval-tmstmp', 'cell-x', 'cell-y', <thghpt for all macs>, 'best [mac]']
    #   - 'best' is a mac, calculated according to:
    #       - 1) /every-other/no-direction : on lap L, pick ap w/ best mean throughput on the current cell, using data from 
    #                                        laps M, w/ M != L. direction not taken into account.
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

    # merge trace data w/ throughput data
    trace_data = pd.DataFrame(columns = ['interval-tmstmp', 'lat', 'lon', 'lap-number', 'direction'])
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
        trace_data = pd.merge(trace_data, data[ ['interval-tmstmp', client['mac'], 'lat', 'lon', 'lap-number', 'direction'] ], on = ['interval-tmstmp', 'lat', 'lon', 'lap-number', 'direction'], how = 'outer')

    # drop rows w/ undefined throughput values for all mac addrs
    trace_data = trace_data.dropna(subset = macs, how = 'all').drop_duplicates(subset = ['interval-tmstmp']).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)

    # keep data of moving period only, i.e. when the bike is moving and getting gps positions
    trace_data = analysis.trace.extract_moving_data(trace_data)
    # fix timestamp gaps
    trace_data['timestamp'] = trace_data['interval-tmstmp'].astype(int)
    # fix lat and lon gaps
    analysis.trace.fix_gaps(trace_data, subset = ['lat', 'lon'])

    # add cell ids
    x_cell_num, y_cell_num = analysis.gps.get_cell_num(trace_data, cell_size = args['cell-size'], lat = [LATN, LATS], lon = [LONW, LONE])
    trace_data['cell-x'] = trace_data['lon'].apply(lambda x : int((x - LONW) / (LONE - LONW) * x_cell_num))
    trace_data['cell-y'] = trace_data['lat'].apply(lambda y : int((y - LATS) / (LATN - LATS) * y_cell_num))

    # now, fill a 'best' column, based on 'method'
    # FIXME: only 2 methods so far : 
    #   - /every-other/no-direction
    trace_data['best'] = ''
    laps = trace_data['lap-number'].unique()

    for lap in laps:

        # <cell-x, cell-y> pairs for 'every other lap'
        other = trace_data[trace_data['lap-number'] != lap].groupby(['cell-x', 'cell-y'])
        # <cell-x, cell-y> pairs for 'this' lap
        this = trace_data[trace_data['lap-number'] == lap].groupby(['cell-x', 'cell-y'])

        for name, group in this:

            # find the current <cell-x, cell-y> pair in 'others'
            other_name = name
            if other_name not in other.groups:
                cc = get_closest_cell(name, other.groups.keys())
                other_name = (cc['cell-x'], cc['cell-y'])

            other_data = trace_data.iloc[other.groups[other_name].tolist()]
            trace_data.loc[(trace_data['lap-number'] == lap) & (trace_data['cell-x'] == name[0]) & (trace_data['cell-y'] == name[1]), 'best'] = other_data[macs].mean().idxmax(axis = 1)

    trace_data = trace_data[trace_data['best'] != ''].sort_values(by = ['interval-tmstmp']).reset_index(drop = True).convert_objects(convert_numeric = True)
    trace_data['block'] = ((trace_data['best'].shift(1) != trace_data['best'])).astype(int).cumsum()

    parsing.utils.to_hdf5(trace_data, ('/%s/%s/%s/%s' % ('best-cell', args['cell-size'], 'every-other', 'no-direction')), database)
