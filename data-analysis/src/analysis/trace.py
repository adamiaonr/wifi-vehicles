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

ref = {'lat' : 41.178685, 'lon' : -8.597872}

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
    macs = []
    for i, client in clients.iterrows():

        db_name = ('/%s/%s' % ('interval-data', client['mac']))
        if db_name not in database.keys():
            continue

        # load data for a client mac
        data = database.select(db_name)
        if data.empty:
            continue

        macs.append(client['mac'])

        if metric == 'dist':

            # fix timestamp gaps
            data.loc[np.isnan(data['timestamp']), 'timestamp'] = data[np.isnan(data['timestamp'])]['interval-tmstmp'].astype(int)
            # fix lat and lon gaps
            data = data.sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
            analysis.trace.fix_gaps(data, subset = ['lat', 'lon'])
            # finally, calc distance to mac addr.
            pos = [ [ row['lat'], row['lon'] ] for index, row in data[['lat', 'lon']].iterrows() ]
            data[client['mac']] = [ mapping.utils.gps_to_dist(client['lat'], client['lon'], p[0], p[1]) for p in pos ]

        else:
            data[client['mac']] = data[metric]

        # update best w/ mac info
        # FIXME: is the use of 'outer' merge correct here?
        best = pd.merge(best, data[ ['interval-tmstmp', client['mac']] ], on = ['interval-tmstmp'], how = 'outer')

    best = best.sort_values(by = ['interval-tmstmp']).reset_index(drop = True)

    # calculate the mac w/ max. value at each row
    if metric == 'dist':
        best['best'] = best[macs].idxmin(axis = 1)

        dist_db_name = ('/%s' % ('dist-data'))
        if dist_db_name not in database.keys():
            parsing.utils.to_hdf5(best, ('/%s' % ('dist-data')), database)

    else:
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
    if db_name not in database.keys():
        sys.stderr.write("""[INFO] %s not in database. aborting.\n""" % (db_name))
        return

    return database.select(db_name).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)

def fix_gaps(data, subset, column = 'interval-tmstmp'):
    # FIXME : still don't know how to do this without copying, hence the variable '_data'
    _data = data[[column] + subset]
    # use pandas native time-based interpolation, which requires a datetime index
    # FIXME : the type of interpolation should be defined as a parameter later on
    _data['datetime'] = pd.to_datetime(_data[column], unit = 's')
    _data.set_index(['datetime'], inplace = True)
    _data.interpolate(method = 'time', inplace = True)
    # update subset columns w/ the interpolated values
    data.update(_data[subset].reset_index(drop = True))

def extract_moving_data(gps_data, method = 'dropna'):

    if method == 'dropna':
        # find the interval-tmstmps of the first and last rows w/ gps positions
        ix = gps_data.dropna(subset = ['lat', 'lon'], how = 'all').iloc[[0,-1]].index.tolist()
        return gps_data.iloc[ix[0]:ix[-1]].sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
    elif method == 'lap-number':
        return gps_data[(gps_data['lap-number'] >= 1) & (gps_data['lap-number'] <= 5)].sort_values(by = ['interval-tmstmp']).reset_index(drop = True)

def get_combination_key(traces):

    # FIXME: there must be a better way of doing this...
    combination_key = pd.DataFrame(columns = ['new-its', 'interval-tmstmp', 'trace-nr'])

    # FIXME: hardcoded arrays are bad, and you should feel bad...
    prev_its = 0.0
    for lap in [1.0, 2.0, 3.0, 4.0 , 5.0]:
        for direction in [1.0, -1.0]:

            _traces = []
            for trace in traces:
                _trace = trace[(trace['lap-number'] == lap) & (trace['direction'] == direction)]

                _trace.sort_values(by = ['ref-dist', 'interval-tmstmp'], ascending = [not bool(direction + 1), True], inplace = True)
                # crude way of getting rid of mono
                _trace['diff'] = _trace['interval-tmstmp'].shift(1) - _trace['interval-tmstmp']
                while (np.amax(_trace['diff']) > 0.0):
                    _trace = _trace[_trace['diff'] <= 0.0]
                    _trace['diff'] = _trace['interval-tmstmp'].shift(1) - _trace['interval-tmstmp']

                _traces.append(_trace)

            new_trace = pd.concat(_traces, ignore_index = True)
            new_trace.sort_values(by = ['ref-dist', 'interval-tmstmp'], ascending = [not bool(direction + 1), True], inplace = True)
            new_trace['new-its'] = new_trace['interval-tmstmp'] - new_trace.iloc[0]['interval-tmstmp']
            new_trace['diff-dist-cumsum'] = np.abs(new_trace['ref-dist'].shift(1) - new_trace['ref-dist']).cumsum().fillna(0.0)
            # set abnormally high 'new-its' to nan
            new_trace.loc[np.abs(new_trace['new-its']) > 500.0, 'new-its'] = None
            new_trace = new_trace.reset_index(drop = True)
            analysis.trace.fix_gaps(new_trace, subset = ['new-its'], column = 'diff-dist-cumsum')
            # finally, round the 'elapsed' column to .5 sec
            new_trace['new-its'] = new_trace['new-its'].apply(analysis.metrics.custom_round) + prev_its

            combination_key = pd.concat([combination_key, new_trace[['new-its', 'interval-tmstmp', 'trace-nr', 'lap-number', 'direction']]], ignore_index = True)
            prev_its = combination_key.iloc[-1]['new-its']

    return combination_key

def generate_new(input_dir, to_combine, new_trace_nr, replace = {}):

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']
    # get trace info
    trace_list = analysis.trace.get_list(input_dir)

    # generate combination key
    traces = []
    for trace_nr in to_combine:

        trace_data = pd.DataFrame()

        trace = trace_list[trace_list['trace-nr'] == int(trace_nr)]
        trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
        database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))
        # FIXME : this is just here to get lap timestamps...
        gps_data, lap_timestamps = analysis.gps.get_data(input_dir, trace_dir, tag_laps = False)

        # gather all the timestamps and ['lat', 'lon'] pairs from trace
        for i, client in clients.iterrows():

            db_name = ('/%s/%s' % ('interval-data', client['mac']))
            if db_name not in database.keys():
                continue

            # load data for a client mac
            data = database.select(db_name)
            if data.empty:
                continue

            # fix 'nan' gaps in ['lat', 'lon'] by time interpolation
            # note : sort data by 'interval-tmstmp' first
            data = data.sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
            analysis.trace.fix_gaps(data, subset = ['lat', 'lon'])
            trace_data = pd.concat([trace_data, data[['interval-tmstmp', 'lat', 'lon']]], ignore_index = True)

        # drop 'nan' lat lon pairs
        trace_data.dropna(subset = ['lat', 'lon'], how = 'all', inplace = True)
        # drop duplicates
        trace_data.drop_duplicates(subset = ['interval-tmstmp', 'lat', 'lon'], inplace = True)
        trace_data = trace_data.sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
        # find distance to a ref position, outside of the experimental circuit
        pos = [ [ row['lat'], row['lon'] ] for index, row in trace_data[['lat', 'lon']].iterrows() ]
        trace_data['ref-dist'] = [ mapping.utils.gps_to_dist(ref['lat'], ref['lon'], p[0], p[1]) for p in pos ]
        # add lap numbers & direction
        trace_data['timestamp'] = trace_data['interval-tmstmp'].astype(int)
        analysis.gps.add_lap_numbers(trace_data, lap_timestamps)
        # keep movement data only
        trace_data = analysis.trace.extract_moving_data(trace_data, method = 'lap-number')
        trace_data['trace-nr'] = int(trace_nr)

        traces.append(trace_data[['interval-tmstmp', 'trace-nr', 'ref-dist', 'lap-number', 'direction']])

    # get the combination key
    combination_key = get_combination_key(traces)

    # use the combination key to save the new trace data
    # new trace directories & files
    new_trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(new_trace_nr))))
    if not os.path.isdir(os.path.join(new_trace_dir, 'processed')):
        os.makedirs(os.path.join(new_trace_dir, 'processed'))

    new_database = pd.HDFStore(os.path.join(new_trace_dir, "processed/database.hdf5"))

    for trace_nr in to_combine:
        trace = trace_list[trace_list['trace-nr'] == int(trace_nr)]
        trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
        database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

        # filter combination key for this trace
        ck = combination_key[combination_key['trace-nr'] == int(trace_nr)]

        for i, client in clients.iterrows():

            db_name = ('/%s/%s' % ('interval-data', client['mac']))
            if db_name not in database.keys():
                continue

            # load data for a client mac
            data = database.select(db_name)
            if data.empty:
                continue

            # check if mac requires a replacement
            if client['mac'] in replace[trace_nr]:
                client['mac'] = replace[trace_nr][client['mac']]

            # fix 'nan' gaps in ['lat', 'lon'] by time interpolation
            # note : sort data by 'interval-tmstmp' first
            data = data.sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
            analysis.trace.fix_gaps(data, subset = ['lat', 'lon'])
            # drop 'nan' lat lon pairs
            data.dropna(subset = ['lat', 'lon'], how = 'all', inplace = True)
            # drop the lap-number and direction columns (will be added on merge)
            data.drop(['lap-number', 'direction'], axis = 1, inplace = True)

            # merge data w/ combination key for the trace
            data = pd.merge(data, ck[['interval-tmstmp', 'new-its', 'lap-number', 'direction']], on = ['interval-tmstmp'], how = 'inner')
            # change the 'interval-tmstmp' index
            data['interval-tmstmp'] = data['new-its']
            parsing.utils.to_hdf5(data, ('/%s/%s' % ('interval-data', client['mac'])), new_database)
