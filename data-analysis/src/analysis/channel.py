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

def get_data(trace_dir, pos_list = ['pos1']):

    chann_data = defaultdict(pd.DataFrame)

    for pos in pos_list:
        for filename in sorted(glob.glob(os.path.join(trace_dir, ('%s/cbt.*.csv' % (pos))))):

            # read cbt .csv file w/ channel util stats gathered using Atheros registers
            chann_data[pos] = pd.read_csv(filename)

            # filter out invalid data:
            #   - invalid timestamps
            #       - FIXME : very sloppy test, but it works
            chann_data[pos]['timestamp'] = chann_data[pos]['timestamp'].astype(float)
            chann_data[pos] = chann_data[pos][chann_data[pos]['timestamp'] > 1000000000.0]
            chann_data[pos]['timestamp'] = chann_data[pos]['timestamp'].astype(int)

            # for debugging purposes, timestamps in str format
            # chann_data[pos]['timestamp-str'] = [ str(ts) for ts in chann_data[pos]['timestamp'] ]

            # FIXME: from a quick (eyes-only) analysis of the data, 
            # we assume cat and cbt increase monotonically in the same time segments.
            # identify segments of increasingly monotonic cat.
            chann_data[pos]['channel-util'] = 0.0
            segments = list(chann_data[pos].index[(chann_data[pos]['cat'] - chann_data[pos]['cat'].shift(1)) < 0.0])
            segments.append(len(chann_data[pos]))

            prev_seg = 0
            for seg in segments:

                _data = chann_data[pos].iloc[prev_seg:seg]
                if len(_data) == 1:
                    continue

                _data['diff-cat'] = _data['cat'] - _data['cat'].shift(1)
                _data['diff-cbt'] = _data['cbt'] - _data['cbt'].shift(1)

                chann_data[pos].loc[prev_seg:seg, 'channel-util'] = (_data['diff-cbt'].astype(float) / _data['diff-cat'].astype(float)) * 100.0

        # # fix first row : avg. of acc. register data 
        # chann_data[pos].loc[0, 'channel-util'] = (chann_data[pos].iloc[0]['cbt'].astype(float) / chann_data[pos].iloc[0]['cat'].astype(float)) * 100.0
        # drop 'Nan' values of channel util.
        chann_data[pos] = chann_data[pos].dropna(subset = ['channel-util'])

    return chann_data