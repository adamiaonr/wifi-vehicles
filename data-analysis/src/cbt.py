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

from random import randint
from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict

from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict

from prettytable import PrettyTable

matplotlib.rcParams.update({'font.size': 16})

def calc_frame_duration(wlan_frames):
    # print("cbt::calc_frame_duration() : [INFO]  : phy type : %s, wlan type : %s, wlan subtype : %s, length : %s, data rate : %s" 
    #     % (phy_type, wlan_type, wlan_sub_type, frame_length, data_rate))
    duration = ((8.0 * (wlan_frames['Length'].values - wlan_frames['radiotap.length'].values)) / wlan_frames['Data rate'].values) + wlan_frames['wlan_radio.preamble']
    return duration

def calc_cbt(input_file):

    # dataframe to contain all cbt info for some channel
    cbt = pd.DataFrame(columns = ['period', 'cbt', 'utilization'])

    chunksize = 10 ** 5
    for chunk in pd.read_csv(input_file, chunksize = chunksize):

        # # calculate frame durations for the chunk
        # chunk['frame.duration'] = calc_frame_duration(chunk)

        # divide chunk in 1 sec periods:
        #   - calculate the end transmission times (time + frame duration)
        chunk['endtime'] = chunk['time'].values + (chunk['wlan_radio.duration'].values / 1000000.0)
        #   - get period nr. from integer part of endtime
        chunk['period.no'] = chunk['endtime'].values.astype(int)
        print(chunk[['period.no', 'PHY type', 'Type', 'Type/Subtype', 'Length', 'Data rate', 'wlan_radio.duration']])

        # get count of type / subtypes per period
        counts = chunk.groupby(['period.no', 'PHY type', 'Type', 'Type/Subtype', 'Length', 'Data rate', 'wlan_radio.duration'])['no'].agg('count').reset_index()
        print(counts[['period.no', 'Type', 'Type/Subtype', 'no']])

        # calc cbt per period
        for p in counts['period.no'].unique():
            # isolate stats for period p
            sel = counts[counts['period.no'] == p]
            # calculate cbt for period p
            _cbt = np.sum(sel['no'].values * sel['wlan_radio.duration'].values)
            # append result to final dataframe
            cbt = cbt.append({'period' : p, 'cbt' : _cbt, 'utilization' : ((_cbt / 1000000.0) * 100.0)}, ignore_index = True)

    print(cbt)

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--input-dir", 
         help = """dir w/ .csv files""")

    args = parser.parse_args()

    if not args.input_dir:
        sys.stderr.write("""%s: [ERROR] please supply a dir w/ .csv files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    calc_cbt(args.input_dir)

    sys.exit(0)