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

def _cell(data, metric, stat, **kwargs):

    if (stat == 'wma') or (stat == 'ewma'):

        # data transferred by band and lap
        tx_data = data[kwargs['macs'] + ['lap-number']].groupby(['lap-number']).sum().reset_index()
        # weighing factors for each lap
        tx_data['n'] = 0.0
        denom = 0.0
        # remove the current lap if it can't be used as candidate
        candidate_laps = set([1.0, 2.0, 3.0, 4.0, 5.0])
        r = 0
        if not kwargs['use_lap']:
            candidate_laps -= set([kwargs['lap']])
            r = 1
        # get the sequence of laps to be used for the *wma calculation:
        #   - over a window of w laps
        #   - we rotate the set of candidate laps <> by lap - 1 positions, and take the last w positions
        laps = analysis.metrics.rotate(list(candidate_laps), -(int(kwargs['lap']) - r))[-kwargs['stat_args']['w']:]
        for i, l in enumerate(laps):

            if stat == 'wma':
                tx_data.loc[tx_data['lap-number'] == l, 'n'] = i
                denom += i

            elif stat == 'ewma':
                tx_data.loc[tx_data['lap-number'] == l, 'n'] = (1.0 - kwargs['stat_args']['alpha'])**(float((len(laps) - 1) - i))
                denom += (1.0 - kwargs['stat_args']['alpha'])**(float((len(laps) - 1) - i))

        for mac in kwargs['macs']:
            tx_data[mac] = (tx_data[mac] * tx_data['n']) / float(denom)

        return tx_data[kwargs['macs']].sum().idxmax(axis = 1)

    elif stat == 'mean':
        # return mac addr which provides max mean() <metric> in the cell (all laps)
        return data[kwargs['macs']].mean().idxmax(axis = 1)

    elif stat == 'max':
        # return mac addr which provides max() <metric> in the cell (all laps)
        return data[kwargs['macs']].max().idxmax(axis = 1)

    else:
        sys.stderr.write("""[ERROR] %s stat not implemented. abort.\n""" % (stat))

def cell(input_dir, trace_nr,
    args,
    force_calc = False):

    # get mac addr info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    clients = mac_addrs[mac_addrs['type'] == 'client']

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    cell_db = ('/%s/%s/%s/%s/%s/%s' % (
        'best-cell',
        args['cell-size'],
        args['metric'], args['stat'], ('-'.join([str(v) for v in args['stat-args'].values()])),
        ('%d-%d' % (int(args['use-current-lap']), int(args['use-direction'])))))

    if cell_db in database.keys():
        if force_calc:
            database.remove(cell_db)
        else:
            sys.stderr.write("""[INFO] %s already in database. skipping data extraction.\n""" % (cell_db))
            return

    # merge trace data w/ throughput data
    trace_data = pd.DataFrame(columns = ['interval-tmstmp', 'lat', 'lon', 'lap-number', 'direction'])
    macs = []
    for i, client in clients.iterrows():

        base_db = ('/%s/%s' % ('interval-data', client['mac']))
        if base_db not in database.keys():
            continue

        # load data for a client mac
        data = database.select(base_db)
        if data.empty:
            continue

        data[client['mac']] = data[args['metric']]
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
    x_cell_num, y_cell_num = analysis.gps.get_cell_num(cell_size = args['cell-size'], lat = [LATN, LATS], lon = [LONW, LONE])
    trace_data['cell-x'] = trace_data['lon'].apply(lambda x : int((x - LONW) / (LONE - LONW) * x_cell_num))
    trace_data['cell-y'] = trace_data['lat'].apply(lambda y : int((y - LATS) / (LATN - LATS) * y_cell_num))

    # now, fill a 'best' column, based on 'method'
    # FIXME: only 2 methods so far : 
    #   - /every-other/no-direction
    trace_data['best'] = ''
    laps = trace_data['lap-number'].unique()

    for lap in laps:

        # training data
        other = None
        if bool(int(args['use-current-lap'])):
            other = trace_data.groupby(['cell-x', 'cell-y'])
        else:
            other = trace_data[trace_data['lap-number'] != lap].groupby(['cell-x', 'cell-y'])

        # test data
        this = trace_data[trace_data['lap-number'] == lap].groupby(['cell-x', 'cell-y'])

        for name, group in this:

            other_name = name
            if other_name not in other.groups:
                closest = analysis.gps.get_closest_cell(name, other.groups.keys())
                other_name = (closest['cell-x'], closest['cell-y'])

            other_data = trace_data.iloc[ other.groups[other_name].tolist() ]
            ix = trace_data[(trace_data['lap-number'] == lap) & (trace_data['cell-x'] == name[0]) & (trace_data['cell-y'] == name[1])].index.tolist()

            if (args['stat'] == 'wma'):
                trace_data.loc[ix, 'best'] = _cell(data = other_data, metric = args['metric'], stat = 'wma', stat_args = args['stat-args'], macs = macs, lap = lap, use_lap = int(args['use-current-lap']))

            elif (args['stat'] == 'ewma'):
                trace_data.loc[ix, 'best'] = _cell(data = other_data, metric = args['metric'], stat = 'ewma', stat_args = args['stat-args'], macs = macs, lap = lap, use_lap = int(args['use-current-lap']))

            elif (args['stat'] == 'mean'):
                # ewma w/ alpha = 0.0 is a typical mean()
                args['stat-args']['alpha'] = 0.0
                trace_data.loc[ix, 'best'] = _cell(data = other_data, metric = args['metric'], stat = 'ewma', stat_args = args['stat-args'], macs = macs, lap = lap, use_lap = int(args['use-current-lap']))

            elif (args['stat'] == 'max'):
                trace_data.loc[ix, 'best'] = _cell(data = other_data, metric = args['metric'], stat = 'max', macs = macs)

            else:
                sys.stderr.write("""[ERROR] %s stat not implemented. abort.\n""" % (stat))
                return

    trace_data = trace_data[trace_data['best'] != ''].sort_values(by = ['interval-tmstmp']).reset_index(drop = True).convert_objects(convert_numeric = True)
    trace_data['block'] = ((trace_data['best'].shift(1) != trace_data['best'])).astype(int).cumsum()

    parsing.utils.to_hdf5(trace_data, cell_db, database)
