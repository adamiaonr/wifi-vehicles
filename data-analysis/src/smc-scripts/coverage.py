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

# for maps
import pdfkit

from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict

import folium
from folium.plugins import HeatMap
from folium.plugins import MarkerCluster
import branca

# gps coords for a 'central' pin on porto, portugal
PORTO_LATITUDE = 41.163158
PORTO_LONGITUDE = -8.6127137

def to_hdf5(
    data, 
    metric, 
    link_data):

    link_data.append(
        ('%s' % (metric)),
        data,
        data_columns = data.columns,
        format = 'table')

def plot_coverage(output_dir, map_type = 'heatmap'):

    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(output_dir, "all-wf-database.hdf5"))    
    # load ap location data
    loc = database.select(('/%s' % ('ap-locations'))).sort_values(by = ['counts'])
    h = len(loc) / 2
    loc = loc.head(h)

    ap_map = folium.Map(location = [PORTO_LATITUDE, PORTO_LONGITUDE], 
        zoom_start = 14, 
        tiles = "Stamen Toner")

    if map_type == 'heatmap':

        hm_wide = HeatMap( 
                        list(zip(loc.new_lat.values, loc.new_lon.values, loc.counts.values)),
                       min_opacity = 0.025,
                       max_val = 50,
                       radius = 5, blur = 10, 
                       max_zoom = 14, )

        ap_map.add_child(hm_wide)

    elif map_type == 'clustered-marker':

        marker_cluster = MarkerCluster().add_to(ap_map)

        for index, row in loc.iterrows():
            folium.Marker(location = [ row['new_lat'], row['new_lon'] ]).add_to(marker_cluster)

    ap_map.save(os.path.join(output_dir, 'ap-locations.html'))

def extract_ap_locations(output_dir):

    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(output_dir, "all-wf-database.hdf5"))    
    # load ap data
    for chunk in database.select(('/%s' % ('ap-stats')), chunksize = 10 ** 5):

        # groupby() 'essid' and 'encode', and calculate location using 'the method'
        ap_locations = chunk.groupby(['essid-hash', 'encode'])[['new_lat', 'new_lon']].mean().reset_index(drop = False)
        loc = ap_locations.groupby(['new_lat', 'new_lon']).size().reset_index(drop = False, name = 'counts')

        to_hdf5(
            loc, 
            ('/%s' % ('ap-locations')), 
            database)

def extract_ap_stats(input_dir, output_dir):

    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(output_dir, "all-wf-database.hdf5"))
    for filename in sorted(glob.glob(os.path.join(input_dir, 'all_wf.grid.csv'))):
        # given the large size of the input data file (> 3 GB), we read the file in chunks
        chunksize = 10 ** 5
        for chunk in pd.read_csv(filename, chunksize = chunksize):
            chunk['essid-hash'] = [ hash(essid) for essid in chunk['essid'].values ]
            to_hdf5(
                chunk[['essid-hash', 'encode', 'snr', 'auth', 'frequency', 'new_lat', 'new_lon']], 
                ('/%s' % ('ap-stats')), 
                database)

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--input-dir", 
         help = """dir w/ trace data""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save graphs & other output data""")

    args = parser.parse_args()

    if not args.input_dir:
        sys.stderr.write("""%s: [ERROR] must provide a dir w/ input files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] must provide an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)
    
    # extract_ap_stats(args.input_dir, args.output_dir)
    # extract_ap_locations(args.output_dir)
    plot_coverage(args.output_dir)

    sys.exit(0)