import pandas as pd
import numpy as np
import os
import csv
import json
import argparse
import subprocess
import sys
import glob
import math
import time
import hashlib
import signal

from random import randint
from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple

def signal_handler(signal, frame):
    global stop_loop
    stop_loop = True

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--input-dir", 
         help = """dir w/ bitrate algo data""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save .hdf5 files""")

    args = parser.parse_args()

    if not args.input_dir:
        sys.stderr.write("""%s: [ERROR] must provide an input dir w/ /sys/kernel/debug/ files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    columns = ['ht-mode', 'guard-interval', '#', 'best-rate', 
        'modulation', 'ix', 'airtime', 'max-thghpt', 
        'avg-thghpt', 'avg-prob', 'std-dev-prob',
        'last-retry', 'last-success', 'last-attempt',
        'sum-success', 'sum-attempts',
        'ideal', 'lookaround', 'avg-agg-frames-ampdu']

    report = pd.DataFrame(columns = sorted(['timestamp', 'station', 'phy', 'dev'] + columns))
    # # load .hdfs database
    # database = pd.HDFStore(os.path.join(args.output_dir, "bitrate-adapt.hdf5"))
    database = os.path.join(args.output_dir, "bitrate-adapt.csv")
    report.to_csv(database)

    # keep iperfing till a CTRL+C is caught...
    # register CTRL+C catcher
    signal.signal(signal.SIGINT, signal_handler)
    stop_loop = False
    while (stop_loop == False):

        for filename in glob.glob(os.path.join(args.input_dir, ('phy*/*/stations/*/rc_stats_csv'))):
            data = pd.read_csv(filename, names = columns)

            # fill missing columns
            data['timestamp'] = time.time()
            data['station'] = filename.split('/')[-2]
            data['dev'] = filename.split('/')[-4]
            data['phy'] = filename.split('/')[-5]

            # report = pd.concat([report, data], ignore_index = True, sort = True)
            # database.append('/bitrate-adapt/rc-stats', data, data_columns = data.columns, format = 'table')
            data.to_csv(database, mode = 'a', header = False, columns = sorted(data.columns))

        time.sleep(5.0)

    sys.exit(0)
