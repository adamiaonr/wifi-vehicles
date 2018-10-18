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

import mapping.utils
import plot.utils
import parsing.utils
import analysis.metrics

from random import randint
from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple
from matplotlib.gridspec import GridSpec
from prettytable import PrettyTable

matplotlib.rcParams.update({'font.size': 16})

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
    'pos1'   : {'color' : 'red',        'lat' : 41.178518, 'lon' : -8.595366}, 
    'pos0'   : {'color' : 'blue',       'lat' : 41.178563, 'lon' : -8.596012}
}

t_diff = lambda t : (float(t[-1]) - float(t[0]))
Range = namedtuple('Range', ['start', 'end'])

def parse_json(input_dir, trace_nr):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))

    iperf3_results = csv.writer(open(os.path.join(trace_dir, ("pos1/iperf3-to-mobile.results.csv")), 'wb+', 0))
    # write headers of report.csv and results.csv files
    iperf3_results.writerow(['time', 'cpu-sndr', 'cpu-rcvr'])

    for filename in sorted(glob.glob(os.path.join(trace_dir, 'pos1/iperf3-to-mobile.report.*.json'))):
        parsing.utils.parse_json(filename, iperf3_results)

def process_metric(data, aggr_metrics, metric):

    # bitrates
    df = None
    if metric == 'bitrate':
        
        df = data[['epoch time', 'frame len']]
        df['epoch time'] = df['epoch time'].astype(int)
        print(df)
        df = df[['epoch time', 'frame len']].groupby(['epoch time']).sum().reset_index().sort_values(by = ['epoch time'])
        df['bitrate'] = df['frame len'] * 8.0

        _metric = ('aggr-%s' % (metric))
        aggr_metrics[_metric] = pd.merge(aggr_metrics[_metric], df[['epoch time', metric]], on = ['epoch time'], how = 'outer').set_index('epoch time').sum(axis = 1).reset_index().sort_values(by = ['epoch time'])
        aggr_metrics[_metric].columns = ['epoch time', metric]

    elif metric == '802.11n data rate':

        df = data[['epoch time', 'wlan data rate']]
        df['epoch time'] = df['epoch time'].astype(int)
        df = df[['epoch time', 'wlan data rate']].groupby(['epoch time']).mean().reset_index()
        df['802.11n data rate'] = df['wlan data rate'] * 1000000.0

    elif metric == 'wlan rssi':

        df = data[['epoch time', 'wlan rssi']]
        df['epoch time'] = df['epoch time'].astype(int)
        df = df[['epoch time', 'wlan rssi']].groupby(['epoch time']).mean().reset_index()

    return df

def plot_time(input_dir, trace_nr, output_dir,
    zoom = None, protocol = 'udp', channel = '1', bw = '20'):

    plt.style.use('classic')
    fig = plt.figure(figsize = (5, 6.0))

    # keep track of xx axis min and max so that all data for each pos series is shown
    time_limits = [None, None]
    if zoom is None:
        time_limits = [None, None]
    else:
        time_limits = zoom

    labels = defaultdict(str)
    for mac in clients:
        labels[mac] = clients[mac]['label']

    plot_configs = OrderedDict([
        ('wlan rssi', { 
            'title' : ("channel %s, %s MHz, %s" % (channel, bw, protocol)),
            'metrics' : ['wlan rssi'], 
            'linewidth' : 0.75,
            'marker' : None,
            'markersize' : 0.0,
            'markeredgewidth' : 0.0, 
            # 'y-limits' : [-75, -40],
            'axis-labels' : ['time', 'rssi (dBm)'] }), 
        # 'inter-arrival' : { 
        #     'metrics' : ['diff'], 
        #     'linewidth' : 0.75,
        #     'marker' : None,
        #     'markersize' : 0.0,
        #     'markeredgewidth' : 0.0, 
        #     'axis-labels' : ['time', 'pkt inter-arr. time (s)'], 
        #     'scale' : ['linear', 'log'] }, 
        # ('seq', { 
        #     'metrics' : ['ip seq'], 
        #     'linewidth' : 0.00,
        #     'marker' : 'o',
        #     'markersize' : 2.00,
        #     'markeredgewidth' : 0.0, 
        #     'axis-labels' : ['time', 'ip id.frag offset'] }),
        ('bitrate', { 
            'metrics' : ['bitrate', 'aggr-bitrate'], 
            'linewidth' : 0.75,
            'marker' : None,
            'markersize' : 0.0,
            'markeredgewidth' : 0.0,
            'scale' : ['linear', 'log'],
            # 'y-limits' : [100000, 1000000000],
            'axis-labels' : ['time', 'throughput (bps)'] }),
        ('wlan data rate', { 
            'metrics' : ['802.11n data rate'], 
            'linewidth' : 0.75,
            'marker' : None,
            'markersize' : 0.0,
            'markeredgewidth' : 0.0,
            'scale' : ['linear', 'log'],
            # 'y-limits' : [0.1, 10 * 1000000.0],
            'axis-labels' : ['time', 'wlan data rate (bps)'] })
    ])

    # aggregate metrics : metrics which sum the values for all clients.
    # for metric with name 'x', the corresponding aggregate metric is 'aggr-x'
    # these should be included in the 'metrics' list for each category, in plot_configs
    aggr_labels = defaultdict(str)
    for category in plot_configs:
        for metric in plot_configs[category]['metrics']:
            if 'aggr' in metric:
                aggr_labels[metric] = 'aggr'

    ax = OrderedDict()
    aggr_metrics = OrderedDict()
    for m, category in enumerate(plot_configs.keys()):
        ax[category] = fig.add_subplot(311 + m)
        ax[category].xaxis.grid(True)
        ax[category].yaxis.grid(True)

        for metric in plot_configs[category]['metrics']:
            if 'aggr' in metric:
                aggr_metrics[metric] = pd.DataFrame(columns = ['epoch time', ('%s' % (metric.split('-')[-1]))])

    # all rssi data that matters is in the monitor.*.csv file in mobile/
    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    for fname in sorted(glob.glob(os.path.join(trace_dir, 'mobile/monitor.wlx24050faaab5d.*.csv'))):

        aggr_thrghpt = pd.DataFrame(columns = ['epoch time', 'bitrate'])

        chunksize = 10 ** 5
        for chunk in pd.read_csv(fname, chunksize = chunksize):

            # clear aggregation dataframes
            for category in plot_configs:
                for metric in plot_configs[category]['metrics']:
                    if 'aggr' in metric:
                        aggr_metrics[metric] = aggr_metrics[metric].iloc[0:0]

            # make sure packets in chunk are sorted by unix timestamp
            chunk = chunk.sort_values(by = ['epoch time'])

            for mac in clients:

                # we only care about rows w/ src station being the client
                data = chunk[(chunk['wlan src addr'] == mac) & (chunk['wlan dst addr'] == ap) & (chunk['ip proto'] == protocol.upper())].reset_index()
                if data.empty:
                    continue

                for category in plot_configs:
                    for metric in plot_configs[category]['metrics']:

                        # some metrics require special processing
                        if metric in ['bitrate', 'aggr-bitrate', '802.11n data rate', 'wlan rssi']:
                            df = process_metric(data, aggr_metrics, metric)

                            if metric == 'bitrate':
                                print(df)

                        else:
                            df = df.iloc[::50, :]

                        if metric in aggr_metrics:
                            continue

                        df = df[np.isfinite(df[metric])]

                        # x axis should be in datetime objects, for plot_date()
                        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in df['epoch time'] ]

                        if not dates:
                            continue

                        # update the x axis limits
                        if zoom is None:
                            plot.utils.update_time_limits(time_limits, dates)

                        ax[category].plot_date(
                            dates,
                            df[metric],
                            linewidth = plot_configs[category]['linewidth'], linestyle = '-', 
                            color = clients[mac]['color'], label = labels[mac], 
                            markersize = plot_configs[category]['markersize'], 
                            marker = plot_configs[category]['marker'], 
                            markeredgewidth = plot_configs[category]['markeredgewidth'])

                # only add labels once per pos series
                labels[mac] = ''

            # plot aggregate metrics
            for category in plot_configs:
                for metric in plot_configs[category]['metrics']:

                    if metric not in aggr_metrics:
                        continue

                    # x axis should be in datetime objects, for plot_date()
                    dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in aggr_metrics[metric]['epoch time'] ]

                    if not dates:
                        continue

                    ax[category].plot_date(
                        dates,
                        aggr_metrics[metric][metric.split('-')[-1]],
                        linewidth = plot_configs[category]['linewidth'], linestyle = '-', 
                        color = 'black', label = aggr_labels[metric], 
                        markersize = plot_configs[category]['markersize'], 
                        marker = plot_configs[category]['marker'], 
                        markeredgewidth = plot_configs[category]['markeredgewidth'])

                    aggr_labels[metric] = ''

    # divide xx axis in 5 ticks
    xticks = plot.utils.get_time_xticks(time_limits)

    for category in plot_configs:

        if 'title' in plot_configs[category]:
            ax[category].set_title(plot_configs[category]['title'])

        ax[category].legend(
            fontsize = 10, 
            ncol = 4, loc = 'lower right',
            handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

        # set axis labels
        ax[category].set_xlabel(plot_configs[category]['axis-labels'][0])
        ax[category].set_ylabel(plot_configs[category]['axis-labels'][1])

        # set x axis limits according to time_limits
        ax[category].set_xlim(time_limits[0], time_limits[1])

        if 'scale' in plot_configs[category]:
            ax[category].set_yscale(plot_configs[category]['scale'][1])
        if 'y-limits' in plot_configs[category]:
            ax[category].set_ylim(plot_configs[category]['y-limits'])

        ax[category].set_xticks(xticks)
        ax[category].set_xticklabels([str(xt)[11:-7] for xt in xticks])

    plt.gcf().autofmt_xdate()
    plt.tight_layout()

    # create output dir for trace (if not existent)
    trace_output_dir = os.path.join(output_dir, ("trace-%03d" % (int(trace_nr))))
    if not os.path.isdir(trace_output_dir):
        os.makedirs(trace_output_dir)

    plt.savefig(os.path.join(trace_output_dir, ("rssi-%s.pdf" % (trace_nr))), bbox_inches = 'tight', format = 'pdf')                


def plot_cbt(input_dir, trace_nr, output_dir,
    zoom = None, channel = '1', bw = '20', protocol = 'udp'):

    plt.style.use('classic')
    fig = plt.figure(figsize = (5, 4.5))

    # cbt as taken from atheros chipset registers
    ax1 = fig.add_subplot(211)
    ax1.xaxis.grid(True)
    ax1.yaxis.grid(True)

    # 'manual' cbt method
    ax2 = fig.add_subplot(212)
    ax2.xaxis.grid(True)
    ax2.yaxis.grid(True)

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))

    # cbt from atheros chipset resgisters
    for filename in sorted(glob.glob(os.path.join(trace_dir, 'pos1/cbt.*.csv'))):

        # read cbt .csv file
        cbt_data = pd.read_csv(filename)
        # filter out invalid timestamps
        # FIXME : very sloppy test, but it works
        cbt_data['timestamp'] = cbt_data['timestamp'].astype(float)
        cbt_data = cbt_data[cbt_data['timestamp'] > 1000000000.0].sort_values(by = ['timestamp'])

        # identify segments of increasingly monotonic cat
        cbt_data['diff'] = cbt_data['cat'] - cbt_data['cat'].shift(1)
        segments = list(cbt_data.index[cbt_data['diff'] < 0.0])
        segments.append(len(cbt_data) - 1)

        freq = int(cbt_data.iloc[0]['freq'])
        prev_seg = 0

        # track xx axis min and max so that all data for each pos series is shown
        time_limits = [None, None]
        if zoom is None:
            time_limits = [None, None]
        else:
            time_limits = zoom

        labels = ['util.', 'rx', 'tx']
        for seg in segments:

            data = cbt_data.iloc[prev_seg:seg]
            if len(data) == 1:
                continue

            diff_cat = data['cat'] - data['cat'].shift(1)
            diff_cbt = data['cbt'] - data['cbt'].shift(1)

            if (freq >= 5180):
                diff_crt = data['crt']
                diff_ctt = data['ctt']
            else:
                diff_crt = data['crt'] - data['crt'].shift(1)
                diff_ctt = data['ctt'] - data['ctt'].shift(1)

            data['cbt-diff'] = diff_cbt / diff_cat
            data['crt-diff'] = diff_crt / diff_cat
            data['ctt-diff'] = diff_ctt / diff_cat

            dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in data['timestamp'] ]

            ax1.plot_date(
                dates,
                data['cbt-diff'] * 100.0,
                linewidth = 0.75, linestyle = '-', color = 'black', label = labels[0], marker = None)

            ax1.plot_date(
                dates,
                data['crt-diff'] * 100.0,
                linewidth = 0.75, linestyle = '-', color = 'grey', label = labels[1], marker = None)

            ax1.plot_date(
                dates,
                data['ctt-diff'] * 100.0,
                linewidth = 0.75, linestyle = '-', color = 'navy', label = labels[2], marker = None)

            # update the x axis limits
            if zoom is None:
                plot.utils.update_time_limits(time_limits, dates)

            prev_seg = seg
            labels = ['', '', '']

        ax1.legend(
            fontsize = 12, 
            ncol = 3, loc = 'upper right',
            handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

        ax1.set_title(("channel %s, %s MHz, %s\n at pos1" % (channel, bw, protocol)))

        ax1.set_xlabel("time")
        ax1.set_ylabel("% of 1 sec")

        ax1.set_xlim(time_limits[0], time_limits[1])
        ax1.set_ylim([0.0, 130.0])
        ax1.set_yticks(np.arange(0.0, 120.0, 20.0))

        # divide xx axis in 5 ticks
        xticks = plot.utils.get_time_xticks(time_limits)
        ax1.set_xticks(xticks)
        ax1.set_xticklabels([str(xt)[11:-7] for xt in xticks])

    # cbt from atheros chipset resgisters
    for filename in sorted(glob.glob(os.path.join(trace_dir, 'mobile/monitor.wlx24050faaab5d.*.csv'))):

        cbt_data, frame_types = analysis.metrics.calc_cbt(filename)
        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in cbt_data['timestamp'] ]

        ax2.plot_date(
            dates,
            cbt_data['utilization'],
            linewidth = 0.75, linestyle = '-', color = 'black', label = 'util.', marker = None)

        ax2.legend(
            fontsize = 12, 
            ncol = 3, loc = 'upper right',
            handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

        ax2.set_title(("at mobile node"))

        ax2.set_xlabel("time")
        ax2.set_ylabel("% of 1 sec")

        ax2.set_xlim(time_limits[0], time_limits[1])
        ax2.set_ylim([0.0, 130.0])
        ax2.set_yticks(np.arange(0.0, 120.0, 20.0))

        # divide xx axis in 5 ticks
        xticks = plot.utils.get_time_xticks(time_limits)
        ax2.set_xticks(xticks)
        ax2.set_xticklabels([str(xt)[11:-7] for xt in xticks])

        plt.gcf().autofmt_xdate()
        plt.tight_layout()

        # create output dir for trace (if not existent)
        trace_output_dir = os.path.join(output_dir, ("trace-%03d" % (int(trace_nr))))
        if not os.path.isdir(trace_output_dir):
            os.makedirs(trace_output_dir)

        plt.savefig(os.path.join(trace_output_dir, ("ct-%s.pdf" % (trace_nr))), bbox_inches = 'tight', format = 'pdf')

def plot_ntp(input_dir, trace_nr, output_dir):

    plt.style.use('classic')
    fig = plt.figure(figsize = (5, 3.0))
    ax = fig.add_subplot(111)
    ax.xaxis.grid(True)
    ax.yaxis.grid(True)

    time_limits = [None, None]
    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    for peer in peers.keys():

        peer_dir = os.path.join(trace_dir, ("%s" % (peer)))
        for filename in sorted(glob.glob(os.path.join(peer_dir, 'ntpstat.*.csv'))):

            ntp_data = pd.read_csv(filename)
            dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in ntp_data['timestamp'] ]

            if not dates:
                continue

            plot.utils.update_time_limits(time_limits, dates)

            # TODO: add a line marking the start of the experiment  
            ax.plot_date(
                dates,
                ntp_data['delta'],
                linewidth = 0.75, linestyle = '-', color = peers[peer]['color'], label = peer, marker = None)

    ax.legend(
        fontsize = 12, 
        ncol = 2, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    ax.set_xlabel("time")
    ax.set_ylabel("ntp offset (ms)")

    # log scale due to major differences in yy axis
    ax.set_yscale('log')
    ax.set_xlim(time_limits[0], time_limits[1])

    # divide xx axis in 5 ticks
    xticks = plot.utils.get_time_xticks(time_limits)
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(xt)[11:-7] for xt in xticks])

    plt.gcf().autofmt_xdate()
    plt.tight_layout()

    # create output dir for trace (if not existent)
    trace_output_dir = os.path.join(output_dir, ("trace-%03d" % (int(trace_nr))))
    if not os.path.isdir(trace_output_dir):
        os.makedirs(trace_output_dir)

    plt.savefig(os.path.join(trace_output_dir, ("ntp-stats-%s.pdf" % (trace_nr))), bbox_inches = 'tight', format = 'pdf')

def plot_cpu(input_dir, trace_nr, output_dir,
    zoom = None, channel = '1', bw = '20', protocol = 'udp'):

    plt.style.use('classic')
    fig = plt.figure(figsize = (5, 3.0))
    ax = fig.add_subplot(111)
    ax.xaxis.grid(True)
    ax.yaxis.grid(True)

    # keep track of xx axis min and max so that all data for each pos series is shown
    time_limits = [None, None]
    if zoom is None:
        time_limits = [None, None]
    else:
        time_limits = zoom

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    label_mobile = 'mobile'
    for peer in peers.keys():

        if peer == 'mobile':
            continue

        peer_dir = os.path.join(trace_dir, ("%s" % (peer)))
        for filename in sorted(glob.glob(os.path.join(peer_dir, 'iperf3-to-mobile.results*csv'))):

            cpu_data = pd.read_csv(filename)

            offset = 0.0
            if peer == 'pos1':
                offset = 0.0
                cpu_data = cpu_data.sort_values(by = ['time'])
            dates = [ datetime.datetime.fromtimestamp(float(dt) - offset) for dt in cpu_data['time'] ]

            if not dates:
                continue

            # update the x axis limits
            if zoom is None:
                plot.utils.update_time_limits(time_limits, dates)

            # TODO: add a line marking the start of the experiment  
            ax.plot_date(
                dates,
                cpu_data['cpu-sndr'],
                linewidth = 0.75, linestyle = '-', color = peers[peer]['color'], label = peer, marker = None)

            ax.plot_date(
                dates,
                cpu_data['cpu-rcvr'],
                linewidth = 0.0, linestyle = None, color = peers['mobile']['color'], label = label_mobile,
                marker = 'o', markersize = 2.50, markeredgewidth = 0.0)

            label_mobile = ''

    ax.legend(
        fontsize = 12, 
        ncol = 2, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    ax.set_title(("channel %s, %s MHz, %s" % (channel, bw, protocol)))

    ax.set_xlabel("time")
    ax.set_ylabel("cpu usage (%)")

    # log scale due to major differences in yy axis
    # ax.set_yscale('log')
    ax.set_xlim(time_limits[0], time_limits[1])
    ax.set_ylim([0.0, 100.0])

    # divide xx axis in 5 ticks
    xticks = plot.utils.get_time_xticks(time_limits)
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(xt)[11:-7] for xt in xticks])

    plt.gcf().autofmt_xdate()
    plt.tight_layout()

    # create output dir for trace (if not existent)
    trace_output_dir = os.path.join(output_dir, ("trace-%03d" % (int(trace_nr))))
    if not os.path.isdir(trace_output_dir):
        os.makedirs(trace_output_dir)

    plt.savefig(os.path.join(trace_output_dir, ("cpu-stats-%s.pdf" % (trace_nr))), bbox_inches = 'tight', format = 'pdf')

def plot_gps(input_dir, trace_nr, output_dir,
    zoom = None, channel = '1', bw = '20', protocol = 'udp'):

    plt.style.use('classic')
    fig = plt.figure(figsize = (5, 4.5))
    
    # dist to client
    ax1 = fig.add_subplot(211)
    ax1.xaxis.grid(True)
    ax1.yaxis.grid(True)
    # speed
    ax2 = fig.add_subplot(212)
    ax2.xaxis.grid(True)
    ax2.yaxis.grid(True)

    # keep track of xx axis min and max so that all data for each pos series is shown
    time_limits = [None, None]
    if zoom is None:
        time_limits = [None, None]
    else:
        time_limits = zoom

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    for filename in sorted(glob.glob(os.path.join(trace_dir, 'mobile/gps-log.*.csv'))):

        gps_data = pd.read_csv(filename)
        gps_data['timestamp'] = gps_data['timestamp'].astype(int)
        gps_data = gps_data.sort_values(by = ['timestamp'])

        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in gps_data['timestamp'] ]
        if not dates:
            continue
        # update the x axis limits
        if zoom is None:
            plot.utils.update_time_limits(time_limits, dates)

        for peer in peers.keys():

            if peer == 'mobile':
                continue

            gps_pos = [ [row['lat'], row['lon'] ] for index, row in gps_data.iterrows()]
            dist = [ mapping.utils.gps_to_dist(peers[peer]['lat'], peers[peer]['lon'], gps[0], gps[1]) for gps in gps_pos ]

            ax1.plot_date(
                dates,
                dist,
                linewidth = 0.75, linestyle = '-', color = peers[peer]['color'], label = peer, 
                marker = 'o', markersize = 1.50, markeredgewidth = 0.0)

        dist = mapping.utils.gps_to_dist(gps_data['lat'], gps_data['lon'], gps_data['lat'].shift(1), gps_data['lon'].shift(1))
        time = gps_data['timestamp'] - gps_data['timestamp'].shift(1)
        gps_data['alt-speed'] = dist / time

        df = gps_data[gps_data['alt-speed'] < 10.0]
        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in df['timestamp'] ]
        if not dates:
            continue

        ax2.plot_date(
            dates,
            df['alt-speed'],
            linewidth = 0.75, linestyle = '-', color = 'black', label = 'speed',
            marker = 'o', markersize = 1.50, markeredgewidth = 0.0)

    # divide xx axis in 5 ticks
    xticks = plot.utils.get_time_xticks(time_limits)

    # dist to client
    ax1.set_title(("channel %s, %s MHz, %s" % (channel, bw, protocol)))
    ax1.set_xlabel("time")
    ax1.set_ylabel("dist. to (m)")
    ax1.set_xlim(time_limits[0], time_limits[1])
    ax1.set_xticks(xticks)
    ax1.set_xticklabels([str(xt)[11:-7] for xt in xticks])

    ax1.legend(
        fontsize = 12, 
        ncol = 1, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    # speed
    ax2.set_xlabel("time")
    ax2.set_ylabel("speed (m/s)")
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

    plt.savefig(os.path.join(trace_output_dir, ("gps-stats-%s.pdf" % (trace_nr))), bbox_inches = 'tight', format = 'pdf')

def plot_pckt_loss(input_dir, trace_nr, output_dir,
    zoom = None, channel = '1', bw = '20', protocol = 'udp'):

    plt.style.use('classic')
    fig = plt.figure(figsize = (5, 3.0))
    
    # dist to client
    ax1 = fig.add_subplot(111)
    ax1.xaxis.grid(True)
    ax1.yaxis.grid(True)

    labels = defaultdict(str)
    for mac in clients:
        labels[mac] = clients[mac]['label']

    # keep track of xx axis min and max so that all data for each pos series is shown
    time_limits = [None, None]
    if zoom is None:
        time_limits = [None, None]
    else:
        time_limits = zoom

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    for fname in sorted(glob.glob(os.path.join(trace_dir, 'mobile/monitor.wlx24050faaab5d.*.csv'))):
        chunksize = 10 ** 5
        for chunk in pd.read_csv(fname, chunksize = chunksize):

            # make sure packets in chunk are sorted by unix timestamp
            chunk = chunk.sort_values(by = ['epoch time'])

            for mac in clients:

                # we only care about rows w/ src station being the client
                data = chunk[(chunk['wlan src addr'] == mac) & (chunk['wlan dst addr'] == ap) & (chunk['ip proto'] == protocol.upper())].reset_index()
                if data.empty:
                    continue

                data = analysis.metrics.add_ip_seq(data)

                df = analysis.metrics.calc_pckt_loss_2(data, method = 'wlan seq number', protocol = protocol)
                # x axis should be in datetime objects, for plot_date()
                dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in df['time'] ]

                if not dates:
                    continue

                # update the x axis limits
                if zoom is None:
                    plot.utils.update_time_limits(time_limits, dates)

                ax1.plot_date(
                    dates,
                    df['pckt-loss'],
                    linewidth = 0.75, linestyle = '-',
                    color = clients[mac]['color'], label = labels[mac], 
                    marker = 'o', markersize = 1.50, markeredgewidth = 0.0)

                labels[mac] = ''

    # divide xx axis in 5 ticks
    xticks = plot.utils.get_time_xticks(time_limits)

    # dist to client
    ax1.set_title(("channel %s, %s MHz, %s" % (channel, bw, protocol)))
    ax1.set_xlabel("time")
    ax1.set_ylabel("pckt loss (%)")
    ax1.set_xlim(time_limits[0], time_limits[1])
    ax1.set_ylim([0.0, 100.0])
    ax1.set_xticks(xticks)
    ax1.set_xticklabels([str(xt)[11:-7] for xt in xticks])

    ax1.legend(
        fontsize = 12, 
        ncol = 1, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    plt.gcf().autofmt_xdate()
    plt.tight_layout()

    # create output dir for trace (if not existent)
    trace_output_dir = os.path.join(output_dir, ("trace-%03d" % (int(trace_nr))))
    if not os.path.isdir(trace_output_dir):
        os.makedirs(trace_output_dir)

    plt.savefig(os.path.join(trace_output_dir, ("pckt-loss-%s.pdf" % (trace_nr))), bbox_inches = 'tight', format = 'pdf')

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

def list_traces(input_dir):

    filename = os.path.join(input_dir, ("trace-info.csv"))
    if not os.path.isfile(filename):
        sys.stderr.write("""%s: [ERROR] no 'trace-info.csv' at %s\n""" % (sys.argv[0], input_dir))
        return -1

    trace_info = pd.read_csv(filename)
    return trace_info

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

    trace_list = list_traces(args.input_dir)
    if args.list_traces:
        table = PrettyTable(list(trace_list.columns))
        for i, row in trace_list.iterrows():
            table.add_row([
                ('%s' % (row['trace-nr'])),
                ('%s' % (row['proto'])), 
                ('%d' % (row['channel'])), 
                ('%d' % (row['bw'])),
                ('%s' % (('%sMbps' % row['bitrate']) if row['bitrate'] != '*' else row['bitrate']))
                ])
        print(table)

    if not args.trace_nr:
        sys.stderr.write("""%s: [ERROR] must provide a trace nr. to analyze\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] must provide an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # plot_ntp(args.input_dir, args.trace_nr, args.output_dir)
    # plot_time(args.input_dir, args.trace_nr, args.output_dir,
    #     zoom = [ datetime.datetime(2018, 8, 7, 16, 58), datetime.datetime(2018, 8, 7, 17, 02) ])
    # plot_cbt(args.input_dir, args.trace_nr, args.output_dir,
    #     zoom = [ datetime.datetime(2018, 8, 7, 16, 58), datetime.datetime(2018, 8, 7, 17, 02) ])
    # plot_cpu(args.input_dir, args.trace_nr, args.output_dir,
    #     zoom = [ datetime.datetime(2018, 8, 7, 16, 58), datetime.datetime(2018, 8, 7, 17, 02) ])

    # fetch trace info from trace list
    trace = trace_list[trace_list['trace-nr'] == int(args.trace_nr)]
    # parse_json(args.input_dir, args.trace_nr)
    time_limits = get_time_limits(args.input_dir, args.trace_nr, protocol = trace['proto'].values[-1])
    plot_time(args.input_dir, args.trace_nr, args.output_dir, 
        zoom = time_limits,
        protocol = trace['proto'].values[-1],
        channel = trace['channel'].values[-1], bw = trace['bw'].values[-1])
    # plot_cbt(args.input_dir, args.trace_nr, args.output_dir,
    #     zoom = time_limits,
    #     protocol = trace['proto'].values[-1],
    #     channel = trace['channel'].values[-1], bw = trace['bw'].values[-1])
    # plot_cpu(args.input_dir, args.trace_nr, args.output_dir,
    #     zoom = time_limits,
    #     protocol = trace['proto'].values[-1],
    #     channel = trace['channel'].values[-1], bw = trace['bw'].values[-1])
    # plot_gps(args.input_dir, args.trace_nr, args.output_dir,
    #     zoom = time_limits,
    #     protocol = trace['proto'].values[-1],
    #     channel = trace['channel'].values[-1], bw = trace['bw'].values[-1])

    # plot_pckt_loss(args.input_dir, args.trace_nr, args.output_dir,
    #     zoom = time_limits,
    #     protocol = trace['proto'].values[-1],
    #     channel = trace['channel'].values[-1], bw = trace['bw'].values[-1])

    sys.exit(0)