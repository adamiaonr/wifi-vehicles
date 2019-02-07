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
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    db_name = ('/%s/%s/%s/%s/%s/%d' % ('selection', 'rss', method, args['scan-period'], args['scan-time'], int(args['bands'])))
    if db_name in database.keys():
        if force_calc:
            database.remove(db_name)
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
        if db not in database.keys():
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
    parsing.utils.to_hdf5(selection, db_name, database)
