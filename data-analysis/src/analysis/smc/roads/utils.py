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

def get_id(name, db_eng = None):

    if db_eng is None:
        db_eng = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')

    # select id, name and length from roads table
    query = ("""SELECT id, name, length FROM roads WHERE name = '%s'""" % (name))
    road = pd.read_sql(query, con = db_eng)
    return road.iloc[0]['id'], road.iloc[0]['name'], road.iloc[0]['length']

def print_info(name, input_dir, db_eng = None):

    if db_eng is None:
        db_eng = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')

    road_id, name, length = analysis.smc.roads.utils.get_id(name, db_eng)
    print("road info:")
    print("\tname : %s, id : %d, length : %s" % (name, road_id, length))

    # session info
    database = analysis.smc.utils.get_db(input_dir)
    session_db = ('/roads/%s/sessions' % (road_id))
    print("\tsessions:")
    data = database.select(session_db)
    data['xx-diff'] = data['xx-diff'].apply(lambda x : abs(x))
    print(data[['cell_id', 'speed', 'xx-diff', 'time']].agg(['min', 'mean', 'median', 'max']))

    print("\tap info:")
    ap_db = ('/roads/%s/rss-vs-distance' % (road_id))
    if (ap_db not in database.keys()):
        sys.stderr.write("""[ERROR] %s not in database. aborting.\n""" % (ap_db))
        return
    data = database.select(ap_db)
    ccols = list(data.columns)
    ccols.remove('xx')
    print("\t\t# of aps : %d" % (len(ccols)))

def add_xx(data, ref_point):
    # FIXME: there must be a better way of doing this
    pos = [ [ row['lat'], row['lon'] ] for index, row in data[['lat', 'lon']].iterrows() ]
    data['xx'] = [ mapping.utils.gps_to_dist(ref_point[0], ref_point[1], p[0], p[1]) for p in pos ]
    data['xx'] = data['xx'].apply(lambda x : round(x))
    # find direction, duration & mean speed of sessions
    data['xx-diff'] = data['xx'] - data['xx'].shift(1)

def add_ap_info(data, coverage):
    data = pd.merge(data, coverage[['ap_id', 'ess_id', 'operator_id', 'is_public']], on = ['ap_id'], how = 'left')
    return data

def get_geo_stats(data): 
    # isolate rows w/ unique <timestamp, session_id, lat, lon> 
    geo = data.drop_duplicates(['timestamp', 'session_id', 'lat', 'lon'])[['timestamp', 'session_id', 'lat', 'lon']].reset_index(drop = True)
    # calc the following geo-related stats:
    #   - distance traveled in-between rows
    #   - time in-between rows
    #   - speed in-between rows
    geo['dist'] = mapping.utils.gps_to_dist(geo['lat'], geo['lon'], geo['lat'].shift(1), geo['lon'].shift(1))
    geo['time'] = (geo['timestamp'] - geo['timestamp'].shift(1)).astype(float)
    #   - make sure 'dist' and 'time' are unspecified in the 1st row of every new session_id
    #     we do this to avoid calculating stats with data from different sessions 
    geo.loc[(geo['session_id'] != geo['session_id'].shift(1)), 'dist'] = 0.0
    geo.loc[(geo['session_id'] != geo['session_id'].shift(1)), 'time'] = np.nan
    geo['speed'] = (geo['dist'] / geo['time']) * (3.6)

    return geo

def get_overlap_dist(road_id, input_dir, strategy, plan):
    hp = analysis.smc.roads.main.get_handoff_plan(road_id = road_id, input_dir = input_dir, strategy = strategy, plan = plan)
    overlap = pd.DataFrame()
    if not hp.empty:
        hp['overlap'] = hp['xx-max'].shift(1) - hp['xx-min']
        overlap = hp[['ap_id', 'range', 'overlap']]

    return overlap

def get_coverage(ap_data, threshold = -80.0):

    # interpolate SMALL gaps, fill LARGE gaps w/ -80 dBm and smooth rss data
    w = 10
    smoothed_data = ap_data.reset_index(drop = True)
    cols = list(ap_data.columns)
    cols.remove('xx')
    smoothed_data[cols] = smoothed_data[cols].interpolate(limit = 3)
    smoothed_data[cols] = smoothed_data[cols].fillna(-80.0)
    smoothed_data[cols] = smoothed_data[cols].rolling(w).mean()
    smoothed_data[cols] = smoothed_data[cols].astype(float)

    coverage = []
    for ap in cols:
        coverage.append({
            'ap_id' : ap, 
            'xx-min' : smoothed_data[['xx', ap]][smoothed_data[ap] > threshold].quantile(.05)['xx'], 
            'xx-max' : smoothed_data[['xx', ap]][smoothed_data[ap] > threshold].quantile(.95)['xx']})

    coverage = pd.DataFrame(coverage)
    # drop nan & duplicate ap_id
    coverage = coverage.dropna(subset = ['xx-min'])
    coverage['ap_id'] = coverage['ap_id'].astype(str)
    coverage = coverage.drop_duplicates(subset = ['ap_id'])
    # add ap coverage range (just for convenience)
    coverage['range'] = coverage['xx-max'] - coverage['xx-min']
    coverage = coverage[(coverage['range'] > 0.0)].reset_index(drop = True)

    return coverage, smoothed_data

def get_coverage_length(hp):

    coverage_length = 0.0
    if not hp.empty:
        prev_max = 0.0
        for i, row in hp.iterrows():
            if row['xx-min'] > prev_max:
                coverage_length += (row['xx-max'] - row['xx-min'])
            else:
                coverage_length += (row['xx-max'] - prev_max)
            prev_max = row['xx-max']

    return coverage_length

def sanitize_coverage(handoff_plan, coverage):

    for ap in handoff_plan['ap_id'].drop_duplicates():
        # find pre-determined coverage limits for selected aps
        # recall: the pre-determined coverage limits of an ap are the min and max xx road 
        # positions within which 90% of the rss measurements over -70 dBm are located
        xx_min = coverage[coverage['ap_id'] == ap]['xx-min'].min()
        xx_max = coverage[coverage['ap_id'] == ap]['xx-max'].min()
        # update handoff plan's xx-min and xx-max
        handoff_plan.loc[(handoff_plan['ap_id'] == ap), 'xx-min'] = max(xx_min, handoff_plan[(handoff_plan['ap_id'] == ap)].iloc[0]['xx-min'])
        handoff_plan.loc[(handoff_plan['ap_id'] == ap), 'xx-max'] = min(xx_max, handoff_plan[(handoff_plan['ap_id'] == ap)].iloc[0]['xx-max'])

    handoff_plan['range'] = handoff_plan['xx-max'] - handoff_plan['xx-min']

    print(handoff_plan)
    return handoff_plan
