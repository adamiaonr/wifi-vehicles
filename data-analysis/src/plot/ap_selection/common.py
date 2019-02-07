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
import timeit
import subprocess
import csv
# for parallel processing of sessions
import multiprocessing as mp 
import hashlib
import datetime
import json

import geopandas as gp

import plot.utils
import plot.gps

import mapping.utils

import analysis.metrics
import analysis.gps

import shapely.geometry

from random import randint
from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple
from matplotlib.gridspec import GridSpec
from prettytable import PrettyTable

matplotlib.rcParams.update({'font.size': 16})

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

    database = analysis.trace.get_db(input_dir, trace_nr)    
    for i, method in enumerate(sorted(configs['methods'].keys())):

        db_name = configs['methods'][method]['db']
        if db_name not in database.keys():
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

def optimal(input_dir, trace_nr, trace_output_dir,
    configs):

    compare_dir = os.path.join(trace_output_dir, ("compare"))
    if not os.path.isdir(compare_dir):
        os.makedirs(compare_dir)

    plt.style.use('classic')
    fig = plt.figure(figsize = (4.0, 3.0))
    ax = fig.add_subplot(1, 1, 1)
    ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)

    # load optimal data
    database = analysis.trace.get_db(input_dir, trace_nr)    
    db_name = configs['optimal']['db']
    if db_name not in database.keys():
        sys.stderr.write("""[ERROR] %s not in database. aborting.\n""" % (db_name))
        return

    optimal_data = database.select(db_name).sort_values(by = ['timed-tmstmp']).reset_index(drop = True)
    optimal_data.rename(index = str, columns = {'best-val' : 'throughput'}, inplace = True)
    # calculate acc. data volume
    optimal_data['dv-opt'] = ((optimal_data['throughput'] * 0.5) * (1.0 / 1000000000.0)) / 8.0

    # load & plot performance data
    label = ['data volume', 'median throughput']
    for i, method in enumerate(sorted(configs['methods'].keys())):

        db_name = configs['methods'][method]['db']
        if db_name not in database.keys():
            sys.stderr.write("""[ERROR] %s not in database. skipping.\n""" % (db_name))
            continue

        data = database.select(db_name).sort_values(by = ['timed-tmstmp']).reset_index(drop = True)
        data.rename(index = str, columns = {'best-val' : 'throughput'}, inplace = True)
        # FIXME : i don't think this is cheating, buuuut...
        if 'strongest-rss' in method:
            data.loc[data['scan-period'] == 1, 'throughput'] = 0.0

        data['dv'] = ((data['throughput'] * 0.5) * (1.0 / 1000000000.0)) / 8.0

        data = pd.merge(data[['timed-tmstmp', 'dv']], optimal_data[['timed-tmstmp', 'dv-opt']], on = ['timed-tmstmp'], how = 'outer')
        data = data.fillna(0.0)
        data = data.drop_duplicates(subset = ['timed-tmstmp']).reset_index(drop = True)
        data = data.sort_values(by = ['timed-tmstmp']).reset_index(drop = True)

        if 'time-limits' in configs:
            data = data[(data['timed-tmstmp'] > configs['time-limits'][0]) & (data['timed-tmstmp'] < configs['time-limits'][1])]

        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in data['timed-tmstmp'] ]

        data['dv'] = data['dv'].cumsum()
        data['dv-opt'] = data['dv-opt'].cumsum()
        data['error'] = ((data['dv-opt'] - data['dv']) / data['dv-opt']) * 100.0
        analysis.metrics.smoothen(data, column = 'error', span = 10)
        ax.plot(
            dates,
            100.0 - data['error'],
            linewidth = 1.0, linestyle = '-', color = configs['methods'][method]['color'], label = configs['methods'][method]['label'], 
            marker = None, markersize = 0.0, markeredgewidth = 0.0)

    leg = ax.legend(
        fontsize = 9, 
        ncol = 1, loc = 'lower right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    for legobj in leg.legendHandles:
        legobj.set_linewidth(3.0)

    ax.set_xlabel("time (sec)")
    ax.set_ylabel("data vol. (% of optimal)")

    # divide xx axis in 5 ticks
    time_limits = [datetime.datetime.fromtimestamp(configs['time-limits'][0]), datetime.datetime.fromtimestamp(configs['time-limits'][1])]
    # x-lims : set w/ time_limits
    ax.set_xlim(time_limits[0], time_limits[1])
    # x-ticks : 
    xticks = plot.utils.get_time_xticks(time_limits)
    ax.set_xticks(xticks)
    xticklabels = [''] * len(xticks)
    for i in list(np.arange(0, len(xticklabels), 5)):
        xticklabels[i] = (((xticks[i].astype('uint64') / 1e6).astype('uint32')) - ((xticks[0].astype('uint64') / 1e6).astype('uint32')))
    ax.set_xticklabels(xticklabels, ha = 'center')

    ax.set_ylim(-5.0, 100.0)
    ax.set_yticks([0.0, 20.0, 40.0, 60.0, 80.0, 100.0])

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
    # space between bars withing groups
    intraspace = 1.0 * barwidth

    # load & plot performance data
    database = analysis.trace.get_db(input_dir, trace_nr)
    label = ['data volume', 'median throughput']
    for i, method in enumerate(sorted(configs['methods'].keys())):
        
        db_name = configs['methods'][method]['db']
        if db_name not in database.keys():
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