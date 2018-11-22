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
# for parallel processing of sessions
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

import parsing.utils

import analysis.metrics
import analysis.trace
import analysis.gps
import analysis.ap_selection.rssi
import analysis.ap_selection.gps

import shapely.geometry

from random import randint

from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple

from prettytable import PrettyTable

from sklearn import linear_model

def handle_remove_dbs(input_dir, trace_nr, keys_to_remove):

    database = analysis.trace.get_db(input_dir, trace_nr)

    for k in keys_to_remove:
        if k in database.keys():
            database.remove(k)
            sys.stderr.write("""%s: [INFO] removed key %s from database\n""" % (sys.argv[0], k))

        else:
            sys.stderr.write("""%s: [INFO] key %s not in database\n""" % (sys.argv[0], k))

def handle_list_dbs(input_dir, trace_nr):
    db = analysis.trace.get_db(input_dir, trace_nr)
    sys.stderr.write("""%s: [INFO] keys in .hdfs database:\n""" % (sys.argv[0]))
    for key in db.keys():
        print('\t%s' % (key))

def handle_list_traces(input_dir, trace_nr):

    # print list of traces
    table = PrettyTable(list(trace_list.columns))
    for i, row in trace_list.iterrows():
        table.add_row([
            ('%s' % (row['trace-nr'])),
            ('%s' % (row['proto'])), 
            ('%d' % (row['channel'])), 
            ('%d' % (row['bw'])),
            ('%s' % (('%s Mbps' % row['bitrate']) if row['bitrate'] != '*' else row['bitrate']))
            ])
    print(table)

    # print info about the requested trace
    trace_info = analysis.trace.get_info(input_dir, trace_nr)

    if not trace_info.empty:
        table = PrettyTable(list(['mac', 'tcp', 'udp', 'tcp-gps', 'udp-gps']))
        for i, row in trace_info.iterrows():
            table.add_row([
                ('%s' % (row['mac'])),
                ('%s' % (int(row['tcp']))), 
                ('%d' % (int(row['udp']))), 
                ('%d' % (int(row['tcp-gps']))),
                ('%s' % (int(row['udp-gps'])))])

        print("%s: dataset stats :" % (sys.argv[0]))
        print(table)

    else:
        sys.stderr.write("""%s: [ERROR] trace info not available for trace %s\n""" % (sys.argv[0], trace_nr))

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--input-dir", 
         help = """dir w/ trace data""")

    parser.add_argument(
        "--list-traces", 
         help = """lists available traces""",
         action = 'store_true')

    parser.add_argument(
        "--list-dbs", 
         help = """lists dbs in .hdfs database""",
         action = 'store_true')

    parser.add_argument(
        "--trace-nr", 
         help = """nr of trace to analyze. e.g., '--trace-nr 009'""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save graphs & other output data""")

    parser.add_argument(
        "--remove-dbs", 
         help = """list of .hdfs keys to remove""")

    args = parser.parse_args()

    if not args.input_dir:
        sys.stderr.write("""%s: [ERROR] must provide a dir w/ input files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    trace_list = analysis.trace.get_list(args.input_dir)

    if trace_list.empty:
        sys.stderr.write("""%s: [ERROR] no trace information available\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)        

    if not args.trace_nr:
        sys.stderr.write("""%s: [ERROR] must provide a trace nr. to analyze\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)
    else:
        if int(args.trace_nr) not in list(trace_list['trace-nr']):
            sys.stderr.write("""%s: [ERROR] provided trace nr. doesn't exist\n""" % sys.argv[0]) 
            parser.print_help()
            sys.exit(1)

    if args.list_traces:
        handle_list_traces(args.input_dir, args.trace_nr)

    if args.list_dbs:
        handle_list_dbs(args.input_dir, args.trace_nr)
    
    trace = trace_list[trace_list['trace-nr'] == int(args.trace_nr)]
    trace_dir = os.path.join(args.input_dir, ("trace-%03d" % (int(args.trace_nr))))
    trace_db_file = os.path.join(trace_dir, "processed/database.hdf5")

    trace_output_dir = os.path.join(args.output_dir, ("trace-%03d" % (int(args.trace_nr))))
    if not os.path.isdir(trace_output_dir):
        os.makedirs(trace_output_dir)

    if args.remove_dbs:
        handle_remove_dbs(args.input_dir, args.trace_nr, args.remove_dbs.split(','))

    sys.exit(0)