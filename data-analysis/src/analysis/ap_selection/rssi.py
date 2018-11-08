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

def basic(input_dir, trace_nr,
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
        # FIXME: 0.5 intervals should not be hardcoded
        if (st < .5):
            st = .5

        data['scan-period'] = (((data.groupby(['ap-period'])['interval-tmstmp'].transform(lambda x : x.diff().cumsum()).fillna(0.0) / (st)).astype(int)) == 0).astype(int)

        # the 'best' mac according to 'wlan rssi': 
        #   - the highest rssi at the end of each ap-period
        #   - it remains for the rest of each scan-period
        data = data.groupby(['ap-period']).apply(_rssi, macs = macs)
        parsing.utils.to_hdf5(data, ('/%s/%s/%d/%d' % ('best-rssi', 'periodic', int(sp), int(st))), database)

    else:
        sys.stderr.write("""[ERROR] method %s not implemented yet. abort.\n""" % (method))
