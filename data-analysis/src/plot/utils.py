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

def update_time_limits(time_limits, array):
    if ((time_limits[0] is None) or (min(array) < time_limits[0])):
        time_limits[0] = np.amin(array)

    if ((time_limits[1] is None) or (max(array) > time_limits[1])):
        time_limits[1] = np.amax(array)

def update_date_limits(time_limits, data):
    dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in data ]
    if dates:
        update_time_limits(time_limits, dates)

def get_time_xticks(time_limits):
    delta = datetime.timedelta(seconds = ((time_limits[1] - time_limits[0]).total_seconds() / 5))
    xticks = np.arange(time_limits[0], time_limits[1] + delta, delta)

    return xticks[:6]
