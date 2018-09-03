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
    # geodataframes, but not both.
    # sources : 
    #   - http://geopandas.org/geometric_manipulations.html
    #   - http://geopandas.org/set_operations.html
    # FIXME: this takes forever... 
    start = timeit.default_timer()
    diff = gp.overlay(base, roads, how = 'symmetric_difference')
    print("%s::get_antiroads() : [INFO] overlay() in %.3f sec" % (sys.argv[0], timeit.default_timer() - start))
    # save the result to a file
    diff.to_file(os.path.join(output_dir, "anti-roads"), driver = 'ESRI Shapefile')

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