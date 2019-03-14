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
import multiprocessing as mp 
import pdfkit
import MySQLdb as mysql
import sqlalchemy
import shapely.geometry
import geopandas as gp

from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict
from geopy.distance import geodesic
from shapely.geometry import Point

# custom imports
#   - analysis.smc.roads
import analysis.smc.roads.extract
import analysis.smc.roads.utils

def best_rss(ap_data, threshold = -80):

    # FIXME: is this correct? 
    # shouldn't you calculate rss plans session by session instead of 
    # aggregating all the session data?

    # (1) fill nan gaps w/ rss = -80 dBm and smooth the rss lines w/ a rolling mean
    aps = list(ap_data.columns)
    aps.remove('xx')

    w = 20
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
    ap_data['bestval'] = ap_data[aps].max(axis = 1)
    ap_data['bestval'] = ap_data['bestval'].fillna(-80.0)

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

        if (prev_rss > (curr_rss - 5.0)) and (prev_rss > -75.0):
            ap_data.loc[i, 'best'] = prev_b
            ap_data.loc[i, 'bestval'] = prev_rss
        elif (curr_rss > -75.0):
            prev_b = b
            ap_data.loc[i, 'bestval'] = curr_rss            
        else:
            ap_data.loc[i, 'best'] = -1

        # print("[%d] %s vs %s [%s]" % (i, prev_rss, curr_rss, b))

    #   - drop rows w/ no best ap
    ap_data = ap_data[ap_data['best'] > 0].reset_index(drop = True)
    #   - mark consecutive positions w/ the same best ap
    ap_data['block'] = ((ap_data['xx'] - ap_data['xx'].shift(1) > 1.0)).astype(int).cumsum()
    ap_data['block'] = ((ap_data['best'] != ap_data['best'].shift(1)) | (ap_data['block'] != ap_data['block'].shift(1))).astype(int).cumsum()

    # (4) build handoff plan out of the blocks
    handoff_plan = ap_data.groupby(['block']).agg({'xx' : ['min', 'max'], 'best' : 'max', 'bestval' : 'mean'}).reset_index(drop = True)
    #   - revert from pandas multi-index & set ap_id to int type
    handoff_plan.columns = list(map(''.join, handoff_plan.columns.values))
    handoff_plan.rename(index = str, columns = {'bestmax' : 'ap_id', 'xxmax' : 'xx-max', 'xxmin' : 'xx-min', 'bestvalmean' : 'mean'}, inplace = True)
    #   - calculate the range of the ap
    handoff_plan['range'] = handoff_plan['xx-max'] - handoff_plan['xx-min']

    handoff_plan = handoff_plan[handoff_plan['range'] > 10.0].reset_index(drop = True)
    handoff_plan['overlaps?'] = (handoff_plan['xx-min'] < handoff_plan['xx-max'].shift(1)).astype(int)
    print(handoff_plan)
    
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

    coverage, ap_data = analysis.smc.roads.utils.get_coverage(data, threshold = -75.0)

    # find first ap in road (xx-coord-wise). set it to the current ap
    #   - if multiple aps are available, tie-break based on range and mean rss, in that order
    coverage = coverage.sort_values(by = ['xx-min', 'xx-max', 'mean'], ascending = [True, False, False]).reset_index(drop = True)

    handoff_plan = coverage.iloc[0:1]

    stop = False
    while not stop:

        #   - overlaps w/ current ap (curr_ap)
        overlap = coverage[(coverage['xx-min'] <= handoff_plan.iloc[-1]['xx-max']) 
            & (coverage['xx-max'] > handoff_plan.iloc[-1]['xx-max'])].sort_values(by = ['xx-max', 'mean'], ascending = [False, False]).reset_index(drop = True)

        if overlap.empty:

            remain = coverage[coverage['xx-min'] >= handoff_plan.iloc[-1]['xx-max']].sort_values(by = ['xx-min', 'xx-max', 'mean'], ascending = [True, False, False]).reset_index(drop = True)
            if remain.empty:
                stop = True
            else:
                handoff_plan = pd.concat([handoff_plan, remain.iloc[0:1]], ignore_index = True)

            continue

        #   - has maximum reach (i.e. xx-max)
        handoff_plan = pd.concat([handoff_plan, overlap.iloc[0:1]], ignore_index = True)

    # get rid of handoff plan rows in which the difference between xx-mins is < 5 m
    handoff_plan['coincides?'] = (handoff_plan['xx-min'] - handoff_plan['xx-min'].shift(-1) > -10.0).astype(int)
    handoff_plan['overlaps?'] = (handoff_plan['xx-min'] < handoff_plan['xx-max'].shift(1)).astype(int)
    handoff_plan = handoff_plan[handoff_plan['coincides?'] < 1].reset_index(drop = True)
    handoff_plan = handoff_plan[handoff_plan['range'] > 10.0].reset_index(drop = True)
    print(handoff_plan)

    return handoff_plan, ap_data[['xx'] + handoff_plan['ap_id'].astype(str).drop_duplicates().tolist()]