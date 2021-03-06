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
#   - parsing
import analysis.smc.utils
#   - analysis.smc.roads
import analysis.smc.roads.selection
import analysis.smc.roads.utils
#   - hdfs utils
import utils.hdfs

# road ref points for xx calculation
ref_points = {
    57 : [41.158179, -8.630399], 
    960 : [41.157160, -8.624431],
    978 : [41.160477, -8.593205],
    67 : [41.148925, -8.599117],
    60 : [41.178685,-8.597872],
    1466 : [41.178685,-8.597872],
    834 : [41.150972, -8.593940],
    1524 : [41.161120, -8.598267]}

def data(name, input_dir, db_eng = None, db_name = 'smf'):

    if db_eng is None:
        db_str = ('mysql+mysqlconnector://root:xpto12x1@localhost/%s' % (db_name))
        db_eng = sqlalchemy.create_engine(db_str)

    # id, name, length of road
    road_id, name, length = analysis.smc.roads.utils.get_id(name, db_eng)
    # extract session data along road to .hdf5 file for convenience (if not available yet)
    database = utils.hdfs.get_db(input_dir, ('%s.hdf5' % (db_name)))
    database_keys = utils.hdfs.get_db_keys(input_dir, ('%s.hdf5' % (db_name)))
    
    db_name = ('/roads/%s/data' % (road_id))
    if db_name not in database_keys:

        # sessions w/ include cell
        query = ("""SELECT 
                    timestamp, 
                    session_id, rss, lat, lon, gps_error, scan_acc, scan_dist, in_road,
                    sessions.cell_id,
                    sessions.ap_id as ap_id, 
                    sessions.ess_id as ess_id,
                    sessions.operator_id as operator_id,
                    bssid, frequency, band, auth_orig, auth_custom, ap.is_public as is_public,
                    essid_hash
                FROM(
                    SELECT road_id, cell_id 
                    FROM roads_cells 
                    WHERE road_id = %d
                ) AS t1
                INNER JOIN sessions
                    ON t1.cell_id = sessions.cell_id
                INNER JOIN ap
                    ON sessions.ap_id = ap.id
                INNER JOIN ess
                    ON ap.ess_id = ess.id""" % (road_id))

        road_data = pd.read_sql(query, con = db_eng)
        road_data['bssid'] = road_data['bssid'].apply(lambda x : x.encode('utf-8'))
        road_data['essid_hash'] = road_data['essid_hash'].apply(lambda x : x.encode('utf-8'))
        # save road_data in .hdfs file
        utils.hdfs.to_hdfs(road_data, ('/roads/%s/data' % (road_id)), database)

    else:
        sys.stderr.write("""[INFO] %s already in database. skipping extraction.\n""" % (db_name))
        return

def coverage(name, input_dir, db_eng = None, db_name = 'smf'):

    if db_eng is None:
        db_str = ('mysql+mysqlconnector://root:xpto12x1@localhost/%s' % (db_name))
        db_eng = sqlalchemy.create_engine(db_str)

    # id, name, length of road
    road_id, name, length = analysis.smc.roads.utils.get_id(name, db_eng)
    database = utils.hdfs.get_db(input_dir, ('%s.hdf5' % (db_name)))
    database_keys = utils.hdfs.get_db_keys(input_dir, ('%s.hdf5' % (db_name)))

    db_name = ('/roads/%s/data' % (road_id))
    if db_name not in database_keys:
        analysis.smc.roads.extract.data(name, input_dir, db_eng)

    # (1) check if any of the dataframes to be created here is missing. if not, we stop here.
    session_db = ('/roads/%s/sessions' % (road_id))
    coverage_db = ('/roads/%s/coverage' % (road_id))
    rss_db = ('/roads/%s/rss' % (road_id))
    if (session_db in database_keys) and (coverage_db in database_keys) and (rss_db in database_keys):
        sys.stderr.write("""[INFO] %s dbs already in database. skipping data extraction.\n""" % (road_id))
        return

    road_data = database.select(db_name)

    # (2) filter out sessions which cross < 10 cells
    sessions = road_data.drop_duplicates(subset = ['session_id', 'cell_id']).groupby(['session_id'])['cell_id'].size().reset_index(drop = False)
    sessions = sessions[sessions['cell_id'] > 10.0].sort_values(by = ['session_id']).reset_index(drop = True)
    # (3) use session data from selected sessions only
    road_data = road_data[road_data['session_id'].isin(sessions['session_id'])].sort_values(by = ['session_id', 'timestamp']).reset_index(drop = True)
    # (4) calculate multiple session stats:
    #   - duration
    #   - median speed
    #   - dist traveled
    #   - diff in xx coords along road axis
    geo_stats = analysis.smc.roads.utils.get_geo_stats(road_data)
    # (5) fill in session stats:
    #   - median speed
    #   - cumulative distance traveled along road
    sessions['speed'] = geo_stats[['session_id', 'speed']].groupby(['session_id'])['speed'].median().reset_index(drop = False).sort_values(by = ['session_id'])['speed']
    sessions['dist'] = geo_stats[['session_id', 'dist']].groupby(['session_id'])['dist'].sum().reset_index(drop = False).sort_values(by = ['session_id'])['dist']

    # (6) add xx pos along road to road_data
    analysis.smc.roads.utils.add_xx(road_data, ref_points[road_id])
    road_data.loc[(road_data['session_id'] != road_data['session_id'].shift(1)), 'xx-diff'] = 0
    # (7) get how far ahead in the road the session got
    sessions['xx-diff'] = road_data[['session_id', 'xx-diff']].groupby(['session_id'])['xx-diff'].sum().reset_index(drop = False).sort_values(by = ['session_id'])['xx-diff']
    sessions['time'] = road_data[['timestamp', 'session_id']].groupby(['session_id'])['timestamp'].apply(list).reset_index(drop = False).sort_values(by = ['session_id'])['timestamp'].apply(lambda x : sorted(x)[-1] - sorted(x)[0])
    # (8) filter sessions:
    #   - median speed > 10 km/h
    #   - abs(xx-dif) > 250 m
    sessions = sessions[(sessions['speed'] > 10.0) & (sessions['xx-diff'].apply(lambda x : abs(x)) > 250.0)].reset_index(drop = True)
    # (9) add session info to database
    if (session_db not in database_keys):
        utils.hdfs.to_hdfs(sessions, session_db, database)

    # (10) filter out data from sessions w/ time >= 1000 seconds
    road_data = road_data[road_data['session_id'].isin(sessions['session_id'])].reset_index(drop = True)
    # (11) find rss vs. xx curves for a set of aps
    # (11.1) filter aps of interest:
    #   - rss < -30 dBm (-30 dBm is already too high to not be an error)
    #   - only use aps w/ show up in > x % of the sessions
    good_aps = road_data[(road_data['rss'] < -30.0)].groupby(['ap_id'])['session_id'].apply(set).reset_index(drop = False)
    good_aps['nr-sessions'] = good_aps['session_id'].apply(lambda x : len(x))
    good_aps = good_aps[good_aps['nr-sessions'] > good_aps['nr-sessions'].quantile(.75)].sort_values(by = ['nr-sessions']).reset_index(drop = True)
    good_aps = road_data[(road_data['rss'] < -30.0) & (road_data['ap_id'].isin(good_aps['ap_id']))].reset_index(drop = True)

    ap_data = pd.DataFrame()    
    # indexing per 'xx' pos to speed up merge    
    ap_data['xx'] = np.arange(good_aps['xx'].min(), good_aps['xx'].max() + 1.0, 1.0)
    ap_data.set_index('xx', inplace = True)
    for ap in set(good_aps['ap_id']):

        rss_data = good_aps[good_aps['ap_id'] == ap][['xx', 'rss']].groupby(['xx']).median().reset_index(drop = False)
        rss_data.rename(index = str, columns = {'rss' : ap}, inplace = True)
        # indexing to speed up merge
        rss_data.set_index('xx', inplace = True)

        ap_data = ap_data.join(rss_data, how = 'left')

    # add an 'xx' column to aps
    ap_data['xx'] = ap_data.index

    # extract road coverage per ap stats
    # i.e., for each ap, find: 
    #   - min and max xx coverage distances:
    #     i.e., the xx interval over which 90% of the rss > -80 dBm were collected
    if (coverage_db not in database_keys):

        coverage, smoothed_data = analysis.smc.roads.utils.get_coverage(ap_data, threshold = -75.0)

        # merge ap info w/ coverage:
        #   - ess id
        #   - operator id
        #   - is_public flag
        road_data['ap_id'] = road_data['ap_id'].astype(str)
        coverage = pd.merge(
            coverage, 
            road_data.drop_duplicates(subset = ['ap_id', 'operator_id', 'is_public', 'ess_id'])[['ap_id', 'operator_id', 'is_public', 'ess_id']], 
            on = ['ap_id'], how = 'left')

        # save coverage in database
        utils.hdfs.to_hdfs(coverage, coverage_db, database)

    # extract rss vs. distance stats
    if (rss_db not in database_keys):
        ap_data.columns = ap_data.columns.astype(str)
        utils.hdfs.to_hdfs(ap_data.reset_index(drop = True), rss_db, database)

def get_handoff_plan(road_id, input_dir, strategy, restriction):

    database = utils.hdfs.get_db(input_dir, ('%s.hdf5' % (db_name)))
    database_keys = utils.hdfs.get_db_keys(input_dir, ('%s.hdf5' % (db_name)))

    handoff_plan_db = ('/roads/%s/handoff/%s/%s/%s' % (road_id, strategy, restriction['open'], restriction['operator']))
    if (handoff_plan_db in database_keys):
        sys.stderr.write("""[INFO] %s already in database. skipping extraction.\n""" % (handoff_plan_db))
        return database.select(handoff_plan_db), database.select('%s/data' % (handoff_plan_db))

    # best-rss uses rss vs. xx data as input
    rss_db = ('/roads/%s/rss' % (road_id))
    if (rss_db not in database_keys):
        sys.stderr.write("""[ERROR] %s not in database. aborting.\n""" % (rss_db))
        return

    ap_data = database.select(rss_db)

    coverage_db = ('/roads/%s/coverage' % (road_id))
    if (coverage_db not in database_keys):
        sys.stderr.write("""[ERROR] %s not in database. aborting.\n""" % (coverage_db))
        return

    coverage = database.select(coverage_db)

    # filter aps according to handoff restrictions
    if restriction['open'] == 'open':
        coverage = coverage[coverage['is_public'] > 0].reset_index(drop = True)
    if restriction['operator'] != 'any':
        coverage = coverage[coverage['operator_id'] == restriction['operator']]

    ap_data = ap_data[['xx'] + list(set(coverage['ap_id'].tolist()) & set(ap_data.columns))].reset_index(drop = True)
    if not list(ap_data.columns).remove('xx'):
        return pd.DataFrame(), pd.DataFrame()

    if 'best-rss' in strategy:
        handoff_plan, ap_data = analysis.smc.roads.selection.best_rss(ap_data)

    elif 'schedule' in strategy:
        t = None
        if 'threshold' in restriction:
            t = restriction['threshold']

        handoff_plan, ap_data = analysis.smc.roads.selection.schedule(ap_data, threshold = t)

    #   - merge info about ess, operator and public flag
    handoff_plan = analysis.smc.roads.utils.add_ap_info(handoff_plan, coverage)

    # save handoff plan and ap data in hdfs database
    utils.hdfs.to_hdfs(handoff_plan, handoff_plan_db, database)
    utils.hdfs.to_hdfs(ap_data, ('%s/data' % (handoff_plan_db)), database)

    return handoff_plan, ap_data

# def clusters(db_eng = None, db_name = 'smf'):

#     if db_eng is None:
#         db_str = ('mysql+mysqlconnector://root:xpto12x1@localhost/%s' % (db_name))
#         db_eng = sqlalchemy.create_engine(db_str)

#     # extract data
#     query = """SELECT 
#         rs.road_id,
#         ap_cnt, ess_cnt, op_cnt, rss_cnt_avg, rss_cnt_std,
#         rss_1, rss_2, rss_3,
#         num_cells
#         FROM road_stats rs
#         INNER JOIN roads r
#         ON rs.road_id = r.id
#         INNER JOIN road_rss_stats rrs
#         ON r.id = rrs.road_id"""

#     data = pd.read_sql(query, con = db_eng)
#     data['rss_score'] = (data['rss_1'] + 10.0 * data['rss_2'] + 100.0 * data['rss_3'])
#     data['rss_score'] /= data['rss_score'].max()
#     data['ap_cnt'] /= data['ap_cnt'].max()
#     columns = list(data.columns)
#     columns.remove('road_id')
#     print(columns)
#     X = data[['ap_cnt', 'rss_score']].values
#     y_pred = KMeans(n_clusters = 4, random_state = 0).fit_predict(X)
#     print(y_pred)

#     plt.figure(figsize=(12, 12))
#     ax = plt.subplot(221)
#     ax.scatter(X[:, 0], X[:, 1], c = y_pred)
#     ax.set_xlabel('# aps')
#     ax.set_ylabel('rss_score')

#     # ax = plt.subplot(222)
#     # ax.scatter(X[:, 0], X[:, 1], c = y_pred)
#     # ax.set_xlabel('# aps')
#     # ax.set_ylabel('rss_score')

#     # ax = plt.subplot(223)
#     # ax.scatter(X[:, 0], X[:, 6], c = y_pred)
#     # ax.set_xlabel('# aps')
#     # ax.set_ylabel('# (-75 dBm < rss < -70 dBm)')

#     # ax = plt.subplot(224)
#     # ax.scatter(X[:, 0], X[:, 7], c = y_pred)
#     # ax.set_xlabel('# aps')
#     # ax.set_ylabel('# (rss > -70 dBm)')

#     plt.show()