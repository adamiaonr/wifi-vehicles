import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.pylab as pl
import os
import argparse
import sys
import glob
import math
import gmplot
import time
# for parallel processing of sessions
import multiprocessing as mp 
import hashlib

from random import randint
from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict

# for ap location estimation
from shapely.geometry import Point
# custom imports
from plot_utils import *

reload(sys)  
sys.setdefaultencoding('utf8')

matplotlib.rcParams.update({'font.size': 16})

# gps coords for a 'central' pin on porto, portugal
PORTO_LATITUDE  = 41.163158
PORTO_LONGITUDE = -8.6127137
# north, south, west, east limits of map, in terms of geo coordinates
PORTO_LATITUDE_LIMIT_NORTH = PORTO_LATITUDE  + 0.03
PORTO_LATITUDE_LIMIT_SOUTH = PORTO_LATITUDE  - 0.03
PORTO_LONGITUDE_LIMIT_EAST = PORTO_LONGITUDE + 0.06
PORTO_LONGITUDE_LIMIT_WEST = PORTO_LONGITUDE - 0.06

# x and y span (in meters) of the map, derived from geo coordinate limits
# NOTE : y is the vertical axis (latitude), x is the horizontal axis (longitude)
Y_SPAN = gps_to_dist(PORTO_LATITUDE_LIMIT_NORTH, 0.0, PORTO_LATITUDE_LIMIT_SOUTH, 0.0)
# FIXME : an x span depends on the latitude, and we're assuming a fixed latitude
X_SPAN = gps_to_dist(PORTO_LONGITUDE_LIMIT_WEST, PORTO_LATITUDE, PORTO_LONGITUDE_LIMIT_EAST, PORTO_LATITUDE)

# fcup : 41.157505,41.150752,-8.647382,-8.629400
# fcup (minor) : 41.152844,41.149629,-8.640344,-8.632748
# feup : 41.180183,41.177093,-8.599869,-8.593644

def get_ap_id(essid, mac_addr):
    return hashlib.md5((str(essid).strip() + str(mac_addr[:6]).strip()).encode()).hexdigest()

# get (x,y) coords of cell w/ side cell_size
def calc_cell(lat, lon, cell_size):

    # calc y (latitude) and x (longitude) coords of cell
    y = ((lat - PORTO_LATITUDE_LIMIT_SOUTH) / (PORTO_LATITUDE_LIMIT_NORTH - PORTO_LATITUDE_LIMIT_SOUTH)) * (Y_SPAN / cell_size)
    x = ((lon - PORTO_LONGITUDE_LIMIT_WEST) / (PORTO_LONGITUDE_LIMIT_EAST - PORTO_LONGITUDE_LIMIT_WEST)) * (X_SPAN / cell_size)

    return int(x), int(y)

def print_map(in_dir, out_dir, cell_size):

    # load gps data
    gps_data = pd.read_csv(os.path.join(in_dir, "gps-log.csv"))
    # clean the dataframe
    gps_data[['epx', 'epy', 'eps']] = gps_data[['epx', 'epy', 'eps']].apply(pd.to_numeric, errors = 'coerce', axis = 1)
    print(gps_data)

    # find the bounding box of the lats and lons
    n = np.amax(gps_data['lat'])
    s = np.amin(gps_data['lat'])
    w = np.amin(gps_data['lon'])
    e = np.amax(gps_data['lon'])
    # find the center of the map
    map_ctr = [((n + s) / 2.0), ((w + e) / 2.0), 16]

    print(map_ctr)

    # deltas in lat and lon equivalent to cell_size
    delta_lat = ((PORTO_LATITUDE_LIMIT_NORTH - PORTO_LATITUDE_LIMIT_SOUTH) * cell_size) / (Y_SPAN)
    delta_lon = ((PORTO_LONGITUDE_LIMIT_EAST - PORTO_LONGITUDE_LIMIT_WEST) * cell_size) / (X_SPAN)

    gmap = defaultdict()
    for cat in ['ep']:
        gmap[cat] = gmplot.GoogleMapPlotter(map_ctr[0], map_ctr[1], map_ctr[2])

    color_map = plt.get_cmap('RdYlGn')

    # colors for each chart category
    colors = defaultdict()
    colors_n = {'ep' : 5}
    for cat in gmap:
        colors[cat] = [color_map(i) for i in np.linspace(0, 1, float(colors_n[cat]))]
        # reverse the lists, so that green is given to lower values
        colors[cat] = colors[cat][::-1]

    # define ranges according to quantiles
    quantiles = pd.DataFrame()

    for q in [10, 25, 50, 75, 90, 99]:

        quantiles = quantiles.append({
            'q' : q,
            'epx': np.nanpercentile(gps_data['epx'], q),
            'epy': np.nanpercentile(gps_data['epy'], q),
            'eps': np.nanpercentile(gps_data['eps'], q),
        }, ignore_index = True)

    limits = defaultdict()
    limits['ep'] = [ 
        ((quantiles.iloc[0]['epx'] + quantiles.iloc[0]['epy']) / 2.0), 
        ((quantiles.iloc[4]['epx'] + quantiles.iloc[4]['epy']) / 2.0) ]
    limits['eps'] = [ quantiles.iloc[0]['eps'], quantiles.iloc[4]['eps'] ]

    print(limits)

    # now, let's start drawing the grids
    for index, row in gps_data.reset_index().iterrows():

        # find the cell the measurement belongs to
        x,y = calc_cell(row['lat'], row['lon'], cell_size)
        # avoid 'out-of-bounds' (i.e. porto bounds) situations
        if x >= (int(X_SPAN / cell_size)) or y >= (int(Y_SPAN / cell_size)):
            continue

        # determine the bounds of the cell, in geo coords
        lats = (
            PORTO_LATITUDE_LIMIT_SOUTH + (y) * delta_lat,
            PORTO_LATITUDE_LIMIT_SOUTH + (y + 1) * delta_lat,
            PORTO_LATITUDE_LIMIT_SOUTH + (y + 1) * delta_lat,
            PORTO_LATITUDE_LIMIT_SOUTH + (y) * delta_lat)

        lons = (
            PORTO_LONGITUDE_LIMIT_WEST + (x) * delta_lon,
            PORTO_LONGITUDE_LIMIT_WEST + (x) * delta_lon,
            PORTO_LONGITUDE_LIMIT_WEST + (x + 1) * delta_lon,
            PORTO_LONGITUDE_LIMIT_WEST + (x + 1) * delta_lon)

        for cat in gmap:

            # extract category value
            if cat == 'ep':
                val = float(row['epx'] + row['epy']) / 2.0
            else:
                val = float(row[cat])

            if math.isnan(val):
                continue

            # calculate appropriate color
            c = int(((val - limits[cat][0]) / (limits[cat][1] - limits[cat][0])) * float(colors_n[cat]))
            c = max(0, c)
            c = min((colors_n[cat] - 1), c)

            rgb = colors[cat][c][:3]
            color = matplotlib.colors.rgb2hex(rgb)

            gmap[cat].polygon(lats, lons, edge_color = "black", edge_width = 0.5, face_color = color, face_alpha = 0.40)

    # print a fake plot, just to extract the legend
    fig = plt.figure(figsize = (12 * len(gmap.keys()), 5))

    subplot_code = 131
    for k, cat in enumerate(gmap.keys()):

        ax = fig.add_subplot(subplot_code + k)

        delta = ((limits[cat][1] - limits[cat][0]) / float(colors_n[cat]))
        values = np.arange(limits[cat][0], limits[cat][1], delta)

        for i, v in enumerate(values):
            ax.bar(
                i, v, 
                alpha = 0.55, width = 0.75, 
                label = ('%.1f - %.1f' % (limits[cat][0] + (i * delta), limits[cat][0] + ((i + 1) * delta))), 
                color = matplotlib.colors.rgb2hex(colors[cat][i][:3]))

        ax.legend(fontsize = 12, ncol = 1, loc = 'upper right')
        ax.set_ylim(0.0, 10000.0)

    fig.tight_layout()
    fig.subplots_adjust(top = 0.95)

    plt.savefig(os.path.join(out_dir, in_dir.rstrip("/").split("/")[-1] + "/wifi-assist-gps.pdf"), bbox_inches = 'tight', format = 'pdf')

    for cat in gmap:
        filename = os.path.join(out_dir, in_dir.rstrip("/").split("/")[-1] + "/gps-error-" + cat + ".html")
        gmap[cat].draw(filename)

def other(in_dir, out_dir, cell_size):

    # load gps data
    gps_data = pd.read_csv(os.path.join(in_dir, "gps-log.csv"))
    # clean the dataframe
    gps_data[['epx', 'epy', 'eps']] = gps_data[['epx', 'epy', 'eps']].apply(pd.to_numeric, errors = 'coerce', axis = 1)    

    # find the bounding box of the lats and lons
    n = np.amax(gps_data['lat'])
    s = np.amin(gps_data['lat'])
    w = np.amin(gps_data['lon'])
    e = np.amax(gps_data['lon'])
    # find the center of the map
    map_ctr = [((n + s) / 2.0), ((w + e) / 2.0), 16]

    # deltas in lat and lon equivalent to cell_size
    delta_lat = ((PORTO_LATITUDE_LIMIT_NORTH - PORTO_LATITUDE_LIMIT_SOUTH) * cell_size) / (Y_SPAN)
    delta_lon = ((PORTO_LONGITUDE_LIMIT_EAST - PORTO_LONGITUDE_LIMIT_WEST) * cell_size) / (X_SPAN)

    wifi_data = pd.read_csv(os.path.join(in_dir, "wifi-log.csv"))

    # join the 2 by timestamp
    joined = pd.merge(gps_data, wifi_data, on = 'time', how = 'inner')

    signal_quality = defaultdict(list)
    for index, row in joined.reset_index().iterrows():

        # find the cell the measurement belongs to
        x,y = calc_cell(row['lat'], row['lon'], cell_size)
        # avoid 'out-of-bounds' (i.e. porto bounds) situations
        if x >= (int(X_SPAN / cell_size)) or y >= (int(Y_SPAN / cell_size)):
            continue

        signal_quality[(x,y)].append(float(row['signal_quality']))

    gmap = defaultdict()
    for cat in ['signal_quality']:
        gmap[cat] = gmplot.GoogleMapPlotter(map_ctr[0], map_ctr[1], map_ctr[2])

    color_map = plt.get_cmap('RdYlGn')

    # colors for each chart category
    colors = defaultdict()
    colors_n = {'signal_quality' : 7}
    for cat in gmap:
        colors[cat] = [color_map(i) for i in np.linspace(0, 1, float(colors_n[cat]))]

    for cell in signal_quality:

        print(cell)

        # x : longitude (horizontal)
        # y : latitude  (vertical)
        x = float(cell[0])
        y = float(cell[1])        

        # determine the bounds of the cell, in geo coords
        lats = (
            PORTO_LATITUDE_LIMIT_SOUTH + (y) * delta_lat,
            PORTO_LATITUDE_LIMIT_SOUTH + (y + 1) * delta_lat,
            PORTO_LATITUDE_LIMIT_SOUTH + (y + 1) * delta_lat,
            PORTO_LATITUDE_LIMIT_SOUTH + (y) * delta_lat)

        lons = (
            PORTO_LONGITUDE_LIMIT_WEST + (x) * delta_lon,
            PORTO_LONGITUDE_LIMIT_WEST + (x) * delta_lon,
            PORTO_LONGITUDE_LIMIT_WEST + (x + 1) * delta_lon,
            PORTO_LONGITUDE_LIMIT_WEST + (x + 1) * delta_lon)        

        for cat in gmap:

            # extract category value
            val = float(np.median(signal_quality[cell]))

            if math.isnan(val):
                continue

            # calculate appropriate color
            c = int(((val) / (70)) * float(colors_n[cat]))
            c = max(0, c)
            c = min((colors_n[cat] - 1), c)

            rgb = colors[cat][c][:3]
            color = matplotlib.colors.rgb2hex(rgb)

            gmap[cat].polygon(lats, lons, edge_color = "black", edge_width = 0.5, face_color = color, face_alpha = 0.40)

    # print a fake plot, just to extract the legend
    fig = plt.figure(figsize = (12 * len(gmap.keys()) + 6, 5))

    subplot_code = 131
    for k, cat in enumerate(gmap.keys()):

        ax = fig.add_subplot(subplot_code + k)

        values = np.arange(0, 70, 10)

        for i, v in enumerate(values):
            ax.bar(
                i, v, 
                alpha = 0.55, width = 0.75, 
                label = ('%.1f - %.1f' % ((i * 10), ((i + 1) * 10))), 
                color = matplotlib.colors.rgb2hex(colors[cat][i][:3]))

        ax.legend(fontsize = 12, ncol = 1, loc = 'upper right')
        ax.set_ylim(0.0, 10000.0)

    ax = fig.add_subplot(132)
    plt.scatter(joined['signal_level_dBm'], joined['signal_quality'], color = "blue", alpha = 0.5)

    ax.set_xlabel("signal level (dBm)")
    ax.set_ylabel("signal quality (0 - 70)")

    fig.tight_layout()
    fig.subplots_adjust(top = 0.95)

    plt.savefig(os.path.join(out_dir, in_dir.rstrip("/").split("/")[-1] + "/wifi-assist-signal-quality.pdf"), bbox_inches = 'tight', format = 'pdf')

    for cat in gmap:
        filename = os.path.join(out_dir, in_dir.rstrip("/").split("/")[-1] + "/wifi-signal-quality.html")
        gmap[cat].draw(filename)

def plot(in_dir, out_dir, cell_size, geo_limits = []):

    """plots stats from 'wifi-assist' sessions"""

    # # print gps error grid
    # print_map(in_dir, out_dir, cell_size)
    other(in_dir, out_dir, cell_size)

