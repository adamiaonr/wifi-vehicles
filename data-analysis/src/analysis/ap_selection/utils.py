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

def extract_performance(
    input_dir, trace_nr,
    db_selection,
    metric = 'throughput',
    force_calc = False):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    perf_db = ('/selection-performance/%s/%s' % (metric, db_selection.replace('/selection/', '')))
    if perf_db in database.keys():
        if force_calc:
            database.remove(perf_db)
        else:
            sys.stderr.write("""[INFO] %s already in database. skipping data extraction.\n""" % (perf_db))
            return

    if db_selection not in database.keys():
        sys.stderr.write("""[ERROR] %s not in database. abort.\n""" % (db_selection))
        return

    # extract selection data
    sel_data = database.select(db_selection).sort_values(by = ['timed-tmstmp']).reset_index(drop = True)
    # sel_data['timed-tmstmp-str'] = sel_data['timed-tmstmp'].astype(str)

    # calculate selection performance data
    sel_perf = pd.DataFrame()
    nodes = ['m1', 'w1', 'w2', 'w3']
    base_db = analysis.trace.extract_best(input_dir, trace_nr, metric)
    perf_data = database.select(base_db)[['timed-tmstmp'] + nodes].sort_values(by = ['timed-tmstmp']).reset_index(drop = True)
    for node in nodes:

        # filter selection data by node
        sd = sel_data[sel_data['best'] == node]
        if sd.empty:
            continue
        # get performance data for node
        perfd = perf_data[['timed-tmstmp', node]]
        perfd[metric] = perfd[node]
        if perfd.empty:
            continue

        # merge perf metric data w/ the selection plan
        sp = pd.merge(sd, perfd[ ['timed-tmstmp', metric] ], on = ['timed-tmstmp'], how = 'left')
        # concat in total selection performance df
        sel_perf = pd.concat([sel_perf, sp], ignore_index = True)

    sel_perf = sel_perf.sort_values(by = ['timed-tmstmp']).reset_index(drop = True)
    sel_perf[metric] = sel_perf[metric].fillna(0.0)
    parsing.utils.to_hdf5(sel_perf, ('/selection-performance/%s/%s' % (metric, db_selection.replace('/selection/', ''))), database)
