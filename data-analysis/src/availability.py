import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
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
# 
import urllib
import geopandas as gp
import geopandas_osm.osm
import shapely.geometry

import timeit

from random import randint
from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict

from prettytable import PrettyTable

matplotlib.rcParams.update({'font.size': 16})
# plt.style.use('seaborn-white')

# gps coords for a 'central' pin on porto, portugal
LAT  = 41.163158
LON = -8.6127137
# north, south, west, east limits of map, in terms of geo coordinates
LATN = LAT + 0.03
LATS = LAT - 0.03
LONE = LON + 0.06
LONW = LON - 0.06

def to_radians(degrees):
    return (degrees * math.pi / 180.0)

def to_degrees(radians):
    return (radians / (math.pi / 180.0))

def gps_to_dist(lat_start, lon_start, lat_end, lon_end):

    # we use the haversine formula to calculate the great-circle distance between two points. 
    # in other words, this calculates the lenght of the shortest arch in-between 2 points, in 
    # a 'great' circle of radius equal to 6371 (the radius of the earth) 
    # source : http://www.movable-type.co.uk/scripts/latlong.html

    # earth radius, in m
    earth_radius = 6371000

    delta_lat = to_radians(lat_end - lat_start)
    delta_lon = to_radians(lon_end - lon_start)

    lat_start = to_radians(lat_start)
    lat_end   = to_radians(lat_end)

    a = (np.sin(delta_lat / 2.0) * np.sin(delta_lat / 2.0)) + (np.sin(delta_lon / 2.0) * np.sin(delta_lon / 2.0)) * np.cos(lat_start) * np.cos(lat_end)
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))

    return earth_radius * c

# x and y span (in meters) of the map, derived from geo coordinate limits
# NOTE : y is the vertical axis (latitude), x is the horizontal axis (longitude)
Y_SPAN = gps_to_dist(LATN, 0.0, LATS, 0.0)
# FIXME : an x span depends on the latitude, and we're assuming a fixed latitude
X_SPAN = gps_to_dist(LONW, LAT, LONE, LAT)

def get_roads(output_dir, bbox = [-8.650, 41.139, -8.578, 41.175], 
    tags = ['highway=motorway', 'highway=trunk', 'highway=primary', 'highway=secondary', 'highway=tertiary', 'highway=residential']):

    bbox = shapely.geometry.geo.box(bbox[0], bbox[1], bbox[2], bbox[3])
    roads = []
    for tag in tags:
        roads.append(geopandas_osm.osm.query_osm('way', bbox, recurse = 'down', tags = tag))

    # concat dfs w/ tags
    roads = gp.GeoDataFrame(pd.concat(roads, ignore_index = True))

    # save file of roads
    roads[roads.type == 'LineString'][['highway', 'name', 'geometry']].to_file(os.path.join(output_dir, "roads"), driver = 'ESRI Shapefile')
    return roads

def get_antiroads(output_dir):

    roads = gp.GeoDataFrame.from_file(os.path.join(output_dir, "roads"))
    # create large base polygon, which covers complete map
    base = [shapely.geometry.Polygon([(-8.650, 41.139), (-8.650, 41.175), (-8.578, 41.175), (-8.578, 41.139)])]
    base = gp.GeoDataFrame({'geometry':base})
    # transform LineString into Polygons, by applying a fine buffer 
    # around the points which form the line
    # this is necessary because gp.overlay() only works w/ polygons
    roads['geometry'] = roads['geometry'].buffer(0.000125)
    # find the symmetric difference between the base polygon and 
    # the roads, i.e. geometries which are only part of one of the 
    # geodataframes, but not both
    # FIXME: this takes forever... 
    start = timeit.default_timer()
    diff = gp.overlay(base, roads, how = 'symmetric_difference')
    print("%s::get_antiroads() : [INFO] overlay() in %.3f sec" % (sys.argv[0], timeit.default_timer() - start))
    # save the result to a file
    diff.to_file(os.path.join(output_dir, "anti-roads"), driver = 'ESRI Shapefile')

# use only roadcells where smc has observations
def refine_roadcells(input_file, output_dir):

    roadcells = gp.GeoDataFrame.from_file(os.path.join(output_dir, "roadcells-raw"))

    coverage = gp.GeoDataFrame()
    chunksize = 10 ** 5
    for chunk in pd.read_csv(input_file, chunksize = chunksize):
        
        # find intersections between captive portal nets and roads
        # collect unique observation points
        nets = chunk[['new_lon' ,'new_lat']].drop_duplicates()
        obs = [shapely.geometry.Point(tuple(x)) for x in nets.values]
        obs = gp.GeoDataFrame({'geometry':obs})

        if obs.empty:
            continue

        # calc intersections (this takes the most time)
        intersection = gp.sjoin(roadcells, obs, how = "inner", op = 'intersects').drop_duplicates(subset = 'index')
        # concat as you go, always dropping duplicates
        coverage = gp.GeoDataFrame(pd.concat([intersection, coverage], ignore_index = True))
        coverage.drop_duplicates(subset = 'index')

    coverage = coverage.reset_index()[['index', 'geometry']].drop_duplicates(subset = 'index')
    coverage.to_file(os.path.join(output_dir, "roadcells-smc"), driver = 'ESRI Shapefile')

def get_roadcells(output_dir, roads, bbox = [LONW, LATS, LONE, LATN], cell_size = 20.0):

    # grid of polygons w/ cell_size side dimension
    # adapted from https://gis.stackexchange.com/questions/269243/create-a-polygon-grid-using-with-geopandas
    # nr. of intervals in x and y axis 
    x = int(np.ceil(X_SPAN / cell_size))
    y = int(np.ceil(Y_SPAN / cell_size))

    w = (LONE - LONW) / float(x)
    h = (LATN - LATS) / float(y)

    polygons = []
    for i in range(x):
        for j in range(y):
            polygons.append(
                shapely.geometry.Polygon(
                    [
                    (LONW + (i * w), LATS + (j * h)), 
                    (LONW + ((i + 1) * w), LATS + (j * h)), 
                    (LONW + ((i + 1) * w), LATS + ((j + 1) * h)), 
                    (LONW + (i * w), LATS + ((j + 1) * h))
                    ]))

    grid = gp.GeoDataFrame({'geometry':polygons})

    # calculate intersection w/ roads (this is INSANELY fast...)
    intersections = gp.sjoin(grid, roads, how = "inner", op = 'intersects').reset_index()[['index', 'geometry']].drop_duplicates(subset = 'index')
    # save intersection
    intersections.to_file(os.path.join(output_dir, "roadcells-raw"), driver = 'ESRI Shapefile')
    return intersections

def get_coverage(input_file, output_dir, threshold = -80):

    # extract roadcells
    s = timeit.default_timer()
    roadcells = gp.GeoDataFrame.from_file(os.path.join(output_dir, "roadcells-smc"))
    print("%s::get_coverage() : [INFO] read roadcells in %.3f sec" % (sys.argv[0], timeit.default_timer() - s))

    labels = {0 : 'cp-zon', 1 : 'cp-meo', 2 : 'open-only', 3 : 'wpa-zon', 4 : 'wpa-meo', 5 : 'wpa-vodafone', 6 : 'wpa-other'}

    # cdf of rssi samples, per operator
    rssis = pd.DataFrame()
    rssis['snr'] = np.arange(threshold, 0 + 2, 1)[:-1]
    for k in labels:
        rssis[labels[k]] = 0

    coverage = gp.GeoDataFrame()
    chunksize = 10 ** 5
    stop = 3
    for chunk in pd.read_csv(input_file, chunksize = chunksize):

        # apply threshold
        # FIXME : also, limit max snr values
        chunk = chunk[(chunk['snr'] >= threshold) & (chunk['snr'] < -10)]
        if chunk.empty:
            print("%s::get_coverage(%d) : [INFO] skipped chunk" % (sys.argv[0], threshold))
            continue

        start = timeit.default_timer()
        # find intersections between captive portal nets and roads
        # collect unique observation points for each category:
        #   - captive portal (cp) zon
        #   - cp meo
        #   - open only
        #   - wpa (all)
        #   - wpa zon
        #   - wpa meo 
        #   - wpa vodafone
        nets = []

        # captive portal nets
        cp = chunk[chunk['auth'] == 1][['essid', 'auth', 'new_lon' ,'new_lat', 'snr']]
        nets.append(cp[cp['essid'] == 'FON_ZON_FREE_INTERNET'].drop_duplicates())
        nets.append(cp[(cp['essid'] == 'MEO-WiFi') | (cp['essid'] == 'PT-WIFI')].drop_duplicates())

        # open only nets
        other_nets = set(nets[0].index.values.tolist() + nets[1].index.values.tolist())
        other_nets = list(set(cp.index.values.tolist()) - other_nets)
        nets.append(cp.ix[other_nets])

        # wpa nets
        wpa = chunk[(chunk['auth'] == 3) | (chunk['auth'] == 4)][['essid', 'auth', 'new_lon' ,'new_lat', 'snr']]
        nets.append(wpa[wpa['essid'].str.contains('ZON-|Optimus') == True].drop_duplicates())
        nets.append(wpa[wpa['essid'].str.contains('MEO-|Thomson') == True].drop_duplicates())
        nets.append(wpa[wpa['essid'].str.contains('Vodafone-|VodafoneFibra-|VodafoneMobileWiFi-') == True].drop_duplicates())

        # open only nets
        other_nets = set(nets[3].index.values.tolist() + nets[4].index.values.tolist() + nets[5].index.values.tolist())
        other_nets = list(set(wpa.index.values.tolist()) - other_nets)
        nets.append(wpa.ix[other_nets])

        for k in labels:
            nets[k]['op'] = labels[k]

        obs = gp.GeoDataFrame(pd.concat(nets, ignore_index = True))
        obs['geometry'] = [shapely.geometry.Point(tuple(x)) for x in obs[['new_lon' ,'new_lat']].values]

        if obs.empty:
            continue

        # calc intersections (this takes the most time)
        intersection = gp.sjoin(roadcells, obs, how = "inner", op = 'intersects')[['index', 'geometry', 'op', 'snr']]

        for k in labels:
            df = intersection[intersection['op'] == labels[k]]
            count, division = np.histogram(df['snr'], bins = np.arange(threshold, 0 + 2, 1))
            rssis[labels[k]] += count

        # drop duplicates for each cell and operator combo, keeping the max() snr
        intersection = intersection.sort_values('snr', ascending = False).drop_duplicates(subset = ['index', 'op']).sort_index()

        # concat as you go, always dropping duplicates
        coverage = gp.GeoDataFrame(pd.concat([intersection, coverage], ignore_index = True))
        coverage.sort_values('snr', ascending = False).drop_duplicates(subset = ['index', 'op']).sort_index()

        print("%s::get_coverage() : [INFO] spatial join in %.3f sec" % (sys.argv[0], timeit.default_timer() - start))

    rssis.to_hdf(os.path.join(output_dir, ('coverage/%d/rssis.h5' % (int(abs(threshold))))), 'rssis', append = False)

    for k in labels:
        start = timeit.default_timer()
        coverage[coverage['op'] == labels[k]].drop_duplicates(subset = 'index').to_file(os.path.join(output_dir, ("coverage/%d/%s" % (int(abs(threshold)), labels[k]))), driver = 'ESRI Shapefile')
        print("%s::get_coverage() : [INFO] wrote %s in %.3f sec" % (sys.argv[0], labels[k], timeit.default_timer() - start))

def plot_coverage(output_dir):

    labels = {
        0 : 'cp-zon', 
        1 : 'cp-meo', 
        2 : 'open-only', 
        3 : 'wpa-zon', 
        4 : 'wpa-meo', 
        5 : 'wpa-vodafone', 
        6 : 'wpa-other'}

    labels_anon = {
        0 : 'Captive portal (CP) op.1', 
        1 : 'CP op.2', 
        2 : 'Open', 
        3 : 'WPA op.1', 
        4 : 'WPA op.2', 
        5 : 'WPA op.3', 
        6 : 'WPA other ops.'}

    # cdfs of rssis
    fig = plt.figure(figsize = (5, 4))
    ax = fig.add_subplot(111)
    ax.xaxis.grid(True, ls = 'dotted', lw = 0.75)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.75)

    # load rssi data for the lowest threshold (i.e. >-80 dbm)
    rssis = pd.read_hdf(os.path.join(output_dir, 'coverage/80/rssis.h5'), 'rssis')
    # linestyles and colors for diff. series
    linestyles = ['-', ':', '-.', '--']
    colors = ['blue', 'red']
    # FIXME: due to a mixup when generating data, we 
    # read indeces of rssis in the following order:
    #   2 : 'Open'
    #   0 : 'Captive portal op.1'
    #   1 : 'Captive portal op.2'
    #   (...)
    for k in [2, 0, 1, 3, 4, 5, 6]:
        
        # list rssi values from highest to lowest rssi value
        a = rssis[labels[k]][::-1]
        # apply a cumulative sum over the values
        # last element contains the sum of all values in the array
        acc = np.array(a.cumsum(), dtype = float)
        # normalize the values (last value becomes 1.0)
        # now we have the cdf
        acc = acc / acc[-1]

        # plot cdfs (diff. colors for 'public' and 'private' networks)
        if k > 2:
            color = colors[1]
        else:
            color = colors[0]

        ax.plot(np.arange(10, len(acc), 1), acc[10:], 
            alpha = 0.75, linewidth = 1.0, color = color, label = labels_anon[k], linestyle = linestyles[(k % 4)])

    ax.set_xlabel("RSSI (dbm)")
    ax.set_ylabel("CDF")

    ax.set_xticks([10, 20, 30, 40, 50, 60, 70, 80])
    ax.set_xticklabels([-10, -20, -30, -40, -50, -60, -70, -80])
    ax.set_yticks(np.arange(0.0, 1.1, 0.1))

    ax.legend(fontsize = 12, ncol = 1, loc='upper left')
    plt.savefig(os.path.join(output_dir, "graphs/rssis.pdf"), bbox_inches = 'tight', format = 'pdf')

    # percentage of availability, over 20 x 20 meter cells which overlap w/ roads
    roadcells = gp.GeoDataFrame.from_file(os.path.join(output_dir, "roadcells-raw"))
    roadcells_num = float(len(roadcells['index'].drop_duplicates()))
    smccells = gp.GeoDataFrame.from_file(os.path.join(output_dir, "roadcells-smc"))
    # get all spaces in-between roads as polygons
    antiroads = gp.GeoDataFrame.from_file(os.path.join(output_dir, "anti-roads"))

    fig = plt.figure(figsize = (6, 4))
    ax = fig.add_subplot(111)
    ax.xaxis.grid(True, ls = 'dotted', lw = 0.75)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.75)

    colors = ['green', 'blue', 'red']
    pos = 0.0
    barwidth = 0.25

    table = PrettyTable(['op', '>-80 dbm', '>-70 dbm', '>-60 dbm'])

    for i, k in enumerate([2, 0, 1, 3, 4, 5, 6]):

        p = []
        for j, r in enumerate([80, 70, 60]):

            # extract coverage data
            df = gp.GeoDataFrame.from_file(os.path.join(output_dir, ("coverage/%d/%s" % (r, labels[k]))))
            p.append(float(len(df['index'].drop_duplicates())) / roadcells_num)
            plt.bar(pos + (j * barwidth), p[-1] * 100.0, alpha = 0.55, width = barwidth, label = ('> -%d dbm' % (r)), color = colors[j])

        pos = i + (3.0 * barwidth) + barwidth
        table.add_row([
            ('%s' % (labels_anon[k])),
            ('%.4f' % (p[0])), 
            ('%.4f' % (p[1])), 
            ('%.4f' % (p[2]))])

    print(table)

    ax.set_xlabel("Operators")
    ax.set_ylabel("% of 20m x 20m cells\noverlapping w/ roads")

    ax.set_xticks(np.arange(barwidth, 7 + barwidth, 1))
    ax.set_xticklabels(['Open', 'CP\nop.1', 'CP\nop.2', 'WPA\nop.1', 'WPA\nop.2', 'WPA\nop.3', 'WPA\nother'])

    ax.set_yticks(np.arange(0, 120, 20))

    # custom legend using matplotlib.patches
    # https://stackoverflow.com/questions/39500265/manually-add-legend-items-python-matplotlib
    patches = [
        matplotlib.patches.Patch(color='green', label = '>-80 dbm'), 
        matplotlib.patches.Patch(color='blue', label = '>-70 dbm'), 
        matplotlib.patches.Patch(color='red', label = '>-60 dbm')
        ]
    ax.legend(handles = patches, fontsize = 12, ncol = 1, loc='upper left')

    plt.savefig(os.path.join(output_dir, "graphs/availability.pdf"), bbox_inches = 'tight', format = 'pdf')

    # availability maps
    # nr. of operators per cell (cp and wpa)

    # bounds = [p.bounds for p in roadcells['geometry']]
    # bounds = pd.DataFrame(bounds, columns = ['w', 's', 'e', 'n'])
    # print("%s::plot_coverage() : [INFO] bbox : [%.3f, %.3f, %.3f, %.3f] " % (sys.argv[0], 
    #     np.min(bounds['w']),
    #     np.min(bounds['s']),
    #     np.max(bounds['e']),
    #     np.max(bounds['n'])))
    # [-8.650, 41.139, -8.578, 41.175]

    fig = plt.figure(figsize = (12, 4.25))

    # params for left and right subplots
    keys = {0 : [2, 0, 1], 1 : [3, 4, 5, 6]}
    titles = {0 : '(a)', 1 : '(b)'}
    for s in [0, 1]:

        ax = fig.add_subplot(121 + s)
        # ax.xaxis.grid(True, ls = 'dotted', lw = 0.75)
        # ax.yaxis.grid(True, ls = 'dotted', lw = 0.75)

        # plot base : road cells in black, smc cells in gray
        roadcells.plot(ax = ax, facecolor = 'black', zorder = 0)
        smccells.plot(ax = ax, facecolor = 'lightgray', zorder = 0)

        nets = []
        for i, k in enumerate(keys[s]):
            nets.append(gp.GeoDataFrame.from_file(os.path.join(output_dir, ("coverage/60/%s" % (labels[k]))))[['index', 'op']])
        nets = gp.GeoDataFrame(pd.concat(nets, ignore_index = True))
        nets = nets.groupby('index').op.nunique().to_frame('n-ops').reset_index()

        colors = ['r', 'yellow', 'cyan', 'lime']
        for i, n in enumerate(np.arange(1, np.amax(nets['n-ops']), 1)):
            indeces = nets[nets['n-ops'] == n]['index'].tolist()
            p = smccells[smccells['index'].isin(indeces)].plot(ax = ax, facecolor = colors[i], linewidth = 0.1, zorder = 0)

        antiroads.plot(ax = ax, color = 'midnightblue', alpha = 1.0, zorder = 5)
        p.set_axis_bgcolor('midnightblue')
        # p.set_axis_bgcolor('mediumblue')

        if s < 1:
            ax.set_ylabel("Latitude")
        else:
            ax.yaxis.set_visible(False)
            # custom legend using matplotlib.patches
            # https://stackoverflow.com/questions/39500265/manually-add-legend-items-python-matplotlib
            patches = [
                matplotlib.patches.Patch(color = 'black', label = 'no data'),
                matplotlib.patches.Patch(color = 'lightgray', label = '<-65 dbm'),
                matplotlib.patches.Patch(color = 'red', label = '1'), 
                matplotlib.patches.Patch(color = 'yellow', label = '2'),
                matplotlib.patches.Patch(color = 'cyan', label = '3'),
                matplotlib.patches.Patch(color = 'lime', label = '4'),]
            legend = ax.legend(handles = patches, fontsize = 12, ncol = 1, loc = 'center right', bbox_to_anchor=(1.25, 0.5))
            legend.get_frame().set_facecolor('white')
            legend.get_frame().set_alpha(1.0)

        ax.set_xlabel("Longitude")
        ax.set_xlim(-8.65, -8.575)
        ax.set_ylim(41.14, 41.175)

        ax.set_title(titles[s])

    fig.tight_layout()
    # fig.subplots_adjust(wspace = 0.3)
    plt.savefig(os.path.join(output_dir, "graphs/coverage.pdf"), bbox_inches = 'tight', format = 'pdf')

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--data-file", 
         help = """.csv file w/ session data""")
    parser.add_argument(
        "--output-dir", 
         help = """output data dir""")

    args = parser.parse_args()

    if not args.data_file:
        sys.stderr.write("""%s: [ERROR] please supply a .csv file w/ input data\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        args.output_dir = "../data/output"

    # roads = get_roads(args.output_dir)
    # get_antroads(args.output_dir)
    # get_roadcells(args.output_dir, roads)
    # refine_roadcells(args.data_file, args.output_dir)
    # for t in [-80, -70, -65, -60]:
    #     get_coverage(args.data_file, args.output_dir, threshold = t)
    # get_coverage(args.data_file, args.output_dir)
    # plot_coverage(args.output_dir)

    sys.exit(0)