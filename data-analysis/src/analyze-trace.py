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
import plot.utils
import parsing.utils
import analysis.metrics
import shapely.geometry

from random import randint

from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple

from prettytable import PrettyTable

from sklearn import linear_model

# gps coords for a 'central' pin on FEUP, portugal
LAT  = (41.176796 + 41.179283) / 2.0
LON = (-8.598336 + -8.593912) / 2.0
# north, south, west, east limits of map, in terms of geo coordinates
LATN = 41.176796
LATS = 41.179283
LONE = -8.593912
LONW = -8.598336

CELL_SIZE = 20.0

# number of cells in grid, in x and y directions
X_CELL_NUM = int(np.ceil((mapping.utils.gps_to_dist(LATN, 0.0, LATS, 0.0) / CELL_SIZE)))
Y_CELL_NUM = int(np.ceil((mapping.utils.gps_to_dist(LAT, LONW, LAT, LONE) / CELL_SIZE)))

# mac address of mobile ap
ap = '24:05:0f:61:51:14'
# mac addresses of clients (side-of-the-road)
clients = OrderedDict()
# clients['24:05:0f:9e:2c:b1'] = {'id' : 2, 'label' : 'pos. 0', 'color' : 'blue',     'lat' : 41.178456, 'lon' : -8.594501, 'ip' : '10.10.10.56'}
clients['24:05:0f:e5:7b:6a'] = {'id' : 2, 'label' : 'pos. 2', 'color' : 'blue',     'lat' : 41.178456, 'lon' : -8.594501, 'ip' : '10.10.10.56'}
clients['fc:ec:da:1b:63:a6'] = {'id' : 1, 'label' : 'pos. 1', 'color' : 'red',      'lat' : 41.178518, 'lon' : -8.595366, 'ip' : '10.10.10.53'}
clients['fc:ec:da:1a:63:a6'] = {'id' : 1, 'label' : 'pos. 1', 'color' : 'red',      'lat' : 41.178518, 'lon' : -8.595366, 'ip' : '10.10.10.140'}
# clients['24:05:0f:6d:ae:36'] = {'id' : 0, 'label' : 'pos. 0', 'color' : 'green',    'lat' : 41.178563, 'lon' : -8.596012, 'ip' : '10.10.10.113'}
clients['78:8a:20:58:1f:6b'] = {'id' : 0, 'label' : 'pos. 0', 'color' : 'green',    'lat' : 41.178563, 'lon' : -8.596012, 'ip' : '10.10.10.170'}
clients['78:8a:20:58:1f:73'] = {'id' : 3, 'label' : 'pos. 3', 'color' : 'magenta',  'lat' : 41.178518, 'lon' : -8.595366, 'ip' : '10.10.10.178'}

# peer names 
peers = {
    'mobile' : {'color' : 'black'}, 
    'pos3'   : {'color' : 'magenta',    'lat' : 41.178518, 'lon' : -8.595366},
    'pos2'   : {'color' : 'green',      'lat' : 41.178456, 'lon' : -8.594501}, 
    'pos1'   : {'color' : 'red',        'lat' : 41.178518, 'lon' : -8.595366, 'macs' : ['78:8a:20:58:1f:73', 'fc:ec:da:1b:63:a6', 'fc:ec:da:1b:63:a6']}, 
    'pos0'   : {'color' : 'blue',       'lat' : 41.178563, 'lon' : -8.596012, 'macs' : ['78:8a:20:58:1f:6b']}
}

def to_hdf5(
    data, 
    metric, 
    link_data):

    link_data.append(
        ('%s' % (metric)),
        data,
        data_columns = data.columns,
        format = 'table')

def process_metric(data, metric, interval = 1.0):

    proc_data = None
    if metric == 'throughput':
            
        # throughput calculated based on wlan frame length
        proc_data = data[['epoch time', 'frame len']]
        # special index to be later used for time intervals
        # proc_data['time'] = ((proc_data['epoch time'] * (1.0 / interval)).astype(int) / (1.0 / interval)).astype(float)
        proc_data['time'] = proc_data['epoch time'].apply(analysis.metrics.myround)
        # groupby() 'time' (interval), and sum size of frames, in byte
        proc_data = proc_data[['time', 'frame len']].groupby(['time']).sum().reset_index().sort_values(by = ['time'])
        proc_data['throughput'] = (proc_data['frame len'] * 8.0) / interval

    elif metric == 'wlan data rate':

        proc_data = data[['epoch time', 'wlan data rate']]
        # proc_data['time'] = ((proc_data['epoch time'] * (1.0 / interval)).astype(int) / (1.0 / interval)).astype(float)
        proc_data['time'] = proc_data['epoch time'].apply(analysis.metrics.myround)
        # groupby() 'time' (interval), and get mean wlan data rate over the interval
        proc_data = proc_data[['time', 'wlan data rate']].groupby(['time']).mean().reset_index().sort_values(by = ['time'])
        # multiply by 1M for bps
        proc_data['wlan data rate'] = proc_data['wlan data rate'] * 1000000.0

    elif metric == 'wlan rssi':

        proc_data = data[['epoch time', 'wlan rssi']]
        # proc_data['time'] = ((proc_data['epoch time'] * (1.0 / interval)).astype(int) / (1.0 / interval)).astype(float)
        proc_data['time'] = proc_data['epoch time'].apply(analysis.metrics.myround)
        # groupby() 'time' (interval), and get mean rssi over the interval
        proc_data = proc_data[['time', 'wlan rssi']].groupby(['time']).mean().reset_index().sort_values(by = ['time'])
        proc_data['wlan rssi'] = proc_data['wlan rssi'].astype(float)

    # elif metric == 'pckt-loss':
    #     # special analysis for packet loss
    #     proc_data = analysis.metrics.calc_pckt_loss_2(data, interval = interval)

    return proc_data

def plot_cell_features(ax, data, metric, x_range, y_range, span = True):

    metric_labels = {
        'wlan rssi' : 'rssi (dBm)', 
        'pckt-loss' : 'packet loss (%)', 
        'wlan data rate' : 'wlan data rate (Mbps)',
        'channel-util' : 'channel util. (%)'
        }

    ax.xaxis.grid(True, ls = 'dotted', lw = 0.75)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.75)

    # sort data according to metric
    data.sort_values(by = [metric])
    # plot w/ different markers, according to the direction of movement
    directions = {1 : {'color' : 'red', 'marker' : 'o', 'label' : 'W to E'}, -1 : {'color' : 'blue', 'marker' : '^', 'label' : 'E to W'}}
    for direction in directions:
        
        _data = data[data['direction'] == direction]
        if _data.empty:
            continue

        if metric == 'wlan data rate':
            _data[metric] = _data[metric] / 1000000.0

        ax.plot(_data[metric], _data['throughput'] / 1000000.0, 
            alpha = 0.75, linewidth = 0.0, color = directions[direction]['color'], label = directions[direction]['label'], linestyle = '-',
            markersize = 2.0, marker = directions[direction]['marker'])

        # draw a vertical span for the mean rss & std dev
        if span:
            mean = _data[metric].mean()
            std_dev = _data[metric].std()
            ax.axvspan(mean - std_dev, mean + std_dev, linewidth = 0.0, facecolor = directions[direction]['color'], alpha = 0.20)
            ax.axvline(x = mean, color = directions[direction]['color'], linestyle = '--', linewidth = .75)

    # # draw a vertical line for the interference mean
    # ax.axvline(x = data['interference-mean'].iloc[0] + rssi_mean, color = 'red', linestyle = '--', linewidth = .75)

    ax.set_xlabel(("%s" % (metric_labels[metric])))
    ax.set_ylabel("throughput (Mbps)")

    ax.set_xlim(x_range)
    ax.set_ylim(y_range)

    ax.legend(fontsize = 12, ncol = 1, loc = 'upper left',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

def plot_client_features(data, trace_output_dir,
    mac,
    to_predict = 'throughput',
    features = ['wlan rssi', 'pckt-loss', 'wlan data rate', 'channel-util']):

    # group data by cell id (x,y)
    grouped = data.groupby(['cell-x', 'cell-y'])

    # only plot cells w/ > 10 data points
    to_plot = []
    for name, group in grouped:
        if len(group) >= 20:
            to_plot.append(name)

    # nr. of cells
    num_cells = len(to_plot)
    # we plot <feature> vs. throughput for relevant cells (w/ 20 or more data points)
    fig = plt.figure(figsize = ((5.0 * len(features)) * 1.0, 2.5 * num_cells))
    outer = gridspec.GridSpec(num_cells, 1, wspace = 0.15, hspace = 0.6)

    # add title w/ mac addr and cell where mac addr is located
    mac_cell = (int((clients[mac]['lon'] - LONW) / (LONE - LONW) * X_CELL_NUM), int((clients[mac]['lat'] - LATS) / (LATN - LATS) * Y_CELL_NUM))
    fig.suptitle(('fixed client %s @cell%s' % (mac, mac_cell)))

    x_range = defaultdict(list)
    x_range['wlan rssi'] = [np.amin(data['wlan rssi'] - 2.5), np.amax(data['wlan rssi'] + 2.5)]
    x_range['pckt-loss'] = [-5, 100.0]
    x_range['channel-util'] = [-5, 100.0]
    x_range['wlan data rate'] = [(np.amin(data['wlan data rate']) / 1000000.0) - 10, (np.amax(data['wlan data rate'])  / 1000000.0) + 10]

    y_range = [(np.amin(data[to_predict]) / 1000000.0), (np.amax(data[to_predict]) / 1000000.0) + 10]

    # get min value per cell id 
    i = 0

    for name, group in grouped:

        if name not in to_plot:
            continue

        # inner subplot : 1 row x len(features) columns
        inner = gridspec.GridSpecFromSubplotSpec(1, len(features), subplot_spec = outer[i], wspace = 0.2, hspace = 0.1)

        # ax.set_title("%s" % (cell_id))
        for j, metric in enumerate(features):
            # add subplot
            ax = plt.Subplot(fig, inner[j])
            plot_cell_features(ax, group, metric, x_range = x_range[metric], y_range = y_range, span = False)
            ax.set_title(('cell: %s, feat.: %s' % (name, metric)))
            fig.add_subplot(ax)

        i = i + 1

    # save plot for rssi vs. pck-loss
    plt.tight_layout()
    # plt.subplots_adjust(top = 0.80)
    plt.savefig(os.path.join(trace_output_dir, ("cell-features.pdf")), bbox_inches = 'tight', format = 'pdf')

def plot_features(
    input_dir, trace_nr, output_dir,
    to_predict = 'throughput',
    features = ['wlan rssi', 'wlan data rate', 'pckt-loss', 'channel-util']):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    for mac in clients:

        if ('/%s/%s' % ('cell-data', mac)) not in database.keys():
            continue

        # load data for a client mac
        data = database.select(('/%s/%s' % ('cell-data', mac)))

        if (set(features).intersection(set(data.columns)) != set(features)):
            continue

        print("nr. of data points for mac %s : %s" % (mac, len(data)))

        # add cell ids to each measurement
        data['cell-x'] = data['lon'].apply(lambda x : int((x - LONW) / (LONE - LONW) * X_CELL_NUM))
        data['cell-y'] = data['lat'].apply(lambda y : int((y - LATS) / (LATN - LATS) * Y_CELL_NUM))

        # create output dir for trace (if not existent)
        trace_output_dir = os.path.join(output_dir, ("trace-%03d/%s" % (int(trace_nr), mac)))
        if not os.path.isdir(trace_output_dir):
            os.makedirs(trace_output_dir)

        # plot features of the data per cell id
        plot_client_features(data, trace_output_dir, mac, to_predict, features)

def plot_model(
    ax, 
    data, 
    direction,
    model, to_predict, features):

    ax.xaxis.grid(True, ls = 'dotted', lw = 0.75)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.75)

    # sort data according to time
    data.sort_values(by = ['time'])

    # plot the ground truth
    ax.plot(xrange(len(data['time'])), data[to_predict] / 1000000.0, 
        alpha = 0.75, linewidth = 0.0, color = 'black', label = 'obs.', linestyle = '-',
        markersize = 2.0, marker = 'o')

    # plot w/ different markers, according to the direction of movement
    directions = {
        1 : {'color' : 'seagreen', 'marker' : '^', 'label' : 'pred.'}, 
        -1 : {'color' : 'dodgerblue', 'marker' : '^', 'label' : 'pred.'}}

    ax.plot(xrange(len(data['time'])), model.predict(data[features]) / 1000000.0, 
        alpha = 0.75, linewidth = 0.0, color = directions[direction]['color'], label = directions[direction]['label'], linestyle = '-',
        markersize = 2.0, marker = directions[direction]['marker'])

    # ax.set_xlabel("data point")
    ax.set_ylabel(("%s (Mbps)" % (to_predict)))

    ax.set_ylim([0.0, 15.0])

    ax.legend(fontsize = 12, ncol = 1, loc = 'upper left',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

def predict_linear_reg(data, to_predict, features):
    reg = linear_model.LinearRegression()
    return reg.fit(data[features], data[to_predict])

def predict(
    input_dir, trace_nr, output_dir,
    method = 'linear-regression',
    to_predict = 'throughput',
    features = ['wlan rssi', 'pckt-loss', 'wlan data rate']):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    for mac in clients:

        # load data for a client mac
        data = database.select(('/%s/%s' % ('cell-data', mac)))

        if (set(features).intersection(set(data.columns)) != set(features)):
            continue

        # add cell ids to each measurement
        data['cell-x'] = data['lon'].apply(lambda x : int((x - LONW) / (LONE - LONW) * X_CELL_NUM))
        data['cell-y'] = data['lat'].apply(lambda y : int((y - LATS) / (LATN - LATS) * Y_CELL_NUM))

        # create output dir for trace (if not existent)
        trace_output_dir = os.path.join(output_dir, ("trace-%03d/%s" % (int(trace_nr), mac)))
        if not os.path.isdir(trace_output_dir):
            os.makedirs(trace_output_dir)

        # group data by cell id (x,y)
        grouped = data.groupby(['cell-x', 'cell-y'])
        # nr. of cells
        # num_cells = len(grouped)
        cells_to_plot = { 
            (14,11) : [(13,10), (13,11), (14,10), (14,11), (15,10), (15,11)],
            (18,11) : [(17,11), (17,12), (18,11), (18,12), (19,11), (19,12)],
            (24,12) : [(23,12), (23,13), (24,12), (24,13), (25,12), (25,13)]}
        num_cells = 6

        # we plot the rssi vs. pckt loss for all cells in one giant grid
        # FIXME : for each cell, we generate 2 plots, side-by-side:
        #   - wlan data rate (yy) vs. rssi (xx)
        #   - wlan data rate (yy) vs. pck-loss (xx)
        outer_side = int(np.ceil(math.sqrt(num_cells)))
        fig = plt.figure(figsize = (10.0 * 1, 2.5 * 6))
        outer = gridspec.GridSpec(6, 1, wspace = 0.2, hspace = 0.5)

        # add title w/ mac addr and cell where mac addr is located
        mac_cell = (int((clients[mac]['lon'] - LONW) / (LONE - LONW) * X_CELL_NUM), int((clients[mac]['lat'] - LATS) / (LATN - LATS) * Y_CELL_NUM))
        fig.suptitle(
            ('%s @%s' % (mac, (int((clients[mac]['lon'] - LONW) / (LONE - LONW) * X_CELL_NUM), int((clients[mac]['lat'] - LATS) / (LATN - LATS) * Y_CELL_NUM)))),
            size = 20)

        x_range = defaultdict(list)
        x_range = [np.amin(data['time']), np.amax(data['time'])]
        y_range = [np.amin(data[to_predict]), np.amax(data[to_predict])]

        # get min value per cell id 
        i = 0
        for name, group in grouped:

            if name not in cells_to_plot[mac_cell]:
                continue

            # inner subplot : 1 row x 2 columns
            inner = gridspec.GridSpecFromSubplotSpec(1, 2, subplot_spec = outer[i], wspace = 0.2, hspace = 0.1)

            # ax.set_title("%s" % (cell_id))
            directions = {1 : {'color' : 'seagreen', 'marker' : 'o', 'label' : 'W to E'}, -1 : {'color' : 'dodgerblue', 'marker' : '^', 'label' : 'E to W'}}
            j = 0
            for direction in directions:

                _data = group[group['direction'] == direction]

                if _data.empty:
                    print("no %s direction for %s @[%s]" % (directions[direction]['label'], mac, name))
                    j = j + 1
                    continue

                if method == 'linear-regression':

                    # get linear regression model
                    model = predict_linear_reg(_data, to_predict, features)

                    if model is None:
                        print("no model for %s direction, %s @[%s]" % (directions[direction]['label'], mac, name))
                        j = j + 1
                        continue

                    # add subplot 
                    ax = plt.Subplot(fig, inner[j])
                    ax.set_title(('cell: %s, dir.: %s' % (name, directions[direction]['label'])))
                    plot_model(ax, _data, direction, model, to_predict, features)
                    fig.add_subplot(ax)

                else:
                    sys.stderr.write("""%s::predict() [ERROR] unknown prediction method\n""" % sys.argv[0]) 
                    parser.print_help()
                    sys.exit(1)

                j = j + 1
            i = i + 1

        # save plot for rssi vs. pck-loss
        plt.tight_layout()
        plt.savefig(os.path.join(trace_output_dir, ("prediction-%s.pdf" % (method))), bbox_inches = 'tight', format = 'pdf')

def get_lap_timestamps(trace_dir):

    trace_dir = os.path.join(trace_dir)
    for filename in sorted(glob.glob(os.path.join(trace_dir, 'mobile/gps-log.*.csv'))):

        gps_data = pd.read_csv(filename)
        gps_data['timestamp'] = gps_data['timestamp'].astype(int)
        gps_data = gps_data.sort_values(by = ['timestamp']).reset_index()

        # find 'peaks' of distance of mobile to client @pos0
        # FIXME : this assumes laps always start next to pos2
        gps_pos = [ [row['lat'], row['lon'] ] for index, row in gps_data.iterrows()]
        gps_data['dist'] = [ mapping.utils.gps_to_dist(peers['pos0']['lat'], peers['pos0']['lon'], gps[0], gps[1]) for gps in gps_pos ] 
        
    return analysis.metrics.find_peaks(gps_data, x_metric = 'timestamp', y_metric = 'dist')

def add_lap_numbers(data, lap_ts):

    i = 0
    while (i + 1) < len(lap_ts['start']):
        # print("[%s, %s]" % (data.iloc[0]['time'], data.iloc[-1]['time']))
        # print("%s : [%s, %s]" % (i + 1, lap_ts['start'][i], lap_ts['start'][i + 1]))
        # lap nr.
        data.loc[(data['timestamp'] > float(lap_ts['start'][i])) & (data['timestamp'] <= float(lap_ts['start'][i + 1])), 'lap-number']  = i + 1        
        # direction
        data.loc[(data['timestamp'] > float(lap_ts['start'][i])) & (data['timestamp'] <= float(lap_ts['turn'][i])), 'direction']  = 1
        data.loc[(data['timestamp'] > float(lap_ts['turn'][i])) & (data['timestamp'] <= float(lap_ts['start'][i + 1])), 'direction']  = -1

        i += 1

def get_gps_data(trace_dir):

    for filename in sorted(glob.glob(os.path.join(trace_dir, 'mobile/gps-log.*.csv'))):

        gps_data = pd.read_csv(filename)
        gps_data['timestamp'] = gps_data['timestamp'].astype(int)
        # get lap timestamp delimiters
        lap_ts = get_lap_timestamps(trace_dir)
        # add lap numbers to gps data
        gps_data['lap-number'] = -1
        gps_data['direction'] = -1
        add_lap_numbers(gps_data, lap_ts)
        # sort by time        
        gps_data = gps_data.sort_values(by = ['timestamp']).reset_index()

    return gps_data, lap_ts

def get_cbt_data(trace_dir):

    cbt_data = defaultdict(pd.DataFrame)
    for pos in ['pos0', 'pos1']:
        for filename in sorted(glob.glob(os.path.join(trace_dir, ('%s/cbt.*.csv' % (pos))))):

            # read cbt .csv file
            cbt_data[pos] = pd.read_csv(filename)

            # filter out invalid data
            # invalid timestamps
            # FIXME : very sloppy test, but it works
            cbt_data[pos]['timestamp'] = cbt_data[pos]['timestamp'].astype(float)
            cbt_data[pos] = cbt_data[pos][cbt_data[pos]['timestamp'] > 1000000000.0]
            cbt_data[pos]['timestamp'] = cbt_data[pos]['timestamp'].astype(int)

            # cbt_data[pos]['timestamp-str'] = [str(ts) for ts in cbt_data[pos]['timestamp']]

            # FIXME: from a quick (eyes-only) analysis of the data, i'll assume
            # cat and cbt increase monotonically in the same time segments
            # identify segments of increasingly monotonic cat
            cbt_data[pos]['channel-util'] = 0.0
            segments = list(cbt_data[pos].index[(cbt_data[pos]['cat'] - cbt_data[pos]['cat'].shift(1)) < 0.0])
            segments.append(len(cbt_data[pos]))

            prev_seg = 0
            for seg in segments:

                _data = cbt_data[pos].iloc[prev_seg:seg]
                if len(_data) == 1:
                    continue

                _data['diff-cat'] = _data['cat'] - _data['cat'].shift(1)
                _data['diff-cbt'] = _data['cbt'] - _data['cbt'].shift(1)

                cbt_data[pos].loc[prev_seg:seg, 'channel-util'] = (_data['diff-cbt'].astype(float) / _data['diff-cat'].astype(float)) * 100.0

        # # fix first row : avg. of acc. register data 
        # cbt_data[pos].loc[0, 'channel-util'] = (cbt_data[pos].iloc[0]['cbt'].astype(float) / cbt_data[pos].iloc[0]['cat'].astype(float)) * 100.0
        cbt_data[pos] = cbt_data[pos].dropna(subset = ['channel-util'])

    return cbt_data

def extract_tx_features(input_dir, trace_nr, protocol = 'tcp', interval = 1.0):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    for mac in clients.keys():
        # FIXME : if any of the macs already has a 'tx' table on the database, we abort
        if ('/%s/%s/%s/%s' % ('seq-numbers', mac, interval, 'tx')) in database.keys():
            return

    # get time series of gps positions, and lap timestamps
    gps_data, lap_tmstmps = get_gps_data(trace_dir)

    # gather data from monitor.*.csv files, containing monitoring data 
    # on fixed positions (i.e., 'tx' data)
    for pos in peers.keys():

        if pos in ['mobile', 'pos3']:
            continue

        dataset_stats = pd.DataFrame(columns = ['mac', 'tcp', 'udp', 'tcp-gps', 'udp-gps'])
        for filename in sorted(glob.glob(os.path.join(trace_dir, ('%s/monitor.*.csv' % (pos))))):

            chunksize = 10 ** 5
            for chunk in pd.read_csv(filename, chunksize = chunksize):

                # don't consider data outside of laps
                if not ((chunk.iloc[0]['epoch time'] > lap_tmstmps['start'][0]) and (chunk.iloc[-1]['epoch time'] < lap_tmstmps['start'][-1])):
                    continue
 
                gps_time_data = chunk[['epoch time']]
                # gps_time_data['epoch-ts'] = gps_time_data['epoch time'].astype(str)
                gps_time_data['timestamp'] = gps_time_data['epoch time'].apply(analysis.metrics.myround).astype(int)
                # get data w/ a resolution of interval seconds
                # gps_time_data['time'] = ((chunk['epoch time'] * (1.0 / interval)).astype(int) / (1.0 / interval)).astype(float)
                gps_time_data['time'] = gps_time_data['epoch time'].apply(analysis.metrics.myround)
                # gps_time_data['time-ts'] = gps_time_data['time'].astype(str)
                gps_time_data = gps_time_data.drop_duplicates(subset = ['time'])

                # merge wifi data w/ gps data (lat, lon and lap info)
                gps_time_data = pd.merge(gps_time_data, gps_data[['timestamp', 'lat', 'lon', 'lap-number', 'direction']], on = ['timestamp'], how = 'inner')

                for mac in peers[pos]['macs']:

                    _time_data = gps_time_data
                    _dataset_stats = {'mac' : mac, 'tcp' : 0.0, 'udp' : 0.0, 'tcp-gps' : 0.0, 'udp-gps' : 0.0}

                    data = chunk[(chunk['wlan src addr'] == mac) & (chunk['wlan dst addr'] == ap) & (chunk['ip proto'] != '')].reset_index(drop = True)
                    if data.empty:
                        continue

                    _dataset_stats['tcp'] = len(data[data['ip proto'] == 'TCP'])
                    _dataset_stats['udp'] = len(data[data['ip proto'] == 'UDP'])

                    data = data[data['ip proto'] == protocol.upper()].reset_index(drop = True)
                    if data.empty:
                        continue

                    # collect wlan seq number stats
                    seq_number_stats = analysis.metrics.calc_wlan_frame_stats(data, intervals = [interval], mode = 'tx')
                    # save 'tx' frame stats
                    for interval in seq_number_stats:
                        to_hdf5(seq_number_stats[interval], ('/%s/%s/%s/%s' % ('seq-numbers', mac, interval, 'tx')), database)

                    _dataset_stats[('%s-gps' % (protocol))] = len(_time_data)
                    dataset_stats = dataset_stats.append(_dataset_stats, ignore_index = True)
                    dataset_stats = dataset_stats.groupby(['mac']).sum().reset_index()

        # # save on database
        # to_hdf5(dataset_stats, ('/%s/%s/%s' % ('dataset-stats', 'tx', pos)), database)

def extract_rx_features(input_dir, trace_nr, 
    to_extract = ['wlan rssi', 'wlan data rate', 'pckt-loss', 'throughput'], 
    protocol = 'tcp',
    interval = 0.5):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    # get time series of gps positions, and lap timestamps
    gps_data, lap_tmstmps = get_gps_data(trace_dir)
    # channel util. time series : a dict(), indexed by positions
    cbt_data = get_cbt_data(trace_dir)

    dataset_stats = pd.DataFrame(columns = ['mac', 'tcp', 'udp', 'tcp-gps', 'udp-gps'])

    # # wifi data
    # # 1) first extract 'tx-side' data, if available
    # extract_tx_features(input_dir, trace_nr, protocol, interval)

    # 2) extract 'rx-side' data, and use 'tx' data to calculate features (if available)
    for filename in sorted(glob.glob(os.path.join(trace_dir, 'mobile/monitor.*.csv'))):

        chunksize = 10 ** 5
        for chunk in pd.read_csv(filename, chunksize = chunksize):

            # don't consider data outside of laps
            # filter by timestamp (note : < start of last lap)
            if not ((chunk.iloc[0]['epoch time'] > lap_tmstmps['start'][0]) and (chunk.iloc[-1]['epoch time'] < lap_tmstmps['start'][-1])):
                continue

            gps_time_data = chunk[['epoch time']]
            # gps_time_data['epoch-ts'] = gps_time_data['epoch time'].astype(str)
            gps_time_data['timestamp'] = gps_time_data['epoch time'].apply(analysis.metrics.myround).astype(int)
            # get data w/ a resolution of interval seconds
            # gps_time_data['time'] = ((chunk['epoch time'] * (1.0 / interval)).astype(int) / (1.0 / interval)).astype(float)
            gps_time_data['time'] = gps_time_data['epoch time'].apply(analysis.metrics.myround)
            # gps_time_data['time-ts'] = gps_time_data['time'].astype(str)
            gps_time_data = gps_time_data.drop_duplicates(subset = ['time'])

            # merge wifi data w/ gps data (lat, lon and lap info)
            gps_time_data = pd.merge(gps_time_data, gps_data[['timestamp', 'lat', 'lon', 'lap-number', 'direction']], on = ['timestamp'], how = 'inner')

            # merge wifi data w/ cbt data 
            # FIXME : why use pos1? pos0 is at the edge, pos1 in the middle...
            # FIXME : this must be changed in the future
            gps_time_data = pd.merge(gps_time_data, cbt_data['pos1'][['timestamp', 'channel-util']], on = ['timestamp'], how = 'inner')
            # gps_time_data['time-str'] = gps_time_data['time'].astype(str)

            for mac in clients:

                _time_data = gps_time_data
                _dataset_stats = {'mac' : mac, 'tcp' : 0.0, 'udp' : 0.0, 'tcp-gps' : 0.0, 'udp-gps' : 0.0}

                data = chunk[(chunk['wlan src addr'] == mac) & (chunk['wlan dst addr'] == ap) & (chunk['ip proto'] != '')].reset_index(drop = True)
                if data.empty:
                    continue

                _dataset_stats['tcp'] = len(data[data['ip proto'] == 'TCP'])
                _dataset_stats['udp'] = len(data[data['ip proto'] == 'UDP'])

                data = data[data['ip proto'] == protocol.upper()].reset_index(drop = True)
                if data.empty:
                    continue

                # collect 'rx-side' wlan frame stats
                seq_number_stats = analysis.metrics.calc_wlan_frame_stats(data, intervals = [interval], mode = 'rx')
                to_hdf5(seq_number_stats[interval], ('/%s/%s/%s/%s' % ('seq-numbers', mac, interval, 'rx')), database)

                for metric in to_extract:

                    proc_data = None
                    # columns of proc_data to add to the final .hdf5 database
                    to_add = ['time', metric]

                    # extract metric by required interval
                    if metric != 'pckt-loss':

                        proc_data = process_metric(data, metric, interval = interval)

                    else:

                        # pckt-loss can be a tricky metric to extract...

                        # primary way of calculating pckt-loss
                        proc_data = seq_number_stats[interval][['time', 'snt', 'rcvd', 'lost']]
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

                    _time_data = pd.merge(_time_data, proc_data[to_add], on = ['time'], how = 'inner')

                # print(mac)
                # print(_time_data)

                _dataset_stats[('%s-gps' % (protocol))] = len(_time_data)
                dataset_stats = dataset_stats.append(_dataset_stats, ignore_index = True)
                dataset_stats = dataset_stats.groupby(['mac']).sum().reset_index()

                # # save on database
                # to_hdf5(_time_data, ('/%s/%s' % ('cell-data', mac)), database)

    # # save on database
    # to_hdf5(dataset_stats, ('/%s/%s' % ('dataset-stats', 'rx')), database)

def plot_cell_consec_features(ax, data, metric, x_range, interval = 0.5):

    metric_labels = {
        'wlan rssi' : 'rssi (dBm)', 
        'pckt-loss' : 'packet loss (%)', 
        'wlan data rate' : 'wlan data rate (Mbps)',
        'throughput' : 'throughput (Mbps)'}

    ax.xaxis.grid(True, ls = 'dotted', lw = 0.75)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.75)

    # plot w/ different markers, according to the direction of movement
    directions = {1 : {'color' : 'red', 'marker' : 'o', 'label' : 'W to E'}, -1 : {'color' : 'blue', 'marker' : '^', 'label' : 'E to W'}}
    grouped = data.groupby(['blocks'])
    for name, group in grouped:
        for direction in directions:
            
            _data = group[group['direction'] == direction]
            if _data.empty:
                continue

            if (metric == 'wlan data rate') or (metric == 'throughput'):
                _data[metric] = _data[metric] / 1000000.0

            ax.plot(_data[metric].mean(), float(len(_data)) * interval, 
                alpha = 0.75, linewidth = 0.0, color = directions[direction]['color'], label = directions[direction]['label'], linestyle = '-',
                markersize = 4.0, marker = directions[direction]['marker'])

            directions[direction]['label'] = ''

    # # draw a vertical line for the interference mean
    # ax.axvline(x = data['interference-mean'].iloc[0] + rssi_mean, color = 'red', linestyle = '--', linewidth = .75)

    ax.set_xlabel(("%s" % (metric_labels[metric])))
    ax.set_ylabel("duration (sec)")

    ax.set_xlim(x_range)
    ax.set_ylim([0.0, 10.0 * interval])

    ax.legend(fontsize = 12, ncol = 1, loc = 'upper left',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

def plot_client_consec_features(
    data, trace_output_dir,
    mac,
    features = ['wlan rssi', 'wlan data rate', 'pckt-loss', 'throughput'],
    interval = 0.5):

    # group data by cell id (x,y)
    grouped = data.groupby(['cell-x', 'cell-y'])

    # only plot cells w/ > 20 data points
    to_plot = []
    for name, group in grouped:
        if len(group) >= 20:
            to_plot.append(name)

    # nr. of cells
    num_cells = len(to_plot)
    # we plot <feature> vs. throughput for relevant cells (w/ 20 or more data points)
    fig = plt.figure(figsize = ((5.0 * len(features)) * 1.0, 2.5 * num_cells))
    outer = gridspec.GridSpec(num_cells, 1, wspace = 0.15, hspace = 0.6)

    # add title w/ mac addr and cell where mac addr is located
    mac_cell = (int((clients[mac]['lon'] - LONW) / (LONE - LONW) * X_CELL_NUM), int((clients[mac]['lat'] - LATS) / (LATN - LATS) * Y_CELL_NUM))
    fig.suptitle(('fixed client %s @cell%s' % (mac, mac_cell)))

    x_range = defaultdict(list)
    x_range['wlan rssi'] = [np.amin(data['wlan rssi'] - 2.5), np.amax(data['wlan rssi'] + 2.5)]
    x_range['pckt-loss'] = [-5, 100.0]
    x_range['wlan data rate'] = [(np.amin(data['wlan data rate']) / 1000000.0) - 10, (np.amax(data['wlan data rate'])  / 1000000.0) + 10]
    x_range['throughput'] = [(np.amin(data['throughput']) / 1000000.0), (np.amax(data['throughput']) / 1000000.0) + 10]

    # y_range = [0.0, (np.amax(data['len']) + 2.0) * interval]

    # get min value per cell id 
    i = 0

    for name, group in grouped:

        if name not in to_plot:
            continue

        # inner subplot : 1 row x len(features) columns
        inner = gridspec.GridSpecFromSubplotSpec(1, len(features), subplot_spec = outer[i], wspace = 0.2, hspace = 0.1)

        # ax.set_title("%s" % (cell_id))
        for j, metric in enumerate(features):
            # add subplot
            ax = plt.Subplot(fig, inner[j])
            plot_cell_consec_features(ax, group, metric, x_range = x_range[metric], interval = interval)
            ax.set_title(('cell: %s, feat.: %s' % (name, metric)))
            fig.add_subplot(ax)

        i = i + 1

    # save plot for rssi vs. pck-loss
    plt.tight_layout()
    # plt.subplots_adjust(top = 0.80)
    plt.savefig(os.path.join(trace_output_dir, ("consec-interval-features.pdf")), bbox_inches = 'tight', format = 'pdf')

def plot_consec_features(
    input_dir, trace_nr, output_dir,
    intervals = [0.5], 
    features = ['wlan rssi', 'wlan data rate', 'pckt-loss', 'throughput']):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    for interval in intervals:
        for mac in clients:

            # db_name = ('/%s/%s/%s' % ('consecutive-intervals', mac, interval))
            db_name = ('/%s/%s' % ('cell-data', mac))
            if db_name not in database.keys():
                continue

            # load data for a client mac
            data = database.select(db_name)

            # create output dir for trace (if not existent)
            trace_output_dir = os.path.join(output_dir, ("trace-%03d/%s" % (int(trace_nr), mac)))
            if not os.path.isdir(trace_output_dir):
                os.makedirs(trace_output_dir)

            # add cell ids to each measurement
            data['cell-x'] = data['lon'].apply(lambda x : int((x - LONW) / (LONE - LONW) * X_CELL_NUM))
            data['cell-y'] = data['lat'].apply(lambda y : int((y - LATS) / (LATN - LATS) * Y_CELL_NUM))

            # find blocks of contiguous intervals
            data['time-diff'] = data['time'] - data['time'].shift(1)
            data['blocks'] = ((data['time-diff'].shift(1) != data['time-diff']) & (data['time-diff'] != .5)).astype(int).cumsum()
            
            plot_client_consec_features(data, trace_output_dir, mac)

def get_cell_id(lat, lon):

    # fraction of longitude (or latitude) range [LONW, lon] over the total [LONW, LONE] interval
    x = (lon - LONW) / (LONE - LONW)
    y = (lat - LATS) / (LATN - LATS)
    # use the above to find the cell number, on both x and y directions
    x = int(x * X_CELL_NUM)
    y = int(y * Y_CELL_NUM)

    return (x, y)

def get_closest_cell(cid, data):

    data['dist'] = [ math.sqrt((row['cell-x'] - cid[0])**2 + (row['cell-y'] - cid[1])**2) for index, row in data.iterrows() ]
    return data.ix[data['dist'].idxmin()]

def gps_predict(input_dir, trace_nr, metrics = ['wlan rssi', 'throughput', 'wlan data rate', 'pckt-loss']):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    # load throughput data
    data = database.select(('/%s/%s' % ('rank', 'throughput')))
    # list of mac addresses
    mac_addrs = list(set(data.columns) - set(['lap-number', 'timestamp', 'time', 'lat', 'lon']))

    gps_predict = pd.DataFrame()
    # for each lap i, predict best ap on lap i + 1
    lap_num = np.amax(data['lap-number'])
    for lap in range(1, lap_num + 1):

        # group by gps pos
        predictor = data[data['lap-number'] == lap].groupby(['lat', 'lon'])[mac_addrs].mean().reset_index()
        # calc cell id for each gps pos
        predictor['cell-x'] = predictor['lon'].apply(lambda x : int((x - LONW) / (LONE - LONW) * X_CELL_NUM))
        predictor['cell-y'] = predictor['lat'].apply(lambda y : int((y - LATS) / (LATN - LATS) * Y_CELL_NUM))

        to_predict = data[data['lap-number'] == (lap + 1)]
        for index, row in to_predict.iterrows():

            # find cell id of current row
            cid = get_cell_id(row['lat'], row['lon'])
            pc = get_closest_cell(cid, predictor)

            gt = row[mac_addrs].idxmax(axis = 1)
            predicted = pc[mac_addrs].idxmax(axis = 1)
            gps_predict = gps_predict.append({
                'time' : row['time'],
                'truth' : gt,
                'predicted' : predicted,
                'diff' : (((row[predicted] - row[gt]) / (row[gt])) * 100.0)}, ignore_index = True)

    # save on database
    to_hdf5(gps_predict, ('/%s/%s' % ('gps-predicted', 'throughput')), database)

def create_grid():

    # limits for (x,y) coordinates in grid
    max_x = int(1.0 * X_CELL_NUM)
    max_y = int(1.0 * Y_CELL_NUM)

    # height and width of cells (in degrees)
    # FIXME : this isn't exactly correct : note that CELL_NUM is calculated w/ np.ceil()
    w = (LONE - LONW) / float(X_CELL_NUM)
    h = (LATN - LATS) / float(Y_CELL_NUM)

    # create a geodataframe of polygons, 1 polygon per cell, w/ cell ids
    polygons = []
    cell_ids = []
    for i in range(max_x):
        for j in range(max_y):

            polygons.append(
                shapely.geometry.Polygon(
                    [
                    (LONW + (i * w), LATS + (j * h)), 
                    (LONW + ((i + 1) * w), LATS + (j * h)), 
                    (LONW + ((i + 1) * w), LATS + ((j + 1) * h)), 
                    (LONW + (i * w), LATS + ((j + 1) * h))
                    ]))

            cell_ids.append({'cell-x' : i, 'cell-y' : j})

    cell_ids = pd.DataFrame(cell_ids, columns = ['cell-x', 'cell-y'])
    grid = gp.GeoDataFrame({'geometry' : polygons, 'cell-x' : cell_ids['cell-x'], 'cell-y' : cell_ids['cell-y']})

    return grid

def rssi_predict(input_dir, trace_nr):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    # load throughput data
    thghpt_data = database.select(('/%s/%s' % ('rank', 'throughput')))
    rssi_data = database.select(('/%s/%s' % ('rank', 'wlan rssi')))
    # list of mac addresses
    mac_addrs = list(set(rssi_data.columns) - set(['lap-number', 'timestamp', 'time', 'lat', 'lon']))

    rssi_predict = pd.DataFrame()
    for index, row in rssi_data.iterrows():

        # find ap w/ best rssi
        predicted = row[mac_addrs].idxmax(axis = 1)
        # find ap w/ best throughput
        to_predict = thghpt_data[thghpt_data['time'] == row['time']]
        gt = to_predict[mac_addrs].idxmax(axis = 1).values[0]

        rssi_predict = rssi_predict.append({
            'time' : row['time'],
            'truth' : gt,
            'predicted' : predicted,
            'diff' : (((to_predict[predicted].values[0] - to_predict[gt].values[0]) / (to_predict[gt].values[0])) * 100.0)}, ignore_index = True)

    # save on database
    to_hdf5(rssi_predict, ('/%s/%s' % ('rssi-predicted', 'throughput')), database)

def plot_grid(input_dir, trace_nr, output_dir, zoom = None):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    sample_count = pd.DataFrame(columns = ['cell-x', 'cell-y', 'count'])
    for mac in clients:

        if ('/%s/%s' % ('cell-data', mac)) not in database.keys():
            continue

        # load data for a client mac
        data = database.select(('/%s/%s' % ('cell-data', mac)))
        # add cell ids
        data['cell-x'] = data['lon'].apply(lambda x : int((x - LONW) / (LONE - LONW) * X_CELL_NUM))
        data['cell-y'] = data['lat'].apply(lambda y : int((y - LATS) / (LATN - LATS) * Y_CELL_NUM))

        # groupby cell id and count samples and concat
        sample_count = pd.concat([sample_count, data.groupby(['cell-x', 'cell-y'])['time'].agg(['count']).reset_index()], ignore_index = True)
        # groupby cell id and sum on count
        sample_count = sample_count.groupby(['cell-x', 'cell-y'])['count'].sum().reset_index()

    # print cdf plot of samples per cell
    cdf = sample_count.groupby(['count']).size().reset_index(name = 'counts')
    cdf['counts'] = np.array(cdf['counts'].cumsum(), dtype = float)
    cdf['counts'] = cdf['counts'] / cdf['counts'].values[-1]

    fig = plt.figure(figsize = (5, 2.5))

    ax = fig.add_subplot(111)
    ax.xaxis.grid(True, ls = 'dotted', lw = 0.75)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.75)

    ax.plot(cdf['count'], cdf['counts'], 
        alpha = 0.75, linewidth = 1.0, color = 'black', label = '# of cells', linestyle = '-')

    ax.set_xlabel("# of samples per cell")
    ax.set_ylabel("CDF")

    # ax.set_xticks(np.arange(0, np.amax(cdf['count']), 10)
    # ax.set_xticklabels([-10, -20, -30, -40, -50, -60, -70, -80])
    ax.set_yticks(np.arange(0.0, 1.1, 0.25))
    ax.legend(fontsize = 12, ncol = 1, loc = 'upper left')

    # create output dir for trace (if not existent)
    trace_output_dir = os.path.join(output_dir, ("trace-%03d" % (int(trace_nr))))
    if not os.path.isdir(trace_output_dir):
        os.makedirs(trace_output_dir)

    plt.tight_layout()
    plt.savefig(os.path.join(trace_output_dir, "samples-per-cell.pdf"), bbox_inches = 'tight', format = 'pdf')

    # print coverage map of cells
    bbox = [LONW, LATS, LONE, LATN]
    roads = None
    if os.path.isdir(os.path.join(trace_output_dir, ("roads"))):
        roads = gp.GeoDataFrame.from_file(os.path.join(trace_output_dir, "roads"))
    else:
        roads = mapping.openstreetmap.get_roads(trace_output_dir, 
            tags = ['highway='], 
            bbox = bbox)

    # filters
    roads = roads.dropna(subset = ['highway'])
    roads = roads[roads['highway'].str.contains('footway|cycleway') == False]
    roads = roads[roads.type == 'LineString'][['highway', 'name', 'geometry']]

    # code to select a bbox from roads
    # FIXME : this uses the .overlay(how = 'intersection') method, which is inneficient
    start = timeit.default_timer()
    # bbox
    bbox = [(-8.597, 41.178), (-8.597, 41.180), (-8.592, 41.180), (-8.592, 41.178)]
    roads['geometry'] = roads['geometry'].buffer(0.000125)
    base = [ shapely.geometry.Polygon(bbox) ]
    base = gp.GeoDataFrame({'geometry':base})
    roads = gp.overlay(base, roads, how = 'intersection')
    print("%s::plot_grid() : [INFO] buffer() produced in %.3f sec" % (sys.argv[0], timeit.default_timer() - start))

    dy = mapping.utils.gps_to_dist(41.180, 0.0, 41.178, 0.0)
    dx = mapping.utils.gps_to_dist(41.178, -8.597, 41.178, -8.592)

    fig = plt.figure(figsize = ((dx / dy) * 5.0, 5.0))

    ax = fig.add_subplot(111)
    ax.xaxis.grid(True, ls = 'dotted', lw = 0.75)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.75)
    
    roads.plot(ax = ax, facecolor = 'blue', zorder = 0)

    # on top of the roads, plot the 5 x 5 m cells for which we have samples, with a gradient color scale
    grid = create_grid()
    # upgrade grid, by merging sample counts w/ polygons
    grid = pd.merge(grid, sample_count, on = ['cell-x', 'cell-y'], how = 'inner')
    # center point for each polygon
    grid['coords'] = grid['geometry'].apply(lambda x: x.representative_point().coords[:])
    grid['coords'] = [ coords[0] for coords in grid['coords'] ]

    # print the polygons, colored according to sample count
    grid.plot(ax = ax, zorder = 5, column = 'count', cmap = 'YlOrRd', legend = True)

    # add aps to map, as red dots
    points = []
    for ap in clients:

        lon = clients[ap]['lon']
        lat = clients[ap]['lat']
        if clients[ap]['id'] == 3:
            lon -= 0.00001
            lat += 0.00001
        elif clients[ap]['id'] == 1:
            lon += 0.00001
            lat -= 0.00001

        points.append(shapely.geometry.Point(lon, lat))

    points = gp.GeoDataFrame({'geometry':points})
    points.plot(ax = ax, zorder = 10, color = 'red')

    for ap in clients:

        lon = clients[ap]['lon']
        lat = clients[ap]['lat'] - 0.00001
        if clients[ap]['id'] == 3:
            lon -= 0.00001
            lat += 0.00001
        elif clients[ap]['id'] == 1:
            lon += 0.00001
            lat -= 0.00001

        plt.annotate(
            s = ('%d' % (clients[ap]['id'])), 
            xy = (lon, lat),
            horizontalalignment = 'center',
            zorder = 15,
            size = 5,
            color = 'white')

    # add cell ids to 
    for idx, row in grid.iterrows():
        plt.annotate(
            s = ('(%s,%s)' % (str(row['cell-x']), str(row['cell-y']))), 
            xy = row['coords'], 
            horizontalalignment = 'center',
            zorder = 20,
            size = 5,
            color = 'white' if row['count'] > 200 else 'black')

    plt.tight_layout()
    plt.savefig(os.path.join(trace_output_dir, "sample-cells.pdf"), bbox_inches = 'tight', format = 'pdf')

def plot_pckt_loss(input_dir, trace_nr, output_dir, intervals = [0.5]):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    metrics = {
        'rcvd'  : {'title' : '# of pckts received per', 'x-axis-label' : '# rcvd packets'},
        'snt'   : {'title' : '# of pckts sent per', 'x-axis-label' : '# snt packets'},
        'loss'  : {'title' : 'packet loss per', 'x-axis-label' : 'packet loss (%)', 'x-axis-lim' : [-5, 105]}
    }
    for mac in clients:

        fig = plt.figure(figsize = (5.0 * 3.0, 7.5 * len(intervals)))

        # load data for a client mac
        i = 1
        db_names = defaultdict(pd.DataFrame)
        for interval in intervals:

            # print('db keys : %s' % (database.keys()))
            db_names['rx'] = ('/%s/%s/%s/%s' % ('seq-numbers', mac, interval, 'rx'))
            if db_names['rx'] not in database.keys():
                # print('no %s' % (db_names['rx']))
                continue

            db_names['tx'] = ('/%s/%s/%s/%s' % ('seq-numbers', mac, '1.0', 'tx'))
            if db_names['tx'] not in database.keys():
                # print('no %s' % (db_names['tx']))
                continue

            # groupby():
            #   - nr. of packets per interval
            #   - nr. of lost packets per interval
            #   - pckt loss per interval

            for metric in metrics:

                db_name = ''
                if metric == 'snt':
                    db_name = db_names['tx']
                else:
                    db_name = db_names['rx']
                
                data = database.select(db_name) 
                if metric == 'loss':
                    data['loss'] = ((data['lost'].astype(float) / data['snt'].astype(float)) * 100.0).astype(int)

                # groupby() data according to the different values 'metric' can take and 
                # count the nr. of times each diff. value occurs
                cdf = data.groupby([metric]).size().reset_index(name = 'count')
                cdf['count'] = np.array(cdf['count'].cumsum(), dtype = float)
                # print(metric)
                # print(cdf)
                if metric == 'loss':
                    cdf['count'] = cdf['count'] / cdf['count'].values[-1]

                ax = fig.add_subplot(3, 3, i)
                i += 1
                ax.xaxis.grid(True, ls = 'dotted', lw = 0.75)
                ax.yaxis.grid(True, ls = 'dotted', lw = 0.75)

                ax.set_title(('%s %s sec' % (metrics[metric]['title'], str(interval))))

                ax.plot(cdf[metric], cdf['count'], 
                    alpha = 0.75, linewidth = 1.0, color = 'black', linestyle = '-')

                ax.set_xlabel(metrics[metric]['x-axis-label'])

                if 'x-axis-lim' in metrics[metric]:
                    ax.set_xlim(metrics[metric]['x-axis-lim'])

                if metric == 'loss':
                    ax.set_ylabel("CDF")
                    ax.set_ylim([-.05, 1.05])
                    ax.set_yticks(np.arange(0.0, 1.1, 0.25))
                else:
                    ax.set_ylabel("# of intervals")
                # ax.legend(fontsize = 12, ncol = 1, loc = 'upper left')

        # create output dir for trace (if not existent)
        trace_output_dir = os.path.join(output_dir, ("trace-%03d/%s" % (int(trace_nr), mac)))
        if not os.path.isdir(trace_output_dir):
            os.makedirs(trace_output_dir)

        plt.tight_layout()
        plt.savefig(os.path.join(trace_output_dir, "pckt-loss.pdf"), bbox_inches = 'tight', format = 'pdf')

def plot_prediction(input_dir, trace_nr, output_dir, zoom = None):

    plt.style.use('classic')
    fig = plt.figure(figsize = (5, 6))

    ax1 = fig.add_subplot(311)
    ax1.xaxis.grid(True)
    ax1.yaxis.grid(True)

    ax2 = fig.add_subplot(312)
    ax2.xaxis.grid(True)
    ax2.yaxis.grid(True)

    ax3 = fig.add_subplot(313)
    ax3.xaxis.grid(True)
    ax3.yaxis.grid(True)

    time_limits = zoom

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    gps_data = database.select(('/%s/%s' % ('gps-predicted', 'throughput')))
    rssi_data = database.select(('/%s/%s' % ('rssi-predicted', 'throughput')))

    gps_error = float(len(gps_data[gps_data['diff'] < 0.0])) / float(len(gps_data))
    rssi_error = float(len(rssi_data[rssi_data['diff'] < 0.0])) / float(len(rssi_data))
    print(gps_error)
    print(rssi_error)
    ax3.bar([0], [gps_error * 100.0], 0.50,
                alpha = 0.75, color = 'b',
                label='gps')
    ax3.bar([1], [rssi_error * 100.0], 0.50,
                alpha = 0.75, color = 'r',
                label='rssi')

    ax3.set_title(("thhpt prediction error"))
    ax3.set_xlabel("methods")
    ax3.set_ylabel("predict. error (%)")
    ax3.set_xlim([-0.5, 2.0])
    ax3.set_ylim([0.0, 100.0])
    ax3.set_xticks([0, 1])
    ax3.set_xticklabels(['gps', 'rssi'])

    ax3.legend(
        fontsize = 12, 
        ncol = 1, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in gps_data['time'] ]
    ax1.plot_date(
        dates,
        gps_data['diff'],
        linewidth = 0.0, linestyle = None, color = 'black', label = 'pred. error',
        marker = 'o', markersize = 2.50, markeredgewidth = 0.0)

    dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in rssi_data['time'] ]
    ax2.plot_date(
        dates,
        rssi_data['diff'],
        linewidth = 0.00, linestyle = None, color = 'black', label = 'pred. error',
        marker = 'o', markersize = 2.50, markeredgewidth = 0.0)

    # divide xx axis in 5 ticks
    xticks = plot.utils.get_time_xticks(time_limits)

    # dist to client
    ax1.set_title(("thhpt prediction via GPS"))
    ax1.set_xlabel("time")
    ax1.set_ylabel("predict. error (%)")
    ax1.set_xlim(time_limits[0], time_limits[1])
    ax1.set_xticks(xticks)
    ax1.set_xticklabels([str(xt)[11:-7] for xt in xticks])

    ax1.legend(
        fontsize = 12, 
        ncol = 1, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    ax2.set_title(("thhpt prediction via rssi"))
    ax2.set_xlabel("time")
    ax2.set_ylabel("predict. error (%)")
    ax2.set_xlim(time_limits[0], time_limits[1])
    ax2.set_xticks(xticks)
    ax2.set_xticklabels([str(xt)[11:-7] for xt in xticks])

    ax2.legend(
        fontsize = 12, 
        ncol = 1, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    plt.gcf().autofmt_xdate()
    plt.tight_layout()

    # create output dir for trace (if not existent)
    trace_output_dir = os.path.join(output_dir, ("trace-%03d" % (int(trace_nr))))
    if not os.path.isdir(trace_output_dir):
        os.makedirs(trace_output_dir)

    plt.savefig(os.path.join(trace_output_dir, ("predict-error-%s.pdf" % (trace_nr))), bbox_inches = 'tight', format = 'pdf')

def get_time_limits(input_dir, trace_nr, protocol):

    time_limits = [None, None]

    # cycle through all data sources for a trace and collect min and max times
    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))    
    # monitor .pacp file
    for fname in sorted(glob.glob(os.path.join(trace_dir, 'mobile/monitor.wlx24050faaab5d.*.csv'))):
        chunksize = 10 ** 5
        for chunk in pd.read_csv(fname, chunksize = chunksize):
            for mac in clients:

                data = chunk[(chunk['wlan src addr'] == mac) & (chunk['wlan dst addr'] == ap) & (chunk['ip proto'] == protocol.upper())].reset_index()
                if data.empty:
                    continue

                plot.utils.update_date_limits(time_limits, data['epoch time'])

    # cbt files
    for filename in sorted(glob.glob(os.path.join(trace_dir, 'pos1/cbt.*.csv'))):

        # read cbt .csv file
        cbt_data = pd.read_csv(filename)
        # filter out invalid timestamps
        # FIXME : very sloppy test, but it works
        cbt_data['timestamp'] = cbt_data['timestamp'].astype(float)
        cbt_data = cbt_data[cbt_data['timestamp'] > 1000000000.0]
        plot.utils.update_date_limits(time_limits, cbt_data['timestamp'])

    # cpu files
    for peer in peers.keys():

        if peer == 'mobile':
            continue

        peer_dir = os.path.join(trace_dir, ("%s" % (peer)))
        for filename in sorted(glob.glob(os.path.join(peer_dir, 'iperf3-to-mobile.results*csv'))):
            cpu_data = pd.read_csv(filename)
            plot.utils.update_date_limits(time_limits, cpu_data['time'])

    return time_limits

def get_trace_info(input_dir, trace_nr, mode = 'rx', pos = 'pos1'):

    trace_info = pd.DataFrame
    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database_file = os.path.join(trace_dir, "processed/database.hdf5")

    if not os.path.isfile(database_file):
        sys.stderr.write("""%s: [ERROR] no .hdf5 available at %s\n""" % (sys.argv[0], trace_dir))
        return trace_info

    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    database_name = ('/%s/%s' % ('dataset-stats', mode))
    if mode == 'tx':
        database_name = ('%s/%s' % (database_name, pos))

    if database_name not in database.keys():
        sys.stderr.write("""%s: [ERROR] no dataset stats available yet\n""" % (sys.argv[0]))
        return trace_info

    trace_info = database.select(database_name)
    return trace_info

def get_trace_list(input_dir):

    filename = os.path.join(input_dir, ("trace-info.csv"))
    if not os.path.isfile(filename):
        sys.stderr.write("""%s: [ERROR] no 'trace-info.csv' at %s\n""" % (sys.argv[0], input_dir))
        return -1

    trace_list = pd.read_csv(filename)
    return trace_list

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--input-dir", 
         help = """dir w/ trace data""")

    parser.add_argument(
        "--list-traces", 
         help = """lists available traces""",
         action = 'store_true')

    parser.add_argument(
        "--trace-nr", 
         help = """nr of trace to analyze. e.g., '--trace-nr 009'""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save graphs & other output data""")

    args = parser.parse_args()

    if not args.input_dir:
        sys.stderr.write("""%s: [ERROR] must provide a dir w/ input files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    trace_list = get_trace_list(args.input_dir)
    if args.list_traces:
        table = PrettyTable(list(trace_list.columns))
        for i, row in trace_list.iterrows():
            table.add_row([
                ('%s' % (row['trace-nr'])),
                ('%s' % (row['proto'])), 
                ('%d' % (row['channel'])), 
                ('%d' % (row['bw'])),
                ('%s' % (('%s Mbps' % row['bitrate']) if row['bitrate'] != '*' else row['bitrate']))
                ])
        print(table)

        for mode in ['rx', 'tx']:

            if mode == 'rx':
                pos = ['mobile']
            elif mode == 'tx':
                pos = ['pos0', 'pos1']

            for p in pos:

                trace_info = get_trace_info(args.input_dir, args.trace_nr, mode, p)

                print("%s: dataset stats for %s probe, %s" % (sys.argv[0], mode, p))

                if not trace_info.empty:
                    table = PrettyTable(list(['mac', 'tcp', 'udp', 'tcp-gps', 'udp-gps']))
                    for i, row in trace_info.iterrows():
                        table.add_row([
                            ('%s' % (row['mac'])),
                            ('%s' % (int(row['tcp']))), 
                            ('%d' % (int(row['udp']))), 
                            ('%d' % (int(row['tcp-gps']))),
                            ('%s' % (int(row['udp-gps'])))])
                    print(table)

    if not args.trace_nr:
        sys.stderr.write("""%s: [ERROR] must provide a trace nr. to analyze\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] must provide an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)
    
    trace = trace_list[trace_list['trace-nr'] == int(args.trace_nr)]

    # extract_tx_features(args.input_dir, args.trace_nr, protocol = trace['proto'].values[-1])
    # extract_rx_features(args.input_dir, args.trace_nr, protocol = trace['proto'].values[-1])
    # extract_rankings(args.input_dir, args.trace_nr)
    # gps_predict(args.input_dir, args.trace_nr)
    # rssi_predict(args.input_dir, args.trace_nr)
    # time_limits = get_time_limits(args.input_dir, args.trace_nr, protocol = trace['proto'].values[-1])
    # plot_prediction(args.input_dir, args.trace_nr, args.output_dir, zoom = time_limits)
    # plot_grid(args.input_dir, args.trace_nr, args.output_dir)
    # plot_features(args.input_dir, args.trace_nr, args.output_dir)
    # predict(args.input_dir, args.trace_nr, args.output_dir,
    #     method = 'linear-regression',
    #     to_predict = 'throughput',
    #     features = ['wlan rssi', 'pckt-loss', 'wlan data rate'])
    # plot_pckt_loss(args.input_dir, args.trace_nr, args.output_dir)
    # extract_consec_intervals(args.input_dir, args.trace_nr, args.output_dir)
    plot_consec_features(args.input_dir, args.trace_nr, args.output_dir)

    # stats, time_range = get_dataset_description(args.input_dir, args.trace_nr)
    # print(stats)
    # print(time_range)

    sys.exit(0)