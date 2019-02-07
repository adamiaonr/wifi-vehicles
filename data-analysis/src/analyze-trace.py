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

import analysis.ap_selection.rss
import analysis.ap_selection.gps
import analysis.ap_selection.utils

import plot.ap_selection.common

import shapely.geometry

from random import randint

from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple

from prettytable import PrettyTable

from sklearn import linear_model

def get_h(configs):

    h = 1
    for m in configs:
        if configs[m]['show'] == 'all':
            h += 2
        else:
            h += 1

    return h

def get_bandmax(data, macs):
    
    data['2.4'] = 0.0
    data['5.0'] = 0.0
    
    for band in ['2.4', '5.0']:
        data[band] = data[macs[band]].max(axis = 1)
        # smoothen data
        analysis.metrics.smoothen(data, column = band, span = 5)

def plot_bands(
    input_dir, trace_nr, output_dir,
    configs,
    time_limits = None):

    plt.style.use('classic')
    fig = plt.figure(figsize = (12.0, 2.0 * 2.25))
    axs = [fig.add_subplot(2, 1, 1), fig.add_subplot(2, 1, 2)]

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']

    database = analysis.trace.get_db(input_dir, trace_nr)

    # (1) load groud truth metric data
    gt_data = analysis.trace.load_best(database, configs['gt-metric'])
    # (2) load wlan rssi data
    rssi_db = ('/%s/%s' % ('best', 'wlan rssi'))
    if rssi_db not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (rssi_db))
        return

    rssi_data = database.select(rssi_db).drop_duplicates(subset = ['interval-tmstmp']).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)

    # (3) for each type of data, get the max for each band 
    # divide mac addrs in 2.4 and 5.0 bands
    macs = defaultdict(list)
    macs['2.4'] = list(set(clients[clients['band'] == 2.4]['mac'].tolist()))
    macs['5.0'] = list(set(clients[clients['band'] == 5.0]['mac'].tolist()))
    # isolate the max() values for each band (for both thghpt and rss)
    # FIXME : nan thghpt values get a 0.0
    gt_data = gt_data.fillna(0.0)
    get_bandmax(gt_data, macs)
    get_bandmax(rssi_data, macs)

    # (4) find time segments for which one band outperforms the other, in terms of the gt-metric
    bands = {'2.4' : {'pref' : 0, 'color' : 'red', 'label' : '2.4 GHz'}, '5.0' : {'pref' : 1, 'color' : 'blue', 'label' : '5 GHz'}}
    gt_data['pref'] = bands['2.4']['pref']
    gt_data.loc[gt_data['5.0'] > gt_data['2.4'], 'pref'] = bands['5.0']['pref']
    gt_data['block'] = ((gt_data['pref'].shift(1) != gt_data['pref'])).astype(int).cumsum()

    # (5) plot band segments of selected aps
    if not time_limits:
        time_limits = [None, None]

    segments = gt_data.groupby(['pref','block'])['interval-tmstmp'].apply(np.array).reset_index(drop = False).sort_values(by = ['block'])
    for band in bands.keys():
        for i, segment in segments[segments['pref'] == bands[band]['pref']].iterrows():

            dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in [ segment['interval-tmstmp'][0], segment['interval-tmstmp'][-1] + 0.5 ] ]
            plot.utils.update_time_limits(time_limits, dates)
    
            for ax in axs:
                ax.axvspan(dates[0], dates[-1], linewidth = 0.0, facecolor = bands[band]['color'], alpha = 0.20)

    # (6) plot max values for rssi and throughput
    for band in bands.keys():

        _data = defaultdict(pd.DataFrame)
        _data['thghpt'] = gt_data[['interval-tmstmp', band]]
        _data['rss'] = rssi_data[['interval-tmstmp', band]]

        for i, key in enumerate(['rss', 'thghpt']):

            coef = 1.0
            if key == 'thghpt':
                coef = 1.0 / 1000000.0

            dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data[key]['interval-tmstmp'] ]
            plot.utils.update_time_limits(time_limits, dates)

            # the values of ground truth metric, provided by the selected ap
            axs[i].plot(
                dates,
                _data[key][band] * coef,
                linewidth = 0.75, 
                linestyle = '-', 
                color = bands[band]['color'], 
                label = bands[band]['label'], 
                markersize = 0.0,
                markeredgewidth = 0.0)

    for ax in axs:

        ax.xaxis.grid(True)
        ax.yaxis.grid(True)

        legend = ax.legend(
            fontsize = 10, 
            ncol = 1, loc = 'upper right',
            handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

        for legobj in legend.legendHandles:
            legobj.set_linewidth(2.0)

    axs[0].set_ylabel('RSS (dBm)')
    axs[1].set_ylabel('throughput (Mbps)')

    # x-label
    for ax in axs:
        ax.set_xlabel('time (sec)')
        # x-lims : set w/ time_limits
        ax.set_xlim(time_limits[0], time_limits[1])
        xticks = plot.utils.get_time_xticks(time_limits, duration = 10.0)
        ax.set_xticks(xticks)
        xticklabels = [''] * len(xticks)
        for i in list(np.arange(0, len(xticklabels), 5)):
            xticklabels[i] = (((xticks[i].astype('uint64') / 1e6).astype('uint32')) - ((xticks[0].astype('uint64') / 1e6).astype('uint32')))
        ax.set_xticklabels(xticklabels, ha = 'center')

    fig.tight_layout()
    filename = os.path.join(output_dir, ("band-profile.pdf"))
    fig.savefig(filename, bbox_inches = 'tight', format = 'pdf')

def plot_ap_selection(input_dir, trace_nr, output_dir, 
    gt_metric, 
    methods,
    configs,
    redraw = False):

    # save plots w/ filenames w/ hashes of configs
    plot_hash = hashlib.md5(json.dumps(configs, sort_keys = True)).hexdigest()
    plot_filename = os.path.join(output_dir, ("ap-selection/ap-selection-methods-%s.pdf" % (plot_hash)))
    plot.utils.save_hash(output_dir, plot_hash = plot_hash, methods = [m for m in configs], configs = configs)

    if os.path.isfile(plot_filename) and (not redraw):
        sys.stderr.write("""[INFO] %s exists. skipping plotting.\n""" % (plot_filename))
        return

    plt.style.use('classic')

    # max. of 2 subplots per ap selection method + 1 best <gt-metric>
    h = get_h(configs)
    fig = plt.figure(figsize = (12.5, h * 2.5))

    time_limits = [None, None]
    axs = []

    # plot gt throughput per interval
    # ax = fig.add_subplot(h, 1, 1)
    # plot.trace.best(ax, args.input_dir, args.trace_nr, metric = gt_metric, time_limits = time_limits)
    # axs.append(ax)

    # plot ap selection method results
    i = 0
    for method in methods:

        if configs[method]['show'] == 'all':
            ax = [ fig.add_subplot(h, 1, (i + 1)), fig.add_subplot(h, 1, (i + 2)) ]
            i += 2
        elif configs[method]['show'] == 'gain-only':
            ax = [ fig.add_subplot(h, 1, (i + 1)) ]
            i += 1

        if method == 'best-rssi':
            plot.ap_selection.rssi(ax, args.input_dir, args.trace_nr,
                gt_metric = gt_metric,
                compare_to = { 'method' : 'best' },    # absolute best, the 'cadillac'
                configs = configs[method],
                time_limits = time_limits)

        elif (method == 'band-steering') or (method == 'history'):
            plot.ap_selection.rssi(ax, args.input_dir, args.trace_nr,
                gt_metric = gt_metric,
                compare_to = {
                    'method' : 'best-rssi',
                    'db-name' : ('/%s/%s/%d/%d' % ('best-rssi', configs['best-rssi']['method'], int(configs['best-rssi']['args']['scan-period']), int(configs['best-rssi']['args']['scan-time'])))
                    },
                configs = configs[method],
                time_limits = time_limits)

        elif method == 'best-cell':
            plot.ap_selection.cell(ax, args.input_dir, args.trace_nr,
                gt_metric = gt_metric,
                compare_to = {
                    'method' : 'best-rssi',
                    'db-name' : ('/%s/%s/%d/%d' % ('best-rssi', configs['best-rssi']['method'], int(configs['best-rssi']['args']['scan-period']), int(configs['best-rssi']['args']['scan-time'])))
                    },
                configs = configs[method],
                time_limits = time_limits)

        # add list of plots to axs
        axs += ax

    for ax in axs:
        # x-lim
        ax.set_xlim(time_limits[0], time_limits[1])

    fig.tight_layout()

    plt.savefig(plot_filename, bbox_inches = 'tight', format = 'pdf')
    plot.utils.save_hash(output_dir, plot_hash = plot_hash, methods = [m for m in configs], configs = configs)

def plot_best(input_dir, trace_nr, output_dir, metrics = ['throughput']):

    plt.style.use('classic')
    h = len(metrics)
    fig = plt.figure(figsize = (12.5, h * 2.0))

    # best metric per interval
    # time_limits = [datetime.datetime.fromtimestamp(1548779160.0), datetime.datetime.fromtimestamp(1548780180.0)]
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
    # time_limits = [datetime.datetime.fromtimestamp(1548779160.0), datetime.datetime.fromtimestamp(1548780180.0)]    
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

def plot_distances(input_dir, trace_nr, output_dir):

    plt.style.use('classic')
    fig = plt.figure(figsize = (12.5, 1.0 * 3.5))

    time_limits = [None, None]
    # dist. of mobile node to each fixed pos.
    ax = fig.add_subplot(1, 1, 1)
    plot.trace.distances(ax, args.input_dir, args.trace_nr, time_limits = time_limits)

    fig.autofmt_xdate()
    fig.tight_layout()
    plt.savefig(os.path.join(output_dir, ("distances.pdf")), bbox_inches = 'tight', format = 'pdf')

def plot_trace_description_indiv(input_dir, trace_nr, output_dir, metric, time_limits = [None, None]):

    plt.style.use('classic')
    fig = plt.figure(figsize = (5.0, 2.0))
    ax = fig.add_subplot(1, 1, 1)

    if metric in ['throughput', 'wlan data rate']:
        plot.trace.rates(ax, input_dir, trace_nr, metric, time_limits = time_limits)
    elif metric == 'channel_util':
        plot.trace.channel_util(ax, input_dir, trace_nr, time_limits = time_limits)
    elif metric == 'distances':
        plot.trace.distances(ax, input_dir, trace_nr, time_limits = time_limits)
    elif metric == 'rss':
        plot.trace.rss(ax, input_dir, trace_nr, time_limits = time_limits)

    # adjust time xx scale to be the same for all graphs
    # divide xx axis in 5 ticks
    # time_limits = [datetime.datetime.fromtimestamp(1548779160.0), datetime.datetime.fromtimestamp(1548779700.0)]    
    # time_limits = [datetime.datetime.fromtimestamp(1548779262.0), datetime.datetime.fromtimestamp(1548780180.0)]    
    # x-label
    ax.set_xlabel('time (sec)')
    # x-lim
    ax.set_xlim(time_limits[0], time_limits[1])
    if metric == 'rss':
        ax.set_ylim(ax.get_ylim()[0], np.ceil(ax.get_ylim()[1] * 0.75))
    else:
        ax.set_ylim(ax.get_ylim()[0], np.ceil(ax.get_ylim()[1] * 1.15))

    # x-ticks
    xticks = plot.utils.get_time_xticks(time_limits)
    ax.set_xticks(xticks)
    # ax.set_xticklabels([str(xt)[11:-7] for xt in xticks])
    xticklabels = [''] * len(xticks)
    for i in list(np.arange(0, len(xticklabels), 5)):
        xticklabels[i] = (((xticks[i].astype('uint64') / 1e6).astype('uint32')) - ((xticks[0].astype('uint64') / 1e6).astype('uint32')))
    ax.set_xticklabels(xticklabels, ha = 'center')

    # fig.tight_layout()
    plt.savefig(os.path.join(output_dir, ("trace-description/%s.pdf" % (('-'.join([str(v) for v in metric.split(' ')])).replace('_', '-')))), bbox_inches = 'tight', format = 'pdf')

def plot_trace_description(input_dir, trace_nr, output_dir, mode = 'all', time_limits = [None, None]):

    if mode == 'indiv':

        for metric in ['throughput', 'wlan data rate', 'channel_util', 'distances', 'rss']:
            plot_trace_description_indiv(input_dir, trace_nr, output_dir, metric)

    else:

        plt.style.use('classic')
        fig = plt.figure(figsize = ((2.0 * 6.25), 3 * (2.0 * 1.5)))

        # best metric per interval
        axs = []

        ax = fig.add_subplot(3, 2, 1)
        plot.trace.rates(ax, input_dir, trace_nr, metric = 'throughput')
        ax.set_ylim(ax.get_ylim()[0], np.ceil(ax.get_ylim()[1] * 1.15))
        axs.append(ax)

        ax = fig.add_subplot(3, 2, 2)
        plot.trace.rates(ax, input_dir, trace_nr, metric = 'wlan data rate')
        ax.set_ylim(ax.get_ylim()[0], np.ceil(ax.get_ylim()[1] * 1.15))
        axs.append(ax)

        ax = fig.add_subplot(3, 2, 3)
        plot.trace.channel_util(ax, input_dir, trace_nr)
        ax.set_ylim(ax.get_ylim()[0], np.ceil(ax.get_ylim()[1] * 1.15))
        axs.append(ax)

        ax = fig.add_subplot(3, 2, 4)
        plot.trace.distances(ax, input_dir, trace_nr)
        ax.set_ylim(ax.get_ylim()[0], np.ceil(ax.get_ylim()[1] * 1.15))
        axs.append(ax)

        ax = fig.add_subplot(3, 2, 5)
        plot.trace.rss(ax, input_dir, trace_nr)
        ax.set_ylim(ax.get_ylim()[0], np.ceil(ax.get_ylim()[1] * 0.75))
        axs.append(ax)

        ax = fig.add_subplot(3, 2, 6)
        plot.trace.rss_distance(ax, input_dir, trace_nr)

        # adjust time xx scale to be the same for all graphs
        # divide xx axis in 5 ticks
        time_limits = [datetime.datetime.fromtimestamp(time_limits[0]), datetime.datetime.fromtimestamp(time_limits[1])]
        for ax in axs:

            #x-label
            ax.set_xlabel('time (sec)')
            # x-lim
            ax.set_xlim(time_limits[0], time_limits[1])            
            # x-ticks
            xticks = plot.utils.get_time_xticks(time_limits)
            ax.set_xticks(xticks)
            # ax.set_xticklabels([str(xt)[11:-7] for xt in xticks])
            xticklabels = [''] * len(xticks)
            for i in list(np.arange(0, len(xticklabels), 5)):
                xticklabels[i] = (((xticks[i].astype('uint64') / 1e6).astype('uint32')) - ((xticks[0].astype('uint64') / 1e6).astype('uint32')))
            ax.set_xticklabels(xticklabels, ha = 'center')

        fig.tight_layout()
        plt.savefig(os.path.join(output_dir, ("trace-description.pdf")), bbox_inches = 'tight', format = 'pdf')

def handle_list_dbs(input_dir, trace_nr):
    dbs = analysis.trace.get_db(input_dir, trace_nr)
    sys.stderr.write("""%s: [INFO] keys in .hdfs database:\n""" % (sys.argv[0]))
    for db in dbs:
        print('\t%s' % (db))

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
        "--list-dbs", 
         help = """lists dbs in .hdfs database""",
         action = 'store_true')

    parser.add_argument(
        "--trace-nr", 
         help = """nr of trace to analyze. e.g., '--trace-nr 009'""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save graphs & other output data""")

    parser.add_argument(
        "--compare", 
         help = """produce comparison plots""",
         action = 'store_true')

    parser.add_argument(
        "--compare-only", 
         help = """don't extract data""",
         action = 'store_true')

    parser.add_argument(
        "--bitrate-only", 
         help = """bitrate adaptation analysis (BETA)""",
         action = 'store_true')

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

    if args.list_dbs:
        handle_list_dbs(args.input_dir, args.trace_nr)
        sys.exit(0)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] must provide an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    compare = False
    if args.compare:
        compare = args.compare

    compare_only = False
    if args.compare_only:
        compare_only = args.compare_only
        compare = True

    bitrate = False
    if args.bitrate_only:
        bitrate = True

    trace = trace_list[trace_list['trace-nr'] == int(args.trace_nr)]
    trace_dir = os.path.join(args.input_dir, ("trace-%03d" % (int(args.trace_nr))))
    trace_db_file = os.path.join(trace_dir, "processed/database.hdf5")
    trace_output_dir = os.path.join(args.output_dir, ("trace-%03d" % (int(args.trace_nr))))

    if not os.path.isdir(trace_output_dir):
        os.makedirs(trace_output_dir)

    # if bitrate:
    #     plot.trace.bitrate(args.input_dir, args.trace_nr, trace_output_dir)
    #     sys.exit(0)

    # analysis.trace.extract_bitrates(args.input_dir, args.trace_nr, protocol = trace['proto'].values[-1])
    # analysis.trace.extract_distances(args.input_dir, args.trace_nr)
    # analysis.trace.extract_channel_util(args.input_dir, args.trace_nr)

    laps = analysis.gps.get_lap_timestamps(args.input_dir, args.trace_nr, threshold = 125.0)
    time_limits = [laps.iloc[0]['timed-tmstmp'], laps.iloc[-1]['timed-tmstmp']]

    plot_trace_description(args.input_dir, args.trace_nr, trace_output_dir, time_limits = time_limits)
    # plot.trace.maps(args.input_dir, args.trace_nr, trace_output_dir, time_limits = time_limits, redraw = True)

    # # calculate the 'cadillac' periods, according to different metrics
    # for metric in ['throughput', 'rss', 'wlan data rate', 'distances']:
    #     analysis.trace.extract_best(args.input_dir, args.trace_nr, metric = metric, smoothen = True, force_calc = False)

    # plot_best(args.input_dir, args.trace_nr, trace_output_dir, metrics = ['throughput', 'rss', 'wlan data rate', 'distances'])

    laps = analysis.gps.get_lap_timestamps(args.input_dir, args.trace_nr, threshold = 125.0)
    time_limits = [laps.iloc[0]['timed-tmstmp'], laps.iloc[-1]['timed-tmstmp']]

    # # strongest rss (dual-band)
    # analysis.ap_selection.rss.strongest_rss(
    #     args.input_dir, args.trace_nr, 
    #     args = {'scan-period' : 5.0, 'scan-time' : 0.5, 'bands' : 3}, 
    #     force_calc = False)
    # analysis.ap_selection.utils.extract_performance(
    #     args.input_dir, args.trace_nr, 
    #     db_selection = '/selection/rss/strongest-rss/5.0/0.5/3',
    #     force_calc = False)

    # # strongest rss (5 GHz)
    # analysis.ap_selection.rss.strongest_rss(
    #     args.input_dir, args.trace_nr, 
    #     args = {'scan-period' : 5.0, 'scan-time' : 0.5, 'bands' : 2}, 
    #     force_calc = False)
    # analysis.ap_selection.utils.extract_performance(
    #     args.input_dir, args.trace_nr, 
    #     db_selection = '/selection/rss/strongest-rss/5.0/0.5/2',
    #     force_calc = False)

    # scripted handoffs
    analysis.ap_selection.gps.scripted_handoffs(args.input_dir, args.trace_nr,
        args = {
            'metric' : 'rss',
            'cell-size' : 5.0,
            'stat' : 'mean',
            'stat-args' : {'alpha' : 0.75, 'w' : 0}
        },
        force_calc = True)

    analysis.ap_selection.utils.extract_performance(args.input_dir, args.trace_nr, 
        db_selection = '/selection/rss/gps/scripted-handoffs',
        force_calc = True)

    # # cell history
    # analysis.ap_selection.gps.cell_history(args.input_dir, args.trace_nr,
    #     args = {
    #         'metric' : 'throughput',
    #         'cell-size' : 20.0,
    #         'stat' : 'max',
    #         'stat-args' : {'alpha' : 0.75, 'w' : 0}
    #     },
    #     force_calc = False)

    # cell history (optimized)
    analysis.ap_selection.gps.optimize_handoffs(args.input_dir, args.trace_nr,
        args = {
            'db' : '/selection-performance/throughput/gps/cell-history/20.0/max/0.75-0',
            'metric' : 'throughput',
            'cell-size' : 20.0,
            'stat' : 'max',
            'stat-args' : {'alpha' : 0.75, 'w' : 0},
        },
        force_calc = False)

    plot.ap_selection.common.compare(
        args.input_dir, args.trace_nr, trace_output_dir,
        configs = {
            'filename' : 'selection-comparison-thghpt',
            'time-limits' : [laps.iloc[2]['timed-tmstmp'], laps.iloc[-1]['timed-tmstmp']],
            'methods' : {
                '0:best' : {
                    'db' : '/best/throughput',
                    'x-ticklabel' : 'opt.'
                },
                '1:strongest-rss' : {
                    'db' : '/selection-performance/throughput/rss/strongest-rss/5.0/0.5/3',
                    'x-ticklabel' : 'best rss'
                },
                '2:strongest-rss' : {
                    'db' : '/selection-performance/throughput/rss/strongest-rss/5.0/0.5/2',
                    'x-ticklabel' : 'best rss*'
                },
                '3:cell-history' : {
                    'db' : '/selection-performance/throughput/rss/gps/scripted-handoffs',
                    'x-ticklabel' : 'scripted'
                },
                # '4:cell-history' : {
                #     'db' : '/selection-performance/throughput/gps/cell-history/20.0/ewma/0.75-0',
                #     'x-ticklabel' : 'cell history (ewma)'
                # },
                # '5:cell-history' : {
                #     'db' : '/selection-performance/throughput/gps/cell-history/5.0/mean/0.75-0',
                #     'x-ticklabel' : 'cell history (5)'
                # },
                '6:cell-history' : {
                    'db' : '/selection-performance/throughput/gps/cell-history/20.0/max/0.75-0',
                    'x-ticklabel' : 'cell history'
                },
                '7:cell-history' : {
                    'db' : '/selection-performance/throughput/gps/cell-history/20.0/max/0.75-0/optimize-handoff',
                    'x-ticklabel' : 'cell history**'
                },
                # '7:cell-history' : {
                #     'db' : '/selection-performance/throughput/gps/cell-history/20.0/max/0.75-0',
                #     'x-ticklabel' : 'cell history (max)'
                # },
            }
        })

    # plot.ap_selection.common.optimal(
    #     args.input_dir, args.trace_nr, trace_output_dir,
    #     configs = {
    #         'filename' : 'optimal',
    #         # 'time-limits' : [1548779160.0, 1548780180.0],
    #         'time-limits' : [1548779262.0, 1548780180.0],
    #         'optimal' : {
    #             'db' : '/best/throughput'
    #         },
    #         'methods' : {
    #             '1:strongest-rss' : {
    #                 'db' : '/selection-performance/throughput/rss/strongest-rss/5.0/0.5/3',
    #                 'label' : 'best rss',
    #                 'color' : 'orange'
    #             },
    #             '2:strongest-rss' : {
    #                 'db' : '/selection-performance/throughput/rss/strongest-rss/5.0/0.5/2',
    #                 'label' : 'best rss*',
    #                 'color' : 'blue'
    #             },
    #             '3:cell-history' : {
    #                 'db' : '/selection-performance/throughput/rss/gps/scripted-handoffs',
    #                 'label' : 'scripted',
    #                 'color' : 'green'
    #             },
    #             # '4:cell-history' : {
    #             #     'db' : '/selection-performance/throughput/gps/cell-history/20.0/ewma/0.75-0',
    #             #     'x-ticklabel' : 'cell history (ewma)'
    #             # },
    #             # '5:cell-history' : {
    #             #     'db' : '/selection-performance/throughput/gps/cell-history/5.0/mean/0.75-0',
    #             #     'x-ticklabel' : 'cell history (5)'
    #             # },
    #             '6:cell-history' : {
    #                 'db' : '/selection-performance/throughput/gps/cell-history/20.0/max/0.75-0',
    #                 'label' : 'cell history',
    #                 'color' : 'red'
    #             },
    #             # '7:cell-history' : {
    #             #     'db' : '/selection-performance/throughput/gps/cell-history/20.0/max/0.75-0',
    #             #     'x-ticklabel' : 'cell history (max)'
    #             # },
    #         }
    #     }
    # )

    plot.ap_selection.common.handoff_analysis(
        args.input_dir, args.trace_nr, trace_output_dir,
        configs = {
            'filename' : 'handoff-analysis',
            'time-limits' : [laps.iloc[2]['timed-tmstmp'], laps.iloc[-1]['timed-tmstmp']],
            'methods' : {
                '0:best' : {
                    'db' : '/best/throughput',
                    'label' : 'opt.',
                    'color' : 'gray'
                },
                '1:strongest-rss' : {
                    'db' : '/selection-performance/throughput/rss/strongest-rss/5.0/0.5/3',
                    'label' : 'best rss',
                    'color' : 'orange'
                },
                '2:strongest-rss' : {
                    'db' : '/selection-performance/throughput/rss/strongest-rss/5.0/0.5/2',
                    'label' : 'best rss*',
                    'color' : 'blue'
                },
                '3:cell-history' : {
                    'db' : '/selection-performance/throughput/rss/gps/scripted-handoffs',
                    'label' : 'scripted',
                    'color' : 'green',
                },
                # '4:cell-history' : {
                #     'db' : '/selection-performance/throughput/gps/cell-history/20.0/ewma/0.75-0',
                #     'x-ticklabel' : 'cell history (ewma)'
                # },
                # '5:cell-history' : {
                #     'db' : '/selection-performance/throughput/gps/cell-history/5.0/mean/0.75-0',
                #     'x-ticklabel' : 'cell history (5)'
                # },
                '6:cell-history' : {
                    'db' : '/selection-performance/throughput/gps/cell-history/20.0/max/0.75-0',
                    'label' : 'cell history',
                    'color' : 'red'
                },
                '7:cell-history' : {
                    'db' : '/selection-performance/throughput/gps/cell-history/20.0/max/0.75-0/optimize-handoff',
                    'label' : 'cell history**',
                    'color' : 'pink'
                },                
                # '7:cell-history' : {
                #     'db' : '/selection-performance/throughput/gps/cell-history/20.0/max/0.75-0',
                #     'x-ticklabel' : 'cell history (max)'
                # },
            }
        })

    sys.exit(0)

    #     # calculate the 'cadillac' periods, according to different metrics
    #     # for metric in ['throughput', 'wlan rssi', 'dist', 'wlan data rate']:
    #     #     analysis.trace.calc_best(args.input_dir, args.trace_nr, metric = metric, force_calc = False)

    #     # plot_best(args.input_dir, args.trace_nr, trace_output_dir, metrics = ['throughput', 'wlan rssi', 'wlan data rate', 'dist'])
    #     # plot_distances(args.input_dir, args.trace_nr, trace_output_dir)
    #     # plot.trace.cells(args.input_dir, args.trace_nr, trace_output_dir, cell_size = 20.0)

    #     # arguments for each method to evaluate
    #     # ground_truth_metric = 'wlan data rate'
    #     ground_truth_metric = 'throughput'

    #     # plot configs
    #     configs = defaultdict(defaultdict)

    #     # date : basic
    #     configs['best-rssi'] = {
    #         'method' : 'periodic',
    #         'args' : {'scan-period' : 5.0, 'scan-time' : 1.0},
    #         'title' : ('best RSS (scan period : %s sec, scan duration : %s sec)' % (5.0, 0.0)),
    #         'sub-title' : ('best RSS (%s gain)' % (ground_truth_metric)),
    #         'y-label' : 'RSS (dBm)',
    #         'y-sec-label' : 'throughput (Mbps)',
    #         # 'y-sec-label' : 'wlan data rate (Mbps)',
    #         'coef' : 1.0 / 1000000.0,
    #         'show' : 'gain-only'
    #     }

    #     # # periodic scan + pick best rssi analysis
    #     # analysis.ap_selection.rssi.periodic(args.input_dir, args.trace_nr,
    #     #     method = 'periodic',
    #     #     args = configs['best-rssi']['args'])

    #     for l in [0]:
    #         for w in [5]:

    #             # scan : band steering
    #             stat = 'mean'
    #             stat_args = {'alpha' : 0.75, 'w' : w}
    #             configs['band-steering'] = {
    #                 'method' : 'band-steering',
    #                 'args' : {
    #                     'scan-period' : 5.0, 'scan-time' : 1.0, 'cell-size' : 20.0, 
    #                     'metric' : ground_truth_metric, 'stat' : ('%s' % (stat)), 'stat-args' : stat_args, 
    #                     'use-current-lap' : l, 'use-direction' : 0},
    #                 'title' : ('band steering (scan period : %s sec, scan dur. : %s sec, cell size : %s m, stat : %s)' % (5.0, 0.0, 20.0, stat)),
    #                 'sub-title' : ('band steering (%s gain)' % (ground_truth_metric)),
    #                 'y-label' : 'RSS (dBm)',
    #                 'y-sec-label' : 'throughput (Mbps)',
    #                 # 'y-sec-label' : 'wlan data rate (Mbps)',
    #                 'coef' : 1.0 / 1000000.0,
    #                 'show' : 'gain-only'
    #             }

    #             # gps : best <stat>.<metric> history of current cell
    #             # stat = 'mean'
    #             stat_args = {'alpha' : 0.75, 'w' : w}
    #             cell_size = 20.0
    #             configs['best-cell'] = {
    #                 'args' : {
    #                     'cell-size' : cell_size, 
    #                     'metric' : ground_truth_metric, 'stat' : ('%s' % (stat)), 'stat-args' : stat_args,
    #                     'use-current-lap' : l, 'use-direction' : 0},
    #                 'title' : ('loc. history (%s) (cell size : %s m, stat : %s)' % (ground_truth_metric, cell_size, stat)),
    #                 'sub-title' : ('loc. history (%s gain)' % (ground_truth_metric)),
    #                 'y-label' : 'throughput (Mbps)',
    #                 # 'y-label' : 'wlan data rate (Mbps)',
    #                 'y-sec-label' : 'throughput (Mbps)',
    #                 'coef' : 1.0 / 1000000.0,
    #                 'show' : 'gain-only'
    #             }

    #             # scan : scan + pick best <stat>.<metric> history of current cell, 
    #             # stat = 'mean'
    #             stat_args = {'alpha' : 0.75, 'w' : w}
    #             cell_size = 20.0
    #             configs['history'] = {
    #                 'method' : 'history',
    #                 'args' : {
    #                     'scan-period' : 5.0, 'scan-time' : 1.0, 'cell-size' : cell_size, 
    #                     'metric' : ground_truth_metric, 'stat' : ('%s' % (stat)), 'stat-args' : stat_args, 
    #                     'use-current-lap' : l, 'use-direction' : 0},
    #                 'title' : ('scan + loc. history (%s) (scan period : %s sec, scan dur. : %s sec, cell size : %s m, stat : %s)' % (ground_truth_metric, 5.0, 0.0, cell_size, stat)),
    #                 'sub-title' : ('scan + loc. history (%s gain)' % (ground_truth_metric)),
    #                 'y-label' : 'RSS (dBm)',
    #                 'y-sec-label' : 'throughput (Mbps)',
    #                 # 'y-sec-label' : 'wlan data rate (Mbps)',
    #                 'coef' : 1.0 / 1000000.0,
    #                 'show' : 'gain-only'
    #             }

    #             # # date : band steering
    #             # analysis.ap_selection.rssi.band_steering(args.input_dir, args.trace_nr,
    #             #     method = 'band-steering',
    #             #     args = configs['band-steering']['args'],
    #             #     force_calc = False)

    #             # # gps : cell history
    #             # analysis.ap_selection.gps.cell(args.input_dir, args.trace_nr,
    #             #     args = configs['best-cell']['args'],
    #             #     force_calc = False)

    #             # # date : history assisted
    #             # analysis.ap_selection.rssi.history(args.input_dir, args.trace_nr,
    #             #     method = 'history',
    #             #     args = configs['history']['args'],
    #             #     force_calc = False)

    #             plot_ap_selection(args.input_dir, args.trace_nr, trace_output_dir, 
    #                 gt_metric = ground_truth_metric,
    #                 # methods = ['best-rssi', 'band-steering', 'history', 'best-cell'],
    #                 methods = ['best-rssi', 'history'],
    #                 configs = configs, 
    #                 redraw = True)

    # if compare:

    #     # plot_bands(args.input_dir, args.trace_nr, trace_output_dir, configs = {'gt-metric' : 'throughput'})

    #     metric = 'throughput'
    #     stat = {'stat' : 'ewma', 'stat-args' : '0.75-5', 'lap-usage' : '0-0'}
    #     plot.trace.compare(args.input_dir, args.trace_nr, trace_output_dir,
    #         configs = {
    #             'gt-metric' : metric,
    #             'metric-alias' : 'thghpt',
    #             'stat' : stat,
    #             'types' : ['rate', 'time'],
    #             'y-label' : {
    #                 'rate' : 'throughput (Mbps)',
    #                 'data' : 'data volume (MByte)',
    #                 'time' : 'time (sec)'
    #             },
    #             'algorithms' : {
    #                 '0:best' : {
    #                     'data' : ('/%s/%s' % ('best', metric)),
    #                     'x-ticklabel' : 'best',
    #                     # 'color' : 'yellow',
    #                     'coef' : 1.0 / 1000000.0
    #                 },
    #                 '1:baseline' : {
    #                     'data' : '/best-rssi/periodic/5/1',
    #                     'x-ticklabel' : 'best RSS',
    #                     # 'color' : 'red',
    #                     'coef' : 1.0 / 1000000.0
    #                 },
    #                 '3:band-steering' : {
    #                     'data' : ('/best-rssi/band-steering/5.0/1.0/20.0/%s/%s/%s/%s' % (metric, stat['stat'], stat['stat-args'], stat['lap-usage'])),
    #                     'x-ticklabel' : 'band steering',
    #                     # 'color' : 'blue',
    #                     'coef' : 1.0 / 1000000.0
    #                 },
    #                 '2:best-of-cell' : {
    #                     'data' : ('/best-cell/20.0/%s/%s/%s/%s' % (metric, stat['stat'], stat['stat-args'], stat['lap-usage'])),
    #                     'x-ticklabel' : 'loc. history',
    #                     # 'color' : 'green',
    #                     'coef' : 1.0 / 1000000.0
    #                 },
    #                 '4:scan-history' : {
    #                     'data' : ('/best-rssi/history/5.0/1.0/20.0/%s/%s/%s/%s' % (metric, stat['stat'], stat['stat-args'], stat['lap-usage'])),
    #                     'x-ticklabel' : 'scan + loc. hist.',
    #                     # 'color' : 'magenta',
    #                     'coef' : 1.0 / 1000000.0
    #                 },
    #                 '5:best-overall' : {
    #                     'data' : ('/best-rssi/history/5.0/1.0/5000.0/%s/%s/%s/%s' % (metric, stat['stat'], stat['stat-args'], stat['lap-usage'])),
    #                     'x-ticklabel' : 'ap rank',
    #                     # 'color' : 'cyan',
    #                     'coef' : 1.0 / 1000000.0
    #                 }
    #             }
    #         })

    # sys.exit(0)