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
