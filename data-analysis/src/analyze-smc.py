import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import os
import re
import argparse
import sys
import glob
import math
import gmplot
import time
import timeit
import subprocess
import csv
import multiprocessing as mp 
import hashlib
import datetime
import json
import mapping.utils
import mapping.openstreetmap
import geopandas as gp
import plot.utils
import plot.trace
import plot.ap_selection
import plot.gps
import plot.smc.sessions
import plot.smc.roads
import parsing.utils
import analysis.metrics
import analysis.trace
import analysis.gps
import analysis.ap_selection.rssi
import analysis.ap_selection.gps
import analysis.smc.sessions
import analysis.smc.utils
import analysis.smc.database
import mapping.utils
import shapely.geometry
# for MySQL & pandas
import MySQLdb as mysql
import sqlalchemy

import analysis.smc.roads.main

from random import randint
from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple
from prettytable import PrettyTable
from sklearn import linear_model

# gps coords for a 'central' pin on porto, portugal
LAT  = 41.163158
LON = -8.6127137
# north, south, west, east limits of map, in terms of geo coordinates
LATN = LAT + 0.03
LATS = LAT - 0.03
LONE = LON + 0.06
LONW = LON - 0.06

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--input-dir", 
         help = """dir w/ smc data""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save processed data""")

    parser.add_argument(
        "--graph-dir", 
         help = """dir to save graphs""")

    parser.add_argument(
        "--populate", 
         help = """populates sql tables w/ smc data""",
         action = 'store_true')

    parser.add_argument(
        "--list-dbs", 
         help = """lists dbs in .hdfs database""",
         action = 'store_true')

    parser.add_argument(
        "--remove-dbs", 
         help = """list of .hdfs keys to remove, separated by ','.
                e.g. --remove-dbs '/db1, /db2'""")

    parser.add_argument(
        "--analyze-roads", 
         help = """list of road names to analyze, separated by ','. 
                e.g.: --analyze-roads 'Rua da Boavista,Avenida da Boavista'""") 

    parser.add_argument(
        "--analyze-sessions", 
         help = """high-level smc dataset analysis""",
                action = 'store_true') 

    args = parser.parse_args()

    if not args.input_dir:
        sys.stderr.write("""%s: [ERROR] must provide a dir w/ input files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] must provide an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.graph_dir:
        sys.stderr.write("""%s: [ERROR] must provide a graph dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if args.list_dbs:
        database = analysis.smc.utils.get_db(args.input_dir)
        sys.stderr.write("""%s: [INFO] keys in .hdfs database:\n""" % (sys.argv[0]))
        for key in database.keys():
            print('\t%s' % (key))

    if args.remove_dbs:
        database = analysis.smc.utils.get_db(args.input_dir)
        for db in args.remove_dbs.split(','):
            if db in database.keys():
                database.remove(db)
                sys.stderr.write("""%s: [INFO] removed db %s\n""" % (sys.argv[0], db))
            else:
                sys.stderr.write("""%s: [INFO] db %s not in database\n""" % (sys.argv[0], db))

    db_eng = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')

    if args.populate:

        # fill roads & cells tables
        bbox = [LONW, LATS, LONE, LATN]
        osm_tags = ['highway=motorway', 'highway=trunk', 'highway=primary', 'highway=secondary', 'highway=tertiary', 'highway=residential']
        mapping.openstreetmap.create_roads_table(args.output_dir, bbox, osm_tags, db_eng = db_eng)
        mapping.openstreetmap.create_roads_cells_table(args.output_dir, bbox, osm_tags, db_eng = db_eng)
        # fill operator table
        analysis.smc.database.create_operator_table(db_eng = db_eng)
        # fill sessions table
        analysis.smc.database.insert_sessions(args.input_dir, db_eng = db_eng)

    if args.analyze_roads:

        roads = args.analyze_roads.split(',')
        # for road in roads:
        #     # analysis.smc.roads.print_info(name = road, input_dir = args.input_dir, db_eng = db_eng)
        #     analysis.smc.roads.main.extract_coverage_data(name = road, input_dir = args.input_dir, db_eng = db_eng)
        #     # analysis.smc.roads.handoff(
        #     #     road_id = road_id,
        #     #     strategy = 'best-rss',
        #     #     plan = {'type' : 'any', 'operator' : 'any', 'label' : 'any'},
        #     #     input_dir = args.input_dir, 
        #     #     db_eng = db_eng)

        # plot.smc.roads.handoff(args.input_dir, args.graph_dir, selection_strategy = 'greedy')
        # plot.smc.roads.coverage_blocks(args.input_dir, args.graph_dir, selection_strategy = 'best-rss')
        # plot.smc.roads.coverage(args.input_dir, args.graph_dir, strategy = 'greedy')
        # plot.smc.roads.signal_quality(args.input_dir, args.graph_dir)
        # plot.smc.roads.map(args.input_dir, args.graph_dir)
        plot.smc.roads.rss(args.input_dir, args.graph_dir, 
            road_id = 960,
            strategy = 'greedy', 
            plan = {'type' : 'any', 'operator' : 'any', 'label' : 'any'})

    if args.analyze_sessions:

        # plot_contact(database, args.output_dir)
        # plot_bands(database, args.output_dir)

        # analysis.smc.sessions.extract_contact(args.input_dir)
        # analysis.smc.sessions.extract_signal_quality(args.input_dir)
        # analysis.smc.sessions.extract_esses(args.input_dir, db_eng = db_eng)
        # analysis.smc.sessions.extract_session_nr(args.input_dir)
        # analysis.smc.sessions.extract_channels(args.input_dir)
        # analysis.smc.sessions.extract_auth(args.input_dir)
        # analysis.smc.sessions.extract_operators(args.input_dir)

        # plot.smc.sessions.signal_quality(args.input_dir, args.graph_dir)
        # plot.smc.sessions.esses(args.input_dir, args.graph_dir, draw_map = True)
        plot.smc.sessions.channels(args.input_dir, args.graph_dir)
        # plot.smc.sessions.auth(args.input_dir, args.graph_dir)
        # plot.smc.sessions.operators(args.input_dir, args.graph_dir)

    sys.exit(0)