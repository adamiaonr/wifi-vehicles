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
import sys
import sqlalchemy

from collections import defaultdict

# custom imports
#   - data transformations
import analysis.smc.database
#   - analysis 
import analysis.trace
#   - smc analysis
import analysis.smc.utils
#   - trace analysis
import analysis.trace.utils.gps
#   - hdfs utils
import utils.hdfs

def device_scans(
    input_dir, 
    limits = {'top-devices' : 5, 'min-session-samples' : 5}, 
    db_eng = None, db_name = 'smf'):

    if db_eng is None:
        db_str = ('mysql+mysqlconnector://root:xpto12x1@localhost/%s' % (db_name))
        db_eng = sqlalchemy.create_engine(db_str)

    database = utils.hdfs.get_db(input_dir, ('%s.hdf5' % (db_name)))
    database_keys = utils.hdfs.get_db_keys(input_dir, ('%s.hdf5' % (db_name)))
    print(database_keys)

    queries = {

        # FIXME: this query seems too inneficient...
        'device-scans' : {
            'query' : ("""SELECT 
                scan_intervals.hw_id, 
                scan_intervals.session_id, 
                scan_intervals.scan_interval
            FROM (
                SELECT 
                    s.hw_id, 
                    s.session_id, 
                    s.timestamp, 
                    IF( @last_session = s.session_id, s.timestamp - @last_tmstmp, 0.0) as scan_interval, 
                    @last_tmstmp := s.timestamp, 
                    @last_session := s.session_id 
                FROM (
                    SELECT hw_id, session_id, timestamp 
                    FROM sessions 
                    GROUP BY hw_id, session_id, timestamp 
                    ORDER BY hw_id, session_id, timestamp ASC 
                    ) AS s,
                ( SELECT @last_tmstmp := 0, @last_session := 0 ) vars
                GROUP BY s.hw_id, s.session_id, s.timestamp) AS scan_intervals
            INNER JOIN
            (SELECT 
                session_id 
            FROM (
                SELECT session_id, COUNT(DISTINCT timestamp) AS session_size 
                FROM sessions 
                GROUP BY session_id) AS t 
            WHERE session_size > %d) as session_sizes
            ON session_sizes.session_id = scan_intervals.session_id
            INNER JOIN
            (SELECT 
                hw_id, 
                count(distinct session_id) as session_cnt 
            FROM sessions 
            GROUP BY hw_id 
            ORDER BY session_cnt DESC LIMIT %d) AS top_devices
            ON top_devices.hw_id = scan_intervals.hw_id""" % (limits['min-session-samples'], limits['top-devices'])),
            'columns' : [],
            'filename' : ('/devices/scan-times/%d-%d' % (limits['min-session-samples'], limits['top-devices']))
        }
    }

    for query in queries:
        print(queries[query]['filename'])
        if queries[query]['filename'] in database_keys:
            sys.stderr.write("""[INFO] %s already in database. skipping extraction.\n""" % (queries[query]['filename']))
            continue

        analysis.smc.database.save_query(input_dir, query, db_eng = db_eng)

def signal_quality(input_dir, cell_size = 20, threshold = -80, in_road = 1):

    # list of queries to make on mysql database
    queries = {

        'rss' : {
            'name' : ('/signal-quality/rss/%s/%s' % (cell_size, int(abs(threshold)))), 
            'query' : ("""SELECT cell_x, cell_y, avg(lat) AS lat, avg(lon) AS lon, avg(rss) AS rss_mean, stddev(rss) AS rss_stddev
            FROM(
                SELECT cell_x, cell_y, avg(lat) AS lat, avg(lon) AS lon, session_id, avg(rss) AS rss
                FROM sessions
                WHERE in_road = %d
                GROUP BY cell_x, cell_y, session_id
                ) AS T
            GROUP BY cell_x, cell_y""" % (in_road)),
            'columns' : []},
    }

    analysis.smc.database.save_query(input_dir, queries, cell_size, threshold, in_road)

def operators(input_dir, cell_size = 20, threshold = -80, in_road = 1):

    # list of queries to make on mysql database
    queries = {

        'bssid_cnt' : {
            'name' : ('/operators/bssid_cnt/%s/%s' % (cell_size, int(abs(threshold)))), 
            'query' : ("""SELECT operator, operator_public, count(distinct bssid) as bssid_cnt
            FROM sessions
            WHERE in_road = %d
            GROUP BY operator, operator_public""" % (in_road)),
            'columns' : ['operator', 'operator_public', 'bssid_cnt']},

        'cell_coverage' : {
            'name' : ('/operators/cell_coverage/%s/%s' % (cell_size, int(abs(threshold)))), 
            'query' : ("""SELECT operator, operator_public, count(distinct cell_x, cell_y) as cell_cnt
            FROM sessions
            WHERE in_road = %d
            GROUP BY operator, operator_public""" % (in_road)),
            'columns' : ['operator', 'operator_public', 'cell_cnt']},

        'cell_coverage_all' : {
            'name' : ('/operators/cell_coverage_all/%s/%s' % (cell_size, int(abs(threshold)))), 
            'query' : ("""SELECT operator_public, count(distinct cell_x, cell_y) as cell_cnt
            FROM sessions
            WHERE operator_known = 1 AND in_road = %d 
            GROUP BY operator_public""" % (in_road)),
            'columns' : ['operator', 'operator_public', 'cell_cnt']},

        'session_cnt' : {
            'name' : ('/operators/session_cnt/%s/%s' % (cell_size, int(abs(threshold)))), 
            'query' : ("""SELECT operator_cnt, count(distinct session_id) as session_cnt
            FROM(
                SELECT cell_x, cell_y, session_id, count(distinct operator) AS operator_cnt
                FROM sessions
                WHERE operator_known = 1 AND in_road = %d
                GROUP BY cell_x, cell_y, session_id
                ) AS T
            GROUP BY operator_cnt""" % (in_road)),
            'columns' : ['operator_cnt', 'session_cnt']},

        'cell_bssid_cnt' : {
            'name' : ('/operators/cell_bssid_cnt/%s/%s' % (cell_size, int(abs(threshold)))), 
            'query' : ("""SELECT cell_x, cell_y, operator, operator_public, count(distinct bssid) as bssid_cnt
                FROM sessions
                WHERE in_road = %d
                GROUP BY cell_x, cell_y, operator, operator_public""" % (in_road)),
            'columns' : ['cell_x, cell_y, operator, operator_public', 'bssid_cnt']},
    }

    analysis.smc.database.save_query(input_dir, queries, cell_size, threshold, in_road)

def esses(input_dir, cell_size = 20, threshold = -80, db_eng = None):

    queries = {
        'xssid_cnt' : {
            'name' : ('/esses/xssid_cnt/%s/%s' % (cell_size, int(abs(threshold)))), 
            'query' : ("""SELECT cell_id, avg(lat) AS lat, avg(lon) AS lon, avg(essid_cnt) AS essid_cnt, avg(bssid_cnt) AS bssid_cnt
            FROM(
                SELECT cell_id, session_id, avg(lat) AS lat, avg(lon) AS lon, count(distinct ess_id) AS essid_cnt, count(distinct ap_id) AS bssid_cnt
                FROM sessions
                GROUP BY cell_id, session_id
                ) AS T
            GROUP BY cell_id"""),
            'columns' : []},

        # 'essid_cnt' : {
        #     'name' : ('/esses/essid_cnt/%s/%s' % (cell_size, int(abs(threshold)))), 
        #     'query' : ("""SELECT bssid_cnt, count(essid) as essid_cnt
        #     FROM(
        #         SELECT essid, count(distinct bssid) AS bssid_cnt
        #         FROM sessions 
        #         WHERE in_road = %d
        #         GROUP BY essid
        #         ) AS T
        #     GROUP BY bssid_cnt""" % (in_road)),
        #     'columns' : []}
    }

    analysis.smc.database.save_query(input_dir, queries, db_eng = db_eng)

def session_nr(input_dir, cell_size = 20, threshold = -80, in_road = 1):

    queries = {
        'session_cnt' : {
            'name' : ('/sessions/session_cnt/%s/%s' % (cell_size, int(abs(threshold)))), 
            'query' : ("""SELECT cell_x, cell_y, avg(lat) AS lat, avg(lon) AS lon, count(distinct cell_x, cell_y, session_id) AS session_cnt
            FROM sessions
            WHERE in_road = %d
            GROUP BY cell_x, cell_y""" % (in_road)),
            'columns' : []}
    }

    analysis.smc.database.save_query(input_dir, queries, cell_size, threshold, in_road)

def channels(input_dir, cell_size = 20, threshold = -80, in_road = 1):

    queries = {
        'ap_cnt' : {
            'name' : ('/channels/ap_cnt/%s/%s' % (cell_size, int(abs(threshold)))), 
            'query' : ("""SELECT cell_x, cell_y, avg(lat) AS lat, avg(lon) AS lon, frequency, ap_cnt, count(distinct session_id) AS session_cnt
            FROM(
                SELECT cell_x, cell_y, avg(lat) AS lat, avg(lon) AS lon, session_id, frequency, count(distinct bssid, frequency) AS ap_cnt
                FROM sessions
                WHERE in_road = %d
                GROUP BY cell_x, cell_y, session_id, frequency
                ) AS T
            GROUP BY cell_x, cell_y, frequency, ap_cnt""" % (in_road)),
            'columns' : []}
    }

    analysis.smc.database.save_query(input_dir, queries, cell_size, threshold, in_road)

def auth(input_dir, cell_size = 20, threshold = -80, in_road = 1):

    queries = {
        'ap_cnt' : {
            'name' : ('/auth/ap_cnt/%s/%s' % (cell_size, int(abs(threshold)))), 
            'query' : ("""SELECT cell_x, cell_y, avg(lat) AS lat, avg(lon) AS lon, re_auth AS auth, ap_cnt, count(distinct session_id) AS session_cnt
            FROM(
                SELECT cell_x, cell_y, avg(lat) AS lat, avg(lon) AS lon, session_id, re_auth, count(distinct bssid, re_auth) AS ap_cnt
                FROM sessions
                WHERE in_road = %d
                GROUP BY cell_x, cell_y, session_id, re_auth
                ) AS T
            GROUP BY cell_x, cell_y, re_auth, ap_cnt""" % (in_road)),
            'columns' : []}
    }

    analysis.smc.database.save_query(input_dir, queries, cell_size, threshold, in_road)

def bands(data, database):

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
    # utils.hdfs.to_hdfs(bands, ('/bands/snr'), database)

    # FIXME: cells w/ 5.0 GHz data are so rare, that we can simply save the full rows
    raw = data[data['cell'].isin(cells)].reset_index(drop = True)[['seconds', 'session_id', 'encode', 'snr', 'auth', 'frequency', 'new_lat', 'new_lon', 'new_err', 'ds', 'acc_scan', 'band', 'cell-x', 'cell-y']]
    raw['session_id'] = raw['session_id'].astype(str).apply(lambda x : x.split(',')[0]).astype(int)
    raw['encode'] = raw['encode'].astype(str)
    utils.hdfs.to_hdfs(raw, ('/bands/raw'), database)
    
def _contact(data, processed_data):

    # distances while under coverage, per block
    distances = data.groupby(['session_id', 'encode', 'band', 'time-block']).apply(analysis.smc.utils.calc_dist).reset_index(drop = True).fillna(0.0)
    distances = distances.groupby(['session_id', 'encode', 'band', 'time-block'])['dist'].sum().reset_index(drop = False).sort_values(by = ['session_id', 'encode', 'band', 'time-block'])
    # times, distance & speed while under coverage, per block
    aps = data.groupby(['session_id', 'encode', 'band', 'time-block'])['seconds'].apply(np.array).reset_index(drop = False).sort_values(by = ['session_id', 'encode', 'band', 'time-block'])
    aps['time'] = aps['seconds'].apply(lambda x : x[-1] - x[0])
    aps['distance'] = distances['dist']
    aps['speed'] = (aps['distance'] / aps['time'].astype(float)).fillna(0.0)
    aps['speed'] = aps['speed'].apply(analysis.trace.utils.metrics.custom_round)

    # - filter out low speeds (e.g., < 1.0 m/s)
    aps = aps[aps['speed'] > 1.0].reset_index(drop = True)

    if aps.empty:
        return

    for cat in ['time', 'speed', 'distance']:
        processed_data[cat] = pd.concat([processed_data[cat], aps.groupby(['band', cat]).size().reset_index(drop = False, name = 'count')], ignore_index = True)
        processed_data[cat] = processed_data[cat].groupby(['band', cat]).sum().reset_index(drop = False)

def contact(input_dir, cell_size = 20.0, threshold = -80.0, in_road = 1):

    output_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    # load .hdfs database
    database = pd.HDFStore(os.path.join(output_dir, "smc.hdf5"))

    to_extract = ['time', 'speed', 'distance']
    for cat in to_extract:    
        db = ('/contact/%s/%s/%s' % (cat, cell_size, int(abs(threshold))))
        if db in database.keys():
            to_extract.remove(cat)

    if not to_extract:
        return

    # read .csv dataset by chunks (> 3GB file)
    filename = os.path.join(input_dir, "all_wf.grid.csv")
    chunksize = 2.5 * (10 ** 4)
    processed_data = defaultdict(pd.DataFrame)
    for chunk in pd.read_csv(filename, chunksize = chunksize):

        print("""%s: [INFO] handling %s sessions in chunk""" % (sys.argv[0], len(chunk['session_id'].unique())))

        # order by session id & timestamp
        chunk = chunk.sort_values(by = ['session_id', 'seconds']).reset_index(drop = True)
        # to speed up computation, filter out values which don't matter
        # - filter out low snrs
        chunk = chunk[chunk['snr'] > threshold].reset_index(drop = True)
        # - filter out invalid freq. bands
        analysis.smc.utils.add_band(chunk)
        chunk = chunk[chunk['band'] >= 0].reset_index(drop = True)
        
        if chunk.empty:
            continue

        # - filter out consecutive time blocks with too few data points
        chunk['time-block'] = ((chunk['seconds'] - chunk['seconds'].shift(1)) > 1.0).astype(int).cumsum()
        # to make computation lighter, get rid of time blocks w/ less than n entries
        chunk = chunk.groupby(['session_id', 'encode', 'time-block']).apply(analysis.smc.utils.mark_size)
        chunk = chunk[chunk['block-size'] > 2].reset_index(drop = True)

        # abort if chunk is empty
        if chunk.empty:
            continue

        # add cell info
        analysis.trace.utils.gps.add_cells(chunk, cell_size)

        # extract_bands(chunk, database)
        _contact(chunk, processed_data)

    # save on database
    for cat in to_extract:
        db = ('/contact/%s/%s/%s' % (cat, cell_size, int(abs(threshold))))
        if db not in database.keys():
            utils.hdfs.to_hdfs(processed_data[cat], db, database)
