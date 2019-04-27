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
import sys
import sqlalchemy

# custom imports
#   - analysis 
import analysis.trace
#   - smc analysis
import analysis.smc.utils
#   - mapping utils
import utils.mapping.utils
#   - hdfs utils
import utils.hdfs

def get_id(name, db_eng = None, db_name = 'smf'):

    if db_eng is None:
        db_str = ('mysql+mysqlconnector://root:xpto12x1@localhost/%s' % (db_name))
        db_eng = sqlalchemy.create_engine(db_str)

    # select id, name and length from roads table
    query = ("""SELECT id, name, length FROM roads WHERE name = '%s'""" % (name))
    road = pd.read_sql(query, con = db_eng)
    return road.iloc[0]['id'], road.iloc[0]['name'], road.iloc[0]['length']

def print_info(name, input_dir, db_eng = None, db_name = 'smf'):

    if db_eng is None:
        db_str = ('mysql+mysqlconnector://root:xpto12x1@localhost/%s' % (db_name))
        db_eng = sqlalchemy.create_engine(db_str)

    road_id, name, length = analysis.smc.roads.utils.get_id(name, db_eng)
    print("road info:")
    print("name : %s, id : %d, length : %s" % (name, road_id, length))

    # session info
    database = utils.hdfs.get_db(input_dir, ('%s.hdf5' % (db_name)))
    database_keys = utils.hdfs.get_db_keys(input_dir, ('%s.hdf5' % (db_name)))

    session_db = ('/roads/%s/sessions' % (road_id))
    print("sessions:")
    data = database.select(session_db)
    data['xx-diff'] = data['xx-diff'].apply(lambda x : abs(x))
    print(data[['cell_id', 'speed', 'xx-diff', 'time']].agg(['min', 'mean', 'median', 'max']))

    print("ap info:")
    ap_db = ('/roads/%s/coverage' % (road_id))
    if (ap_db not in database_keys):
        sys.stderr.write("""[ERROR] %s not in database. aborting.\n""" % (ap_db))
        return

    data = database.select(ap_db)
    print("# of aps : %d" % (len(data[['ap_id']].drop_duplicates())))

def add_xx(data, ref_point):
    # FIXME: there must be a better way of doing this
    pos = [ [ row['lat'], row['lon'] ] for index, row in data[['lat', 'lon']].iterrows() ]
    data['xx'] = [ utils.mapping.utils.gps_to_dist(ref_point[0], ref_point[1], p[0], p[1]) for p in pos ]
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
    geo['dist'] = utils.mapping.utils.gps_to_dist(geo['lat'], geo['lon'], geo['lat'].shift(1), geo['lon'].shift(1))
    geo['time'] = (geo['timestamp'] - geo['timestamp'].shift(1)).astype(float)
    #   - make sure 'dist' and 'time' are unspecified in the 1st row of every new session_id
    #     we do this to avoid calculating stats with data from different sessions 
    geo.loc[(geo['session_id'] != geo['session_id'].shift(1)), 'dist'] = 0.0
    geo.loc[(geo['session_id'] != geo['session_id'].shift(1)), 'time'] = np.nan
    geo['speed'] = (geo['dist'] / geo['time']) * (3.6)

    return geo

def get_overlap(road_id, input_dir, db_name = 'smf'):
    
    database = utils.hdfs.get_db(input_dir, ('%s.hdf5' % (db_name)))
    database_keys = utils.hdfs.get_db_keys(input_dir, ('%s.hdf5' % (db_name)))
    coverage_db = ('/roads/%s/coverage' % (road_id))
    if (coverage_db not in database_keys):
        sys.stderr.write("""[ERROR] %s not in database. aborting.\n""" % (coverage_db))
        return

    coverage = database.select(coverage_db)
    coverage = coverage.sort_values(by = ['xx-min', 'xx-max'], ascending = [True, True])

    overlap = pd.DataFrame()
    if not coverage.empty:
        coverage['overlap'] = coverage['xx-max'].shift(1) - coverage['xx-min']
        overlap = coverage[['ap_id', 'range', 'overlap']]

    return overlap

def get_coverage(ap_data, threshold = -80.0):

    ap_data.columns = ap_data.columns.astype(str)

    # interpolate SMALL gaps, fill LARGE gaps w/ -80 dBm and smooth rss data
    w = 20
    smoothed_data = ap_data.reset_index(drop = True)
    cols = list(ap_data.columns)
    cols.remove('xx')
    smoothed_data[cols] = smoothed_data[cols].interpolate(limit = 3)
    smoothed_data[cols] = smoothed_data[cols].fillna(-80.0)
    smoothed_data[cols] = smoothed_data[cols].rolling(w).mean()
    smoothed_data[cols] = smoothed_data[cols].astype(float)

    coverage = []
    for ap in cols:
        
        # find contiguous segments of road in which ap rss > threshold
        rss = smoothed_data[['xx', ap]][smoothed_data[ap] > threshold].reset_index(drop = True)
        rss['block'] = ((rss['xx'] - rss['xx'].shift(1) > 1.0)).astype(int).cumsum()
        rss = rss.groupby(['block']).agg({'xx' : ['min', 'max'], ap : ['mean']}).reset_index(drop = True)
        rss.columns = list(map(''.join, rss.columns.values))
        rss.rename(index = str, columns = {'xxmax' : 'xx-max', 'xxmin' : 'xx-min', ('%smean' % (ap)) : 'mean'}, inplace = True)

        for i, row in rss.iterrows(): 
            coverage.append({
                'ap_id' : ap, 
                'xx-min' : row['xx-min'], 
                'xx-max' : row['xx-max'],
                'mean' : row['mean']})

    coverage = pd.DataFrame(coverage)
    # # drop nan & duplicate ap_id
    # coverage = coverage.dropna(subset = ['xx-min'])
    # coverage['ap_id'] = coverage['ap_id'].astype(str)
    # coverage = coverage.drop_duplicates(subset = ['ap_id'])
    # add ap coverage range (just for convenience)
    coverage['range'] = coverage['xx-max'] - coverage['xx-min']
    coverage = coverage[(coverage['range'] > 0.0)].reset_index(drop = True)

    return coverage, smoothed_data

def get_coverage_length(handoff_plan): 

    coverage_length = 0.0
    if not handoff_plan.empty:

        # we can use the handoff plan directly
        prev_max = 0.0
        for i, row in handoff_plan.iterrows():

                if row['xx-min'] > prev_max:
                    coverage_length += (row['xx-max'] - row['xx-min'])
                else:
                    coverage_length += (row['xx-max'] - prev_max)

                prev_max = row['xx-max']

    return coverage_length
