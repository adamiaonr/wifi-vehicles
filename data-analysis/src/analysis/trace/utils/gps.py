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
import os
import glob
import datetime

from collections import defaultdict

# custom imports
#   - hdfs utils
import utils.hdfs
#   - mapping utils
import utils.mapping.utils

# north, south, west, east gps coord limits of FEUP map
LATN = 41.176796
LATS = 41.179283
LONE = -8.593912
LONW = -8.598336
# central gps coords for FEUP
LAT  = (41.176796 + 41.179283) / 2.0
LON = (-8.598336 + -8.593912) / 2.0

def get_closest_cell(cell, candidates):
    
    cells = pd.DataFrame()
    for c in candidates:
        cells = cells.append({'cell-x' : c[0], 'cell-y' : c[1]}, ignore_index = True)
    cells['diff'] = np.abs(cells['cell-x'] - cell[0]) + np.abs(cells['cell-y'] - cell[1])
    return cells.ix[cells['diff'].idxmin()]

def get_lap_datetimes(gps_data):

    segments = gps_data.groupby(['lap-number'])['interval-tmstmp'].apply(np.array).reset_index(drop = False)
    timestamps = defaultdict(datetime.datetime)
    for i, segment in segments.iterrows():
        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in [ segment['interval-tmstmp'][0], segment['interval-tmstmp'][-1] ] ]
        timestamps[segment['lap-number']] = dates[0]

    return timestamps

def get_cell_datetimes(gps_data):

    segments = gps_data.groupby(['cell-x', 'cell-y', 'lap-number', 'direction'])['interval-tmstmp'].apply(np.array).reset_index(drop = False)
    timestamps = []
    for i, segment in segments.iterrows():
        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in [ segment['interval-tmstmp'][0], segment['interval-tmstmp'][-1] ] ]
        timestamps.append(dates[0])

    return sorted(timestamps)

def get_cell_num(cell_size, lat = [LATN, LATS], lon = [LONW, LONE]):
    # x-axis : longitude
    LAT = sum(np.array(lat)) / 2.0
    X_CELL_NUM = int(np.ceil((utils.mapping.utils.gps_to_dist(LAT, lon[0], LAT, lon[1]) / cell_size)))
    # y-axis : latitude
    Y_CELL_NUM = int(np.ceil((utils.mapping.utils.gps_to_dist(lat[0], 0.0, lat[1], 0.0) / cell_size)))
    return X_CELL_NUM, Y_CELL_NUM

def add_cells(data, cell_size, bbox = [LONW, LATS, LONE, LATN]):

    lat_s = bbox[1]
    lat_n = bbox[3]
    lon_w = bbox[0]
    lon_e = bbox[2]

    # extract nr. of cells in the designated area
    xx, yy = get_cell_num(cell_size = cell_size, lat = [lat_n, lat_s], lon = [lon_w, lon_e])
    # add cell ids to data, based on [new_lat, new_lon]
    data['cell_x'] = data['lon'].apply(lambda x : int((x - lon_w) / (lon_e - lon_w) * xx)).astype(int)
    data['cell_y'] = data['lat'].apply(lambda y : int((y - lat_s) / (lat_n - lat_s) * yy)).astype(int)
    # drop rows with out-of-bounds cell coords
    data.drop(data[(data['cell_y'] < 0) | (data['cell_x'] < 0) | (data['cell_y'] > (yy - 1)) | (data['cell_x'] > (xx - 1))].index, inplace = True)
    # it will be useful to get a single integer id
    data['cell_id'] = (data['cell_y'].apply(lambda y : (y * xx)) + data['cell_x']).astype(int)    

def add_lap_numbers(data, lap_timestamps):

    # reset 'lap-number' and 'direction' columns
    data['lap-number'] = -1.0
    data['direction'] = -1.0

    i = 0
    while (i + 1) < len(lap_timestamps['start']):
        # set lap nr.
        data.loc[(data['timestamp'] > float(lap_timestamps['start'][i])) & (data['timestamp'] <= float(lap_timestamps['start'][i + 1])), 'lap-number'] = i + 1

        # set direction(s) :
        #    1 : East to West
        #   -1 : West to East
        data.loc[(data['timestamp'] > float(lap_timestamps['start'][i])) & (data['timestamp'] <= float(lap_timestamps['turn'][i])), 'direction'] = 1
        data.loc[(data['timestamp'] > float(lap_timestamps['turn'][i]))  & (data['timestamp'] <= float(lap_timestamps['start'][i + 1])), 'direction']  = -1

        i += 1

# def get_lap_timestamps(data, ref = {'lat' : 41.178685, 'lon' : -8.597872}):
#     # find 'peaks' of distance to a ref position, guaranteed to be outside of the experimental circuit
#     pos = [ [row['lat'], row['lon'] ] for index, row in data.iterrows() ]
#     data['lap-dist'] = [ mapping.utils.gps_to_dist(ref['lat'], ref['lon'], gps[0], gps[1]) for gps in pos ]
#     return analysis.metrics.find_peaks(data, x_metric = 'timestamp', y_metric = 'lap-dist')

def get_lap_timestamps(input_dir, trace_nr, ref_ap = 'w1', threshold = 155.0):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    dist = database.select('/best/distances').sort_values(by = ['timed-tmstmp'])
    dist = dist[dist[ref_ap] > threshold]
    dist['lap'] = (dist['timed-tmstmp'] - dist['timed-tmstmp'].shift(1) > 5.0).astype(int).cumsum()
    return dist.sort_values(by = ['lap', 'w1']).drop_duplicates(subset = 'lap')[['timed-tmstmp', 'lap']].reset_index(drop = True)

def get_data(input_dir, trace_dir, tag_laps = False, use_gps_time = True):

    # we record two gps timestamps in the machine running gpsd:
    #   a) the timestamp of the machine when a new gps line comes in
    #   b) the timestamp reported by gps
    # if use_gps_time is set to True, we use b), else we use a)
    time_column = 'timestamp'
    if use_gps_time:
        time_column = 'time'

    for filename in sorted(glob.glob(os.path.join(trace_dir, 'gps-log.*.csv'))):
        
        gps_data = pd.read_csv(filename)
        gps_data['timestamp'] = gps_data[time_column].astype(int)
        gps_data = gps_data.sort_values(by = ['timestamp']).reset_index(drop = True)

        # reset 'lap-number' and 'direction' columns
        gps_data['lap-number'] = -1.0
        gps_data['direction'] = -1.0
        # if lap numbers are to be tagged, add them to gps_data
        if tag_laps:
            # get lap timestamps
            lap_timestamps = get_lap_timestamps(gps_data)
            # add lap numbers and direction
            add_lap_numbers(gps_data, lap_timestamps)

        # sort by unix timestamp
        # FIXME: why a second time?
        gps_data = gps_data.sort_values(by = ['timestamp']).reset_index(drop = True)

    return gps_data
