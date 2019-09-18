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
import os
import sys
import hashlib
import geopandas as gp
import shapely.geometry
import timeit

# custom imports
#   - mapping utils
import mapping.geopandas_osm.osm as osm
import mapping.utils

def get_road_hash(bbox, tags):
    return hashlib.md5((','.join([str(c) for c in bbox]) + ',' + ','.join(tags)).encode('utf-8')).hexdigest()

def extract_roads(output_dir, 
    bbox, 
    tags = ['highway=motorway', 'highway=trunk', 'highway=primary', 'highway=secondary', 'highway=tertiary', 'highway=residential', 'building=all']):

    # check if road information is already extracted. return road_hash if it is.
    road_hash = get_road_hash(bbox, tags)
    road_dir = os.path.join(output_dir, road_hash)
    if os.path.isdir(road_dir):
        sys.stderr.write("""[INFO] %s exists. skipping OSM extraction.\n""" % (road_dir))
        roads = gp.GeoDataFrame.from_file(road_dir) 
        return roads

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

    return roads

def extract_cells(bbox, tags, cell_size = 5.0):

    # extract nr. of cells in the designated area
    xx, yy = mapping.utils.get_cell_num(cell_size = cell_size, lat = [bbox[1], bbox[3]], lon = [bbox[0], bbox[2]])
    w = (bbox[2] - bbox[0]) / float(xx)
    h = (bbox[3] - bbox[1]) / float(yy)

    cells = pd.DataFrame(columns = ['id', 'cell_x', 'cell_y'])
    
    polygons = []
    cells = []
    for i in range(xx):
        for j in range(yy):
            polygons.append(
                shapely.geometry.Polygon(
                    [
                    (bbox[0] + (i * w), bbox[1] + (j * h)), 
                    (bbox[0] + ((i + 1) * w), bbox[1] + (j * h)), 
                    (bbox[0] + ((i + 1) * w), bbox[1] + ((j + 1) * h)), 
                    (bbox[0] + (i * w), bbox[1] + ((j + 1) * h))
                    ]))

            lat = (bbox[1] + (j * h) + bbox[1] + ((j + 1) * h)) / 2.0
            lon = (bbox[0] + (i * w) + bbox[0] + ((i + 1) * w)) / 2.0
            cells.append({'id' : int((j * xx) + i), 'cell_x' : i, 'cell_y' : j, 'lat' : lat, 'lon' : lon})

    cells = pd.DataFrame(cells)
    grid = gp.GeoDataFrame({
        'geometry' : polygons, 
        'cell_id' : cells['id'].tolist(), 
        'cell_x' : cells['cell_x'].tolist(),
        'cell_y' : cells['cell_y'].tolist(),
        'cell_lat' : cells['lat'].tolist(),
        'cell_lon' : cells['lon'].tolist(),
    })
    # the CRS of grid is 4326 (or WGS84), the one used by GPS    
    grid.crs = {'init' : 'epsg:4326'}

    return grid, w, h
