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
import plot.smc.sessions

import parsing.utils

import analysis.metrics
import analysis.trace
import analysis.gps
import analysis.ap_selection.rssi
import analysis.ap_selection.gps

import analysis.smc.sessions
import analysis.smc.utils
import analysis.smc.data



import mapping.utils

import shapely.geometry

from random import randint

from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple

from prettytable import PrettyTable

from sklearn import linear_model

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

    # analysis.smc.data.to_sql(args.input_dir)

    # plot_contact(database, args.output_dir)
    # plot_bands(database, args.output_dir)

    analysis.smc.sessions.extract_contact(args.input_dir)    
    # analysis.smc.sessions.extract_signal_quality(args.input_dir)
    # analysis.smc.sessions.extract_esses(args.input_dir)
    # analysis.smc.sessions.extract_session_nr(args.input_dir)
    # analysis.smc.sessions.extract_channels(args.input_dir)
    # analysis.smc.sessions.extract_auth(args.input_dir)
    # analysis.smc.sessions.extract_operators(args.input_dir)

    # plot.smc.sessions.signal_quality(args.input_dir, args.output_dir)
    # plot.smc.sessions.esses(args.input_dir, args.output_dir)
    # plot.smc.sessions.channels(args.input_dir, args.output_dir)
    # plot.smc.sessions.auth(args.input_dir, args.output_dir)
    # plot.smc.sessions.operators(args.input_dir, args.output_dir)

    sys.exit(0)