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
import multiprocessing as mp 
import pdfkit
import MySQLdb as mysql
import sqlalchemy
import shapely.geometry
import geopandas as gp

from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict
from geopy.distance import geodesic
from shapely.geometry import Point

# custom imports
#   - analysis 
import analysis.trace
#   - smc analysis
import analysis.smc.utils

# gps coords for a 'central' pin on porto, portugal
LAT  = 41.163158
LON = -8.6127137
# north, south, west, east limits of map, in terms of geo coordinates
LATN = LAT + 0.03
LATS = LAT - 0.03
LONE = LON + 0.06
LONW = LON - 0.06

CELL_SIZE = 20.0

def save_query(input_dir, queries, db_eng = None):

    if db_eng is None:
        db_eng = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')

    output_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    database = pd.HDFStore(os.path.join(output_dir, "smc.hdf5"))

    for query in queries:
        if queries[query]['name'] not in database.keys():
            start_time = timeit.default_timer()
            data = pd.read_sql(queries[query]['query'], con = db_eng)
            print("%s::save_query() : [INFO] sql query took %.3f sec" % (sys.argv[0], timeit.default_timer() - start_time))
            analysis.smc.utils.to_hdf5(data, queries[query]['name'], database)

def do_sql_query(queries):
    engine = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')
    with engine.connect() as eng:
        for query in queries:
            start_time = timeit.default_timer()
            eng.execute(queries[query]['query'])
            print("%s::do_sql_query() : [INFO] sql query took %.3f sec" % (sys.argv[0], timeit.default_timer() - start_time))

def table_exists(table_name, db_eng = None):
    
    if not db_eng:
        db_eng = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')

    query = ("""SELECT COUNT(*) as cnt FROM %s""" % (table_name))
    data = pd.read_sql(query, con = db_eng)
    return (data.iloc[0]['cnt'] > 0)

def create_operator_table(db_eng = None):

    if db_eng is None:
        db_eng = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')

    if analysis.smc.database.table_exists('operator', db_eng):
        print("%s::create_operator_table() : [INFO] operator table exists. skipping." % (sys.argv[0]))
        return

    operators = []
    operators.append({'id' : 0, 'name' : 'unknown'})
    for op in analysis.smc.utils.operators:
        operators.append({'id' : op, 'name' : analysis.smc.utils.operators[op]['name']})

    operators = pd.DataFrame(operators).sort_values(by = ['id']).reset_index(drop = True)
    start = timeit.default_timer()
    
    try:
        operators.to_sql(con = db_eng, name = 'operator', if_exists = 'fail', index = False)
    except Exception:
        sys.stderr.write("""%s::create_cells_table() : [WARNING] %s table exists. skipping.\n""" % (sys.argv[0], 'operator'))

    print("%s::crate_operator_table() : [INFO] stored operator in sql database (%.3f sec)" % (sys.argv[0], timeit.default_timer() - start))

def insert_aps(data, db_eng = None):

    if db_eng is None:
        db_eng = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')

    start_time = timeit.default_timer()
    # use sql for memory efficient (albeit more time consuming...)
    data = data.drop_duplicates(subset = ['bssid', 'essid_hash']).reset_index(drop = True)
    data.to_sql(con = db_eng, name = 'aux', if_exists = 'replace', index = False)
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
    query = """INSERT IGNORE INTO ap (bssid, frequency, band, auth_orig, auth_custom, is_public, ess_id, operator_id)
            SELECT bssid, frequency, band, auth_orig, auth_custom, t2.is_public as is_public, id as ess_id, t2.operator_id as operator_id
            FROM(
                SELECT DISTINCT bssid, essid_hash, frequency, band, auth_orig, auth_custom, is_public, operator_id
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

def insert_sessions(
    input_dir, 
    cell_size = 20,
    db_eng = None):

    output_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    # connect to smc mysql database
    # FIXME : shouldn't you create a db connection object w/ <engine>.connect()?
    # according to https://docs.sqlalchemy.org/en/latest/core/connections.html,
    # calling <engine>.execute() acquires a new Connection on its own.
    # creating a lot of connections per execute() may be inefficient.
    if db_eng is None:
        db_eng = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')

    if analysis.smc.database.table_exists('sessions', db_eng):
        print("%s::insert_sessions() : [INFO] sessions table exists. skipping." % (sys.argv[0]))
        return

    # load road data
    road_data = pd.read_sql('SELECT * FROM roads_cells', con = eng)
    # load operator data
    operator_data = pd.read_sql('SELECT * FROM operator', con = eng)
    # start adding data to the database
    filename = os.path.join(input_dir, "all_wf.grid.csv")
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
                'seconds' : 'timestamp', 
                'session_id' : 'session_id', 
                'encode' : 'bssid', 
                'snr' : 'rss', 
                'auth' : 'auth_orig',
                'new_lat' : 'lat', 'new_lon' : 'lon', 'new_err' : 'gps_error', 
                'ds' : 'scan_dist', 'acc_scan' : 'scan_acc'}, inplace = True)

        # add cell ids
        # FIXME : this is wrong, since cell ids depend on cell size
        analysis.gps.add_cells(chunk, cell_size, bbox = [LONW, LATS, LONE, LATN])
        chunk = chunk[['timestamp', 'session_id', 'essid', 'bssid', 'rss', 'auth_orig', 'frequency', 'band', 'cell_id', 'lat', 'lon', 'gps_error', 'scan_dist', 'scan_acc']].reset_index(drop = True)
        # set column ['in_road'] = 1 if measurement made from a road
        chunk['in_road'] = 0
        chunk.loc[chunk['cell_id'].isin(road_data['cell_id']), 'in_road'] = 1
        # link essid w/ operator
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

        # data types
        for c in ['cell_id', 'timestamp', 'session_id', 'rss', 'frequency', 'band', 'in_road', 'auth_orig', 'auth_custom', 'operator_id', 'is_public']:
            chunk[c] = [str(s).split(',')[0] for s in chunk[c]]
            chunk[c] = chunk[c].astype(int)
        for c in ['lat', 'lon', 'gps_error', 'scan_acc', 'scan_dist']:
            chunk[c] = chunk[c].astype(float)

        print("%s::insert_sessions() : [INFO] pre-processing time : %.3f sec" % (sys.argv[0], timeit.default_timer() - start_time))

        # sql inserts
        #   - ess
        #   - ap
        #   - ap_ess
        ap_ids = insert_aps(chunk, db_eng = db_eng)
        #   - sessions
        st2 = timeit.default_timer()
        chunk = chunk[['timestamp', 'session_id', 'bssid', 'operator_id', 'rss', 'lat', 'lon', 'gps_error', 'scan_dist', 'scan_acc', 'cell_id', 'in_road']].reset_index(drop = True)
        chunk = pd.merge(chunk, ap_ids, on = ['bssid'], how = 'left')
        chunk[['timestamp', 'session_id', 'ap_id', 'ess_id', 'operator_id', 'rss', 'lat', 'lon', 'gps_error', 'scan_dist', 'scan_acc', 'cell_id', 'in_road']].to_sql(con = db_eng, name = 'sessions', if_exists = 'append', index = False)
        print("%s::insert_sessions() : [INFO] sql insert in sessions : %.3f sec (total : %.3f sec)" % (sys.argv[0], timeit.default_timer() - st2, timeit.default_timer() - start_time))
