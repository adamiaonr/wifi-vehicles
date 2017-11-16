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

# for maps
import pdfkit

from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict

# for ap location estimation
from shapely.geometry import Point

from random import randint

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

# info about the sense-my-city dataset
#   ds : distance travelled by the user during the scanning period
#   freq : channel frequency
#   acc_scan : mean accuracy from the GPS during the scanning period
#   new_err : mean error related to the map matching process (was conducted by others)
#   new_lat | new_lot : location where the scan was associated
#   g_lat | g_lon : cell location
#   auth : authentication mode (0 - Unknown, 1 - Open, 2 - WEP, 3 - WPA, 4 - WPA2, 5 - Enterprise (RADIUS/.11x/Other).)
WIFI_AUTH = {0: 'unknown', 1: 'open', 2: 'wep', 3: 'wpa', 4: 'wpa2', 5: 'wpa2-enter'}

# dict of wifi providers. structure is as follows:
#   [id of provider] : ['<public/private flag>:<common essid prefix>']
WIFI_PROVIDERS = {
    1 : ['meo', '0:MEO-WiFi', '1:MEO-', '1:Thomson', '0:PT-WIFI'], 
    2 : ['zon', '0:FON_ZON', '1:ZON-'], 
    3 : ['eduroam', '0:eduroam'],
    4 : ['porto-digital', '0:WiFi Porto Digital'],
    5 : ['vodafone', '1:Vodafone-', '1:VodafoneFibra-' '1:VodafoneMobileWiFi-'],
    6 : ['lab-cc', '0:LabCC'],
    7 : ['unknown']
}
# columns of .hdf5 stores for different wifi bands (2.4 and 5.0 ghz)
WIFI_BANDS_COLUMNS = {
    1 : ['ts', 'session_id', 'xy', 'provider', 'mac_addr', 'essid', 'access', 'segment_type', 'f2412','f2417','f2422','f2427','f2432','f2437','f2442','f2447','f2452','f2457','f2462','f2467','f2472'],
    2 : ['ts', 'session_id', 'xy', 'provider', 'mac_addr', 'essid', 'access', 'segment_type', 'f5180','f5200','f5220','f5240','f5260','f5280','f5300','f5320','f5500','f5520','f5560','f5580','f5600','f5620']
}
# translation between wifi band indexes and textual representation
WIFI_BANDS = {1 : '2.4', 2 : '5.0', '2.4' : 1, '5.0' : 2}
# translation between wifi band channel # and frequencies
WIFI_CHANNELS = {   
    1 : {'f2412' : 1, 'f2417' : 2, 'f2422' : 3, 'f2427' : 4, 'f2432' : 5, 'f2437' : 6, 'f2442' : 7, 'f2447' : 8, 'f2452' : 9, 'f2457' : 10, 'f2462' : 11, 'f2467' : 12, 'f2472' : 13 }
}

# segment types according to speed. translation between indexes and textual 
# representation
SEGMENT_TYPES = {0 : 'stationary', 1 : 'pedestrian-speed', 2 : 'vehicular-speed'}

def extract_coverage(out_dir, ap_stats, band = 1, segment_types = []):

    # we'll save data for the map in a .csv file
    coverage = pd.DataFrame(columns = ['cell', 'n', 'ss', 'channels'])

    # segment types part of query
    segment_query = ""
    if segment_types:
        segment_query = " or ".join([("segment_type == %d" % (s)) for s in segment_types])
        segment_query = " and ( " + segment_query + " )"

    print(segment_query)

    # extract coverage data on a session basis
    dataset = ('channels/%s' % (WIFI_BANDS[band]))
    session_ids = ap_stats.select_column(dataset, 'session_id').unique()    
    for session_id in session_ids:

        sd = ap_stats.select(dataset, ("""session_id == %d%s""" % (session_id, segment_query)))
        cells = sd['xy'].unique()
        for cell in cells:

            # pull cell data into memory
            cd = sd[sd['xy'] == cell]
            # nr. of visible essids
            essids = cd.groupby(['essid'])['essid'].count()
            essids = len(essids)
            # median ss : filter by ss < 0.0
            ss = cd[cd[WIFI_BANDS_COLUMNS[band][8:]].lt(0.0)].median().max()
            # nr. of channels : filter by ss < 0.0
            channels = cd[cd[WIFI_BANDS_COLUMNS[band][8:]].lt(0.0)][WIFI_BANDS_COLUMNS[band][8:]].sum().count()

            coverage = coverage.append({
                'cell' : cell,
                'n' : essids,
                'ss' : ss,
                'channels' : channels
                }, ignore_index = True)

            del cd
        del sd

    coverage = coverage.groupby(['cell']).median().reset_index()

    segment_suffix = ""
    if segment_types:
        segment_suffix = "-" + "".join([str(s) for s in segment_types])
    coverage.to_csv(os.path.join(out_dir, "coverage" + segment_suffix + ".csv"), sep = ',')

def coverage(out_dir, ap_stats, cell_size, map_ctr, band = 1, segment_types = []):

    gmap = defaultdict()
    for cat in ['n', 'ss', 'channels']:
        gmap[cat] = gmplot.GoogleMapPlotter(map_ctr[0], map_ctr[1], map_ctr[2])

    # deltas in lat and lon equivalent to cell_size
    delta_lat = ((PORTO_LATITUDE_LIMIT_NORTH - PORTO_LATITUDE_LIMIT_SOUTH) * cell_size) / (Y_SPAN)
    delta_lon = ((PORTO_LONGITUDE_LIMIT_EAST - PORTO_LONGITUDE_LIMIT_WEST) * cell_size) / (X_SPAN)

    # colors for each chart category
    # color map w/ gradient from red to green
    color_map = plt.get_cmap('RdYlGn')
    colors = defaultdict()
    # define the nr. of steps in the color scale for each category
    colors_n = {'n' : 10, 'ss' : 5, 'channels' : 5}
    for cat in gmap:
        colors[cat] = [color_map(i) for i in np.linspace(0, 1, float(colors_n[cat]))]

    # # show the hex codes
    # for i, color in enumerate(colors):
    #     print("color[%d] : %s" % (i, matplotlib.colors.rgb2hex(color[:3]).lstrip('#')))

    # collect the data
    segment_suffix = ""
    if segment_types:
        segment_suffix = "-" + "".join([str(s) for s in segment_types])
    filenames = [os.path.join(out_dir, "coverage" + segment_suffix + ".csv")]
    if (not os.path.exists(filenames[0])):
        extract_coverage(out_dir, ap_stats, band = band, segment_types = segment_types)

    coverage = pd.read_csv(filenames[0]).reset_index()

    limits = defaultdict()
    for cat in gmap:
        limits[cat] = [coverage[cat].min(), np.nanpercentile(coverage[cat], 100)]

    print(limits)

    for index, row in coverage.iterrows():

        cell = [float(e) for e in row['cell'].split(":")]

        # x : longitude (horizontal)
        # y : latitude  (vertical)
        x = float(cell[0])
        y = float(cell[1])

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
            val = float(row[cat])
            if math.isnan(val):
                continue
            # calculate appropriate color
            c = int(((val - limits[cat][0]) / (limits[cat][1] - limits[cat][0])) * float(colors_n[cat]))
            c = max(0, c)
            c = min((colors_n[cat] - 1), c)

            rgb = colors[cat][c][:3]
            color = matplotlib.colors.rgb2hex(rgb)

            gmap[cat].polygon(lats, lons, edge_color = "black", edge_width = 0.5, face_color = color, face_alpha = 1.00)

    # print a fake plot, just to extract the legend
    fig = plt.figure(figsize = (12, 5))

    subplot_code = 131
    for k, cat in enumerate(gmap.keys()):

        ax = fig.add_subplot(subplot_code + k)

        delta = (((limits[cat][1]) - limits[cat][0]) / float(colors_n[cat]))
        values = np.arange(limits[cat][0], limits[cat][1], delta)

        for i, v in enumerate(values):
            ax.bar(
                i, v, 
                alpha = 0.55, width = 0.75, 
                label = ('[%d, %d]' % (math.ceil(limits[cat][0] + (i * delta)), math.floor(limits[cat][0] + ((i + 1) * delta)))), 
                color = matplotlib.colors.rgb2hex(colors[cat][i][:3]))

        ax.legend(fontsize = 12, ncol = 1, loc = 'upper right')
        ax.set_ylim(0.0, 10000.0)

    fig.tight_layout()
    fig.subplots_adjust(top = 0.95)

    plt.savefig(os.path.join(out_dir, "../../graphs/maps/coverage-legend" + segment_suffix + ".pdf"), bbox_inches = 'tight', format = 'pdf')

    for cat in gmap:
        filename = os.path.join(out_dir, "../../graphs/maps/coverage-" + cat + segment_suffix + ".html")
        gmap[cat].draw(filename)

def plot(out_dir, cell_size = 10.0, geo_limits = [], segment_types = []):

    """plots stats from 'sense my city' sessions"""

    if not geo_limits:
        map_ctr = [PORTO_LATITUDE, PORTO_LONGITUDE, 14.5]
    else:
        map_ctr = [((geo_limits[0] + geo_limits[1]) / 2.0), ((geo_limits[2] + geo_limits[3]) / 2.0), 16]

    # load the .hdf5 store
    ap_stats = None
    filename = os.path.join(out_dir, 'ap-stats.hdf5')
    if (not os.path.exists(filename)):
        sys.stderr.write("""%s: [ERROR] no .hdf5 files found\n""" % sys.argv[0]) 
        sys.exit(1)
    else:
        ap_stats = pd.HDFStore(os.path.join(out_dir, 'ap-stats.hdf5'))

    #extract_coverage(out_dir, ap_stats, segment_types = [1, 2])
    coverage(out_dir, ap_stats, cell_size, map_ctr, band = 2, segment_types = [2])
