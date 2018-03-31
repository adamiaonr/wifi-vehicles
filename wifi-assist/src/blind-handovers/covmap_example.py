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
import multiprocessing as mp 
import hashlib
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

# custom imports
import coverage_map
import availability

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--log-dir", 
         help = """dir w/ .csv data""")
    parser.add_argument(
        "--output-dir", 
         help = """output data dir""")

    args = parser.parse_args()

    if not args.log_dir:
        sys.stderr.write("""%s: [ERROR] please supply a dir of .csv files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        args.output_dir = "../data/output"

    # initialize coverage map obj
    cmap = coverage_map.CoverageMap()
    # build cov map from gps and scan logs
    # FIXME: this should be changed in the future
    gps = os.path.join(args.log_dir, "gps-log.csv")
    scans = os.path.join(args.log_dir, "wifi-scans.csv")
    start = timeit.default_timer()
    cmap.build(gps, scans)
    print("%s::main() : [INFO] built map in %.3f sec" % (sys.argv[0], timeit.default_timer() - start))

    # generate a simple visualization of the coverage map
    # use the ration of lat and lon spans to get appropriate 
    # proportions in the fig
    dx = abs((-8.593912 + 0.001) - (-8.598336 - 0.001))
    dy = abs((41.179283 + 0.001) - (41.176796 - 0.001))
    fig = plt.figure(figsize = (4.25 * (dx / dy), 4.25))
    ax = fig.add_subplot(111)

    ax.xaxis.grid(True, ls = 'dotted', lw = 0.75)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.75)

    # extract map of roads (all type) from openstreetmap
    roads = availability.get_roads(
        args.output_dir, 
        bbox = [-8.598336, 41.179283, -8.593912, 41.176796], 
        tags = ['highway='])
    # filters
    roads = roads.dropna(subset = ['highway'])
    roads = roads[roads['highway'].str.contains('footway|cycleway') == False]
    roads = roads[roads.type == 'LineString'][['highway', 'name', 'geometry']]
    # plot the roads in black
    roads.plot(ax = ax, color = 'black', zorder = 0)

    # axis limits
    ax.set_xlim(-8.598336 - 0.001, -8.593912 + 0.001)
    ax.set_ylim(41.176796 - 0.001, 41.179283 + 0.001)
    # axis labels
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    # axis ticks
    ax.set_xticks(np.arange(-8.598, -8.592, 0.002))
    ax.set_yticks(np.arange(41.176, 41.180, 0.001))

    fig.tight_layout()
    # fig.subplots_adjust(wspace = 0.3)
    plt.savefig(os.path.join(args.output_dir, "road-map.pdf"), bbox_inches = 'tight', format = 'pdf')

    # collect the coverage polygons by wifi network
    polygons = defaultdict(list)
    for cell in cmap.map:
        for ap in cmap.map[cell].aps:

            label = cmap.aps[ap].essid
            polygons[label].append(
                shapely.geometry.Polygon(
                    [
                    (cmap.map[cell].bounds[2], cmap.map[cell].bounds[1]), 
                    (cmap.map[cell].bounds[2], cmap.map[cell].bounds[3]), 
                    (cmap.map[cell].bounds[0], cmap.map[cell].bounds[3]), 
                    (cmap.map[cell].bounds[0], cmap.map[cell].bounds[1])
                    ]))

    # plot the 5x5 meter coverage for a selected nr. of networks
    nets = {'enduroam' : 'green', 'swarm' : 'yellow', 'linksys' : 'blue', 'INEGI-WIFI' : 'red', 'raspberrypi' : 'orange'}
    patches = []
    for net in nets:

        grid = gp.GeoDataFrame({'geometry':polygons[net]})
        if grid.empty:
            continue
        grid.plot(ax = ax, facecolor = nets[net], zorder = 1, alpha = 0.75)

        patches.append(matplotlib.patches.Patch(color = nets[net], label = net))

    # custom legend using matplotlib.patches
    # https://stackoverflow.com/questions/39500265/manually-add-legend-items-python-matplotlib
    legend = ax.legend(handles = patches, fontsize = 12, ncol = 1, loc = 'center right', bbox_to_anchor=(1.25, 0.5))
    legend.get_frame().set_facecolor('white')
    legend.get_frame().set_alpha(1.0)

    fig.tight_layout()
    # fig.subplots_adjust(wspace = 0.3)
    plt.savefig(os.path.join(args.output_dir, "coverage-map.pdf"), bbox_inches = 'tight', format = 'pdf')