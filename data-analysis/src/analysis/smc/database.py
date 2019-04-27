# analysis.smc.database.py : smc analysis database interface
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
import glob
import hashlib
import timeit
import sqlalchemy
import json

# custom imports
#   - analysis 
import analysis.trace
#   - smc analysis
import analysis.smc.utils
#   - trace analysis
import analysis.trace.utils.gps
#   - hdfs utils
import utils.hdfs

# gps coords for a 'central' pin on porto, portugal
LAT  = 41.163158
LON = -8.6127137
# north, south, west, east limits of map, in terms of geo coordinates
LATN = LAT + 0.03
LATS = LAT - 0.03
LONE = LON + 0.06
LONW = LON - 0.06

CELL_SIZE = 20.0

def save_query(input_dir, query, db_eng = None, db_name = 'smf'):

    if db_eng is None:
        db_str = ('mysql+mysqlconnector://root:xpto12x1@localhost/%s' % (db_name))
        db_eng = sqlalchemy.create_engine(db_str)

    output_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    database = utils.hdfs.get_db(input_dir, ('%s.hdf5' % (db_name)))
    database_keys = utils.hdfs.get_db_keys(input_dir, ('%s.hdf5' % (db_name)))
    if query['filename'] not in database_keys:
        start_time = timeit.default_timer()
        data = pd.read_sql(query['query'], con = db_eng)
        print("%s::save_query() : [INFO] sql query took %.3f sec" % (sys.argv[0], timeit.default_timer() - start_time))
        utils.hdfs.to_hdfs(data, query['filename'], database)

def exec_query(queries, db_eng = None, db_name = 'smf'):

    if not db_eng:
        db_str = ('mysql+mysqlconnector://root:xpto12x1@localhost/%s' % (db_name))
        db_eng = sqlalchemy.create_engine(db_str)

    for query in queries:
        start_time = timeit.default_timer()
        db_eng.execute(queries[query]['query'].strip())
        print("%s::exec_query() : [INFO] sql query took %.3f sec" % (sys.argv[0], timeit.default_timer() - start_time))

def to_csv(queries, db_eng = None, db_name = 'smf'):

    if not db_eng:
        db_str = ('mysql+mysqlconnector://root:xpto12x1@localhost/%s' % (db_name))
        db_eng = sqlalchemy.create_engine(db_str)

    for query in queries:
        start_time = timeit.default_timer()
        data = pd.read_sql(queries[query]['query'], con = db_eng)
        print("%s::to_csv() : [INFO] %s sql query took %.3f sec" % (sys.argv[0], queries[query]['filename'], timeit.default_timer() - start_time))

        if 'name' in data.columns:
            data['name'] = data['name'].apply(lambda x : x.encode('utf-8'))

        data.to_csv(queries[query]['filename'])

def table_exists(table_name, db_eng = None, db_name = 'smf'):
    
    if not db_eng:
        db_str = ('mysql+mysqlconnector://root:xpto12x1@localhost/%s' % (db_name))
        db_eng = sqlalchemy.create_engine(db_str)

    query = ("""SELECT COUNT(*) as cnt FROM %s""" % (table_name))
    data = pd.read_sql(query, con = db_eng)
    return (data.iloc[0]['cnt'] > 0)

def create_road_stats_table(db_eng = None, db_name = 'smf'):

    if not db_eng:
        db_str = ('mysql+mysqlconnector://root:xpto12x1@localhost/%s' % (db_name))
        db_eng = sqlalchemy.create_engine(db_str)

    # list of queries to make on mysql database
    queries = {

        'road_stats' : {
            'name' : 'road_stats',
            'query' : ("""CREATE TABLE IF NOT EXISTS road_stats
                SELECT road_id, 
                    avg(ap_cnt) as ap_cnt, 
                    avg(ess_cnt) as ess_cnt, 
                    avg(op_cnt) as op_cnt, 
                    avg(rss_cnt) as rss_cnt_avg, 
                    stddev(rss_cnt) as rss_cnt_std
                FROM(
                    SELECT road_id, 
                        session_id, 
                        count(distinct ap_id) as ap_cnt, 
                        count(distinct ess_id) as ess_cnt,
                        count(distinct operator_id) as op_cnt,
                        count(rss) as rss_cnt
                    FROM roads_cells r
                    INNER JOIN sessions s
                    ON r.cell_id = s.cell_id
                    WHERE in_road = 1
                    GROUP BY road_id, session_id
                    ) as T
                GROUP BY road_id""")},

        'road_operators' : {
            'name' : 'road_operators',
            'query' : ("""CREATE TABLE IF NOT EXISTS road_operators
            SELECT road_id, 
                COUNT(DISTINCT CASE WHEN operator_id = 1 THEN s.ap_id ELSE NULL END) as '1',
                COUNT(DISTINCT CASE WHEN operator_id = 2 THEN s.ap_id ELSE NULL END) as '2',
                COUNT(DISTINCT CASE WHEN operator_id = 3 THEN s.ap_id ELSE NULL END) as '3',
                COUNT(DISTINCT CASE WHEN operator_id = 4 THEN s.ap_id ELSE NULL END) as '4',
                COUNT(DISTINCT CASE WHEN operator_id = 5 THEN s.ap_id ELSE NULL END) as '5'
            FROM roads_cells r
            INNER JOIN sessions s
            ON r.cell_id = s.cell_id
            GROUP BY road_id""")},

        'road_cell_stats' : {
            'name' : 'road_cell_stats', 
            'query' : ("""CREATE TABLE IF NOT EXISTS road_cell_stats
            SELECT 
                road_id, 
                cell_id, 
                avg(ap_cnt) as ap_cnt, 
                avg(ess_cnt) as ess_cnt, 
                avg(op_cnt) as op_cnt,
                avg(rss_mean) as rss_mean, 
                stddev(rss_mean) as rss_stddev
            FROM(
                SELECT 
                    road_id, 
                    r.cell_id, 
                    session_id, 
                    count(distinct ap_id) as ap_cnt, 
                    count(distinct ess_id) as ess_cnt, 
                    count(DISTINCT CASE WHEN (operator_id > 0) THEN operator_id ELSE NULL END) as op_cnt, 
                    avg(rss) as rss_mean
                FROM roads_cells r
                INNER JOIN sessions s
                ON r.cell_id = s.cell_id
                WHERE in_road = 1 
                GROUP BY road_id, r.cell_id, session_id
                ) as T
            GROUP BY road_id, cell_id""")},

        'road_rss_stats' : {
            'name' : 'road_rss_stats',
            'query' : ("""CREATE TABLE IF NOT EXISTS road_rss_stats
            SELECT road_id,
                count(CASE WHEN (rss_mean < -75) then 1 else null end) as rss_1,
                count(CASE WHEN (rss_mean >= -75) AND (rss_mean < -70) then 1 else null end) as rss_2,
                count(CASE WHEN (rss_mean >= -70) then 1 else null end) as rss_3,
                count(distinct cell_id) as num_cells
            FROM road_cell_stats
            GROUP BY road_id""")},
    }

    # make 'raw' sql query, to be saved in another table
    analysis.smc.database.exec_query(queries)

    return 0

def create_operator_table(db_eng = None, db_name = 'smf'):

    if not db_eng:
        db_str = ('mysql+mysqlconnector://root:xpto12x1@localhost/%s' % (db_name))
        db_eng = sqlalchemy.create_engine(db_str)

    if analysis.smc.database.table_exists('operator', db_eng):
        print("%s::create_operator_table() : [INFO] operator table exists. skipping." % (sys.argv[0]))
        return

    operators = []
    operators.append({'id' : 0, 'name' : 'unknown'})
    for op in analysis.smc.utils.operators:
        operators.append({'id' : op, 'name' : analysis.smc.utils.operators[op]['name']})

    start = timeit.default_timer()
    for op in operators:
        query = ("""INSERT IGNORE INTO operator (id, name) VALUES (%d, "%s")""" % (op['id'], op['name']))
        db_eng.execute(query)

    print("%s::crate_operator_table() : [INFO] stored operator in sql database (%.3f sec)" % (sys.argv[0], timeit.default_timer() - start))

def insert_aps(data, db_eng = None, db_name = 'smf'):

    if not db_eng:
        db_str = ('mysql+mysqlconnector://root:xpto12x1@localhost/%s' % (db_name))
        db_eng = sqlalchemy.create_engine(db_str)

    start_time = timeit.default_timer()
    # use sql for memory efficient (albeit more time consuming...)
    data = data.drop_duplicates(subset = ['bssid', 'essid_hash']).reset_index(drop = True)
    data[['bssid', 'essid', 'essid_hash', 'is_public', 'operator_id']].to_sql(con = db_eng, name = 'aux', if_exists = 'replace', index = False)
    print("%s::insert_aps() : [INFO] sql aux : %.3f sec" % (sys.argv[0], timeit.default_timer() - start_time))

    #   - ess :
    #       - a) select rows from aux w/ essid_hash not in ess
    #       - b) insert rows from a) into ess
    start_time = timeit.default_timer()
    query = """INSERT IGNORE INTO ess (essid_hash, is_public, operator_id)
            SELECT DISTINCT essid_hash, is_public, operator_id
            FROM aux"""
    db_eng.execute(query)
    print("%s::insert_aps() : [INFO] sql ess : %.3f sec" % (sys.argv[0], timeit.default_timer() - start_time))

    #   - ap :
    #       - a) select rows from aux w/ bssid not in ap
    #       - b) inner join a) with ess on essid_hash to find ess_id for each ap
    #       - c) insert rows from b) into ap
    start_time = timeit.default_timer()
    # FIXME : the use of 'IGNORE' made it significantly faster
    query = """INSERT IGNORE INTO ap (bssid, is_public, ess_id, operator_id)
            SELECT bssid, t2.is_public as is_public, id as ess_id, t2.operator_id as operator_id
            FROM(
                SELECT DISTINCT bssid, essid_hash, is_public, operator_id
                FROM aux
            ) AS t2
            INNER JOIN (
                SELECT DISTINCT id, essid_hash
                FROM ess
                WHERE essid_hash IN (SELECT essid_hash FROM aux)
            ) AS t3
            ON t2.essid_hash = t3.essid_hash
            """
    db_eng.execute(query)
    print("%s::insert_aps() : [INFO] sql ap : %.3f sec" % (sys.argv[0], timeit.default_timer() - start_time))

    # get the <ap_id, ess_id> tuples based on bssids in aux
    start_time = timeit.default_timer()
    query = """SELECT DISTINCT id as ap_id, bssid, ess_id
            FROM ap
            WHERE bssid IN (SELECT bssid FROM aux)"""
    data = pd.read_sql(query, con = db_eng)

    print("%s::insert_aps() : [INFO] sql <ap_id, ess_id> : %.3f sec" % (sys.argv[0], timeit.default_timer() - start_time))
    return data

def insert_x(data, table = 'hw', db_eng = None, db_name = 'smf'):

    if not db_eng:
        db_str = ('mysql+mysqlconnector://root:xpto12x1@localhost/%s' % (db_name))
        db_eng = sqlalchemy.create_engine(db_str)

    start_time = timeit.default_timer()
    # use sql for memory efficient (albeit more time consuming...)
    columns = [('%s_descr' % (table)), ('%s_hash' % (table))]
    data = data.drop_duplicates(subset = columns).reset_index(drop = True)
    data.to_sql(con = db_eng, name = 'aux', if_exists = 'replace', index = False)
    print("%s::insert_x() : [INFO] sql aux : %.3f sec" % (sys.argv[0], timeit.default_timer() - start_time))

    start_time = timeit.default_timer()
    query = ("""INSERT IGNORE INTO %s (descr, hash)
            SELECT DISTINCT %s
            FROM aux""" % (table, ','.join(columns)))
    db_eng.execute(query)
    print("%s::insert_x() : [INFO] sql %s : %.3f sec" % (sys.argv[0], table, timeit.default_timer() - start_time))

    # get the <ap_id, ess_id> tuples based on bssids in aux
    start_time = timeit.default_timer()
    query = ("""SELECT DISTINCT id as %s, hash as %s
            FROM %s
            WHERE hash IN (SELECT %s FROM aux)""" % (('%s_id' % (table)), ('%s_hash' % (table)), table, ('%s_hash' % (table))))
    data = pd.read_sql(query, con = db_eng)

    print("%s::insert_x() : [INFO] sql <%s, %s> : %.3f sec" % (sys.argv[0], ('%s_id' % (table)), ('%s_hash' % (table)), timeit.default_timer() - start_time))
    return data

def insert_sessions(
    input_dir, 
    cell_size = 20,
    db_eng = None, db_name = 'smf'):

    output_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    # connect to smc mysql database
    # FIXME : shouldn't you create a db connection object w/ <engine>.connect()?
    # according to https://docs.sqlalchemy.org/en/latest/core/connections.html,
    # calling <engine>.execute() acquires a new Connection on its own.
    # creating a lot of connections per execute() may be inefficient.
    if not db_eng:
        db_str = ('mysql+mysqlconnector://root:xpto12x1@localhost/%s' % (db_name))
        db_eng = sqlalchemy.create_engine(db_str)

    if analysis.smc.database.table_exists('sessions', db_eng):
        print("%s::insert_sessions() : [INFO] sessions table exists. skipping." % (sys.argv[0]))
        return

    # load road data
    road_data = pd.read_sql('SELECT * FROM roads_cells', con = db_eng)
    # load operator data
    operator_data = pd.read_sql('SELECT * FROM operator', con = db_eng)
    # start adding data to the database

    for filename in sorted(glob.glob(os.path.join(input_dir, ('*.csv')))):
        # filename = os.path.join(input_dir, "all_wf.grid.csv")

        print(filename)

        chunksize = 10 ** 5
        for chunk in pd.read_csv(filename, chunksize = chunksize):

            start_time = timeit.default_timer()

            # to speed up computation, filter out values which don't matter
            # - filter out low RSS (i.e., only consider RSS > -80 dBm)
            chunk = chunk[chunk['snr'] > -80.0].reset_index(drop = True)
            if chunk.empty:
                continue

            #   - extract freq bands
            # FIXME: is this redundant?
            analysis.smc.utils.add_band(chunk)
            #   - filter unknown bands (we consider 2.4 GHz and 5.0 GHz)
            chunk = chunk[chunk['band'] >= 0].reset_index(drop = True)
            if chunk.empty:
                continue

            # rename columns
            chunk.rename(
                index = str, 
                columns = {
                    'utc_seconds' : 'timestamp', 
                    'session_id' : 'session_id', 
                    'mac_addr' : 'bssid', 
                    'snr' : 'rss', 
                    'auth' : 'auth_orig',
                    'hardware' : 'hw_descr', 'software' : 'sw_descr'}, inplace = True)

            # add cell ids
            analysis.trace.utils.gps.add_cells(chunk, cell_size, bbox = [LONW, LATS, LONE, LATN])

            chunk = chunk[[
                'timestamp', 'session_id', 'user_id', 'daily_user_id',
                'essid', 'bssid', 
                'rss', 'frequency', 'band', 'auth_orig', 'mode',
                'cell_id', 'lat', 'lon', 'alt', 'speed', 'track', 'nsats', 'acc',
                'hw_descr', 'sw_descr', 'extra']].reset_index(drop = True)

            # set column ['in_road'] = 1 if measurement made from a road
            chunk['in_road'] = 0
            chunk.loc[chunk['cell_id'].isin(road_data['cell_id']), 'in_road'] = 1
            # link essid w/ operator
            chunk['essid'] = chunk['essid'].fillna('unknown')
            chunk['operator_id'] = [ analysis.smc.utils.get_operator(s) for s in chunk['essid'].astype(str).tolist() ]
            # public or private essid?
            ops = [ [ row['essid'], row['operator_id'] ] for index, row in chunk[['essid', 'operator_id']].iterrows() ]
            chunk['is_public'] = [ analysis.smc.utils.is_public(op[0], op[1]) for op in ops ]

            # authentication re-branding
            chunk['auth_custom'] = 0
            chunk = analysis.smc.utils.rebrand_auth(chunk).reset_index(drop = True)

            # deal w/ str encodings
            chunk['bssid'] = chunk['bssid'].apply(lambda x : x.encode('utf-8'))
            # FIXME : due to an encoding error, we cannot 
            # chunk['essid'] = chunk['essid'].apply(lambda x : x.encode('utf-8'))
            chunk['essid_hash'] = chunk['essid'].apply(lambda x : hashlib.md5(str(x)).hexdigest())
            chunk['essid'] = chunk['essid_hash']

            # fill *_dscr nan w/ 'unknown'
            chunk[['hw_descr', 'sw_descr']] = chunk[['hw_descr', 'sw_descr']].fillna('unknown')
            # deal w/ str encodings
            chunk['hw_descr'] = chunk['hw_descr'].apply(lambda x : x.encode('utf-8'))
            chunk['sw_descr'] = chunk['sw_descr'].apply(lambda x : x.encode('utf-8'))
            # create hashes
            chunk['hw_hash'] = chunk['hw_descr'].apply(lambda x : hashlib.md5(str(x)).hexdigest())
            chunk['sw_hash'] = chunk['sw_descr'].apply(lambda x : hashlib.md5(str(x)).hexdigest())

            # extra capabilities processing
            chunk['extra'] = chunk['extra'].fillna('{}')
            chunk['extra'] = chunk['extra'].apply(lambda x : json.loads(x))
            chunk['channel_width'] = chunk['extra'].apply(lambda x : int(x['channelWidth']) if 'channelWidth' in x else 0).astype(int)
            chunk['extra'] = ''

            # data types
            for c in ['cell_id', 'timestamp', 
                'session_id', 'user_id', 'daily_user_id',
                'rss', 'frequency', 'band', 'in_road', 
                'auth_orig', 'auth_custom', 'operator_id', 'is_public', 'channel_width']:
                chunk[c] = [str(s).split(',')[0] for s in chunk[c]]
                chunk[c] = chunk[c].astype(int)

            for c in ['lat', 'lon', 'nsats', 'acc', 'alt', 'speed', 'track']:
                chunk[c] = chunk[c].astype(float)

            print("%s::insert_sessions() : [INFO] pre-processing time : %.3f sec" % (sys.argv[0], timeit.default_timer() - start_time))

            # sql inserts
            #   - aps
            #   - ess
            #   - ess_ap
            ap_ids = insert_aps(chunk, db_eng = db_eng)
            #   - hw 
            hw_ids = insert_x(chunk, table = 'hw', db_eng = db_eng)
            #   - sw
            sw_ids = insert_x(chunk, table = 'sw', db_eng = db_eng)
            #   - sessions
            st2 = timeit.default_timer()
            chunk = chunk[[
                'timestamp', 'session_id', 'user_id', 'daily_user_id',
                'bssid', 'operator_id', 
                'rss', 'frequency', 'auth_orig', 'auth_custom', 'mode',
                'lat', 'lon', 'alt', 'speed', 'track', 'nsats', 'acc',
                'hw_hash', 'sw_hash', 'cell_id', 'in_road', 'channel_width']].reset_index(drop = True)

            chunk = pd.merge(chunk, ap_ids, on = ['bssid'], how = 'left')
            chunk = pd.merge(chunk, hw_ids, on = ['hw_hash'], how = 'left')
            chunk = pd.merge(chunk, sw_ids, on = ['sw_hash'], how = 'left')

            chunk = chunk[[
                'timestamp', 'session_id', 'user_id', 'daily_user_id',
                'ap_id', 'ess_id', 'operator_id', 
                'rss', 'frequency', 'auth_orig', 'auth_custom', 'mode',
                'lat', 'lon', 'alt', 'speed', 'track', 'nsats', 'acc',
                'hw_id', 'sw_id', 'cell_id', 'in_road', 'channel_width']].reset_index(drop = True)

            chunk.to_sql(con = db_eng, name = 'sessions', if_exists = 'append', index = False)

            print("%s::insert_sessions() : [INFO] sql insert in sessions : %.3f sec (total : %.3f sec)" % (sys.argv[0], timeit.default_timer() - st2, timeit.default_timer() - start_time))
