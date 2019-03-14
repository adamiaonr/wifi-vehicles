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

import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import os
import re
import argparse
import sys
import glob
import math
import gmplot
import time
import subprocess
import csv
# for parallel processing of sessions
import multiprocessing as mp 
import hashlib
import datetime
import json

from random import randint
from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple
from matplotlib.gridspec import GridSpec
from prettytable import PrettyTable

# global variable to keep hdfs keys in memory
# this is done to avoid excessive lookup time when calling db.keys()
# e.g., issue reported here : https://github.com/pandas-dev/pandas/issues/17593 
db_keys = []

def get_db(input_dir, hdfs_file = 'database.hdf5'):
    db_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(db_dir):
        os.makedirs(db_dir)
    database = pd.HDFStore(os.path.join(db_dir, hdfs_file))
    return database

def get_db_keys(input_dir, hdfs_file = 'database.hdf5'):
    global db_keys
    if not db_keys:
        db_keys = get_db(input_dir, hdfs_file = hdfs_file).keys()
    return db_keys

def to_hdfs(data, metric, database):
    database.append(
        ('%s' % (metric)),
        data,
        data_columns = data.columns,
        format = 'table')

    # update database keys everytime you save a table
    global db_keys
    db_keys = database.keys()

def remove_dbs(input_dir, hdfs_file = 'database.hdf5', dbs = []):

    database = get_db(input_dir, hdfs_file = hdfs_file)
    database_keys = get_db_keys(input_dir, hdfs_file = hdfs_file)

    for db in dbs:
        if db in database_keys:
            database.remove(db)
            sys.stderr.write("""%s: [INFO] removed db %s\n""" % (sys.argv[0], db))
        else:
            sys.stderr.write("""%s: [INFO] db %s not in database\n""" % (sys.argv[0], db))

    # update database keys everytime you remove tables
    global db_keys
    db_keys = database.keys()