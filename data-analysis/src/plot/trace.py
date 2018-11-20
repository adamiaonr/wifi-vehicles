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

# north, south, west, east limits of map, in terms of geo coordinates
LATN = 41.176796
LATS = 41.179283
LONE = -8.593912
LONW = -8.598336
# gps coords for a 'central' pin on FEUP, Porto, Portugal
LAT  = (41.176796 + 41.179283) / 2.0
LON = (-8.598336 + -8.593912) / 2.0

def distances(ax, input_dir, trace_nr, time_limits = None):

    ax.xaxis.grid(True)
    ax.yaxis.grid(True)

    ax.set_title('dist. (in m) to fixed pos. (trace %s)' % (trace_nr))

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']

    # get dist. data
    dist_data = analysis.trace.get_distances(input_dir, trace_nr)
    # aux variables
    if not time_limits:
        time_limits = [None, None]

    visited = []
    for i, client in clients.iterrows():

        if client['mac'] not in dist_data:
            continue

        # avoid going through same pos twice
        if client['label'] in visited:
            continue
        else:
            visited.append(client['label'])

        _dist_data = dist_data[ ['interval-tmstmp', client['mac']] ].drop_duplicates(subset = ['interval-tmstmp'])
        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _dist_data['interval-tmstmp'] ]
        plot.utils.update_time_limits(time_limits, dates)

        ax.plot_date(
            dates,
            _dist_data[client['mac']],
            linewidth = 0.0, linestyle = '-', color = client['color'], label = client['label'], 
            marker = client['marker'], markersize = client['marker-size'], markeredgewidth = 0.0)

    ax.legend(
        fontsize = 10, 
        ncol = 4, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    # # draw vertical lines for each lap & turn
    # gps_data, lap_timestamps = analysis.gps.get_data(input_dir, os.path.join(input_dir, ("trace-%03d" % (int(trace_nr)))), tag_laps = False)
    # for ts in lap_timestamps['start']:
    #     ax.axvline(x = datetime.datetime.fromtimestamp(ts), color = 'k', linestyle = '-', linewidth = .75)
    # for ts in lap_timestamps['turn']:
    #     ax.axvline(x = datetime.datetime.fromtimestamp(ts), color = 'k', linestyle = '--', linewidth = .75)

    # divide xx axis in 5 ticks
    xticks = plot.utils.get_time_xticks(time_limits)

    ax.set_xlabel("time")
    ax.set_ylabel("distance (m)")

    ax.set_xlim(time_limits[0], time_limits[1])
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(xt)[11:-7] for xt in xticks])

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

    best_db = ('/%s/%s' % ('best', metric))
    if best_db not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (best_db))
        return

    ax.xaxis.grid(True)
    ax.yaxis.grid(True)
    ax.set_title('pos. w/ best %s per 0.5 sec segment (trace %s)' % (metric, trace_nr))

    data = database.select(best_db).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
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
            _data[client['mac']] * configs[metric]['coef'],
            linewidth = 0.0, 
            linestyle = '-', 
            color = client['color'], 
            label = client['label'], 
            markersize = client['marker-size'], 
            marker = client['marker'], 
            markeredgewidth = 0.0)

    # # plot a black line w/ throughput for all mac addrs
    # _data = data.iloc[::5, :]
    # dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ]
    # ax.plot(
    #     dates,
    #     (_data[macs].max(axis = 1).values) * configs[metric]['coef'],
    #     alpha = .5,
    #     linewidth = 0.75, 
    #     linestyle = '-', 
    #     color = 'black', 
    #     marker = None)

    ax.legend(
        fontsize = 10, 
        ncol = 4, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

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
    
def create_grid(x_cell_num, y_cell_num, lat = [LATN, LATS], lon = [LONW, LONE]):

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

            cell_ids.append({'cell-x' : i, 'cell-y' : j})

    cell_ids = pd.DataFrame(cell_ids, columns = ['cell-x', 'cell-y'])
    grid = gp.GeoDataFrame({'geometry' : polygons, 'cell-x' : cell_ids['cell-x'], 'cell-y' : cell_ids['cell-y']})

    return grid

def cells(input_dir, trace_nr, trace_output_dir, cell_size = 20.0, redraw = False):

    maps_dir = os.path.join(trace_output_dir, ("maps"))
    if not os.path.isdir(maps_dir):
        os.makedirs(maps_dir)
        
    maps_dir = os.path.join(maps_dir, ("%s" % (cell_size)))
    if not os.path.isdir(maps_dir):
        os.makedirs(maps_dir)
    elif not redraw:
        sys.stderr.write("""[INFO] %s exists. skipping plotting.\n""" % (maps_dir))
        return

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']

    database = analysis.trace.get_db(input_dir, trace_nr)

    # get gps pos of trace
    dist_db = ('/%s' % ('dist-data'))
    if dist_db not in database.keys():
        sys.stderr.write("""[INFO] %s already in database. skipping data extraction.\n""" % (dist_db))
        return

    gps_data = database.select(dist_db).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)[['interval-tmstmp', 'lat', 'lon', 'lap-number', 'direction']]

    # merge gps data w/ throughput data
    macs = []
    for i, client in clients.iterrows():

        interval_db = ('/%s/%s' % ('interval-data', client['mac']))
        if interval_db not in database.keys():
            continue

        # load data for a client mac
        data = database.select(interval_db)
        if data.empty:
            continue

        data[client['mac']] = data['throughput']
        macs.append(client['mac'])

        # FIXME : 'interval-data' already has gps info. why are we merging it again?
        gps_data = pd.merge(gps_data, data[ ['interval-tmstmp', client['mac']] ], on = ['interval-tmstmp'], how = 'outer')

    # drop rows w/ undefined throughput values for all mac addrs
    gps_data = gps_data.dropna(subset = macs, how = 'all').drop_duplicates(subset = ['interval-tmstmp']).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
    # fix timestamp gaps
    gps_data['timestamp'] = gps_data['interval-tmstmp'].astype(int)

    plot.gps.heatmap(gps_data.groupby(['lat', 'lon']).size().reset_index(name = 'counts'), maps_dir, 
        map_cntr = [LAT, LON], map_types = ['heatmap', 'clustered-marker'])

    # add cell ids
    x_cell_num, y_cell_num = analysis.gps.get_cell_num(gps_data, cell_size = cell_size, lat = [LATN, LATS], lon = [LONW, LONE])
    gps_data['cell-x'] = gps_data['lon'].apply(lambda x : int((x - LONW) / (LONE - LONW) * x_cell_num))
    gps_data['cell-y'] = gps_data['lat'].apply(lambda y : int((y - LATS) / (LATN - LATS) * y_cell_num))

    # print cdf plot of samples per cell
    sample_count = gps_data.groupby(['cell-x', 'cell-y']).size().reset_index(name = 'count')
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

    # print coverage map of cells
    bbox = [LONW, LATS, LONE, LATN]
    roads = None
    if os.path.isdir(os.path.join(trace_output_dir, ("roads"))):
        roads = gp.GeoDataFrame.from_file(os.path.join(trace_output_dir, "roads"))
    else:
        roads = mapping.openstreetmap.get_roads(trace_output_dir, 
            tags = ['highway='], 
            bbox = bbox)

    # filters
    roads = roads.dropna(subset = ['highway'])
    roads = roads[roads['highway'].str.contains('footway|cycleway') == False]
    roads = roads[roads.type == 'LineString'][['highway', 'name', 'geometry']]

    # code to select a bbox from roads
    # FIXME : this uses the .overlay(how = 'intersection') method, which is inneficient
    start = timeit.default_timer()
    # bbox
    bbox = [(-8.597, 41.178), (-8.597, 41.180), (-8.592, 41.180), (-8.592, 41.178)]
    roads['geometry'] = roads['geometry'].buffer(0.000025)
    base = [ shapely.geometry.Polygon(bbox) ]
    base = gp.GeoDataFrame({'geometry':base})
    roads = gp.overlay(base, roads, how = 'intersection')
    print("%s::plot_grid() : [INFO] buffer() produced in %.3f sec" % (sys.argv[0], timeit.default_timer() - start))

    dy = mapping.utils.gps_to_dist(41.180, 0.0, 41.178, 0.0)
    dx = mapping.utils.gps_to_dist(41.178, -8.597, 41.178, -8.592)

    fig = plt.figure(figsize = ((dx / dy) * 5.0, 5.0))

    ax = fig.add_subplot(111)
    ax.xaxis.grid(True, ls = 'dotted', lw = 0.75)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.75)
    
    roads.plot(ax = ax, facecolor = 'black', zorder = 0)

    # on top of the roads, plot the 5 x 5 m cells for which we have samples, with a gradient color scale
    grid = create_grid(x_cell_num, y_cell_num, lat = [LATN, LATS], lon = [LONW, LONE])
    # upgrade grid, by merging sample counts w/ polygons
    grid = pd.merge(grid, sample_count, on = ['cell-x', 'cell-y'], how = 'inner')
    # center point for each polygon
    grid['coords'] = grid['geometry'].apply(lambda x: x.representative_point().coords[:])
    grid['coords'] = [ coords[0] for coords in grid['coords'] ]

    # print the polygons, colored according to sample count
    grid.plot(ax = ax, zorder = 5, column = 'count', cmap = 'YlOrRd', legend = True, alpha = .75)

    # add aps to map, as red dots
    points = []
    for i, client in clients.iterrows():

        lon = client['lon']
        lat = client['lat']
        if client['id'] == 3:
            lon -= 0.00001
            lat += 0.00001
        elif client['id'] == 1:
            lon += 0.00001
            lat -= 0.00001

        points.append(shapely.geometry.Point(lon, lat))

    points = gp.GeoDataFrame({'geometry':points})
    points.plot(ax = ax, zorder = 10, color = 'red')

    for i, client in clients.iterrows():

        lon = client['lon']
        lat = client['lat'] - 0.00001
        if client['id'] == 3:
            lon -= 0.00001
            lat += 0.00001
        elif client['id'] == 1:
            lon += 0.00001
            lat -= 0.00001

        plt.annotate(
            s = ('%d' % (client['id'])), 
            xy = (lon, lat),
            horizontalalignment = 'center',
            zorder = 15,
            size = 5,
            color = 'white')

    # add cell ids to 
    for idx, row in grid.iterrows():
        plt.annotate(
            s = ('(%s,%s)' % (str(row['cell-x']), str(row['cell-y']))), 
            xy = row['coords'], 
            horizontalalignment = 'center',
            zorder = 20,
            size = 5,
            color = 'white' if row['count'] > 200 else 'black')

    plt.tight_layout()
    plt.savefig(os.path.join(maps_dir, "cell-map.pdf"), bbox_inches = 'tight', format = 'pdf')

def compare(
    input_dir, trace_nr, trace_output_dir, 
    configs):

    compare_dir = os.path.join(trace_output_dir, ("compare"))
    if not os.path.isdir(compare_dir):
        os.makedirs(compare_dir)

    compare_dir = os.path.join(compare_dir, ("%s" % (configs['metric-alias'])))
    if not os.path.isdir(compare_dir):
        os.makedirs(compare_dir)

    plt.style.use('classic')

    # plot independent figs for throughput and time
    figs = defaultdict(plt.figure)
    axs = defaultdict()
    for key in configs['types']:
        
        figs[key] = plt.figure(figsize = (3.0, 3.5))

        axs[key] = figs[key].add_subplot(1, 1, 1)
        axs[key].xaxis.grid(True)
        axs[key].yaxis.grid(True)

    # create axs[0] 2nd axis for data volume
    if 'data' in configs['y-label'].keys():
        ax2 = axs['rate'].twinx()

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

    database = analysis.trace.get_db(input_dir, trace_nr)

    # (1) load (ground truth) metric data
    gt_data = analysis.trace.load_best(database, configs['gt-metric'])
    # (2) load data & plot, for each algorithm
    label = {
        'data' : 'data vol.', 
        'rate' : ('median %s' % (configs['metric-alias'])),
        'conn' : 'conn.', 
        'disconn' : 'disconn.'}

    for i, algo in enumerate(sorted(configs['algorithms'].keys())):

        if configs['algorithms'][algo]['data'] == ('/best/%s' % (configs['gt-metric'])):
            data = gt_data
            data['best-val'] = data['gt-val']

        else:
            data = analysis.trace.load_and_merge(database, configs['algorithms'][algo]['data'], gt_data)

        data['diff'] = data['interval-tmstmp'] - data['interval-tmstmp'].shift(1)
        coef = float(configs['algorithms'][algo]['coef'])

        # data volume
        if 'data' in configs['y-label'].keys():
    
            ax2.bar(xx,
                ((data['best-val'] * 0.5).sum() * coef) / 8.0,
                width = barwidth, linewidth = 0.250, alpha = .75, 
                color = 'red', label = label['data'])

            # trick to add ax2's legend to ax's legend
            axs['rate'].bar(np.nan, np.nan, label = label['data'], linewidth = 0.250, alpha = .75, color = 'red')
            label['data'] = ''

            # median throughput
            axs['rate'].bar(xx - barwidth,
                (data['best-val']).median() * coef,
                width = barwidth, linewidth = 0.250, alpha = .75, 
                color = 'blue', label = label['rate'])

        else:

            # median throughput
            axs['rate'].bar(xx - (barwidth),
                (data['best-val']).median() * coef,
                width = (2.0 * barwidth), linewidth = 0.250, alpha = .75, 
                color = 'blue', label = label['rate'])

        label['rate'] = ''

        if 'time' in axs.keys():
            axs['time'].bar(xx - barwidth,
                (len(data[data['best-val'] == 0.0]) * 0.5) + (data['diff'] - 0.5).sum(),
                width = barwidth, linewidth = 0.250, alpha = .75, 
                color = 'red', label = label['disconn'])

            # median throughput
            axs['time'].bar(xx,
                (len(data[data['best-val'] > 0.0]) * 0.5),
                width = barwidth, linewidth = 0.250, alpha = .75, 
                color = 'green', label = label['conn'])

            label['conn'] = ''
            label['disconn'] = ''

        # xticks & xticklabel
        xticks.append(xx)
        xtickslabels.append(configs['algorithms'][algo]['x-ticklabel'])

        if i < (len(configs['algorithms'].keys()) - 1):
            xx += interspace

        # FIXME: force garbage collector to delete (?)
        data = None

    # legend
    axs['rate'].legend(
        fontsize = 10, 
        ncol = 1, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    if 'time' in axs.keys():
        axs['time'].legend(
            fontsize = 10, 
            ncol = 1, loc = 'upper right',
            handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    for key in axs:
        # x-axis
        axs[key].set_xlim(-(1.5 * barwidth), xx + (1.5 * barwidth))
        axs[key].set_xticks(xticks)
        axs[key].set_xticklabels(xtickslabels, rotation = 45, ha = 'right')
        # y-axis
        axs[key].set_ylabel(configs['y-label'][key])

    # so that legend doesn't overlap w/ bars
    axs['rate'].set_ylim(0.0, np.ceil(axs['rate'].get_ylim()[1] * 1.25))
    if 'data' in configs['y-label'].keys():
        # 2nd y-axis in 'rate' plot
        k = float(len(axs['rate'].get_yticks()) - 1)
        d = ax2.get_yticks()[1] - ax2.get_yticks()[0]
        ax2.set_ylim(0.0, k * d)
        ax2.set_ylabel('data volume (MByte)')

    axs['time'].set_ylim(0.0, (axs['time'].get_ylim()[1] * 1.25))

    for fig in figs:
        figs[fig].tight_layout()
        figs[fig].savefig(
            os.path.join(compare_dir, ("%s-%s-%s-%s-%s.pdf" % (configs['metric-alias'], fig.split(':')[-1], configs['stat']['stat'], configs['stat']['stat-args'].replace('.', ''), configs['stat']['lap-usage']))), 
            bbox_inches = 'tight', format = 'pdf')
