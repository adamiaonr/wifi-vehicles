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

import parsing.utils

import analysis.metrics
import analysis.trace
import analysis.ap_selection

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

# CELL_SIZE = 20.0
CELL_SIZE = 500.0

# number of cells in grid, in x and y directions
X_CELL_NUM = int(np.ceil((mapping.utils.gps_to_dist(LATN, 0.0, LATS, 0.0) / CELL_SIZE)))
Y_CELL_NUM = int(np.ceil((mapping.utils.gps_to_dist(LAT, LONW, LAT, LONE) / CELL_SIZE)))

def plot_ap_selection(input_dir, trace_nr, output_dir, 
    gt_metric, 
    methods,
    plot_configs):

    plt.style.use('classic')
    # 2 subplots per method
    h = (2 * len(methods)) + 1
    fig = plt.figure(figsize = (12.5, h * 3.0))

    time_limits = [None, None]
    axs = []

    # plot gt throughput per interval
    ax = fig.add_subplot(h, 1, 1)
    axs.append(ax)
    plot.trace.best(ax, args.input_dir, args.trace_nr, metric = gt_metric, time_limits = time_limits)

    # plot results of each selection method
    for i, method in enumerate(methods):

        # add 2 subplots
        ax = [fig.add_subplot(h, 1, (i + 1) * 2), fig.add_subplot(h, 1, ((i + 1) * 2) + 1)]
        # plot ap selection results
        if method == 'best-rssi':
            plot.ap_selection.rssi(ax, args.input_dir, args.trace_nr,
                gt_metric = gt_metric,
                compare_to = {
                    'method' : 'best' },    # absolute best, the 'cadillac'
                plot_configs = plot_configs[method],
                time_limits = time_limits)

        elif method == 'best-cell':
            plot.ap_selection.cell(ax, args.input_dir, args.trace_nr,
                gt_metric = gt_metric,
                compare_to = {
                    'method' : 'best-rssi',
                    'db-name' : ('/%s/%s/%d/%d' % ('best-rssi', plot_configs['best-rssi']['method'], int(plot_configs['best-rssi']['args']['scan-period']), int(plot_configs['best-rssi']['args']['scan-time'])))
                    },
                plot_configs = plot_configs[method],
                time_limits = time_limits)

        # add list of plots to axs
        axs += ax

    fig.tight_layout()
    plt.savefig(os.path.join(output_dir, ("ap-selection-methods.pdf")), bbox_inches = 'tight', format = 'pdf')

def plot_best(input_dir, trace_nr, output_dir, metrics = ['throughput']):

    plt.style.use('classic')
    h = len(metrics)
    fig = plt.figure(figsize = (12.5, h * 2.5))

    # best metric per interval
    time_limits = [None, None]
    axs = []
    for i, metric in enumerate(metrics):
        ax = fig.add_subplot(h, 1, i + 1)
        plot.trace.best(ax, args.input_dir, args.trace_nr, metric = metric, time_limits = time_limits)
        axs.append(ax)

    # # dist. of mobile node to each fixed pos.
    # ax = fig.add_subplot(h, 1, h)
    # plot.trace.distances(ax, args.input_dir, args.trace_nr)
    # axs.append(ax)

    # adjust time xx scale to be the same for all graphs
    # divide xx axis in 5 ticks
    for ax in axs:
        #x-label
        ax.set_xlabel('time')
        # x-lim
        ax.set_xlim(time_limits[0], time_limits[1])
        #x-ticks
        xticks = plot.utils.get_time_xticks(time_limits)
        ax.set_xticks(xticks)
        ax.set_xticklabels([str(xt)[11:-7] for xt in xticks])

    fig.autofmt_xdate()
    fig.tight_layout()
    plt.savefig(os.path.join(output_dir, ("cadillac.pdf")), bbox_inches = 'tight', format = 'pdf')

def handle_list_traces(input_dir, trace_nr):

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

    # print info about the requested trace
    trace_info = analysis.trace.get_info(input_dir, trace_nr)

    if not trace_info.empty:
        table = PrettyTable(list(['mac', 'tcp', 'udp', 'tcp-gps', 'udp-gps']))
        for i, row in trace_info.iterrows():
            table.add_row([
                ('%s' % (row['mac'])),
                ('%s' % (int(row['tcp']))), 
                ('%d' % (int(row['udp']))), 
                ('%d' % (int(row['tcp-gps']))),
                ('%s' % (int(row['udp-gps'])))])

        print("%s: dataset stats :" % (sys.argv[0]))
        print(table)

    else:
        sys.stderr.write("""%s: [ERROR] trace info not available for trace %s\n""" % (sys.argv[0], trace_nr))

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

    trace_list = analysis.trace.get_list(args.input_dir)

    if trace_list.empty:
        sys.stderr.write("""%s: [ERROR] no trace information available\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)        

    if not args.trace_nr:
        sys.stderr.write("""%s: [ERROR] must provide a trace nr. to analyze\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)
    else:
        if int(args.trace_nr) not in list(trace_list['trace-nr']):
            sys.stderr.write("""%s: [ERROR] provided trace nr. doesn't exist\n""" % sys.argv[0]) 
            parser.print_help()
            sys.exit(1)

    if args.list_traces:
        handle_list_traces(args.input_dir, args.trace_nr)
        sys.exit(0)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] must provide an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)
    
    trace = trace_list[trace_list['trace-nr'] == int(args.trace_nr)]
    trace_dir = os.path.join(args.input_dir, ("trace-%03d" % (int(args.trace_nr))))
    trace_db_file = os.path.join(trace_dir, "processed/database.hdf5")

    trace_output_dir = os.path.join(args.output_dir, ("trace-%03d" % (int(args.trace_nr))))
    if not os.path.isdir(trace_output_dir):
        os.makedirs(trace_output_dir)

    # if trace rx data doesn't exist, extract it now
    if not os.path.isfile(trace_db_file):
        # extract rx data w/ default options
        analysis.trace.extract_rx_features(args.input_dir, args.trace_nr, protocol = trace['proto'].values[-1])

    # # calculate the 'cadillac' periods, according to different metrics
    # for metric in ['throughput', 'wlan rssi', 'dist']:
    #     analysis.trace.calc_best(args.input_dir, args.trace_nr, metric = metric)
        
    # plot_best(args.input_dir, args.trace_nr, trace_output_dir, metrics = ['throughput', 'wlan rssi', 'dist'])

    # rssi analysis (default args, i.e., 'periodic scan' analysis)
    # analysis.ap_selection.rssi(args.input_dir, args.trace_nr,
    #     method = 'periodic',
    #     args = {'periodic' : {'scan_period' : 20.0, 'scan_time' : 1.0}})

    # cell history
    data = analysis.ap_selection.cell(args.input_dir, args.trace_nr,
        args = {'cell-size' : 10.0})

    gt_metric = 'throughput'
    plot_ap_selection(args.input_dir, args.trace_nr, trace_output_dir, 
        gt_metric = gt_metric,
        methods = ['best-rssi', 'best-cell'],
        plot_configs = {
            'best-rssi' : {
                    'method' : 'periodic',
                    'args' : {'scan-period' : 10.0, 'scan-time' : 1.0},
                    'title' : ('scan + best RSS (period : %s sec, scan duration : %s sec)' % (10.0, 1.0)),
                    'sub-title' : ('scan + best RSS (%s gain)' % (gt_metric)),
                    'y-label' : 'throughput (Mbps)',
                    'coef' : 1.0 / 1000000.0
            },
            'best-cell' : {
                    'args' : {'cell-size' : 10.0},
                    'title' : ('best mean thghpt per cell, in other laps (cell-size : %s m)' % (10.0)),
                    'sub-title' : ('best mean thghpt per cell (%s gain)' % (gt_metric)),
                    'y-label' : 'throughput (Mbps)',
                    'coef' : 1.0 / 1000000.0
            }
        })

    sys.exit(0)