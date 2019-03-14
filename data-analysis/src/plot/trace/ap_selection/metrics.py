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
#   - plotting
import plot.trace
import plot.utils
import plot.gps
#   - analysis
import analysis.trace

matplotlib.rcParams.update({'font.size': 16})

def scripted_evolution(input_dir, trace_nr, 
    trace_output_dir,
    args = {'metric' : 'throughput'},
    configs = {
        'db' : '/selection/throughput/gps/scripted-handoffs/lap-data',
        'metric' : 'throughput', 
        'y-label' : 'throughput (Mbps)', 
        'coef' : 1.0 / 1000000.0,
        'ylim' : [0.0, 70.0]
    }):

    nodes = {
        'm1' : {
            'color' : 'red',
            'label' : '38',
            'marker' : 'o',
            'markersize' : 2.0
        },
        'w1' : {
            'color' : 'green',
            'label' : '46',
            'marker' : 'o',
            'markersize' : 2.0
        },
        'w2' : {
            'color' : 'blue',
            'label' : '6',
            'marker' : 'o',
            'markersize' : 2.0
        },        
        'w3' : {
            'color' : 'orange',
            'label' : '11',
            'marker' : 'o',
            'markersize' : 2.0
        },
    }

    compare_dir = os.path.join(trace_output_dir, ("compare"))
    if not os.path.isdir(compare_dir):
        os.makedirs(compare_dir)

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = utils.hdfs.get_db(trace_dir, 'database.hdf5')
    database_keys = utils.hdfs.get_db_keys(trace_dir)

    # load db w/ lap data
    db_name = configs['db']
    if db_name not in database_keys:
        sys.stderr.write("""[ERROR] %s not in database. skipping.\n""" % (db_name))
        return

    data = database.select(db_name).sort_values(by = ['timed-tmstmp']).reset_index(drop = True)
    n = data['lap'].max()
    plt.style.use('classic')
    fig = plt.figure(figsize = (2.0 * (4.0), n * (2.0 * 1.5)))

    for l in xrange(2, data['lap'].max() + 1):

        # FIXME : don't count w/ 'w3' after lap 5 for trace 82
        _nodes = ['m1', 'w1', 'w2', 'w3']
        if (l > 6) & (int(trace_nr) == 82):
            _nodes = ['m1', 'w1', 'w2']

        # calc handoff script from laps [... , l - 2, l - 1]
        _data = data[(data['lap'] < l) & (data['lap'] >= 0)]
        for node in _nodes:
            if 'filter' in args:
                _data.loc[_data[node] > args['filter'], node] = np.nan
        _data.dropna()

        # determine handoff distances
        k = {1 : 1, 0 : -1}
        for d in k:

            # handoff distances depend on direction:
            #   - if E to W (ref-dist decreases): handoff is triggered at higher distance of an best
            #   - if W to E (ref-dist increases): handoff is triggered at lower distance of an best            
            hs = _data[_data['direction'] == d]
            hs = hs.sort_values(by = ['ref-dist']).reset_index(drop = True)
            for node in _nodes:
                analysis.trace.utils.metrics.smoothen(hs, column = node, span = 50)

            print(l)
            print("(%s, %s, %s)" % (n, 2, (2 * (l - 2)) + d + 1))
            ax = fig.add_subplot(n, 2, (2 * (l - 2)) + d + 1)

            ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
            ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)
            ax.set_title('lap : %s, direction : %s' % (l, ('E->W' if d == 0 else 'W->E')))

            for node in _nodes:
                ax.plot(
                    hs['ref-dist'],
                    hs[node] * configs['coef'],
                    linewidth = 1.0, linestyle = '-', color = nodes[node]['color'], label = nodes[node]['label'], 
                    marker = None, markersize = 0.0, markeredgewidth = 0.0)

            leg = ax.legend(
                fontsize = 10, 
                ncol = 4, loc = 'upper right',
                handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

            for legobj in leg.legendHandles:
                legobj.set_linewidth(2.0)

            ax.set_xlabel("distance (m)")
            ax.set_ylabel(configs['y-label'])
            ax.set_xlim(data['ref-dist'].min(), data['ref-dist'].max())

    fig.tight_layout()
    plt.savefig(os.path.join(compare_dir, ("scripted-evolution/%s.pdf" % (args['metric']))), bbox_inches = 'tight', format = 'pdf')

    # totals for all laps
    plt.style.use('classic')
    fig = plt.figure(figsize = (2.0 * (3.0), 1.0 * (2.0 * 1.5)))

    # calc handoff script from laps [... , l - 2, l - 1]
    _data = data[data['lap'] >= 0]
    for node in nodes:
        if 'filter' in args:
            _data.loc[_data[node] > args['filter'], node] = np.nan

    _data.dropna()

    # determine handoff distances
    k = {1 : 1, 0 : -1}
    for d in k:

        # handoff distances depend on direction:
        #   - if E to W (ref-dist decreases): handoff is triggered at higher distance of an best
        #   - if W to E (ref-dist increases): handoff is triggered at lower distance of an best            
        hs = _data[_data['direction'] == d]
        hs = hs.sort_values(by = ['ref-dist']).reset_index(drop = True)
        for node in nodes:
            analysis.trace.utils.metrics.smoothen(hs, column = node, span = 50)

        ax = fig.add_subplot(1, 2, d + 1)

        ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
        ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)
        ax.set_title('%s' % (('east to west' if d == 0 else 'west to east')))

        for node in nodes:
            ax.plot(
                hs['ref-dist'],
                hs[node] * configs['coef'],
                linewidth = 1.0, linestyle = '-', color = nodes[node]['color'], label = nodes[node]['label'], 
                marker = None, markersize = 0.0, markeredgewidth = 0.0)

        leg = ax.legend(
            fontsize = 10, 
            ncol = 4, loc = 'upper right',
            handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

        for legobj in leg.legendHandles:
            legobj.set_linewidth(2.0)

        ax.set_xlabel("distance (m)")
        ax.set_ylabel(configs['y-label'])
        ax.set_xlim(data['ref-dist'].min(), data['ref-dist'].max())
        ax.set_ylim(configs['ylim'])

    fig.tight_layout()
    plt.savefig(os.path.join(compare_dir, ("scripted-evolution/%s-totals.pdf" % (args['metric']))), bbox_inches = 'tight', format = 'pdf')

def handoff_analysis(input_dir, trace_nr, trace_output_dir,
    configs):

    compare_dir = os.path.join(trace_output_dir, ("compare"))
    if not os.path.isdir(compare_dir):
        os.makedirs(compare_dir)

    plt.style.use('classic')
    fig = plt.figure(figsize = (1.5 * 4.0, 3.0))

    axs = []
    for i, case in enumerate(['handoff-nr', 'contact-time']):
        axs.append(fig.add_subplot(1, 2, i + 1))
        axs[-1].xaxis.grid(True, ls = 'dotted', lw = 0.05)
        axs[-1].yaxis.grid(True, ls = 'dotted', lw = 0.05)

    # keep track of xticks and labels
    xx = 0.0
    xticks = []
    xtickslabels = []
    # fixed bar graph parameters
    barwidth = 0.5
    # space between big groups of bars
    interspace = 2.0 * barwidth
    # space between bars withing groups
    intraspace = 1.0 * barwidth

    axs[0].set_title('(a) # of handoffs')
    axs[1].set_title('(b) connection duration')

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = utils.hdfs.get_db(trace_dir, 'database.hdf5')
    # database = analysis.trace.get_db(input_dir, trace_nr)
    database_keys = utils.hdfs.get_db_keys(trace_dir)

    for i, method in enumerate(sorted(configs['methods'].keys())):

        db_name = configs['methods'][method]['db']
        if db_name not in database_keys:
            sys.stderr.write("""[ERROR] %s not in database. skipping.\n""" % (db_name))
            continue

        data = database.select(db_name).sort_values(by = ['timed-tmstmp']).reset_index(drop = True)

        if 'time-limits' in configs:
            data = data[(data['timed-tmstmp'] > configs['time-limits'][0]) & (data['timed-tmstmp'] < configs['time-limits'][1])]

        data['ap-block'] = ((data['best'] != data['best'].shift(1))).astype(int).cumsum()
        times = data.groupby(['ap-block', 'best'])['timed-tmstmp'].apply(list).reset_index(drop = False)
        times = times.dropna(subset = ['best'])
        times['timed-tmstmp'] = times['timed-tmstmp'].apply(lambda x : sorted(x))
        times['duration'] = times['timed-tmstmp'].apply(lambda x : x[-1] - x[0])
        times['duration'] = times['duration'] + 0.5

        # (1) handoffs (nr. of blocks - 1) (bar graph)
        axs[0].bar(xx - (barwidth / 2.0),
            len(times) - 1.0,
            width = barwidth, linewidth = 0.250, alpha = .75, 
            color = configs['methods'][method]['color'], label = configs['methods'][method]['label'])

        # xticks & xticklabel handling
        xticks.append(xx)
        xtickslabels.append('')
        if i < (len(configs['methods'].keys()) - 1):
            xx += interspace

        # (2) ap contact times (cdf)
        plot.utils.cdf(axs[1], times[['ap-block', 'duration']], metric = 'duration',
            plot_configs = {
                'x-label' : 'duration (sec)',
                'coef' : 1.0,
                'linewidth' : 1.0,
                'markersize' : 0.0,
                'marker' : None,
                'markeredgewidth' : 0.0,
                'label' : '',
                'color' : configs['methods'][method]['color'],
                # 'x-ticks' : [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
                # 'x-lim' : [-80.0, -30.0]
            })

    # legend
    axs[0].legend(
        fontsize = 9, 
        ncol = 1, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    # leg = axs[1].legend(
    #     fontsize = 9, 
    #     ncol = 1, loc = 'lower right',
    #     handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    # for legobj in leg.legendHandles:
    #     legobj.set_linewidth(3.0)

    # x-axis
    axs[0].set_xlim(-(1.5 * barwidth), xx + (1.5 * barwidth))
    axs[0].set_xticks(xticks)
    axs[0].set_xticklabels(xtickslabels, rotation = 30, ha = 'right')
    # y-axis
    #   - data volume
    axs[0].set_ylabel('# of handoffs')
    # # so that legend doesn't overlap w/ bars
    axs[0].set_ylim(0.0, np.ceil(axs[0].get_ylim()[1] * 1.50))

    fig.tight_layout()
    fig.savefig(
        os.path.join(compare_dir, ("%s.pdf" % (configs['filename']))), bbox_inches = 'tight', format = 'pdf')

def compare(
    input_dir, trace_nr, trace_output_dir, 
    configs):

    compare_dir = os.path.join(trace_output_dir, ("compare"))
    if not os.path.isdir(compare_dir):
        os.makedirs(compare_dir)

    plt.style.use('classic')

    fig = plt.figure(figsize = (4.0, 3.0))
    # axis:
    #   ax : data volume
    #   ax2 : median throughput
    ax = fig.add_subplot(1, 1, 1)
    ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)
    ax2 = ax.twinx()

    # keep track of xticks and labels
    xx = 0.0
    xticks = []
    xtickslabels = []
    # fixed bar graph parameters
    barwidth = 0.5
    # space between big groups of bars
    interspace = 3.0 * barwidth
    # space between bars within groups
    intraspace = 1.0 * barwidth

    # load & plot performance data
    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = utils.hdfs.get_db(trace_dir, 'database.hdf5')
    # database = analysis.trace.get_db(input_dir, trace_nr)
    database_keys = utils.hdfs.get_db_keys(trace_dir)

    label = ['data volume', 'median throughput']
    for i, method in enumerate(sorted(configs['methods'].keys())):
        
        db_name = configs['methods'][method]['db']
        if db_name not in database_keys:
            sys.stderr.write("""[ERROR] %s not in database. skipping.\n""" % (db_name))
            continue

        data = database.select(db_name).sort_values(by = ['timed-tmstmp']).reset_index(drop = True)
        data.rename(index = str, columns = {'best-val' : 'throughput'}, inplace = True)

        if 'time-limits' in configs:
            data = data[(data['timed-tmstmp'] > configs['time-limits'][0]) & (data['timed-tmstmp'] < configs['time-limits'][1])]

        # # FIXME : i don't think this is cheating, buuuut...
        # if 'strongest-rss' in method:
        #     data.loc[data['scan-period'] == 1, 'throughput'] = 0.0

        # if ('3:' in method) or ('1:' in method):
        #     print(method)
        #     print(data)
        #     print(data.groupby(['best']).size().reset_index())
        #     print(data.groupby(['best']).size().reset_index()[0].sum())

        # data volume
        ax.bar(xx - barwidth,
            ((data['throughput'] * 0.5).sum() * (1.0 / 1000000000.0)) / 8.0,
            width = barwidth, linewidth = 0.250, alpha = .75, 
            color = 'red', label = label[0])

        # median throughput
        ax2.bar(xx,
            (data['throughput']).median() * (1.0 / 1000000.0),
            width = barwidth, linewidth = 0.250, alpha = .75, 
            color = 'blue', label = label[1])

        # trick to add ax2's legend to ax's legend
        ax.bar(np.nan, np.nan, label = label[1], linewidth = 0.250, alpha = .75, color = 'blue')
        label[0] = ''
        label[1] = ''

        # xticks & xticklabel handling
        xticks.append(xx)
        xtickslabels.append(configs['methods'][method]['x-ticklabel'])
        if i < (len(configs['methods'].keys()) - 1):
            xx += interspace

        # FIXME: force garbage collector to delete (?)
        data = None

    # legend
    ax.legend(
        fontsize = 9, 
        ncol = 1, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    # x-axis
    ax.set_xlim(-(1.5 * barwidth), xx + (1.5 * barwidth))
    ax.set_xticks(xticks)
    ax.set_xticklabels(xtickslabels, rotation = 30, ha = 'right')
    # y-axis
    #   - data volume
    ax.set_ylabel('data volume (GByte)')
    # so that legend doesn't overlap w/ bars
    ax.set_ylim(0.0, np.ceil(ax.get_ylim()[1] * 1.25))
    #   - median throughput
    k = float(len(ax.get_yticks()) - 1)
    d = ax2.get_yticks()[1] - ax2.get_yticks()[0]
    ax2.set_ylim(0.0, (2.0 * k) * d)
    ax2.set_ylabel('median throughput (Mbps)')

    fig.tight_layout()
    fig.savefig(
        os.path.join(compare_dir, ("%s.pdf" % (configs['filename']))), bbox_inches = 'tight', format = 'pdf')