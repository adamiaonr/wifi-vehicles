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
import timeit
import geopandas as gp
import shapely.geometry

# for parallel processing of sessions
import multiprocessing as mp 

# for maps
import pdfkit

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

# global variable to keep hdfs keys in memory
# this is done to avoid excessive lookup time when calling db.keys()
# e.g., issue reported here : https://github.com/pandas-dev/pandas/issues/17593 
db_keys = []

def get_db(input_dir):
    db_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(db_dir):
        os.makedirs(db_dir)
    database = pd.HDFStore(os.path.join(db_dir, "smc.hdf5"))
    return database

def get_db_keys(input_dir):
    global db_keys
    if not db_keys:
        db_keys = get_db(input_dir).keys()
    return db_keys

def to_hdf5(data, metric, database):
    database.append(
        ('%s' % (metric)),
        data,
        data_columns = data.columns,
        format = 'table')

   	# update database keys everytime you save a table
    global db_keys
    db_keys = database.keys()

def remove_dbs(input_dir, dbs):

    database = get_db(args.input_dir)
    database_keys = get_db_keys(args.input_dir)

    for db in dbs:
        if db in database_keys:
            database.remove(db)
            sys.stderr.write("""%s: [INFO] removed db %s\n""" % (sys.argv[0], db))
        else:
            sys.stderr.write("""%s: [INFO] db %s not in database\n""" % (sys.argv[0], db))

    # update database keys everytime you remove tables
    global db_keys
    db_keys = database.keys()
