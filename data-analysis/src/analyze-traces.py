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
import analysis.ap_selection.rssi

import shapely.geometry

from random import randint

from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple

from prettytable import PrettyTable

from sklearn import linear_model

plt.style.use('classic')

def init(input_dir, output_dir, traces):

    trace_list = analysis.trace.get_list(input_dir)

    for trace_nr in traces:
        trace = trace_list[trace_list['trace-nr'] == int(trace_nr)]
        # generate trace db filename
        trace_dir = os.path.join(args.input_dir, ("trace-%03d" % (int(trace_nr))))
        trace_db_file = os.path.join(trace_dir, "processed/database.hdf5")
        if not os.path.isfile(trace_db_file):
            # extract rx data w/ default options
            analysis.trace.extract_rx_features(input_dir, trace_nr, protocol = trace['proto'].values[-1])

def plot_bands(input_dir, output_dir, traces, metrics = ['wlan rssi', 'wlan data rate', 'throughput']):

    plot_configs = {
        'wlan rssi' : {
                'x-label' : 'distance (m)',
                'y-label' : 'RSS (dBm)',
                'coef' : 1.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : ''
        },
        'wlan data rate' : {
                'x-label' : 'distance (m)',
                'y-label' : 'wlan data rate (Mbps)',
                'coef' : 1.0 / 1000000.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : ''
        },
        'throughput' : {
                'x-label' : 'distance (m)',
                'y-label' : 'throughput (Mbps)',
                'coef' : 1.0 / 1000000.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : ''
        }
    }

    # get trace info
    trace_list = analysis.trace.get_list(input_dir)
    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    clients = mac_addrs[mac_addrs['type'] == 'client']

    # len(metrics) x 2 plots
    figs = defaultdict(plt.figure)
    axs = defaultdict(list)
    for m, metric in enumerate(metrics):

        # add figure
        figs[metric] = plt.figure(figsize = (2.0 * 3.0, 2.0))
        # add ax objs to figure
        axs[metric] = [figs[metric].add_subplot(1, 2, 1), figs[metric].add_subplot(1, 2, 2)]
        # add titles to ax objs
        axs[metric][0].set_title('%s vs. dist.' % (metric))
        axs[metric][1].set_title('%s' % (metric))

    # to calc cdfs on-the-fly, we use a dict of dataframes
    cdf = {'2.4 GHz' : defaultdict(pd.DataFrame), '5 GHz' : defaultdict(pd.DataFrame)}
    bands = {'2.4 GHz' : {'label' : '2.4 GHz', 'color' : 'red'}, '5 GHz' : {'label' : '5 GHz', 'color' : 'blue'}}
    for trace_nr in traces:

        trace = trace_list[trace_list['trace-nr'] == int(trace_nr)]
        trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
        database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

        # extract metric data
        for i, client in clients.iterrows():

            db_name = ('/%s/%s' % ('interval-data', client['mac']))
            if db_name not in database.keys():
                continue

            # load data for a client mac
            data = database.select(db_name)
            if data.empty:
                continue

            # fix 'nan' gaps in ['lat', 'lon'] by time interpolation
            analysis.trace.fix_gaps(data, subset = ['lat', 'lon'])
            # calculate distances
            pos = [ [ row['lat'], row['lon'] ] for index, row in data[['lat', 'lon']].iterrows() ]
            data['distance'] = [ mapping.utils.gps_to_dist(client['lat'], client['lon'], p[0], p[1]) for p in pos ]

            band = ''
            if trace['channel'].values[-1] in [36, 40]:
                band = '5 GHz'
            elif trace['channel'].values[-1] in [1, 6, 11]:
                band = '2.4 GHz'

            for metric in metrics:

                plot_configs[metric]['label'] = bands[band]['label']
                plot_configs[metric]['color'] = bands[band]['color']

                # partial 'vs dist.' plot
                plot.utils.vs(axs[metric][0], data, metrics = ['distance', metric], plot_configs = plot_configs[metric])
                # cdfs on-the-fly
                cdf[band][metric] = pd.concat([cdf[band][metric], data.groupby([metric]).size().reset_index(name = 'counts')], ignore_index = True)
                cdf[band][metric].groupby([metric])['counts'].sum().reset_index()

            bands[band]['label'] = ''

    for fb in cdf:
        for metric in cdf[fb]:
            
            plot_configs[metric]['label'] = fb
            plot_configs[metric]['color'] = bands[fb]['color']
            plot_configs[metric]['x-label'] = plot_configs[metric]['y-label']

            plot.utils.cdf(axs[metric][1], cdf[fb][metric], metric = metric, plot_configs = plot_configs[metric])

    band_dir = os.path.join(output_dir, ("freq-band-stats"))
    if not os.path.isdir(band_dir):
        os.makedirs(band_dir)

    for metric in figs:
        figs[metric].tight_layout()
        figs[metric].savefig(os.path.join(band_dir, ("%s-%s.pdf" % (metric.replace(' ', '-'), '-'.join(sorted([('%03d' % (int(t))) for t in traces]))))), bbox_inches = 'tight', format = 'pdf')

def handle_list_traces(input_dir):

    # print list of traces
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
        "--output-dir", 
         help = """dir to save graphs & other output data""")

    # trace nrs. to combine in analysis
    traces = [32, 36, 37, 45, 46, 48, 49]
    # traces = [32, 36, 46, 49]

    args = parser.parse_args()

    if not args.input_dir:
        sys.stderr.write("""%s: [ERROR] must provide a dir w/ input files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    trace_list = analysis.trace.get_list(args.input_dir)

    if trace_list.empty:
        sys.stderr.write("""%s: [ERROR] no trace information available\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if args.list_traces:
        handle_list_traces(args.input_dir, args.trace_nr)
        sys.exit(0)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] must provide an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # initialize trace data
    init(args.input_dir, args.output_dir, traces)
    
    # plot:
    #   - consider all traces in the list (tcp or udp)
    #   - 'rssi' vs. 'dist' for each band : 2.4 Ghz and 5.0 Ghz
    #   - 'throughput' vs. 'dist' for each band : 2.4 Ghz and 5.0 Ghz
    plot_bands(args.input_dir, args.output_dir, traces)

    # analysis.trace.combine(args.input_dir, to_combine = [49, 46],
    #     new_trace_nr = 55, 
    #     replace = {46 : {}, 49 : {'24:05:0f:e5:7b:6a' : '24:05:0f:e5:7b:6b'}})

    sys.exit(0)