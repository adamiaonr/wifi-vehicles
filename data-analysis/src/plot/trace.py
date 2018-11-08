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
            markersize = client['marker-size'], 
            marker = client['marker'], 
            markeredgewidth = 0.0)

    # # plot a black line w/ throughput for all mac addrs
    # _data = data.iloc[::5, :]
    # dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ]
    # ax.plot(
    #     dates,
    #     (_data[macs].max(axis = 1).values) * plot_configs[metric]['coef'],
    #     alpha = .5,
    #     linewidth = 0.75, 
    #     linestyle = '-', 
    #     color = 'black', 
    #     marker = None)

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

def cells(input_dir, trace_nr, trace_output_dir, cell_size = 20.0):

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    # get gps pos of trace
    gps_data, lap_tmstmps = analysis.gps.get_data(input_dir, trace_dir, tag_laps = False)
    gps_data['interval-tmstmp'] = [ (float(ts)) for ts in gps_data['timestamp'] ]
    gps_data = gps_data.sort_values(by = ['interval-tmstmp']).reset_index(drop = True)

    # merge gps data w/ throughput data
    macs = []
    for i, client in clients.iterrows():

        db_name = ('/%s/%s' % ('interval-data', client['mac']))
        if db_name not in database.keys():
            continue

        # load data for a client mac
        data = database.select(db_name)
        if data.empty:
            continue

        data[client['mac']] = data['throughput']
        macs.append(client['mac'])

        gps_data = pd.merge(gps_data, data[ ['interval-tmstmp', client['mac']] ], on = ['interval-tmstmp'], how = 'outer')

    # drop rows w/ undefined throughput values for all mac addrs
    gps_data = gps_data.dropna(subset = macs, how = 'all').drop_duplicates(subset = ['interval-tmstmp']).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
    # keep data of moving period only, i.e. when the bike is moving and getting gps positions
    gps_data = analysis.trace.extract_moving_data(gps_data)
    # fix timestamp gaps
    gps_data.loc[np.isnan(gps_data['timestamp']), 'timestamp'] = gps_data[np.isnan(gps_data['timestamp'])]['interval-tmstmp'].astype(int)
    # fix lat and lon gaps
    analysis.trace.fix_gaps(gps_data, subset = ['lat', 'lon'])

    plot.gps.heatmap(gps_data.groupby(['lat', 'lon']).size().reset_index(name = 'counts'), trace_output_dir, 
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
    plt.savefig(os.path.join(trace_output_dir, "cell-cdfs.pdf"), bbox_inches = 'tight', format = 'pdf')

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
    plt.savefig(os.path.join(trace_output_dir, "cell-map.pdf"), bbox_inches = 'tight', format = 'pdf')
