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
import hashlib
import timeit

# for parallel processing of sessions
import multiprocessing as mp 
# for maps
import pdfkit
# for MySQL & pandas
import MySQLdb as mysql
import sqlalchemy
import shapely.geometry

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

import analysis.smc.roads.main
import analysis.smc.roads.utils

import parsing.utils
import mapping.utils

import geopandas as gp

def best_rss(ap_data):

    # FIXME: is this correct? 
    # shouldn't you calculate rss plans session by session instead of 
    # aggregating all the session data?

    # (1) fill nan gaps w/ rss = -80 dBm and smooth the rss lines w/ a rolling mean
    aps = list(ap_data.columns)
    aps.remove('xx')

    w = 10
    for ap in aps:
        #   - interpolate small nan gaps
        ap_data[ap] = ap_data[ap].interpolate(limit = 3)
        #   - fill large nan gaps w/ low rss value (e.g., -80 dBm)
        ap_data[ap] = ap_data[ap].fillna(-80.0)
        #   - apply a rolling mean() of w previous samples
        ap_data[ap] = ap_data[ap].rolling(w).mean()
        ap_data[ap] = ap_data[ap].astype(float)

    # (2) get the 'best' ap per xx pos
    ap_data['best'] = ap_data[aps].idxmax(axis = 1)
    ap_data['best'] = ap_data['best'].fillna(-1)

    # (3) apply smoothed rss + hysteresis algorithm:
    #   - assume a hysteresis of 5 dBm
    #   - compare rss[best] and rss[prev_best] mean of 10 previous samples
    #       - the 10 prev samples come from the rolling mean in step (1)
    #       - at 10 m.s-1, 10 samples are equivalent to ~1 sec (note that 1 beacon per sec is the best we can get w/ the smc dataset anyway)
    #   - if smoothed_rss[prev_best] > (smoothed_rss[new_best] - 5), keep the current ap
    # FIXME : this iterative approach is very inefficient (and ugly to look at)
    j = 0
    prev_b = ''
    for i in xrange(0, len(ap_data)):
        prev_b = ap_data['best'].loc[i]
        if prev_b > 0:
            break
        j += 1

    for i in xrange(j + 1, len(ap_data)):
        b = ap_data['best'].loc[i]
        if b < 0:
            continue

        # FIXME : this is a patch to solve some stupid error, 
        # which makes a pd.core.series.Series appear in the middle of 
        # a column of a DataFrame, which is otherwise filled w/ float...
        curr_rss = ap_data[b].loc[i]
        if isinstance(curr_rss, pd.core.series.Series):
            curr_rss = curr_rss.max()
        prev_rss = ap_data[prev_b].loc[i]

        if (prev_rss > (curr_rss - 5.0)) and (prev_rss > -80.0):
            ap_data.loc[i, 'best'] = prev_b
        elif (curr_rss > -80.0):
            prev_b = b
        else:
            ap_data.loc[i, 'best'] = -1

        # print("[%d] %s vs %s [%s]" % (i, prev_rss, curr_rss, b))

    #   - drop rows w/ no best ap
    ap_data = ap_data[ap_data['best'] > 0].reset_index(drop = True)
    #   - find consecutive positions w/ the same best ap
    ap_data['block'] = (ap_data['best'] != ap_data['best'].shift(1)).astype(int).cumsum()

    # (4) build handoff plan out of the blocks
    handoff_plan = ap_data.groupby(['block']).agg({'xx' : ['min', 'max'], 'best' : 'max'}).reset_index(drop = True)
    #   - revert from pandas multi-index & set ap_id to int type
    handoff_plan.columns = list(map(''.join, handoff_plan.columns.values))
    handoff_plan.rename(index = str, columns = {'bestmax' : 'ap_id', 'xxmax' : 'xx-max', 'xxmin' : 'xx-min'}, inplace = True)
    #   - calculate the range of the ap
    handoff_plan['range'] = handoff_plan['xx-max'] - handoff_plan['xx-min']

    # (5) restrict ap ranges to previously computed ranges
    # FIXME: ok, is this correct? 
    #   - i think it's fair, because the outliers are probably just that, 
    #     and those would result in a wrong sense of coverage
    # handoff_plan = sanitize_coverage(handoff_plan, coverage)
    
    return handoff_plan, ap_data[['xx'] + handoff_plan['ap_id'].astype(str).drop_duplicates().tolist()]
    
def greedy(data):
    
    # (greedy) algorithm:
    #   1) find first ap in road. set it to curr_ap
    #   2) add curr_ap to handoff plan.
    #   3) find set of subsequent aps whose coverage overlaps w/ curr_ap
    #   4) if set is empty:
    #       - find set of non-overlapping aps:
    #       - if set is empty, terminate
    #       - if set is not empty, set curr_ap to first ap in set. goto 2)
    #   5) if set is not empty, pick ap with *furthest* coverage. set it to curr_ap. goto 2)

    coverage, ap_data = analysis.smc.roads.utils.get_coverage(data, threshold = -70.0)

    # find first ap in road (xx-coord-wise). set it to the current ap.
    curr_ap = coverage.loc[coverage['xx-min'].idxmin()]
    stop = False
    handoff_plan = coverage[coverage['ap_id'] == curr_ap['ap_id']]
    while not stop:
        #   - overlaps w/ current ap (curr_ap)
        over = coverage[(coverage['ap_id'] != curr_ap['ap_id']) 
            & (coverage['xx-min'] < curr_ap['xx-max']) 
            & (coverage['xx-max'] > curr_ap['xx-max'])]
        
        if over.empty:

            remain = coverage[coverage['xx-min'] > curr_ap['xx-max']].reset_index(drop = True)
            if remain.empty:
                stop = True
            else:
                curr_ap = remain.loc[remain['xx-min'].idxmin()]
                handoff_plan = pd.concat([handoff_plan, remain[remain['ap_id'] == curr_ap['ap_id']]], ignore_index = True)

            continue

        #   - has maximum reach (i.e. xx-max)
        curr_ap = over.loc[over['xx-max'].idxmax()]
        handoff_plan = pd.concat([handoff_plan, over[over['ap_id'] == curr_ap['ap_id']]], ignore_index = True)

    return handoff_plan, ap_data[['xx'] + handoff_plan['ap_id'].astype(str).drop_duplicates().tolist()]