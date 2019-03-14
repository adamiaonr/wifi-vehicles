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
from matplotlib.gridspec import GridSpec
from prettytable import PrettyTable

# custom imports
#   - plot
import plot.utils
import plot.gps
#   - mapping utils
import utils.mapping.utils
#   - trace analysis
import analysis.trace

matplotlib.rcParams.update({'font.size': 16})

# north, south, west, east gps coord limits of FEUP map
LATN = 41.176796
LATS = 41.179283
LONE = -8.593912
LONW = -8.598336
# central gps coords for FEUP
LAT  = (41.176796 + 41.179283) / 2.0
LON = (-8.598336 + -8.593912) / 2.0

def rates(ax, input_dir, trace_nr, metric = 'throughput', time_limits = None):

    # plot configurations
    # FIXME : this should be a parameter passed to the function
    nodes = {
        'm1' : {
            'color' : 'red',
            'label' : '38',
            'marker' : 'o',
            'coef' : 1.0 / 1000000.0,
            'markersize' : 2.0
        },
        'w1' : {
            'color' : 'green',
            'label' : '46',
            'marker' : 'o',
            'coef' : 1.0 / 1000000.0,
            'markersize' : 2.0
        },
        'w2' : {
            'color' : 'blue',
            'label' : '6',
            'marker' : 'o',
            'coef' : 1.0 / 1000000.0,
            'markersize' : 2.0
        },        
        'w3' : {
            'color' : 'orange',
            'label' : '11',
            'marker' : 'o',
            'coef' : 1.0 / 1000000.0,
            'markersize' : 2.0
        },
    }

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    ax.xaxis.grid(True)
    ax.yaxis.grid(True)
    ax.set_title('%s per channel (trace %s)' % (metric, trace_nr))

    # aux variables
    if not time_limits:
        time_limits = [None, None]

    for node in sorted(nodes.keys()):

        db_name = ('/%s/%s/%s' % (node, 'basic', 'bitrates'))
        if db_name not in database.keys():
            sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (db_name))
            return

        data = database.select(db_name).sort_values(by = ['timed-tmstmp']).reset_index(drop = True)

        _data = data[['timed-tmstmp', metric]].drop_duplicates(subset = ['timed-tmstmp'])
        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['timed-tmstmp'] ]
        plot.utils.update_time_limits(time_limits, dates)

        analysis.trace.utils.metrics.smoothen(_data, column = metric, span = 10)

        ax.plot_date(
            dates,
            _data[metric] * nodes[node]['coef'],
            linewidth = 1.0, linestyle = '-', color = nodes[node]['color'], label = nodes[node]['label'], 
            marker = None, markersize = 0.0, markeredgewidth = 0.0)

    leg = ax.legend(
        fontsize = 10, 
        ncol = 4, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    for legobj in leg.legendHandles:
        legobj.set_linewidth(2.0)

    # divide xx axis in 5 ticks
    xticks = plot.utils.get_time_xticks(time_limits)

    ax.set_xlabel("time")
    ax.set_ylabel("%s (Mbps)" % (metric))

    ax.set_xlim(time_limits[0], time_limits[1])
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(xt)[11:-7] for xt in xticks])

def rss(ax, input_dir, trace_nr, time_limits = None):

    nodes = {
        'm1' : {
            'color' : 'red',
            'label' : '38',
            'marker' : 'o',
            'coef' : 1.0 / 1000000.0,
            'markersize' : 2.0
        },
        'w1' : {
            'color' : 'green',
            'label' : '46',
            'marker' : 'o',
            'coef' : 1.0 / 1000000.0,
            'markersize' : 2.0
        },
        'w2' : {
            'color' : 'blue',
            'label' : '6',
            'marker' : 'o',
            'coef' : 1.0 / 1000000.0,
            'markersize' : 2.0
        },        
        'w3' : {
            'color' : 'orange',
            'label' : '11',
            'marker' : 'o',
            'coef' : 1.0 / 1000000.0,
            'markersize' : 2.0
        },
    }

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    ax.xaxis.grid(True)
    ax.yaxis.grid(True)
    ax.set_title('RSS per channel (trace %s)' % (trace_nr))

    # aux variables
    if not time_limits:
        time_limits = [None, None]

    for node in sorted(nodes.keys()):

        db_name = ('/%s/%s/%s' % (node, 'basic', 'beacons'))
        if db_name not in database.keys():
            sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (db_name))
            return

        data = database.select(db_name).sort_values(by = ['epoch time']).reset_index(drop = True)

        _data = data[['epoch time', 'wlan rssi']].drop_duplicates(subset = ['epoch time'])
        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['epoch time'] ]
        plot.utils.update_time_limits(time_limits, dates)

        analysis.trace.utils.metrics.smoothen(_data, column = 'wlan rssi', span = 10)

        ax.plot_date(
            dates,
            _data['wlan rssi'],
            linewidth = 1.0, linestyle = '-', color = nodes[node]['color'], label = nodes[node]['label'], 
            marker = None, markersize = 0.0, markeredgewidth = 0.0)

    leg = ax.legend(
        fontsize = 10, 
        ncol = 4, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    for legobj in leg.legendHandles:
        legobj.set_linewidth(2.0)

    # divide xx axis in 5 ticks
    xticks = plot.utils.get_time_xticks(time_limits)

    ax.set_xlabel("time")
    ax.set_ylabel("RSS (dBm)")

    ax.set_xlim(time_limits[0], time_limits[1])
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(xt)[11:-7] for xt in xticks])

def vs_distance(ax, input_dir, trace_nr, configs):

    nodes = {
        'm1' : {
            'color' : 'red',
            'label' : '38',
            'marker' : 'o',
            'coef' : 1.0 / 1000000.0,
            'markersize' : 2.0
        },
        'w1' : {
            'color' : 'green',
            'label' : '46',
            'marker' : 'o',
            'coef' : 1.0 / 1000000.0,
            'markersize' : 2.0
        },
        'w2' : {
            'color' : 'blue',
            'label' : '6',
            'marker' : 'o',
            'coef' : 1.0 / 1000000.0,
            'markersize' : 2.0
        },        
        'w3' : {
            'color' : 'orange',
            'label' : '11',
            'marker' : 'o',
            'coef' : 1.0 / 1000000.0,
            'markersize' : 2.0
        },
    }

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    ax.xaxis.grid(True)
    ax.yaxis.grid(True)
    ax.set_title('%s (per channel) vs. distance (trace %s)' % (configs['metric'], trace_nr))

    # get rss data from all nodes
    data = analysis.trace.utils.data.merge_gps(input_dir, trace_nr, configs['metric'], cell_size = 20.0)
    data = data[['timed-tmstmp', 'lat', 'lon'] + nodes.keys()].sort_values(by = ['timed-tmstmp']).reset_index(drop = True)
    # for node in nodes.keys():
    #     analysis.metrics.smoothen(data, column = node, span = 50)

    # add distance to ref point
    ref = {'lat' : 41.178685, 'lon' : -8.597872}
    pos = [ [ row['lat'], row['lon'] ] for index, row in data[['lat', 'lon']].iterrows() ]
    data['ref-dist'] = [ utils.mapping.utils.gps_to_dist(ref['lat'], ref['lon'], p[0], p[1]) for p in pos ]
    data = data.sort_values(by = ['ref-dist']).reset_index(drop = True)
    # offset = data['ref-dist'].min()
    offset = 0.0

    for node in sorted(nodes.keys()):

        _data = data[['ref-dist', node]]
        if 'filter' in configs:
            _data = _data[_data[node] < configs['filter']]
        _data = _data.sort_values(by = ['ref-dist']).reset_index(drop = True)
        analysis.trace.utils.metrics.smoothen(_data, column = node, span = 50)

        ax.plot(
            _data['ref-dist'] - offset,
            _data[node] * configs['coef'],
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
    ax.set_xlim(data['ref-dist'].min() - offset, data['ref-dist'].max() - offset)

def channel_util(ax, input_dir, trace_nr, time_limits = None):

    aps = {
        'ap1' : {
            'color' : 'blue',
            'label' : '6',
            'linewidth' : 1.0,
            'marker' : None,
            'markersize' : 0.0
        },
        'ap2' : {
            'color' : 'red',
            'label' : '38',
            'linewidth' : 1.0,
            'marker' : None,
            'markersize' : 0.0
        },
        'ap3' : {
            'color' : 'orange',
            'label' : '11',
            'linewidth' : 1.0,
            'marker' : None,
            'markersize' : 0.0
        },
        'ap4' : {
            'color' : 'green',
            'label' : '46',
            'linewidth' : 1.0,
            'marker' : None,
            'markersize' : 0.0
        },
    }

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    ax.xaxis.grid(True)
    ax.yaxis.grid(True)
    ax.set_title('channel util. per channel (trace %s)' % (trace_nr))

    # aux variables
    if not time_limits:
        time_limits = [None, None]

    for ap in sorted(aps.keys()):

        db_name = ('/%s/%s/%s' % (ap, 'basic', 'channel-util'))
        if db_name not in database.keys():
            sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (db_name))
            return

        data = database.select(db_name).sort_values(by = ['timestamp']).reset_index(drop = True)

        _data = data[['timestamp', 'cutil']].drop_duplicates(subset = ['timestamp'])
        _data = _data[_data['cutil'] < 100.0]
        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['timestamp'] ]
        plot.utils.update_time_limits(time_limits, dates)

        analysis.trace.utils.metrics.smoothen(_data, column = 'cutil', span = 5)

        ax.plot_date(
            dates,
            _data['cutil'],
            linewidth = aps[ap]['linewidth'], linestyle = '-', color = aps[ap]['color'], label = aps[ap]['label'], 
            marker = aps[ap]['marker'], markersize = aps[ap]['markersize'], markeredgewidth = 0.0)

    leg = ax.legend(
        fontsize = 10, 
        ncol = 4, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    for legobj in leg.legendHandles:
        legobj.set_linewidth(2.0)

    # divide xx axis in 5 ticks
    xticks = plot.utils.get_time_xticks(time_limits)

    ax.set_xlabel("time")
    ax.set_ylabel("channel util. (%)")

    ax.set_xlim(time_limits[0], time_limits[1])
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(xt)[11:-7] for xt in xticks])

    ax.set_ylim([0.0, 115])
    ax.set_yticks([0, 20, 40, 60, 80, 100])

def distances(ax, input_dir, trace_nr, time_limits = None):

    pos = {
        'p1' : {
            'color' : 'green',
            'label' : '11 & 46',
            'linewidth' : 1.0,
            'marker' : None,
            'markersize' : 0.0
        },
        'p2' : {
            'color' : 'red',
            'label' : '6 & 38',
            'linewidth' : 1.0,
            'marker' : None,
            'markersize' : 0.0
        },        
    }

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))
    db_name = ('/%s/%s' % ('gps', 'distances'))
    if db_name not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (db_name))
        return

    dist_data = database.select(db_name).sort_values(by = ['timestamp']).reset_index(drop = True)

    ax.xaxis.grid(True)
    ax.yaxis.grid(True)
    ax.set_title('dist. (in m) to ap positions (trace %s)' % (trace_nr))

    # aux variables
    if not time_limits:
        time_limits = [None, None]

    for p in pos:

        _dist_data = dist_data[['timestamp', p]].drop_duplicates(subset = ['timestamp'])
        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _dist_data['timestamp'] ]
        plot.utils.update_time_limits(time_limits, dates)

        ax.plot_date(
            dates,
            _dist_data[p],
            linewidth = pos[p]['linewidth'], linestyle = '-', color = pos[p]['color'], label = pos[p]['label'], 
            marker = pos[p]['marker'], markersize = pos[p]['markersize'], markeredgewidth = 0.0)

    leg = ax.legend(
        fontsize = 10, 
        ncol = 4, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    for legobj in leg.legendHandles:
        legobj.set_linewidth(2.0)

    # divide xx axis in 5 ticks
    xticks = plot.utils.get_time_xticks(time_limits)

    ax.set_xlabel("time")
    ax.set_ylabel("distance to AP pos. (m)")

    ax.set_xlim(time_limits[0], time_limits[1])
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(xt)[11:-7] for xt in xticks])

def bitrate(input_dir, trace_nr, trace_output_dir, time_limits = None):

    plt.style.use('classic')

    # plot configs
    best = {
        '1:A'  : {'color' : 'green',  'linestyle' : '-', 'label' : 'A', 'x-label' : '', 'coef' : 1.0, 'marker' : None, 'markersize' : 0.0},
        '2:B'  : {'color' : 'blue',   'linestyle' : '-', 'label' : 'B', 'x-label' : '', 'coef' : 1.0, 'marker' : None, 'markersize' : 0.0},
        '3:C'  : {'color' : 'red',    'linestyle' : '-', 'label' : 'C', 'x-label' : '', 'coef' : 1.0, 'marker' : None, 'markersize' : 0.0},
        '4:D'  : {'color' : 'orange', 'linestyle' : '-', 'label' : 'D', 'x-label' : '', 'coef' : 1.0, 'marker' : None, 'markersize' : 0.0},
        '5:BP' : {'color' : 'blue',   'linestyle' : ':', 'label' : 'BP', 'x-label' : '', 'coef' : 1.0, 'marker' : 'o', 'markersize' : 1.5},
        '6:CP' : {'color' : 'red', 'linestyle' : ':', 'label' : 'CP', 'x-label' : '', 'coef' : 1.0, 'marker' : 'o', 'markersize' : 2.5},
        '7:DP' : {'color' : 'orange', 'linestyle' : ':', 'label' : 'DP', 'x-label' : '', 'coef' : 1.0, 'marker' : 'o', 'markersize' : 3.5}
    }

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    bitrates = pd.read_csv(os.path.join(trace_dir, ('bitrate-adapt.csv')))

    # 1) 'best-rate' chain performance over time
    if not time_limits:
        time_limits = [None, None]

    figs = [ plt.figure(figsize = (12.0, 1.0 * 2.0)), plt.figure(figsize = (6.0, 1.0 * 2.0)) ]
    axs = [ figs[0].add_subplot(1, 2, 1), figs[0].add_subplot(1, 2, 2), figs[1].add_subplot(1, 2, 1), figs[1].add_subplot(1, 2, 2) ]

    for b in sorted(best.keys()):

        data = bitrates[bitrates['best-rate'] == b.split(':')[-1]]
        if data.empty:
            continue

        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in data['timestamp'] ]
        plot.utils.update_time_limits(time_limits, dates)

        # note: why is the avg. thghpt so much lower than the expected bitrate w/ MCS14?
        axs[0].plot_date(
            dates,
            data['avg-thghpt'],
            linewidth = 0.5, linestyle = '-', color = best[b]['color'], label = b.split(':')[-1], 
            marker = best[b]['marker'], markersize = best[b]['markersize'], markeredgewidth = 0.0)

        axs[1].plot_date(
            dates,
            data['avg-prob'] / 100.0,
            linewidth = 0.5, linestyle = '-', color = best[b]['color'], label = b.split(':')[-1], 
            marker = best[b]['marker'], markersize = best[b]['markersize'], markeredgewidth = 0.0)

        best[b]['x-label'] = 'avg. throughput (Mbps)'
        plot.utils.cdf(axs[2], data, metric = 'avg-thghpt', plot_configs = best[b])

        best[b]['x-label'] = 'avg. del. probability'
        best[b]['x-lim'] = [0.60, 1.0]
        best[b]['coef'] = 0.01
        plot.utils.cdf(axs[3], data, metric = 'avg-prob', plot_configs = best[b])

    for i in [0, 1]:

        axs[i].xaxis.grid(True)
        axs[i].yaxis.grid(True)

        legend = axs[i].legend(
            fontsize = 8, 
            ncol = 3, loc = 'lower right',
            handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

        for legobj in legend.legendHandles:
            legobj.set_linewidth(1.0)

    axs[0].set_ylabel('bitrate (Mbps)')
    axs[1].set_ylabel('del. probability')
    axs[1].set_ylim([0.6, 1.1])

    # x-label
    for k in [0, 1]:

        axs[k].set_xlabel('time (sec)')
        # x-lims : set w/ time_limits
        axs[k].set_xlim(time_limits[0], time_limits[1])
        xticks = plot.utils.get_time_xticks(time_limits, duration = 10.0)
        axs[k].set_xticks(xticks)
        xticklabels = [''] * len(xticks)
        for i in list(np.arange(0, len(xticklabels), 5)):
            xticklabels[i] = (((xticks[i].astype('uint64') / 1e6).astype('uint32')) - ((xticks[0].astype('uint64') / 1e6).astype('uint32')))
        axs[k].set_xticklabels(xticklabels, ha = 'center')

    figs[0].tight_layout()
    figs[0].savefig(os.path.join(trace_output_dir, ("bitrate-best-rates.pdf")), bbox_inches = 'tight', format = 'pdf')

    figs[1].tight_layout()
    figs[1].savefig(os.path.join(trace_output_dir, ("bitrate-best-rates-cdfs.pdf")), bbox_inches = 'tight', format = 'pdf')
    
def create_grid(lat = [LATN, LATS], lon = [LONW, LONE], cell_size = 20.0):

    x_cell_num, y_cell_num = analysis.trace.utils.gps.get_cell_num(cell_size = cell_size, lat = lat, lon = lon)
    # limits for (x,y) coordinates in grid
    max_x = int(x_cell_num)
    max_y = int(y_cell_num)
    # height and width of cells (in degrees)
    w = (lon[1] - lon[0]) / float(x_cell_num)
    h = (lat[0] - lat[1]) / float(y_cell_num)

    # create a geodataframe of polygons, 1 polygon per cell, w/ cell ids
    polygons = []
    cell_ids = []
    for i in range(max_x):
        for j in range(max_y):

            polygons.append(
                shapely.geometry.Polygon(
                    [
                    (lon[0] + (i * w), lat[1] + (j * h)), 
                    (lon[0] + ((i + 1) * w), lat[1] + (j * h)), 
                    (lon[0] + ((i + 1) * w), lat[1] + ((j + 1) * h)), 
                    (lon[0] + (i * w), lat[1] + ((j + 1) * h))
                    ]))

            cell_ids.append({'cell_x' : i, 'cell_y' : j})

    cell_ids = pd.DataFrame(cell_ids, columns = ['cell_x', 'cell_y'])
    grid = gp.GeoDataFrame({'geometry' : polygons, 'cell_x' : cell_ids['cell_x'], 'cell_y' : cell_ids['cell_y']})
    return grid, w, h

def maps(input_dir, trace_nr, trace_output_dir, 
    bbox = [LONW, LATS, LONE, LATN],
    cell_size = 20.0, redraw = False, time_limits = []):

    # save map graphs on <trace-output-dir>/maps/<cell-size>/
    maps_dir = os.path.join(trace_output_dir, ("maps"))
    if not os.path.isdir(maps_dir):
        os.makedirs(maps_dir)

    maps_dir = os.path.join(maps_dir, ("%s" % (cell_size)))
    if not os.path.isdir(maps_dir):
        os.makedirs(maps_dir)
    elif not redraw:
        sys.stderr.write("""[INFO] %s exists. skipping plotting.\n""" % (maps_dir))
        return

    database = utils.hdfs.get_db(input_dir, trace_nr)
    # get gps coords of trace
    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    gps_data = analysis.trace.utils.gps.get_data(input_dir, trace_dir)[['timestamp', 'lat', 'lon']]

    if time_limits:
        gps_data = gps_data[(gps_data['timestamp'] >= time_limits[0]) & (gps_data['timestamp'] <= time_limits[1])].reset_index(drop = True)

    # gps_data.rename(index = str, columns = {'timestamp' : 'timed-tmstmp'}, inplace = True)
    timestamp_limits = [gps_data.iloc[0]['timestamp'], gps_data.iloc[-1]['timestamp']]

    nodes = {
        'm1' : {
            'color' : 'red',
            'label' : '38',
            'marker' : 'o',
            'coef' : 1.0 / 1000000.0,
            'markersize' : 2.0
        },
        'w1' : {
            'color' : 'green',
            'label' : '46',
            'marker' : 'o',
            'coef' : 1.0 / 1000000.0,
            'markersize' : 2.0
        },
        'w2' : {
            'color' : 'blue',
            'label' : '6',
            'marker' : 'o',
            'coef' : 1.0 / 1000000.0,
            'markersize' : 2.0
        },        
        'w3' : {
            'color' : 'orange',
            'label' : '11',
            'marker' : 'o',
            'coef' : 1.0 / 1000000.0,
            'markersize' : 2.0
        },
    }

    # merge gps coords data w/ tcpdump sample timestamps
    # NOTE : this will open gaps in gps_data, which will be closed later via interpolation of lat, lon coords
    for node in nodes:
        db_name = ('/%s/%s/%s' % (node, 'basic', 'bitrates'))
        if db_name not in database.keys():
            sys.stderr.write("""[INFO] %s already in database. skipping data extraction.\n""" % (db_name))
            continue

        rate_data = database.select(db_name).sort_values(by = ['timed-tmstmp']).reset_index(drop = True)[['timed-tmstmp']]
        rate_data['timestamp'] = rate_data['timed-tmstmp'].astype(int)
        gps_data = pd.merge(gps_data, rate_data,  on = ['timestamp'], how = 'left')

    # fill the gaps left by merge using interpolation
    gps_data = gps_data.sort_values(by = ['timestamp']).reset_index(drop = True)
    gps_data = gps_data[(gps_data['timestamp'] >= timestamp_limits[0]) & (gps_data['timestamp'] <= timestamp_limits[1])]
    # analysis.trace.fix_gaps(gps_data, subset = ['lat', 'lon'], column = 'timed-tmstmp')
    # gps_data = gps_data.dropna(subset = ['lat', 'lon'])

    # 1) print a 'fancy' heatmap using the folium library
    center_lat = (bbox[1] + bbox[3]) / 2.0
    center_lon = (bbox[0] + bbox[2]) / 2.0
    plot.gps.heatmap(gps_data.groupby(['lat', 'lon']).size().reset_index(name = 'counts'), maps_dir, 
        map_cntr = [center_lat, center_lon], map_types = ['heatmap', 'clustered-marker'])

    # 2) print a custom heatmap, divided by cells, which will be used in our algos 
    # add cell ids
    analysis.trace.utils.gps.add_cells(gps_data, cell_size, bbox = bbox)    
    # 2.1) print cdf plot of samples per cell
    sample_count = gps_data.groupby(['cell_id', 'cell_x', 'cell_y']).size().reset_index(drop = False, name = 'count')
    cdf = sample_count.groupby(['count']).size().reset_index(name = 'counts')
    cdf['counts'] = np.array(cdf['counts'].cumsum(), dtype = float)
    cdf['counts'] = cdf['counts'] / cdf['counts'].values[-1]

    fig = plt.figure(figsize = (5, 2.5))
    ax = fig.add_subplot(111)
    ax.xaxis.grid(True, ls = 'dotted', lw = 0.75)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.75)

    ax.plot(cdf['count'], cdf['counts'], 
        alpha = 0.75, linewidth = 1.0, color = 'blue', linestyle = '-')

    ax.set_xlabel("# of samples per cell")
    ax.set_ylabel("CDF")

    # ax.set_xticks(np.arange(0, np.amax(cdf['count']), 10)
    # ax.set_xticklabels([-10, -20, -30, -40, -50, -60, -70, -80])
    ax.set_yticks(np.arange(0.0, 1.1, 0.25))

    plt.tight_layout()
    plt.savefig(os.path.join(maps_dir, "cell-cdfs.pdf"), bbox_inches = 'tight', format = 'pdf')

    # 2.2) print map of cells
    # extract roads using OpenStreetMaps APIs
    road_hash = utils.mapping.openstreetmap.get_road_hash(bbox = bbox, tags = ['highway='])
    if not os.path.isdir(os.path.join(trace_output_dir, road_hash)):
        roads = utils.mapping.openstreetmap.extract_roads(trace_output_dir, 
            tags = ['highway='], 
            bbox = bbox)
    roads = gp.GeoDataFrame.from_file(os.path.join(trace_output_dir, road_hash))

    # filters : remove unwanted roads
    roads = roads.dropna(subset = ['highway'])
    roads = roads[roads['highway'].str.contains('footway|cycleway') == False]
    roads = roads[roads.type == 'LineString'][['highway', 'name', 'geometry']]

    # code to select a bbox from roads
    # FIXME : this uses the .overlay(how = 'intersection') method, which is inneficient
    start = timeit.default_timer()
    # define a smaller bbox
    # FIXME : why not use the original bbox passed as argument? well, OpenStreetMaps doesn't
    #         allow us to extract roads from a small bbox such as the one below
    _bbox = [(-8.597, 41.178), (-8.597, 41.180), (-8.592, 41.180), (-8.592, 41.178)]
    roads['geometry'] = roads['geometry'].buffer(0.000025)
    base = [ shapely.geometry.Polygon(_bbox) ]
    base = gp.GeoDataFrame({'geometry':base})
    roads = gp.overlay(base, roads, how = 'intersection')
    print("%s::maps() : [INFO] buffer() produced in %.3f sec" % (sys.argv[0], timeit.default_timer() - start))

    # the CRS in the original dataframe is 4326 (or WGS84), the one used by GPS
    roads.crs = {'init' : 'epsg:4326'}
    # find the graph's hight-width ratio
    dy = utils.mapping.utils.gps_to_dist(41.180, 0.0, 41.178, 0.0)
    dx = utils.mapping.utils.gps_to_dist(41.178, -8.597, 41.178, -8.592)
    # create fig w/ h-w ratio
    fig = plt.figure(figsize = ((dx / dy) * 5.0, 5.0))

    ax = fig.add_subplot(111)
    ax.xaxis.grid(True, ls = 'dotted', lw = 0.75)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.75)
    
    # convert roads CRS to 3763, with meter coords
    roads.plot(ax = ax, facecolor = 'black', zorder = 0)

    # on top of the roads, draw the cells for which we have samples, with a gradient color scale
    grid, w, h = create_grid(lat = [bbox[3], bbox[1]], lon = [bbox[0], bbox[2]], cell_size = cell_size)
    # upgrade grid, by merging sample counts w/ polygons
    grid = pd.merge(grid, sample_count, on = ['cell_x', 'cell_y'], how = 'inner')
    # center point for each polygon
    grid['coords'] = grid['geometry'].apply(lambda x: x.representative_point().coords[:])
    grid['coords'] = [ coords[0] for coords in grid['coords'] ]
    # print the polygons, colored according to sample count
    grid.crs = {'init' : 'epsg:4326'}
    grid.loc[grid['count'] > grid['count'].median(), 'count'] = grid['count'].median()
    grid.plot(ax = ax, zorder = 5, column = 'count', cmap = 'YlOrRd', legend = True, alpha = .75)

    ax.set_title('# of packets recorded per %d m x %d m cell' % (int(cell_size), int(cell_size)))
    ax.set_xlabel('distance (m)')
    ax.set_ylabel('distance (m)')

    xticks = np.arange(bbox[0], bbox[2] + (2* w), w)
    ax.set_xticks(xticks)
    ax.set_xticklabels(
        np.arange((3 - int(grid['cell_x'].min())) * int(cell_size), (int(cell_size) * len(xticks)) -int(grid['cell_x'].min()), int(cell_size)),
        rotation = 30, ha = 'right')

    yticks = np.arange(bbox[1], bbox[3] + h, h)
    ax.set_yticks(yticks)
    ax.set_yticklabels(np.arange((3 - int(grid['cell_y'].min())) * int(cell_size), (int(cell_size) * len(xticks)) -int(grid['cell_y'].min()), int(cell_size)))

    # add aps positions to map, as red dots
    aps = {
        'ap2' : {
            'color' : 'red',
            'label' : 'P2',
            'lat' : 41.178518,
            'lon' : -8.595366
        },
        'ap4' : {
            'color' : 'green',
            'label' : 'P1',
            'lat' : 41.178563,
            'lon' : -8.596012
        },
    }


    points = []
    for i, ap in enumerate(aps):

        lon = aps[ap]['lon']
        lat = aps[ap]['lat']

        points.append(shapely.geometry.Point(lon, lat))

    points = gp.GeoDataFrame({'geometry' : points})
    points.plot(ax = ax, zorder = 10, color = 'red')

    for i, ap in enumerate(aps):

        plt.annotate(
            s = ('%s' % (aps[ap]['label'])), 
            xy = (aps[ap]['lon'], aps[ap]['lat'] - 0.00001),
            horizontalalignment = 'center',
            zorder = 15,
            size = 5,
            color = 'white')

    # add cell ids to 
    for idx, row in grid.iterrows():
        plt.annotate(
            s = ('(%s,%s)' % (str(row['cell_x']), str(row['cell_y']))), 
            xy = row['coords'], 
            horizontalalignment = 'center',
            zorder = 20,
            size = 5,
            color = 'white' if row['count'] > 200 else 'black')

    plt.tight_layout()
    plt.savefig(os.path.join(maps_dir, "cell-map.pdf"), bbox_inches = 'tight', format = 'pdf')

def best(ax, input_dir, trace_nr, 
    metric = 'throughput',
    configs = {
        'throughput' : {
            'y-label' : 'throughput (Mbps)',
            'coef' : 1.0 / 1000000.0
        },
        'wlan data rate' : {
            'y-label' : 'wlan data rate (Mbps)',
            'coef' : 1.0 / 1000000.0
        },
        'rss' : {
            'y-label' : 'RSS (dbm)',
            'coef' : 1.0
        },
        'distances' : {
            'y-label' : 'dist (m)',
            'coef' : 1.0
        }
    }, 
    time_limits = None):

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

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    db_name = ('/%s/%s' % ('best', metric))
    if db_name not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (db_name))
        return

    data = database.select(db_name).sort_values(by = ['timed-tmstmp']).reset_index(drop = True)
    # FIXME: why do we end up w/ duplicate 'interval-tmstmp' values?
    data = data.drop_duplicates(subset = ['timed-tmstmp'])

    ax.xaxis.grid(True)
    ax.yaxis.grid(True)

    if metric == 'distances':
        ax.set_title("""closest AP (per 0.5 sec segment, trace %s)""" % (trace_nr))
    else:
        ax.set_title("""AP w/ best %s (per 0.5 sec segment, trace %s)""" % (metric, trace_nr))

    # (1) plot background segments w/ color of best mac for the segment
    # find blocks of consecutive mac addrs
    data['block'] = ((data.best.shift(1) != data.best) | ((data['timed-tmstmp'].shift(1) - data['timed-tmstmp']) < -0.5)).astype(int).cumsum()
    segments = data.groupby(['best','block'])['timed-tmstmp'].apply(np.array).reset_index(drop = False).sort_values(by = ['block'])
    for node in nodes:
        for i, segment in segments[segments['best'] == node].iterrows():
            dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in [ segment['timed-tmstmp'][0], segment['timed-tmstmp'][-1] + 0.5 ] ]
            ax.axvspan(dates[0], dates[-1], linewidth = 0.0, facecolor = nodes[node]['color'], alpha = 0.20)

    # (2) plot all metric values
    if not time_limits:
        time_limits = [None, None]

    for node in nodes:

        _data = data[data['best'] == node]
        if _data.empty:
            continue

        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['timed-tmstmp'] ]
        plot.utils.update_time_limits(time_limits, dates)

        ax.plot(
            dates,
            _data['best-val'] * configs[metric]['coef'],
            linewidth = 0.0, 
            linestyle = '-', 
            color = nodes[node]['color'], 
            label = nodes[node]['label'], 
            markersize = nodes[node]['markersize'], 
            marker = nodes[node]['marker'], 
            markeredgewidth = 0.0)

    ax.set_ylabel(configs[metric]['y-label'])

    # x-label
    ax.set_xlabel('time')
    # x-lims
    ax.set_xlim(time_limits[0], time_limits[1])
    # divide xx axis in 5 ticks
    xticks = plot.utils.get_time_xticks(time_limits)
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(xt)[11:-7] for xt in xticks])

    plt.gcf().autofmt_xdate()
