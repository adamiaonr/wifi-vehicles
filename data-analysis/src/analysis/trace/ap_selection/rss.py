# analyze-trace.py : code to analyze custom wifi trace collections
# Copyright (C) 2018  adamiaonr@cmu.edu

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from __future__ import absolute_import

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
import multiprocessing as mp 
import hashlib
import datetime
import json
import geopandas as gp
import shapely.geometry

from random import randint
from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple
from prettytable import PrettyTable
from sklearn import linear_model

# custom imports
#   - hdfs utils
import utils.hdfs
#   - analysis

# north, south, west, east limits of map, in terms of geo coordinates
LATN = 41.176796
LATS = 41.179283
LONE = -8.593912
LONW = -8.598336
# gps coords for a 'central' pin on FEUP, Porto, Portugal
LAT  = (41.176796 + 41.179283) / 2.0
LON = (-8.598336 + -8.593912) / 2.0

# source : https://medium.com/@sean.turner026/applying-custom-functions-to-groupby-objects-in-pandas-61af58955569
def select_rss(data, aps, mode = 'strongest-rss'):

    if mode == 'strongest-rss':

        # # FIXME : don't consider 'w3' after lap 5
        # if (data.iloc[0]['lap'] > 6) and ('w3' in aps):
        #     aps.remove('w3')

        # highest rss among rows w/ ['scan period'] == 1
        ap = data[data['scan-period'] == 1][aps].max().idxmax(axis = 1)
        data['best'] = ap
        data['best-obs'] = data[data['scan-period'] == 1][aps].max()[ap]

    return data

def strongest_rss(input_dir, trace_nr,
    method = 'strongest-rss',
    args = {'scan-period' : 5.0, 'scan-time' : 0.5, 'bands' : 3},
    force_calc = False):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = utils.hdfs.get_db(trace_dir, 'database.hdf5')
    # database =     database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))
    database_keys = utils.hdfs.get_db_keys(trace_dir)

    db_name = ('/%s/%s/%s/%s/%s/%d' % ('selection', 'rss', method, args['scan-period'], args['scan-time'], int(args['bands'])))
    if db_name in database_keys:
        if force_calc:
            # database.remove(db_name)
            utils.hdfs.remove_dbs(trace_dir, [db_name])
        else:
            sys.stderr.write("""[INFO] %s already in database. skipping data extraction.\n""" % (db_name))
            return

    # merge all beacons from all aps
    nodes = {'m1' : {'band' : 2}, 'w1' : {'band' : 2}, 'w2' : {'band' : 1}, 'w3' : {'band' : 1}}
    aps = []
    rss_data = pd.DataFrame(columns = ['timed-tmstmp'])
    for node in nodes.keys():

        # bands code:
        #   1 : just 2.4 GHz
        #   2 : just 5 GHz
        #   3 : both 2.4 GHz and 5 GHz
        if (int(args['bands']) < 3) and (nodes[node]['band'] != int(args['bands'])):
            continue

        aps.append(node)

        db = ('/%s/%s/%s' % (node, 'basic', 'beacons'))
        if db not in database_keys:
            return None

        data = database.select(db)[['epoch time', 'wlan rssi']].sort_values(by = ['epoch time']).reset_index(drop = True)
        data['timed-tmstmp'] = data['epoch time'].apply(analysis.metrics.custom_round)
        # 'shrink' w/ max per 'timed-tmstmp'
        data = data[['timed-tmstmp', 'wlan rssi']].groupby(['timed-tmstmp']).max().reset_index(drop = False).sort_values(by = ['timed-tmstmp'])
        data[node] = data['wlan rssi']
        rss_data = pd.merge(rss_data, data[ ['timed-tmstmp', node] ], on = ['timed-tmstmp'], how = 'outer')

    # mark scan periods
    sp = args['scan-period']
    st = args['scan-time']
    rss_data['ap-period'] = ((rss_data['timed-tmstmp'] - rss_data.iloc[0]['timed-tmstmp']) / (sp + st)).astype(int)
    rss_data['scan-period'] = (((rss_data.groupby(['ap-period'])['timed-tmstmp'].transform(lambda x : x.diff().cumsum()).fillna(0.0) / (st)).astype(int)) == 0).astype(int)

    # add lap numbers
    laps = analysis.gps.get_lap_timestamps(input_dir, trace_nr)
    # add lap numbers to data
    rss_data['lap'] = -1
    for l, row in laps.iterrows():
        rss_data.loc[(rss_data['lap'] == -1) & (rss_data['timed-tmstmp'] <= row['timed-tmstmp']), 'lap'] = row['lap']
    rss_data.loc[rss_data['lap'] == -1, 'lap'] = len(laps)

    # now, groupby() scan period and pick the ap w/ max rss during a scan period
    selection = rss_data.groupby(['ap-period']).apply(select_rss, aps = aps, mode = 'strongest-rss')
    utils.hdfs.to_hdfs(selection, db_name, database)

def smoothed_hyteresis(input_dir, trace_nr,
    method = 'smoothed-hysteresis',
    args = {'w' : 5.0, 'hysteresis' : 5.0, 'bands' : 3},
    force_calc = False):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = utils.hdfs.get_db(trace_dir, 'database.hdf5')
    # database =     database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))
    database_keys = utils.hdfs.get_db_keys(trace_dir)

    db_name = ('/%s/%s/%s/%s/%s/%d' % ('selection', 'rss', method, args['w'], args['hysteresis'], int(args['bands'])))
    if db_name in database_keys:
        if force_calc:
            # database.remove(db_name)
            utils.hdfs.remove_dbs(trace_dir, [db_name])
        else:
            sys.stderr.write("""[INFO] %s already in database. skipping data extraction.\n""" % (db_name))
            return

    # merge all beacons from all aps
    nodes = {'m1' : {'band' : 2}, 'w1' : {'band' : 2}, 'w2' : {'band' : 1}, 'w3' : {'band' : 1}}
    aps = []
    rss_data = pd.DataFrame(columns = ['timed-tmstmp'])
    for node in nodes.keys():

        # bands code:
        #   1 : just 2.4 GHz
        #   2 : just 5 GHz
        #   3 : both 2.4 GHz and 5 GHz
        if (int(args['bands']) < 3) and (nodes[node]['band'] != int(args['bands'])):
            continue

        aps.append(node)

        db = ('/%s/%s/%s' % (node, 'basic', 'beacons'))
        if db not in database_keys:
            return None

        data = database.select(db)[['epoch time', 'wlan rssi']].sort_values(by = ['epoch time']).reset_index(drop = True)
        data['timed-tmstmp'] = data['epoch time'].apply(analysis.metrics.custom_round)
        # 'shrink' w/ max per 'timed-tmstmp'
        data = data[['timed-tmstmp', 'wlan rssi']].groupby(['timed-tmstmp']).max().reset_index(drop = False).sort_values(by = ['timed-tmstmp'])
        data[node] = data['wlan rssi']
        rss_data = pd.merge(rss_data, data[ ['timed-tmstmp', node] ], on = ['timed-tmstmp'], how = 'outer')

    # smoothen rss data
    cols = list(rss_data.columns)
    cols.remove('timed-tmstmp')
    rss_data[cols] = rss_data[cols].interpolate(limit = 3)
    rss_data[cols] = rss_data[cols].fillna(-80.0)
    # default 5 second window
    w = args['w']
    rss_data[cols] = rss_data[cols].rolling(int(w / 0.5)).mean()
    rss_data[cols] = rss_data[cols].astype(float)

    rss_data['best'] = rss_data[cols].idxmax(axis = 1)
    rss_data['best'] = rss_data['best'].fillna(-1)
    rss_data['best-obs'] = rss_data[cols].max(axis = 1)
    rss_data['best-obs'] = rss_data['best-obs'].fillna(-90.0)

    # apply smoothed rss + hysteresis algorithm:
    #   - assume a hysteresis of 5 dBm
    #   - compare rss[best] and rss[prev_best] mean of w / 0.5 previous samples
    #   - if smoothed_rss[prev_best] > (smoothed_rss[new_best] - 5), keep the current ap
    # FIXME : this iterative approach is very inefficient (and ugly to look at)
    j = 0
    prev_b = None

    for i in xrange(0, len(rss_data)):
        prev_b = rss_data['best'].loc[i]
        if prev_b > 0:
            break
        j += 1

    for i in xrange(j + 1, len(rss_data)):
        b = rss_data['best'].loc[i]
        if b < 0:
            continue

        # FIXME : this is a patch to solve some stupid error, 
        # which makes a pd.core.series.Series appear in the middle of 
        # a column of a DataFrame, which is otherwise filled w/ float...
        curr_rss = rss_data[b].loc[i]
        if isinstance(curr_rss, pd.core.series.Series):
            curr_rss = curr_rss.max()

        prev_rss = rss_data[prev_b].loc[i]

        if (prev_rss > (curr_rss - 5.0)) and (prev_rss > -80.0):
            rss_data.loc[i, 'best'] = prev_b
            rss_data.loc[i, 'best-obs'] = prev_rss
        elif (curr_rss > -80.0):
            prev_b = b
            rss_data.loc[i, 'best-obs'] = curr_rss
        else:
            rss_data.loc[i, 'best'] = -1

    rss_data = rss_data[rss_data['best'] != -1].reset_index(drop = True)
    utils.hdfs.to_hdfs(rss_data, db_name, database)

def ap_scores(input_dir, trace_nr,
    method = 'ap-scores',
    force_calc = False):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = utils.hdfs.get_db(trace_dir, 'database.hdf5')
    # database =     database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))
    database_keys = utils.hdfs.get_db_keys(trace_dir)

    sh_db = ''
    sh_thghpt_db = ''

    db_name = ('/%s/%s/%s/%s/%s/%d' % ('selection', 'rss', method, args['w'], args['hysteresis'], int(args['bands'])))
    if db_name in database_keys:
        if force_calc:
            # database.remove(db_name)
            utils.hdfs.remove_dbs(trace_dir, [db_name])
        else:
            sys.stderr.write("""[INFO] %s already in database. skipping data extraction.\n""" % (db_name))
            return

    # merge all beacons from all aps
    nodes = {'m1' : {'band' : 2}, 'w1' : {'band' : 2}, 'w2' : {'band' : 1}, 'w3' : {'band' : 1}}
    aps = []
    rss_data = pd.DataFrame(columns = ['timed-tmstmp'])
    for node in nodes.keys():

        # bands code:
        #   1 : just 2.4 GHz
        #   2 : just 5 GHz
        #   3 : both 2.4 GHz and 5 GHz
        if (int(args['bands']) < 3) and (nodes[node]['band'] != int(args['bands'])):
            continue

        aps.append(node)

        db = ('/%s/%s/%s' % (node, 'basic', 'beacons'))
        if db not in database_keys:
            return None

        data = database.select(db)[['epoch time', 'wlan rssi']].sort_values(by = ['epoch time']).reset_index(drop = True)
        data['timed-tmstmp'] = data['epoch time'].apply(analysis.metrics.custom_round)
        # 'shrink' w/ max per 'timed-tmstmp'
        data = data[['timed-tmstmp', 'wlan rssi']].groupby(['timed-tmstmp']).max().reset_index(drop = False).sort_values(by = ['timed-tmstmp'])
        data[node] = data['wlan rssi']
        rss_data = pd.merge(rss_data, data[ ['timed-tmstmp', node] ], on = ['timed-tmstmp'], how = 'outer')

    # smoothen rss data
    cols = list(rss_data.columns)
    cols.remove('timed-tmstmp')
    rss_data[cols] = rss_data[cols].interpolate(limit = 3)
    rss_data[cols] = rss_data[cols].fillna(-80.0)
    # default 5 second window
    w = 5.0
    rss_data[cols] = rss_data[cols].rolling((w / 0.5)).mean()
    rss_data[cols] = rss_data[cols].astype(float)

    rss_data['best'] = rss_data[cols].idxmax(axis = 1)
    rss_data['best'] = rss_data['best'].fillna(-1)
    rss_data['best-obs'] = rss_data[cols].max(axis = 1)
    rss_data['best-obs'] = rss_data['best-obs'].fillna(-90.0)

    # apply smoothed rss + hysteresis algorithm:
    #   - assume a hysteresis of 5 dBm
    #   - compare rss[best] and rss[prev_best] mean of w / 0.5 previous samples
    #   - if smoothed_rss[prev_best] > (smoothed_rss[new_best] - 5), keep the current ap
    # FIXME : this iterative approach is very inefficient (and ugly to look at)
    j = 0
    prev_b = None

    for i in xrange(0, len(rss_data)):
        prev_b = rss_data['best'].loc[i]
        if prev_b > 0:
            break
        j += 1

    for i in xrange(j + 1, len(rss_data)):
        b = rss_data['best'].loc[i]
        if b < 0:
            continue

        # FIXME : this is a patch to solve some stupid error, 
        # which makes a pd.core.series.Series appear in the middle of 
        # a column of a DataFrame, which is otherwise filled w/ float...
        curr_rss = rss_data[b].loc[i]
        if isinstance(curr_rss, pd.core.series.Series):
            curr_rss = curr_rss.max()

        prev_rss = rss_data[prev_b].loc[i]

        if (prev_rss > (curr_rss - 5.0)) and (prev_rss > -80.0):
            rss_data.loc[i, 'best'] = prev_b
            rss_data.loc[i, 'best-obs'] = prev_rss
        elif (curr_rss > -80.0):
            prev_b = b
            rss_data.loc[i, 'best-obs'] = curr_rss
        else:
            rss_data.loc[i, 'best'] = -1

    utils.hdfs.to_hdfs(rss_data, db_name, database)