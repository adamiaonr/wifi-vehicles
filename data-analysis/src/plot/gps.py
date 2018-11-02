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
import parsing.utils
import analysis.metrics
import shapely.geometry

from random import randint

from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple

from prettytable import PrettyTable

from sklearn import linear_model

# north, south, west, east limits of map, in terms of geo coordinates
LATN = 41.176796
LATS = 41.179283
LONE = -8.593912
LONW = -8.598336
# gps coords for a 'central' pin on FEUP, Porto, Portugal
LAT  = (41.176796 + 41.179283) / 2.0
LON = (-8.598336 + -8.593912) / 2.0

# CELL_SIZE = 20.0
CELL_SIZE = 500.0

# number of cells in grid, in x and y directions
X_CELL_NUM = int(np.ceil((mapping.utils.gps_to_dist(LATN, 0.0, LATS, 0.0) / CELL_SIZE)))
Y_CELL_NUM = int(np.ceil((mapping.utils.gps_to_dist(LAT, LONW, LAT, LONE) / CELL_SIZE)))

def cells(input_dir, trace_nr, output_dir):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    sample_count = pd.DataFrame(columns = ['cell-x', 'cell-y', 'count'])
    for mac in clients:

        if ('/%s/%s' % ('interval-data', mac)) not in database.keys():
            continue

        # load data for a client mac
        data = database.select(('/%s/%s' % ('interval-data', mac)))
        # add cell ids
        data['cell-x'] = data['lon'].apply(lambda x : int((x - LONW) / (LONE - LONW) * X_CELL_NUM))
        data['cell-y'] = data['lat'].apply(lambda y : int((y - LATS) / (LATN - LATS) * Y_CELL_NUM))

        # groupby cell id and count samples and concat
        sample_count = pd.concat([sample_count, data.groupby(['cell-x', 'cell-y'])['time'].agg(['count']).reset_index()], ignore_index = True)
        # groupby cell id and sum on count
        sample_count = sample_count.groupby(['cell-x', 'cell-y'])['count'].sum().reset_index()

    # print cdf plot of samples per cell
    cdf = sample_count.groupby(['count']).size().reset_index(name = 'counts')
    cdf['counts'] = np.array(cdf['counts'].cumsum(), dtype = float)
    cdf['counts'] = cdf['counts'] / cdf['counts'].values[-1]

    fig = plt.figure(figsize = (5, 2.5))

    ax = fig.add_subplot(111)
    ax.xaxis.grid(True, ls = 'dotted', lw = 0.75)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.75)

    ax.plot(cdf['count'], cdf['counts'], 
        alpha = 0.75, linewidth = 1.0, color = 'black', label = '# of cells', linestyle = '-')

    ax.set_xlabel("# of samples per cell")
    ax.set_ylabel("CDF")

    # ax.set_xticks(np.arange(0, np.amax(cdf['count']), 10)
    # ax.set_xticklabels([-10, -20, -30, -40, -50, -60, -70, -80])
    ax.set_yticks(np.arange(0.0, 1.1, 0.25))
    ax.legend(fontsize = 12, ncol = 1, loc = 'upper left')

    # create output dir for trace (if not existent)
    trace_output_dir = os.path.join(output_dir, ("trace-%03d" % (int(trace_nr))))
    if not os.path.isdir(trace_output_dir):
        os.makedirs(trace_output_dir)

    plt.tight_layout()
    plt.savefig(os.path.join(trace_output_dir, "samples-per-cell.pdf"), bbox_inches = 'tight', format = 'pdf')

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
    roads['geometry'] = roads['geometry'].buffer(0.000125)
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
    
    roads.plot(ax = ax, facecolor = 'blue', zorder = 0)

    # on top of the roads, plot the 5 x 5 m cells for which we have samples, with a gradient color scale
    grid = create_grid()
    # upgrade grid, by merging sample counts w/ polygons
    grid = pd.merge(grid, sample_count, on = ['cell-x', 'cell-y'], how = 'inner')
    # center point for each polygon
    grid['coords'] = grid['geometry'].apply(lambda x: x.representative_point().coords[:])
    grid['coords'] = [ coords[0] for coords in grid['coords'] ]

    # print the polygons, colored according to sample count
    grid.plot(ax = ax, zorder = 5, column = 'count', cmap = 'YlOrRd', legend = True)

    # add aps to map, as red dots
    points = []
    for ap in clients:

        lon = clients[ap]['lon']
        lat = clients[ap]['lat']
        if clients[ap]['id'] == 3:
            lon -= 0.00001
            lat += 0.00001
        elif clients[ap]['id'] == 1:
            lon += 0.00001
            lat -= 0.00001

        points.append(shapely.geometry.Point(lon, lat))

    points = gp.GeoDataFrame({'geometry':points})
    points.plot(ax = ax, zorder = 10, color = 'red')

    for ap in clients:

        lon = clients[ap]['lon']
        lat = clients[ap]['lat'] - 0.00001
        if clients[ap]['id'] == 3:
            lon -= 0.00001
            lat += 0.00001
        elif clients[ap]['id'] == 1:
            lon += 0.00001
            lat -= 0.00001

        plt.annotate(
            s = ('%d' % (clients[ap]['id'])), 
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
    plt.savefig(os.path.join(trace_output_dir, "sample-cells.pdf"), bbox_inches = 'tight', format = 'pdf')
