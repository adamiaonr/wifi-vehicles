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

# CELL_SIZE = 20.0
CELL_SIZE = 500.0

# number of cells in grid, in x and y directions
X_CELL_NUM = int(np.ceil((mapping.utils.gps_to_dist(LATN, 0.0, LATS, 0.0) / CELL_SIZE)))
Y_CELL_NUM = int(np.ceil((mapping.utils.gps_to_dist(LAT, LONW, LAT, LONE) / CELL_SIZE)))

def get_list(input_dir):

    filename = os.path.join(input_dir, ("trace-info.csv"))
    if not os.path.isfile(filename):
        sys.stderr.write("""%s: [ERROR] no 'trace-info.csv' at %s\n""" % (sys.argv[0], input_dir))
        # return empty dataframe
        return pd.DataFrame()

    trace_list = pd.read_csv(filename)
    return trace_list

def get_info(input_dir, trace_nr, mode = 'rx'):

    trace_info = pd.DataFrame()

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database_file = os.path.join(trace_dir, "processed/database.hdf5")
    if not os.path.isfile(database_file):
        sys.stderr.write("""%s: [ERROR] no .hdf5 available at %s\n""" % (sys.argv[0], trace_dir))
        # return empty dataframe
        return trace_info

    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    database_name = ('/%s/%s' % ('dataset-stats', mode))
    if database_name not in database.keys():
        sys.stderr.write("""%s: [ERROR] no dataset stats available yet\n""" % (sys.argv[0]))
        # return empty dataframe
        return trace_info

    # load trace data into dataframe and return
    trace_info = database.select(database_name)
    return trace_info

def extract_rx_features(input_dir, trace_nr, 
    to_extract = ['wlan rssi', 'wlan data rate', 'pckt-loss', 'throughput'], 
    protocol = 'tcp',
    interval = 0.5,
    tag_laps = False,
    tag_gps = True):

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    ap = str(mac_addrs[mac_addrs['type'] == 'ap']['mac'].values[-1])
    clients = mac_addrs[mac_addrs['type'] == 'client']

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))
    # as a safeguard, if rx data already exists for the trace, abort rx data extraction
    for mac in list(clients['mac']):
        db_name = ('/%s/%s' % ('interval-data', mac))
        if db_name in database.keys():
            sys.stderr.write("""[ERROR] %s already in database. abort.\n""" % (db_name))
            return

    # get time series of gps positions, and lap timestamps
    gps_data, lap_tmstmps = analysis.gps.get_data(input_dir, trace_dir, tag_laps = tag_laps)
    # channel util. time series : a dict(), indexed by positions
    cbt_data = analysis.channel.get_data(trace_dir)

    # gather general info about trace dataset
    dataset_stats = pd.DataFrame(columns = ['mac', 'tcp', 'udp', 'tcp-gps', 'udp-gps'])

    # # wifi data
    # # 1) first extract 'tx-side' data, if available
    # extract_tx_features(input_dir, trace_nr, protocol, interval)

    # 2) extract 'rx-side' data, and use 'tx' data to calculate features (if available)
    for filename in sorted(glob.glob(os.path.join(trace_dir, 'mobile/monitor.*.csv'))):

        chunksize = 10 ** 5
        for chunk in pd.read_csv(filename, chunksize = chunksize):

            # don't consider data outside of laps
            if (tag_laps) and not ((chunk.iloc[0]['epoch time'] > lap_tmstmps['start'][0]) and (chunk.iloc[-1]['epoch time'] < lap_tmstmps['start'][-1])):
                continue

            # merge channel util. data on 'timestamp'
            chunk['timestamp'] = chunk['epoch time'].astype(int)
            chunk = pd.merge(chunk, cbt_data['pos1'][['timestamp', 'channel-util']], on = ['timestamp'], how = 'left')

            # extract rx data per client
            for mac in list(clients['mac']):

                # filter wlan frames exchanged from mac to ap, w/ the correct ip proto field
                client_data = chunk[ (chunk['wlan src addr'] == mac) & (chunk['wlan dst addr'] == ap) & (chunk['ip proto'] == protocol.upper()) ].reset_index(drop = True)
                if client_data.empty:
                    continue

                # create a 'interval-tmstmp' for each interval over which metrics are considered
                client_data['interval-tmstmp'] = client_data['epoch time'].apply(analysis.metrics.custom_round)

                # client 'rx' data, per interval
                rx_data = client_data[['interval-tmstmp', 'timestamp', 'channel-util']].drop_duplicates(subset = ['interval-tmstmp'])

                # dataset stats are collected per mac
                dataset_data = {'mac' : mac, 'tcp' : 0.0, 'udp' : 0.0, 'tcp-gps' : 0.0, 'udp-gps' : 0.0}
                # collect dataset stats (protocol column)
                dataset_data[protocol.upper()] = len(client_data)

                # collect 'rx-side' wlan frame stats
                # FIXME: this still requires review...
                seq_number_stats = analysis.metrics.calc_wlan_frame_stats(client_data, intervals = [interval], mode = 'rx')
                parsing.utils.to_hdf5(seq_number_stats[interval], ('/%s/%s/%s/%s' % ('seq-numbers', mac, interval, 'rx')), database)

                # add one column per metric to extract
                for metric in to_extract:

                    # columns of proc_data to add to the final .hdf5 database
                    to_add = ['interval-tmstmp', metric]

                    # metrics require processing per interval
                    proc_data = None
                    if metric != 'pckt-loss':
                        proc_data = analysis.metrics.process_metric(client_data, metric, interval = interval)

                    else:

                        # pckt-loss can be a tricky metric to extract...

                        # primary way of calculating pckt-loss
                        proc_data = seq_number_stats[interval][ ['interval-tmstmp', 'snt', 'rcvd', 'lost'] ]
                        proc_data[metric] = ((proc_data['lost'].astype(float) / proc_data['snt'].astype(float)) * 100.0).astype(int)

                        # # if 'tx-side' data is available, calculate alternative pckt-loss metric
                        # if ('/%s/%s/%s/%s' % ('seq-numbers', mac, interval, 'tx')) in database.keys():
                            
                        #     # extract wlan frame data for 'tx-side'
                        #     snt = database.select(('/%s/%s/%s/%s' % ('seq-numbers', mac, interval, 'tx')))[['time', 'snt']]
                        #     # merge w/ 'rx-side' data, 'rcvd' column, according to 'time'
                        #     snt = pd.merge(proc_data[['time', 'rcvd']], snt[['time', 'snt']], on = ['time'], how = 'inner')
                        #     # calculate alternative pckt-loss as ((# sent) - (# rcvd)) / (# sent)
                        #     proc_data[('%s-alt' % (metric))] = (((snt['snt'] - snt['rcvd']) / snt['snt']) * 100.0).astype(int)

                        #     to_add.append(('%s-alt' % (metric)))

                    # merge the new metric column into rx_data
                    rx_data = pd.merge(rx_data, proc_data[to_add], on = ['interval-tmstmp'], how = 'left')
                    # merge channel util. data 

                # save rx data in .hdf5 database
                # if a gps tagged data is required, merge the client data w/ gps data
                if tag_gps:
                    rx_data = pd.merge(rx_data, gps_data[['timestamp', 'lat', 'lon', 'lap-number', 'direction']], on = ['timestamp'], how = 'left')
                    dataset_data[('%s-gps' % (protocol))] = len(rx_data['lat'].dropna())

                # rx_data['interval-tmstmp-str'] = [ str(tmstmp) for tmstmp in rx_data['interval-tmstmp'] ]
                # print(rx_data)

                parsing.utils.to_hdf5(rx_data, ('/%s/%s' % ('interval-data', mac)), database)
                
                # update dataset stats
                dataset_stats = dataset_stats.append(dataset_data, ignore_index = True)
                dataset_stats = dataset_stats.groupby(['mac']).sum().reset_index()

    # save dataset stats on database
    parsing.utils.to_hdf5(dataset_stats, ('/%s/%s' % ('dataset-stats', 'rx')), database)

def calc_best(input_dir, trace_nr, metric = 'throughput'):

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    # as a safeguard, if best period data already exists for the trace, abort
    db_name = ('/%s/%s' % ('best', metric))
    if db_name in database.keys():
        sys.stderr.write("""[INFO] %s already in database\n""" % (db_name))
        return

    best = pd.DataFrame(columns = ['interval-tmstmp'])

    if metric == 'dist':

        # get dist. data from each fixed client
        dist_data = analysis.trace.get_distances(input_dir, trace_nr)
        # oversampling of timestamps (1 sec) into intervals (.5 sec)
        best['interval-tmstmp'] = [ (float(ts)) for ts in dist_data['timestamp'] ] + [ (float(ts) + 0.5) for ts in dist_data['timestamp'] ]
        best = best.sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
        # keep a 'timestamp' column for merging
        best['timestamp'] = best['interval-tmstmp'].astype(int)
        best = pd.merge(best, dist_data, on = ['timestamp'], how = 'right')

        # calculate the mac w/ min. value at each row
        best['best'] = best[ [col for col in dist_data.columns if col not in {'timestamp'}] ].idxmin(axis = 1)

    else:

        macs = []
        for mac in list(clients['mac']):

            db_name = ('/%s/%s' % ('interval-data', mac))
            if db_name not in database.keys():
                continue

            # load data for a client mac
            data = database.select(db_name)
            if data.empty:
                continue

            data[mac] = data[metric]
            macs.append(mac)
            # update best w/ mac info
            # FIXME: is the use of 'outer' merge correct here?
            best = pd.merge(best, data[ ['interval-tmstmp', mac] ], on = ['interval-tmstmp'], how = 'outer')

        # calculate the mac w/ max. value at each row
        best['best'] = best[macs].idxmax(axis = 1)

    parsing.utils.to_hdf5(best, ('/%s/%s' % ('best', metric)), database)

def get_distances(input_dir, trace_nr):

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']

    # save data on .hdf5 database
    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    db_name = ('/%s' % ('dist-data'))
    if db_name in database.keys():
        sys.stderr.write("""[INFO] %s already in database\n""" % (db_name))
        return database.select(db_name).sort_values(by = ['timestamp'])

    else:
        sys.stderr.write("""[INFO] %s not in database. extracting.\n""" % (db_name))

        # extract gps positions of mobile node
        gps_data, lap_tmstmps = analysis.gps.get_data(trace_dir, tag_laps = False)
        mobile_pos = [ [ row['lat'], row['lon'] ] for index, row in gps_data.iterrows() ]
        # dist. data
        dist_data = gps_data[['timestamp']]
        for i, client in clients.iterrows():
            dist_data[client['mac']] = [ mapping.utils.gps_to_dist(client['lat'], client['lon'], pos[0], pos[1]) for pos in mobile_pos ]

        # save in .hdf5 file
        parsing.utils.to_hdf5(dist_data, ('/%s' % ('dist-data')), database)
        return dist_data

def fix_gaps(data, subset):

    # FIXME : still don't know how to do this without copying...
    _data = data[['interval-tmstmp'] + subset]
    _data['datetime'] = pd.to_datetime(_data['interval-tmstmp'], unit = 's')
    _data.set_index(['datetime'], inplace = True)
    _data.interpolate(method = 'time', inplace = True)
    # update subset
    data.update(_data[subset].reset_index(drop = True))

def extract_moving_data(gps_data):

    # find the interval-tmstmps of the first and last rows w/ gps positions
    ix = gps_data.dropna(subset = ['lat', 'lon'], how = 'all').iloc[[0,-1]].index.tolist()
    return gps_data.iloc[ix[0]:ix[-1]].sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
