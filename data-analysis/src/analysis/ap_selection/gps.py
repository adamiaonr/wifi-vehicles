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

# north, south, west, east gps coord limits of FEUP map
LATN = 41.176796
LATS = 41.179283
LONE = -8.593912
LONW = -8.598336
# central gps coords for FEUP
LAT  = (41.176796 + 41.179283) / 2.0
LON = (-8.598336 + -8.593912) / 2.0

def select_gps(data, method, args):

    if method == 'cell-history':
        
        nodes = ['m1', 'w1', 'w2', 'w3']

        if args['stat'] == 'ewma':
            data[nodes] = data[nodes].ewm(alpha = float(args['stat-args']['alpha'])).mean()
        elif args['stat'] == 'mean':
            data[nodes] = data[nodes].expanding().mean()
        elif args['stat'] == 'max':
            data[nodes] = data[nodes].expanding().max()

        # NOTE : the shift(1) is necessary, because this algorithm selects the best based on
        # previous history only, i.e. it must not count with the throughput values of the current cell period,
        # which - by definition - are unknown
        data['best'] = data[nodes].idxmax(axis = 1).shift(1)

    return data

def optimize_handoffs(input_dir, trace_nr, args, force_calc = False):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    nodes = ['m1', 'w1', 'w2', 'w3']

    if args['db'] not in database.keys():
        sys.stderr.write("""[ERROR] %s not in database. abort.\n""" % (db_name))
        return

    opt_db = ('%s/optimize-handoff' % (args['db']))
    if opt_db in database.keys():
        if force_calc:
            database.remove(opt_db)
        else:
            sys.stderr.write("""[INFO] %s already in database. skipping data extraction.\n""" % (opt_db))
            return

    data = database.select(args['db']).sort_values(by = ['timed-tmstmp']).reset_index(drop = True)
    data['ap-block'] = ((data['best'] != data['best'].shift(1))).astype(int).cumsum()

    times = data.groupby(['ap-block', 'best'])['timed-tmstmp'].apply(list).reset_index(drop = False)
    times['timed-tmstmp'] = times['timed-tmstmp'].apply(lambda x : sorted(x))
    times['duration'] = times['timed-tmstmp'].apply(lambda x : x[-1] - x[0])
    times['duration'] = times['duration'] + 0.5
    times['fix'] = 0
    times.loc[(times['duration'] < 5) & (times.index < (len(times) - 1)), 'fix'] = 1
    times['fix-block'] = ((times['fix'] == 1) & (times['fix'] != times['fix'].shift(1))).astype(int).cumsum()

    times['~fix'] = ~times['fix']
    times['fix-to-block'] = ((times['~fix'] & (times['fix'].shift(1)))).astype(int).cumsum()
    fix_key = times[['best', 'fix-to-block']].drop_duplicates(subset = ['fix-to-block']).reset_index(drop = True)
    fix_key['fix-to'] = fix_key['best']
    times = pd.merge(times, fix_key[['fix-to', 'fix-to-block']], on = ['fix-to-block'], how = 'left')
    data = pd.merge(data, times[['ap-block', 'fix', 'fix-to']], on = ['ap-block'], how = 'left')
    data.loc[data['fix'] == 1, 'best'] = data[data['fix'] == 1]['fix-to']

    # data = data[(data['timed-tmstmp'] > 1548781953.0) & (data['timed-tmstmp'] < 1548782668.0)]
    # data['timed-tmstmp-str'] = data['timed-tmstmp'].astype(str)
    # print(data[['timed-tmstmp-str', 'ap-block', 'best']].groupby('best').size())

    # sys.exit(0)

    data = data.drop_duplicates(subset = ['timed-tmstmp']).reset_index(drop = True)
    data = data.sort_values(by = ['timed-tmstmp']).reset_index(drop = True)
    data[args['metric']] = 0.0
    for node in nodes:
        data.loc[data['best'] == node, args['metric']] = data[data['best'] == node][node]

    parsing.utils.to_hdf5(data, opt_db, database)    

def cell_history(input_dir, trace_nr,
    args,
    force_calc = False):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    if args['metric'] == 'throughput':
        cell_history_db = ('/selection-performance/%s/gps/cell-history/%s/%s/%s' % (
            args['metric'],
            args['cell-size'],
            args['stat'], 
            ('-'.join([str(v) for v in args['stat-args'].values()]))))
    else:
        cell_history_db = ('/selection/%s/gps/cell-history/%s/%s/%s' % (
            args['metric'],
            args['cell-size'],
            args['stat'], 
            ('-'.join([str(v) for v in args['stat-args'].values()]))))        

    if cell_history_db in database.keys():
        if force_calc:
            database.remove(cell_history_db)
        else:
            sys.stderr.write("""[INFO] %s already in database. skipping data extraction.\n""" % (cell_history_db))
            return

    # merge /best/<metric> & gps data + add cell info
    data = analysis.trace.merge_gps(input_dir, trace_nr, args['metric'], cell_size = float(args['cell-size']))

    # add period numbers, i.e. distinct periods of time during which client was in a distinct cell <x,y>
    nodes = ['m1', 'w1', 'w2', 'w3']
    data = data.sort_values(by = ['cell_id', 'timed-tmstmp']).reset_index(drop = True)
    data['period'] = (((data['timed-tmstmp'] - data['timed-tmstmp'].shift(1)) > 5.0) | (data['cell_id'] != data['cell_id'].shift(1))).astype(int).cumsum()
    # calc avg <metric> per cell-period
    sel_period = data[['cell_id', 'period'] + nodes].groupby(['cell_id', 'period']).mean().reset_index(drop = False)

    if args['metric'] == 'rss':
        sel_period = sel_period.fillna(-100.0)
    else:
        sel_period = sel_period.fillna(0.0)

    # calculate selection plan, per cell period
    sel_period = sel_period.groupby(['cell_id']).apply(select_gps, method = 'cell-history', args = args)

    selection = pd.merge(data, sel_period[['period', 'best']], on = ['period'], how = 'left')
    # print(len(selection))
    # selection['timed-tmstmp-str'] = selection['timed-tmstmp'].astype(str)
    # print(selection[selection.duplicated(subset = ['timed-tmstmp'], keep = False)].sort_values(by = ['timed-tmstmp']))
    # sys.exit(0)
    selection = selection.drop_duplicates(subset = ['timed-tmstmp']).reset_index(drop = True)
    selection = selection.sort_values(by = ['timed-tmstmp']).reset_index(drop = True)
    selection[args['metric']] = 0.0
    for node in nodes:
        selection.loc[selection['best'] == node, args['metric']] = selection[selection['best'] == node][node]

    parsing.utils.to_hdf5(selection, cell_history_db, database)

def scripted_handoffs(input_dir, trace_nr,
    args,
    force_calc = False):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    sh_db = ('/selection/%s/gps/scripted-handoffs' % (args['metric']))
    if sh_db in database.keys():
        if force_calc:
            database.remove(sh_db)
        else:
            sys.stderr.write("""[INFO] %s already in database. skipping data extraction.\n""" % (sh_db))
            return

    # get lap timestamps
    laps = analysis.gps.get_lap_timestamps(input_dir, trace_nr)
    # get rss data from all nodes
    nodes = ['m1', 'w1', 'w2', 'w3']
    data = analysis.trace.merge_gps(input_dir, trace_nr, 'rss', cell_size = 20.0)
    data = data[['timed-tmstmp', 'lat', 'lon'] + nodes].sort_values(by = ['timed-tmstmp']).reset_index(drop = True)

    # add lap numbers to data
    data['lap'] = -1
    for l, row in laps.iterrows():
        data.loc[(data['lap'] == -1) & (data['timed-tmstmp'] <= row['timed-tmstmp']), 'lap'] = row['lap']
    data.loc[data['lap'] == -1, 'lap'] = len(laps)

    # algorithm:
    #   - objective : find the distance at which to handoff to a new ap, based on rss
    #   - the algorithm should be iterative, i.e. at lap i + 2, we should use history 
    #     from laps i and i + 1 to determine the handoff cell, at lap i + 3 from laps i, i + 1 and i + 2, etc.

    # calculate distances & direction of movement, relative to a reference point (located outside of the circuit)
    # FIXME : the ref_point should be given as argument
    ref_point = {'lat' : 41.178685, 'lon' : -8.597872}
    pos = [ [ row['lat'], row['lon'] ] for index, row in data[['lat', 'lon']].iterrows() ]
    data['ref-dist'] = [ mapping.utils.gps_to_dist(ref_point['lat'], ref_point['lon'], p[0], p[1]) for p in pos ]

    # calculate the direction of movement by looking at the change in ref-dist: 
    #   - 0 : east to west (ref-dist decreases) 
    #   - 1 : west to east (ref-dist increases) 
    data['direction'] = (data['ref-dist'] >= data['ref-dist'].shift(1)).astype(int)

    # to make things easier, treat ref distances in m precision
    # data['ref-dist'] = data['ref-dist'].apply(analysis.metrics.custom_round, prec = 1, base = .5)
    data['ref-dist'] = data['ref-dist'].apply(lambda x : round(x))

    # iteratively calculate the handoff scripts w/ the info available after each lap
    for l in xrange(2, len(laps) + 1):

        # # FIXME : don't count w/ 'w3' after lap 5
        # if l > 6:
        #     nodes = ['m1', 'w1', 'w2']

        # calc handoff script from laps [... , l - 2, l - 1]
        handoff_script = data[data['lap'] < l].sort_values(by = ['ref-dist', 'direction'])
        for node in nodes:
            handoff_script.loc[handoff_script[node] > -30.0, node] = np.nan

        handoff_script.dropna()

        for node in nodes:
            analysis.metrics.smoothen(handoff_script, column = node, span = 50)

        # find best ap of each row (max rss)
        handoff_script['best'] = handoff_script[nodes].idxmax(axis = 1)
        # determine handoff distances
        k = {1 : 1, 0 : -1}
        for d in k:
            # handoff distances depend on direction:
            #   - if E to W (ref-dist decreases): handoff is triggered at higher distance of an best
            #   - if W to E (ref-dist increases): handoff is triggered at lower distance of an best            
            hs = handoff_script[handoff_script['direction'] == d]
            hs['handoff'] = (hs['best'] != hs['best'].shift(k[d])).astype(int)
            hs = hs[hs['handoff'] == 1].reset_index(drop = True)
            print(hs[['direction', 'ref-dist', 'best']])

            # apply handoff script to current lap
            for i, h in hs.iterrows():
                if d == 1:
                    data.loc[(data['lap'] == l) & (data['ref-dist'] > h['ref-dist']), 'best'] = h['best']
                else:
                    data.loc[(data['lap'] == l) & (data['direction'] == d) & (data['ref-dist'] < h['ref-dist']), 'best'] = h['best']

    parsing.utils.to_hdf5(data, sh_db, database)
