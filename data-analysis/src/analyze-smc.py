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
import plot.trace
import plot.ap_selection
import plot.gps

import parsing.utils

import analysis.metrics
import analysis.trace
import analysis.gps
import analysis.ap_selection.rssi
import analysis.ap_selection.gps
import analysis.smc.sessions
import analysis.smc.utils

import mapping.utils

import shapely.geometry

from random import randint

from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple

from prettytable import PrettyTable

from sklearn import linear_model

def plot_coverage(database, output_dir):

    plt.style.use('classic')

    plot_configs = {
        'time' : {
                'x-label' : 'time (sec)',
                'coef' : 1.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : 'blue',
                'x-ticks' : [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
                'x-lim' : [0.0, 30.0]
        },
        'speed' : {
                'x-label' : 'speed (m/s)',
                'coef' : 1.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : 'red',
                'x-ticks' : [0.0, 12.5, 25.0, 37.5, 50.0],
                'x-lim' : [0.0, 50.0]
        }
    }

    fig = plt.figure(figsize = (2.0 * 3.0, 2.5))
    axs = []
    for s, stat in enumerate(plot_configs.keys()):
        # add ax objs to figure
        axs.append(fig.add_subplot(1, 2, s + 1))
        # add titles to ax objs
        axs[s].set_title('contact %s' % (stat))

    for s, stat in enumerate(plot_configs.keys()):

        db = ('/%s/%s' % ('coverage', stat))
        if db not in database.keys():
            sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (db))
            return

        # mix bands
        data = database.select(db).groupby([stat]).sum().reset_index(drop = False)
        data.rename(index = str, columns = {'count' : 'counts'}, inplace = True)

        plot.utils.cdf(axs[s], data, metric = stat, plot_configs = plot_configs[stat])

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, ("coverage-cdfs.pdf")), bbox_inches = 'tight', format = 'pdf')

def plot_bands(database, output_dir):

    plt.style.use('classic')

    db = ('/%s/%s' % ('bands', 'raw'))
    if db not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (db))
        return

    # group raw data by session, ap, cell and band
    data = database.select(db).groupby(['session_id', 'cell-x', 'cell-y', 'band'])['snr'].apply(np.array).reset_index(drop = False).sort_values(by = ['cell-x', 'cell-y', 'session_id']).reset_index(drop = False)
    data['id'] = data['session_id'].astype(str) + '.' + data['cell-x'].astype(str) + '.' + data['cell-y'].astype(str)
    data['xx'] = (data['id'] != data['id'].shift(1)).astype(int).cumsum()
    data['xx'] -= 1

    bands = {0 : {'title' : 'RSS per session & cell\n(2.4 GHz)', 'color' : 'red'}, 1 : {'title' : '5 GHz', 'color' : 'blue'}}

    fig = plt.figure(figsize = (2.0 * 3.0, 2.5))
    axs = []
    for b, band in enumerate(bands.keys()):
        # add ax objs to figure
        axs.append(fig.add_subplot(1, 2, b + 1))
        # add titles to ax objs
        axs[b].set_title('%s' % (bands[band]['title']))

        axs[b].xaxis.grid(True, ls = 'dotted', lw = 0.25)
        axs[b].yaxis.grid(True, ls = 'dotted', lw = 0.25)

        _data = data[data['band'] == band]

        # max & min
        yy_max = _data['snr'].apply(np.amax)
        yy_min = _data['snr'].apply(np.amin)

        # axs[b].plot(_data.index, yy_max, color = 'black', linewidth = .5, linestyle = ':', label = 'max')
        # axs[b].plot(_data.index, yy_min, color = 'black', linewidth = .5, linestyle = '-.', label = 'min')
        # fill area in-between max and min
        axs[b].fill_between(_data['xx'], yy_min, yy_max, 
            facecolor = bands[band]['color'], alpha = .50, interpolate = True, linewidth = 0.0,
            label = '[min, max]')

        # median
        axs[b].plot(_data['xx'], _data['snr'].apply(np.median), color = 'black', linewidth = .25, linestyle = '-', label = 'median')

        axs[b].set_xlabel('session & cell pairs')
        axs[b].set_ylabel("RSS (dBm)")

        # no x-ticks
        axs[b].set_xticks(np.arange(0, analysis.metrics.custom_round(np.amax(data['xx']), base = 10) + 10, 10))

        legend = axs[b].legend(
            fontsize = 10, 
            ncol = 1, loc = 'upper right',
            handletextpad = 0.2, handlelength = 1.5, labelspacing = 0.2, columnspacing = 0.5)

        for legobj in legend.legendHandles:
            legobj.set_linewidth(0.5)


    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, ("bands-rss-distribution.pdf")), bbox_inches = 'tight', format = 'pdf')

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--input-dir", 
         help = """dir w/ smc data""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save graphs & other output data""")

    args = parser.parse_args()

    if not args.input_dir:
        sys.stderr.write("""%s: [ERROR] must provide a dir w/ input files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] must provide an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # analysis.smc.sessions.extract(args.input_dir)
    database = analysis.smc.utils.get_db(args.input_dir)
    plot_coverage(database, args.output_dir)
    plot_bands(database, args.output_dir)

    sys.exit(0)