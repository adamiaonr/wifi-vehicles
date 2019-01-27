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
# for parallel processing of sessions
import multiprocessing as mp 
import hashlib
# 
import urllib
import geopandas as gp
import shapely.geometry
import timeit

from random import randint
from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict

from prettytable import PrettyTable

import mapping.utils
import mapping.openstreetmap
import analysis.smc.utils
import analysis.smc.data

def to_csv(output_dir, cell_size = 20):

    queries = {
        'road_general_stats' : {
            'filename' : os.path.join(output_dir, ('processed/road_general_stats_%sm.csv' % (cell_size))), 
            'query' : ("""SELECT * 
            FROM road_general_stats r 
            INNER JOIN road_lengths l
            ON r.name_hash = l.name_hash""")}
    }

    conn = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')
    for query in queries:
        data = pd.read_sql(queries[query]['query'], con = conn)
        data.to_csv(queries[query]['filename'])

def extract_road_stats(output_dir):

    # list of queries to make on mysql database
    queries = {

        # 'road_general_stats' : {
        #     'name' : 'road_general_stats', 
        #     'query' : ("""CREATE TABLE road_general_stats
        #     SELECT road_id, count(distinct bssid) as bssid_cnt, count(distinct essid) as essid_cnt, count(distinct operator) as operator_cnt, count(distinct r.cell_id) as cell_cnt, avg(rss) as rss_mean, stddev(rss) as rss_stddev
        #     FROM roads_cells r
        #     INNER JOIN sessions s
        #     ON r.cell_id = s.cell_id
        #     WHERE in_road = 1 AND operator_known = 1
        #     GROUP BY road_id""")},

        'road_general_stats' : {
            'name' : 'road_general_stats', 
            'query' : ("""SELECT road_id
            FROM roads_cells r
            INNER JOIN sessions s
            ON r.cell_id = s.cell_id
            WHERE in_road = 1 AND operator_known = 1
            GROUP BY road_id""")},

        # 'road_cell_stats' : {
        #     'name' : 'road_cell_stats', 
        #     'query' : ("""SELECT road_id, cell_id, avg(bssid_cnt) as bssid_cnt_avg, stddev(bssid_cnt) as bssid_cnt_stddev, max(bssid_cnt) as bssid_cnt_max, min(bssid_cnt) as bssid_cnt_min, avg(essid_cnt) as essid_cnt_avg, stddev(essid_cnt) as essid_cnt_stddev, max(essid_cnt) as essid_cnt_max, min(essid_cnt) as essid_cnt_min, avg(operator_cnt) as operator_cnt_avg, stddev(operator_cnt) as operator_cnt_stddev, max(operator_cnt) as operator_cnt_max, min(operator_cnt) as operator_cnt_min, avg(rss_mean) as rss_mean, stddev(rss_mean) as rss_stddev, max(rss_max) as rss_max, min(rss_min) as rss_min
        #     INTO road_cells_stats
        #     FROM(
        #         SELECT road_id, cell_id, session_id, count(distinct bssid) as bssid_cnt, count(distinct essid) as essid_cnt, count(distinct operator) as operator_cnt, avg(rss) as rss_mean, max(rss) as rss_max, min(rss) as rss_min
        #         FROM roads_cells r
        #         INNER JOIN sessions s
        #         ON r.cell_id = s.cell_id
        #         WHERE in_road = 1 AND WHERE operator_known = 1
        #         GROUP BY road_id, cell_id, session_id
        #         ) as T
        #     GROUPBY road_id, cell_id
        #     """)},
    }

    # make 'raw' sql query, to be saved in another table
    analysis.smc.data.do_sql_query(queries)

    return 0

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()
    # options (self-explanatory)
    parser.add_argument(
        "--input-dir", 
         help = """dir w/ smc data""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save graphs & other output data""")

    args = parser.parse_args()

    if not args.input_dir:
        sys.stderr.write("""%s: [ERROR] must provide a dir w/ input files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] must provide an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    road_hash = mapping.openstreetmap.extract_roads(args.output_dir)
    road_cells_dir = mapping.openstreetmap.extract_road_cells(args.output_dir, road_hash)

    mapping.openstreetmap.create_roads_table(args.output_dir, road_hash)
    #extract_road_stats(args.output_dir)

    sys.exit(0)