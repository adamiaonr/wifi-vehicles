import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import os
import re
import argparse
import sys
import glob
import math
import gmplot
import time
import subprocess
import csv
# for parallel processing of sessions
import multiprocessing as mp 
import hashlib
import datetime
import json

import plot.utils
import mapping.utils

import analysis.metrics
import analysis.gps

from random import randint
from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple
from matplotlib.gridspec import GridSpec
from prettytable import PrettyTable

matplotlib.rcParams.update({'font.size': 16})

def distances(ax, input_dir, trace_nr, time_limits = None):

    ax.xaxis.grid(True)
    ax.yaxis.grid(True)

    ax.set_title('dist. (in m) of mobile node to each fixed pos. (trace %s)' % (trace_nr))

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']

    # get dist. data
    dist_data = analysis.trace.get_dist(input_dir, trace_nr)
    # aux variables
    if not time_limits:
        time_limits = [None, None]

    visited = []
    for i, client in clients.iterrows():

        # avoid going through same pos twice
        if client['label'] in visited:
            continue
        else:
            visited.append(client['label'])

        _dist_data = dist_data[ ['timestamp', client['mac']] ]
        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _dist_data['timestamp'] ]
        plot.utils.update_time_limits(time_limits, dates)

        ax.plot_date(
            dates,
            _dist_data[client['mac']],
            linewidth = 0.0, linestyle = '-', color = client['color'], label = client['label'], 
            marker = 'o', markersize = 2.50, markeredgewidth = 0.0)

    ax.legend(
        fontsize = 10, 
        ncol = 4, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    # divide xx axis in 5 ticks
    xticks = plot.utils.get_time_xticks(time_limits)

    ax.set_xlabel("time")
    ax.set_ylabel("distance (m)")

    ax.set_xlim(time_limits[0], time_limits[1])
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(xt)[11:-7] for xt in xticks])

def best(ax, input_dir, trace_nr, 
    metric = 'throughput',
    plot_configs = {
        'throughput' : {
            'y-label' : 'throughput (Mbps)',
            'coef' : 1.0 / 1000000.0
        },
        'wlan rssi' : {
            'y-label' : 'RSS (dbm)',
            'coef' : 1.0
        },
        'dist' : {
            'y-label' : 'dist (m)',
            'coef' : 1.0
        }
    },
    time_limits = None):

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))    

    db_name = ('/%s/%s' % ('best', metric))
    if db_name not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (db_name))
        return

    ax.xaxis.grid(True)
    ax.yaxis.grid(True)
    ax.set_title('pos. w/ best %s per 0.5 sec segment (trace %s)' % (metric, trace_nr))

    data = database.select(db_name).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
    # FIXME: why do we end up w/ duplicate 'interval-tmstmp' values?
    data = data.drop_duplicates(subset = ['interval-tmstmp'])

    # (1) plot background segments w/ color of best mac for the segment
    # find blocks of consecutive mac addrs
    data['block'] = ((data.best.shift(1) != data.best) | ((data['interval-tmstmp'].shift(1) - data['interval-tmstmp']) < -0.5)).astype(int).cumsum()
    data['interval-tmstmp-str'] = [ str(tmstmp) for tmstmp in data['interval-tmstmp'] ]
    segments = data.groupby(['best','block'])['interval-tmstmp'].apply(np.array).reset_index(drop = False).sort_values(by = ['block'])

    for i, client in clients.iterrows():
        for i, segment in segments[segments['best'] == client['mac']].iterrows():
            dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in [ segment['interval-tmstmp'][0], segment['interval-tmstmp'][-1] + 0.5 ] ]
            ax.axvspan(dates[0], dates[-1], linewidth = 0.0, facecolor = client['color'], alpha = 0.20)
            # ax.axvline(dates[-1], color = client['color'], linestyle = '--', linewidth = .75)

    # (2) plot all metric values
    if not time_limits:
        time_limits = [None, None]

    macs = []
    for i, client in clients.iterrows():

        _data = data[data['best'] == client['mac']]
        if _data.empty:
            continue
        macs.append(client['mac'])

        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ]
        plot.utils.update_time_limits(time_limits, dates)

        ax.plot(
            dates,
            _data[client['mac']] * plot_configs[metric]['coef'],
            linewidth = 0.0, 
            linestyle = '-', 
            color = client['color'], 
            label = client['label'], 
            markersize = 2.50, 
            marker = 'o', 
            markeredgewidth = 0.0)

    # plot a black line w/ throughput for all mac addrs
    _data = data.iloc[::5, :]
    dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ]
    ax.plot(
        dates,
        (_data[macs].max(axis = 1).values) * plot_configs[metric]['coef'],
        alpha = .5,
        linewidth = 0.75, 
        linestyle = '-', 
        color = 'black', 
        marker = None)

    ax.legend(
        fontsize = 10, 
        ncol = 4, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    ax.set_ylabel(plot_configs[metric]['y-label'])

    # x-label
    ax.set_xlabel('time')
    # x-lims
    ax.set_xlim(time_limits[0], time_limits[1])
    # divide xx axis in 5 ticks
    xticks = plot.utils.get_time_xticks(time_limits)
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(xt)[11:-7] for xt in xticks])

    plt.gcf().autofmt_xdate()
    