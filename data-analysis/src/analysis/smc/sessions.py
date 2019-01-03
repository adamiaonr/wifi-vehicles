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
import hashlib
import timeit

# for parallel processing of sessions
import multiprocessing as mp 
# for maps
import pdfkit
# for MySQL & pandas
import MySQLdb as mysql
import sqlalchemy
import shapely.geometry

from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict

# geodesic distance
from geopy.distance import geodesic

# for ap location estimation
from shapely.geometry import Point

# custom imports
import analysis.metrics
import analysis.trace
import analysis.gps
import analysis.ap_selection.rssi
import analysis.ap_selection.gps

import parsing.utils
import mapping.utils

import geopandas as gp

def get_road_data(input_dir, data, columns):

    # create a geopandas dataframe out of data, which has 'lat' and 'lon' columns
    geodf = gp.GeoDataFrame(data)
    # add a 'geometry' column, built out of Point objects, in turn created from [lon, lat] columns
    geodf['geometry'] = [ shapely.geometry.Point(tuple(x)) for x in geodf[['lon' ,'lat']].values ]

    if geodf.empty:
        return

    # load road cell coordinates
    start_time = timeit.default_timer()
    road_cells = gp.GeoDataFrame.from_file(os.path.join(input_dir, "roadcells-smc"))
    print("%s::extract_road_data() : [INFO] read road-cells file in %.3f sec" % (sys.argv[0], timeit.default_timer() - start_time))
    # intersection between road cells and data 
    start_time = timeit.default_timer()
    intersection = gp.sjoin(road_cells, geodf, how = "inner", op = 'intersects')[['index', 'geometry', 'cell_x', 'cell_y'] + columns]
    print("%s::extract_road_data() : [INFO] intersection in %.3f sec" % (sys.argv[0], timeit.default_timer() - start_time))

    return intersection

def extract_signal_quality(input_dir, cell_size = 20, threshold = -80):

    output_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    # save processed data on .hdf5 database
    database = pd.HDFStore(os.path.join(output_dir, "smc.hdf5"))
    # connect to SMC mysql database
    conn = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')

    table = ('/signal-quality/total/%s/%s' % (cell_size, int(abs(threshold))))
    if table not in database.keys():
        # time mysql queries
        start_time = timeit.default_timer()
        # get rss stats per <cell, session> pair from mysql database
        data = pd.read_sql(
            """SELECT cell_x, cell_y, avg(lat) AS lat, avg(lon) AS lon, avg(rss) AS rss_mean, stddev(rss) AS rss_stddev
            FROM(
                SELECT cell_x, cell_y, session_id, avg(lat) AS 'lat', avg(lon) AS 'lon', avg(rss) AS 'rss'
                FROM original
                GROUP BY cell_x, cell_y, session_id
                ) AS T
            GROUP BY cell_x, cell_y""",             
            con = conn)

        print("%s::extract_signal_quality() : [INFO] data retrieved (%.3f sec)" % (sys.argv[0], timeit.default_timer() - start_time))
        # save data on .hdf5 database
        parsing.utils.to_hdf5(data, ('/signal-quality/total/%s/%s' % (cell_size, int(abs(threshold)))), database)

    else:
        data = database.select(table)

    # only road cells now...
    table = ('/signal-quality/road/%s/%s' % (cell_size, int(abs(threshold))))
    if table not in database.keys():
        intersection = get_road_data(input_dir, data, columns = ['rss_mean', 'rss_stddev'])
        # save numeric data on database
        parsing.utils.to_hdf5(intersection[['cell_x', 'cell_y'] + ['rss_mean', 'rss_stddev']], table, database)
        # save intersection shapefile (for map printing)
        map_dir = os.path.join(output_dir, "signal-quality")
        if not os.path.isdir(map_dir):
            os.makedirs(map_dir)

        intersection.to_file(os.path.join(map_dir, ("%s-%s" % (cell_size, int(abs(threshold))))), driver = 'ESRI Shapefile')

def extract_esses(input_dir, cell_size = 20, threshold = -80):

    output_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    database = pd.HDFStore(os.path.join(output_dir, "smc.hdf5"))
    conn = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')

    # 2 types data, saved in dict:
    #   - 'counts' : avg. nr. of bssids, essids and operators observed per session, at each cell
    #   - 'aps' : nr. of distinct bssids per essid, for all cells

    tables = {
        'counts' : {
            'name' : ('/esses/total/counts/%s/%s' % (cell_size, int(abs(threshold)))), 
            'query' : """SELECT cell_x, cell_y, avg(lat) AS lat, avg(lon) AS lon, avg(essid_cnt) AS essid_cnt, avg(bssid_cnt) AS bssid_cnt, avg(operator_cnt) AS operator_cnt
            FROM(
                SELECT cell_x, cell_y, session_id, avg(lat) AS lat, avg(lon) AS lon, count(distinct essid) AS essid_cnt, count(distinct bssid) AS bssid_cnt, count(distinct operator) AS operator_cnt
                FROM original
                GROUP BY cell_x, cell_y, session_id
                ) AS T
            GROUP BY cell_x, cell_y""",
            'columns' : ['essid_cnt', 'bssid_cnt', 'operator_cnt']},

        'aps' : {
            'name' : ('/esses/total/aps/%s/%s' % (cell_size, int(abs(threshold)))), 
            'query' : """SELECT bssid_cnt, count(essid) as essid_cnt
            FROM(
                SELECT essid, count(distinct bssid) AS bssid_cnt
                FROM original 
                GROUP BY essid
                ) AS T
            GROUP BY bssid_cnt""",
            'columns' : []}
    }

    data = defaultdict(pd.DataFrame)
    for table in tables:
        if tables[table]['name'] not in database.keys():
            start_time = timeit.default_timer()
            data[table] = pd.read_sql(tables[table]['query'],con = conn)
            print("%s::extract_esses() : [INFO] data retrieved (%.3f sec)" % (sys.argv[0], timeit.default_timer() - start_time))
            parsing.utils.to_hdf5(data[table], tables[table]['name'], database)
        else:
            data[table] = database.select(tables[table]['name'])

    table = ('/esses/road/counts/%s/%s' % (cell_size, int(abs(threshold))))
    if table not in database.keys():
        intersection = get_road_data(input_dir, data['counts'], columns = tables['counts']['columns'])
        parsing.utils.to_hdf5(intersection[['cell_x', 'cell_y'] + tables['counts']['columns']], table, database)
        map_dir = os.path.join(output_dir, "ess-cnt")
        if not os.path.isdir(map_dir):
            os.makedirs(map_dir)

        intersection.to_file(os.path.join(map_dir, ("%s-%s" % (cell_size, int(abs(threshold))))), driver = 'ESRI Shapefile')

def extract_session_nr(input_dir, cell_size = 20, threshold = -80):

    output_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    database = pd.HDFStore(os.path.join(output_dir, "smc.hdf5"))
    conn = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')

    table = ('/sessions/total/%s/%s' % (cell_size, int(abs(threshold))))
    if table not in database.keys():
        start_time = timeit.default_timer()
        data = pd.read_sql(
            """SELECT cell_x, cell_y, avg(lat) AS lat, avg(lon) AS lon, count(distinct cell_x, cell_y, session_id) AS session_cnt
            FROM original
            GROUP BY cell_x, cell_y""",
            con = conn)

        print("%s::extract_channels() : [INFO] data retrieved (%.3f sec)" % (sys.argv[0], timeit.default_timer() - start_time))
        parsing.utils.to_hdf5(data, table, database)

    else:
        data = database.select(table)

    table = ('/sessions/road/%s/%s' % (cell_size, int(abs(threshold))))
    if table not in database.keys():
        intersection = get_road_data(input_dir, data, columns = ['session_cnt'])
        parsing.utils.to_hdf5(intersection[['cell_x', 'cell_y'] + ['session_cnt']], table, database)

def extract_channels(input_dir, cell_size = 20, threshold = -80):

    output_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    database = pd.HDFStore(os.path.join(output_dir, "smc.hdf5"))
    conn = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')

    table = ('/channels/total/%s/%s' % (cell_size, int(abs(threshold))))
    if table not in database.keys():
        start_time = timeit.default_timer()
        data = pd.read_sql(
            """SELECT cell_x, cell_y, avg(lat) AS lat, avg(lon) AS lon, frequency, ap_cnt, count(distinct session_id) AS session_cnt
            FROM(
                SELECT cell_x, cell_y, avg(lat) AS lat, avg(lon) AS lon, session_id, frequency, count(distinct bssid, frequency) AS ap_cnt
                FROM original
                GROUP BY cell_x, cell_y, session_id, frequency
                ) AS T
            GROUP BY cell_x, cell_y, frequency, ap_cnt""",
            con = conn)

        print("%s::extract_channels() : [INFO] data retrieved (%.3f sec)" % (sys.argv[0], timeit.default_timer() - start_time))
        parsing.utils.to_hdf5(data, table, database)

    else:
        data = database.select(table)

    table = ('/channels/road/%s/%s' % (cell_size, int(abs(threshold))))
    if table not in database.keys():
        intersection = get_road_data(input_dir, data, columns = ['frequency', 'ap_cnt', 'session_cnt'])
        parsing.utils.to_hdf5(intersection[['cell_x', 'cell_y'] + ['frequency', 'ap_cnt', 'session_cnt']], table, database)

def extract_auth(input_dir, cell_size = 20, threshold = -80):

    output_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    database = pd.HDFStore(os.path.join(output_dir, "smc.hdf5"))
    conn = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')

    table = ('/auth/total/%s/%s' % (cell_size, int(abs(threshold))))
    if table not in database.keys():
        start_time = timeit.default_timer()
        data = pd.read_sql(
            """SELECT cell_x, cell_y, avg(lat) AS lat, avg(lon) AS lon, re_auth AS auth, ap_cnt, count(distinct session_id) AS session_cnt
            FROM(
                SELECT cell_x, cell_y, avg(lat) AS lat, avg(lon) AS lon, session_id, re_auth, count(distinct bssid, re_auth) AS ap_cnt
                FROM original
                GROUP BY cell_x, cell_y, session_id, re_auth
                ) AS T
            GROUP BY cell_x, cell_y, re_auth, ap_cnt""",
            con = conn)

        print("%s::extract_channels() : [INFO] data retrieved (%.3f sec)" % (sys.argv[0], timeit.default_timer() - start_time))
        parsing.utils.to_hdf5(data, table, database)

    else:
        data = database.select(table)

    table = ('/auth/road/%s/%s' % (cell_size, int(abs(threshold))))
    if table not in database.keys():
        intersection = get_road_data(input_dir, data, columns = ['auth', 'ap_cnt', 'session_cnt'])
        parsing.utils.to_hdf5(intersection[['cell_x', 'cell_y'] + ['auth', 'ap_cnt', 'session_cnt']], table, database)

def extract_bands(data, database):

    # if no data points in one of the bands, abort
    if data[data['band'] == 1].empty:
        return

    # find cells w/ 5.0 GHz data points
    data['cell'] = data['cell-x'].astype(str) + '.' + data['cell-y'].astype(str)
    cells = data[data['band'] == 1]['cell']

    # # FIXME: a cell size of 5.0 m will result in 2010 x 1335 ~ 3M cells
    # bands = data.groupby(['session_id', 'encode', 'cell-x', 'cell-y', 'band']).agg({'snr' : 'median', 'seconds' : 'count'}).reset_index(drop = False)
    # bands.rename(index = str, columns = {'seconds' : 'count'}, inplace = True)
    # bands['snr'] = bands['snr'].apply(analysis.metrics.custom_round)
    # bands['session_id'] = bands['session_id'].astype(int)
    # bands = bands[['session_id', 'encode', 'cell-x', 'cell-y', 'band', 'snr', 'count']].reset_index(drop = True)

    # print(bands)
    # parsing.utils.to_hdf5(bands, ('/bands/snr'), database)

    # FIXME: cells w/ 5.0 GHz data are so rare, that we can simply save the full rows
    raw = data[data['cell'].isin(cells)].reset_index(drop = True)[['seconds', 'session_id', 'encode', 'snr', 'auth', 'frequency', 'new_lat', 'new_lon', 'new_err', 'ds', 'acc_scan', 'band', 'cell-x', 'cell-y']]
    raw['session_id'] = raw['session_id'].astype(str).apply(lambda x : x.split(',')[0]).astype(int)
    raw['encode'] = raw['encode'].astype(str)
    print(raw)
    parsing.utils.to_hdf5(raw, ('/bands/raw'), database)
    
def extract_coverage(data, processed_data):

    # distances while under coverage, per block
    distances = data.groupby(['session_id', 'encode', 'band', 'time-block']).apply(calc_dist).reset_index(drop = True).fillna(0.0)
    distances = distances.groupby(['session_id', 'encode', 'band', 'time-block'])['dist'].sum().reset_index(drop = False).sort_values(by = ['session_id', 'encode', 'band', 'time-block'])

    # times, distance & speed while under coverage, per block
    aps = data.groupby(['session_id', 'encode', 'band', 'time-block'])['seconds'].apply(np.array).reset_index(drop = False).sort_values(by = ['session_id', 'encode', 'band', 'time-block'])
    aps['time'] = aps['seconds'].apply(lambda x : x[-1] - x[0])
    aps['dist'] = distances['dist']
    aps['speed'] = (aps['dist'] / aps['time'].astype(float)).fillna(0.0)
    aps['speed'] = aps['speed'].apply(analysis.metrics.custom_round)

    # - filter out low speeds (e.g., < 1.0 m/s)
    aps = aps[aps['speed'] > 1.0].reset_index(drop = True)

    if aps.empty:
        return

    for cat in ['time', 'speed']:
        processed_data[cat] = pd.concat([processed_data[cat], aps.groupby(['band', cat]).size().reset_index(drop = False, name = 'count')], ignore_index = True)
        processed_data[cat] = processed_data[cat].groupby(['band', cat]).sum().reset_index(drop = False)

def extract(input_dir, cell_size = 5.0):

    output_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    # processed data 
    processed_data = defaultdict(pd.DataFrame)

    # load .hdfs database
    database = pd.HDFStore(os.path.join(output_dir, "smc.hdf5"))
    # remove '/band' data from database
    if ('/bands/snr') in database.keys():
        database.remove('/bands/snr')
    if ('/bands/raw') in database.keys():
        database.remove('/bands/raw')

    # read .csv dataset by chunks (> 3GB file)
    filename = os.path.join(input_dir, "all_wf.grid.csv")
    chunksize = 2.5 * (10 ** 4)
    for chunk in pd.read_csv(filename, chunksize = chunksize):

        print("""%s: [INFO] handling %s sessions in chunk""" % (sys.argv[0], len(chunk['session_id'].unique())))

        # order by session id & timestamp
        chunk = chunk.sort_values(by = ['session_id', 'seconds']).reset_index(drop = True)

        # to speed up computation, filter out values which don't matter
        # - filter out low snrs
        chunk = chunk[chunk['snr'] > -75.0].reset_index(drop = True)
        # - filter out invalid freq. bands
        add_band(chunk)
        chunk = chunk[chunk['band'] >= 0].reset_index(drop = True)
        
        if chunk.empty:
            continue

        # - filter out consecutive time blocks with too few data points
        chunk['time-block'] = ((chunk['seconds'] - chunk['seconds'].shift(1)) > 1.0).astype(int).cumsum()
        # to make computation lighter, get rid of time blocks w/ less than n entries
        chunk = chunk.groupby(['session_id', 'encode', 'time-block']).apply(mark_size)
        chunk = chunk[chunk['block-size'] > 2].reset_index(drop = True)

        # abort if chunk is empty
        if chunk.empty:
            continue

        # add cell info
        add_cells(chunk, cell_size)

        extract_bands(chunk, database)
        extract_coverage(chunk, processed_data)

    # save on database
    for cat in ['time', 'speed']:
    
        db = ('/signal-quality/%s' % (cat))
        if db in database.keys():
            database.remove(db)

        parsing.utils.to_hdf5(processed_data[cat], db, database)
