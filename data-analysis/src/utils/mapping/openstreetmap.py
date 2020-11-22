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
from __future__ import absolute_import

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
import shapely.geometry
import timeit
import sqlalchemy

from random import randint
from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict
from prettytable import PrettyTable

# custom imports
#   - analysis
import analysis.smc.database
import analysis.trace.utils.gps
#   - mapping utils
import utils.mapping.utils
import utils.mapping.geopandas_osm.osm as osm

# gps coords for a 'central' pin on porto, portugal
LAT  = 41.163158
LON = -8.6127137
# north, south, west, east limits of map, in terms of geo coordinates
LATN = LAT + 0.03
LATS = LAT - 0.03
LONE = LON + 0.06
LONW = LON - 0.06

CELL_SIZE = 20.0

#DEFAULT_HIGHWAY = ['highway=motorway', 'highway=trunk', 'highway=primary', 'highway=secondary', 'highway=tertiary', 'highway=residential']
DEFAULT_HIGHWAY = ['highway=motorway', 'highway=trunk', 'highway=primary', 'highway=secondary']

def get_road_hash(bbox, tags):
    return hashlib.md5((','.join([str(c) for c in bbox]) + ',' + ','.join(tags)).encode('utf-8')).hexdigest()

def create_cells_table(data, db_eng = None):

    if db_eng is None:
        db_eng = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')

    if analysis.smc.database.table_exists('cells', db_eng):
        print("%s::create_cells_table() : [INFO] cells table exists. skipping." % (sys.argv[0]))
        return

    start = timeit.default_timer()

    try:
        data.to_sql(con = db_eng, name = 'cells', if_exists = 'append', index = False)
    except Exception:
        sys.stderr.write("""%s::create_cells_table() : [WARNING] %s table exists. skipping.\n""" % (sys.argv[0], 'cells'))

    print("%s::create_cells_table() : [INFO] stored cells in sql database (%.3f sec)" % (sys.argv[0], timeit.default_timer() - start))

def create_roads_cells_table(output_dir, 
    bbox = [LONW, LATS, LONE, LATN], 
    tags = DEFAULT_HIGHWAY,
    cell_size = CELL_SIZE, 
    db_eng = None):

    extract_roads(output_dir, bbox, tags)
    extract_cells(output_dir, bbox, tags, cell_size = cell_size)

    if db_eng is None:
        db_eng = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')

    if analysis.smc.database.table_exists('roads_cells', db_eng):
        print("%s::create_roads_cells_table() : [INFO] roads_cells table exists. skipping." % (sys.argv[0]))
        return

    # load roads
    roads = pd.read_sql('SELECT * FROM roads', con = db_eng)
    # load cells (intersection w/ roads)
    road_hash = get_road_hash(bbox, tags)
    cells = gp.GeoDataFrame.from_file(os.path.join(output_dir, ("cells/%s" % (road_hash))))
    cells = cells.dropna(subset = ['name']).reset_index(drop = True)
    cells['name'] = cells['name'].apply(lambda x : x.encode('utf-8'))
    cells['name_hash'] = cells['name'].apply(lambda x : hashlib.md5(x).hexdigest())

    # merge cells w/ roads 
    roads_cells = pd.merge(cells[['cell_id', 'name_hash']], roads[['id', 'name_hash']], on = ['name_hash'], how = 'left')
    # store roads_cells junction table
    start = timeit.default_timer()
    roads_cells['road_id'] = roads_cells['id']

    try:
        roads_cells[['road_id', 'cell_id']].drop_duplicates().to_sql(con = db_eng, name = 'roads_cells', if_exists = 'append', index = False)
    except Exception:
        sys.stderr.write("""%s::create_roads_cells_table() : [WARNING] %s table exists. skipping.\n""" % (sys.argv[0], 'roads_cells'))

    print("%s::create_roads_cells_table() : [INFO] stored roads_cells in sql database (%.3f sec)" % (sys.argv[0], timeit.default_timer() - start))

def create_roads_table(output_dir, 
    bbox = [LONW, LATS, LONE, LATN], 
    tags = DEFAULT_HIGHWAY,
    db_eng = None):

    road_hash = get_road_hash(bbox, tags)
    road_dir = os.path.join(output_dir, road_hash)
    # extract road info from osm (if needed)
    extract_roads(output_dir, bbox, tags)

    if db_eng is None:
        db_eng = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')
    if analysis.smc.database.table_exists('roads', db_eng):
        print("%s::create_roads_table() : [INFO] roads table exists. skipping." % (sys.argv[0]))
        return

    # get road information
    roads = gp.GeoDataFrame.from_file(road_dir)
    # convert roads GeoDataFrame to a Coordinate Reference System (CRS) from which we can directly derive linear measurements
    # source: http://ryan-m-cooper.com/blog/gps-points-to-line-segments.html
    # we use epsg code 3763, which contains Portugal, and allows use to measure lengths in meters
    # the CRS in the original dataframe is 4326 (or WGS84), the one used by GPS
    roads.crs = {'init' : 'epsg:4326'}
    # encode road names in utf-8
    roads = roads.dropna(subset = ['name']).reset_index(drop = True)
    roads['name'] = roads['name'].apply(lambda x : x.encode('utf-8'))
    roads['name_hash'] = roads['name'].apply(lambda x : hashlib.md5(x).hexdigest())

    # convert roads CRS to 3763 to calculate length in meters
    _roads = roads.to_crs(epsg = 3763)
    # calculate length (in meters) of LineString segments
    _roads['length'] = _roads['geometry'].length
    # groupby() LineString segments by road name (e.g., 'Avenida da Boavista')
    lengths = _roads.groupby(['name', 'name_hash'])['length'].sum().reset_index(drop = False)

    start = timeit.default_timer()

    try:
        lengths.to_sql(con = db_eng, name = 'roads', if_exists = 'append', index_label = 'id')
    except Exception:
        sys.stderr.write("""%s::create_roads_table() : [WARNING] %s table exists. skipping.\n""" % (sys.argv[0], 'roads'))

    print("%s::create_roads_table() : [INFO] roads stored in sql database (%.3f sec)" % (sys.argv[0], timeit.default_timer() - start))

def extract_roads(output_dir, 
    bbox = [LONW, LATS, LONE, LATN], 
    tags = DEFAULT_HIGHWAY):

    # check if road information is already extracted. return road_hash if it is.
    road_hash = get_road_hash(bbox, tags)
    road_dir = os.path.join(output_dir, road_hash)
    if os.path.isdir(road_dir):
        sys.stderr.write("""[INFO] %s exists. skipping OSM extraction.\n""" % (road_dir))
        return

    bbox = shapely.geometry.geo.box(bbox[0], bbox[1], bbox[2], bbox[3])
    roads = []
    start = timeit.default_timer()
    # extract road information from OpenStreetMap (OSM) service
    for tag in tags:
        roads.append(osm.query_osm('way', bbox, recurse = 'down', tags = tag))
    print("%s::extract_roads() : [INFO] extracted road data from OpenStreetMaps in %.3f sec" % (sys.argv[0], timeit.default_timer() - start))

    # concat all tags in single dataframe
    roads = gp.GeoDataFrame(pd.concat(roads, ignore_index = True))
    # save OSM data in road_dir
    roads[roads.type == 'LineString'].to_file(road_dir, driver = 'ESRI Shapefile')

def extract_cells(
    output_dir, bbox, tags,
    cell_size = CELL_SIZE,
    force = False):

    cells_dir = os.path.join(output_dir, 'cells')
    if not os.path.isdir(cells_dir):
        os.makedirs(cells_dir)

    road_hash = get_road_hash(bbox, tags)
    cells_dir = os.path.join(cells_dir, road_hash)
    if os.path.isdir(cells_dir) and (not force):
        sys.stderr.write("""[INFO] %s exists. skipping cell intersection.\n""" % (cells_dir))
        return

    # extract nr. of cells in the designated area
    xx, yy = analysis.trace.utils.gps.get_cell_num(cell_size = cell_size, lat = [LATN, LATS], lon = [LONW, LONE])
    w = (LONE - LONW) / float(xx)
    h = (LATN - LATS) / float(yy)

    cells = pd.DataFrame(columns = ['id', 'cell_x', 'cell_y'])
    
    polygons = []
    cells = []
    for i in range(xx):
        for j in range(yy):
            polygons.append(
                shapely.geometry.Polygon(
                    [
                    (LONW + (i * w), LATS + (j * h)), 
                    (LONW + ((i + 1) * w), LATS + (j * h)), 
                    (LONW + ((i + 1) * w), LATS + ((j + 1) * h)), 
                    (LONW + (i * w), LATS + ((j + 1) * h))
                    ]))

            cells.append({'id' : int((j * xx) + i), 'cell_x' : i, 'cell_y' : j})

    # create cells table
    cells = pd.DataFrame(cells)
    create_cells_table(cells)

    grid = gp.GeoDataFrame({'geometry' : polygons, 'cell_id' : cells['id'].tolist()})
    # the CRS of grid is 4326 (or WGS84), the one used by GPS    
    grid.crs = {'init' : 'epsg:4326'}
    # get road information
    roads = gp.GeoDataFrame.from_file(os.path.join(output_dir, road_hash))
    # calculate intersection w/ roads (this is INSANELY fast...)
    start = timeit.default_timer()
    intersections = gp.sjoin(grid, roads, how = "inner", op = 'intersects').reset_index()[['index', 'geometry', 'name', 'cell_id']].drop_duplicates(subset = 'index')
    print("%s::extract_cells() : [INFO] geopandas sjoin in %.3f sec" % (sys.argv[0], timeit.default_timer() - start))
    # save intersection
    intersections.to_file(cells_dir, driver = 'ESRI Shapefile')
