import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.pylab as pl
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

# for ap location estimation
from shapely.geometry import Point
# custom imports
from plot_utils import *

matplotlib.rcParams.update({'font.size': 16})

# gps coords for a 'central' pin on porto, portugal
PORTO_LATITUDE  = 41.163158
PORTO_LONGITUDE = -8.6127137
# north, south, west, east limits of map, in terms of geo coordinates
PORTO_LATITUDE_LIMIT_NORTH = PORTO_LATITUDE  + 0.03
PORTO_LATITUDE_LIMIT_SOUTH = PORTO_LATITUDE  - 0.03
PORTO_LONGITUDE_LIMIT_EAST = PORTO_LONGITUDE + 0.06
PORTO_LONGITUDE_LIMIT_WEST = PORTO_LONGITUDE - 0.06
# x and y span (in m) of the map, derived from geo coordinate limits
Y_SPAN = gps_to_dist(PORTO_LATITUDE_LIMIT_NORTH, 0.0, PORTO_LATITUDE_LIMIT_SOUTH, 0.0)
# FIXME : an x span depends on the latitude, and we're assuming a fixed latitude
X_SPAN = gps_to_dist(PORTO_LONGITUDE_LIMIT_WEST, PORTO_LATITUDE, PORTO_LONGITUDE_LIMIT_EAST, PORTO_LATITUDE)

# fcup : 41.157505,41.150752,-8.647382,-8.629400
# fcup (minor) : 41.152844,41.149629,-8.640344,-8.632748
# feup : 41.180183,41.177093,-8.599869,-8.593644

# info about the sense-my-city dataset
#   ds : distance travelled by the user during the scanning period
#   freq : channel frequency
#   acc_scan : mean accuracy from the GPS during the scanning period
#   new_err : mean error related to the map matching process (was conducted by others)
#   new_lat | new_lot : location where the scan was associated
#   g_lat | g_lon : cell location
#   auth : authentication mode (0 - Unknown, 1 - Open, 2 - WEP, 3 - WPA, 4 - WPA2, 5 - Enterprise (RADIUS/.11x/Other).)
WIFI_AUTH = {0: 'unknown', 1: 'open', 2: 'wep', 3: 'wpa', 4: 'wpa2', 5: 'wpa2-enter'}

CDF_COLUMNS = ['time-diff', 2412, 2417, 2422, 2427, 2432, 2437, 2442, 2447, 2452, 2457, 2462, 2467, 2472, 2484]
GPS_COLUMNS = ['ts', 'gps-acc']

def get_ap_id(essid, mac_addr):
    return hashlib.md5((str(essid).strip() + str(mac_addr[:6]).strip()).encode()).hexdigest()

# get (x,y) coords of cell w/ side cell_size
def calc_cell(lat, lon, cell_size):

    # calc x and y coords in cell
    x = ((lat - PORTO_LATITUDE_LIMIT_SOUTH) / (PORTO_LATITUDE_LIMIT_NORTH - PORTO_LATITUDE_LIMIT_SOUTH)) * (X_SPAN / cell_size)
    y = ((lon - PORTO_LONGITUDE_LIMIT_WEST) / (PORTO_LONGITUDE_LIMIT_EAST - PORTO_LONGITUDE_LIMIT_WEST)) * (Y_SPAN / cell_size)

    return int(x), int(y)

# returns True if session data was collected outside some box of gps coords
def out_of_box(session_data, geo_limits):

    max_lat = np.amax(session_data['new_lat'])
    min_lat = np.amin(session_data['new_lat'])
    max_lon = np.amax(session_data['new_lon'])
    min_lon = np.amin(session_data['new_lon'])
 
    # print("channel-switch::out_of_box : session geo limits : [%f,%f,%f,%f]" % (max_lat, min_lat, min_lon, max_lon))
    # print("channel-switch::out_of_box : box geo limits : %s" % (geo_limits))

    if (max_lon < geo_limits[2]) or (geo_limits[3] < min_lon):
        return True
    if (max_lat < geo_limits[1]) or (geo_limits[0] < min_lat):
        return True

    return False

# pick the cell with max. snr values for any of the channels, as an approximation
# of the closest to the ap.
def find_best_cell(ap_stats):

    cells = pd.DataFrame(columns = ['cell', 'mean'])

    for cell in ap_stats:

        if cell == 'channels' or cell == 'info':
            continue

        df = ap_stats[cell].groupby('ts').sum().mean()
        # print("\tswitch::extract_stats : active channels : %d" % (df.count()))

        cells = cells.append({
            'cell' : cell,
            'mean' : df.max()
            }, ignore_index = True)

    return cells.ix[cells['mean'].idxmax()]['cell']

def count(session_channel_snr):

    # histogram of time-diff per session
    time_count = pd.DataFrame()

    for index, row in session_channel_snr.iterrows():
        time_count = time_count.append({
            'time-diff' : row['time-diff'],
            str(row['freq']) : 1.0
            }, ignore_index = True)

    time_count = time_count.groupby('time-diff').sum()

    # nr. of switches per session
    if len(session_channel_snr) > 1:
        switch_count = pd.DataFrame({'nr-sessions' : {len(session_channel_snr): 1}})
        switch_count.index.names = ['nr-switch']

    return time_count.fillna(0.0), switch_count

def update_cdf(out_dir, session_channel_snr):

    # transform the list of stronger channel periods into a freq. count table,
    # indexed by time-diff, and w/ channel frequencies as the columns, e.g.:
    # 'time-diff'    ch_1    ch_2    ch_3    ...     ch_n
    # 1.0            0       0       0               2
    # 2.0            0       1       0               1
    # 3.0            1       0       1               0
    time_count, switch_count = count(session_channel_snr)

    print(time_count)
    print(switch_count)

    if not switch_count.empty:

        switch_cdf_filename = os.path.join(out_dir, "switch-cdf.csv")
        if os.path.exists(switch_cdf_filename):
            switch_cdf = pd.read_csv(switch_cdf_filename, index_col = 'nr-switch')
            switch_cdf = switch_cdf.add(switch_count, fill_value = 0.0)
        else:
            switch_cdf = switch_count

        switch_cdf = switch_cdf.fillna(0.0)
        switch_cdf.to_csv(switch_cdf_filename, sep = ',')

    # load the cdf stored in disk (if it exists)
    time_cdf_filename = os.path.join(out_dir, "time-cdf.csv")
    if os.path.exists(time_cdf_filename):
        time_cdf = pd.read_csv(time_cdf_filename, index_col = 'time-diff')
        time_cdf = time_cdf.add(time_count, fill_value = 0.0)
    else:
        time_cdf = time_count

    time_cdf = time_cdf.fillna(0.0)
    time_cdf.to_csv(time_cdf_filename, sep = ',')

# extract wifi scan ap stats indexed by cell (x,y) indeces
def extract_stats(out_dir, session_data,  cell_size, geo_limits):

    nr_scans = 0
    nr_valid = 0

    # we collect 2 things:
    #   - snr stats per channel (frequency)
    #   - gps error stats per region of the map
    snr_stats = defaultdict()
    gps_error_stats = defaultdict()

    for index, row in session_data.iterrows():

        # don't consider points which fall out of the box defined by geo_limits
        if out_of_box(row, geo_limits):
            # print("channel-switch::extract_stats : skipping [%.3f,%.3f]" % (row['new_lat'], row['new_lon']))
            continue
        # print("channel-switch::extract_stats : [%.3f,%.3f] within geo limits" % (row['new_lat'], row['new_lon']))

        essid = row['essid']
        mac_addr = row['encode']
        # get the ap id, based on the essid and mac addr.
        ap = get_ap_id(essid, mac_addr)

        if ap not in snr_stats:
            snr_stats[ap] = defaultdict()
            snr_stats[ap]['channels'] = set([])

            snr_stats[ap]['info'] = (str(essid), str(mac_addr[:6]))

        # x,y coords of cell in which the wifi scan was made.
        # this is important, because we want to analyze snr readings on the cell 
        # with max. mean snr (i.e. ideally the the closest to the ap as possible).
        x,y = calc_cell(row['new_lat'], row['new_lon'], cell_size)
        if x >= (int(X_SPAN / cell_size)) or y >= (int(Y_SPAN / cell_size)):
            continue

        # print("channel-switch::extract_stats : analyzing cell (%d,%d)" % (x,y))

        # index snr_stats by cell (x,y) coords. we later select the (x,y) 
        # with higher mean snrs
        if (x,y) not in snr_stats[ap]:
            snr_stats[ap][(x,y)] = pd.DataFrame()

        if (x,y) not in gps_error_stats:
            gps_error_stats[(x,y)] = pd.DataFrame(columns = GPS_COLUMNS)

        ts = row['seconds']
        gps_error_stats[(x,y)] = gps_error_stats[(x,y)].append({
            'ts' : ts, 
            'gps-acc' : row['acc_scan']
            }, ignore_index = True)

        freq = row['frequency']
        snr_stats[ap]['channels'].add(freq)

        # append row to 'snr' dataframe, setting the snr value on the freq column
        # FIXME : is there a better way of doing this?
        snr_stats[ap][(x,y)] = snr_stats[ap][(x,y)].append({
            'ts' : ts,
            int(freq) : row['snr']
            }, ignore_index = True)

        nr_scans += 1

    # after collecting the snr and gps error data for the session, update the 
    # general dataframes starting w/ aps
    for ap in snr_stats:

        # print("channel-switch::extract_stats : evaluating ap %s:" % (ap))

        # B) condense rows w/ same timestamp 
        session_channel_snr = snr_stats[ap][find_best_cell(snr_stats[ap])].groupby('ts').sum()
        # discard aps w/ less than 2 timestamp rows
        if len(session_channel_snr) < 2:
            continue

        # C) find the 'stronger' channel for each timestamp, and represent them 
        # in a column 'freq'
        session_channel_snr = session_channel_snr.idxmax(axis = 1).to_frame('freq')

        # D) for each 'stronger' channel x, find the periods of time for which 
        # x is the strongest.
        session_channel_snr['block'] = (session_channel_snr.freq.shift(1) != session_channel_snr.freq).astype(int).cumsum()
        session_channel_snr = session_channel_snr.reset_index().groupby(['freq', 'block'])['ts'].apply(np.array).to_frame('time-diff').reset_index()

        time_diff = lambda t : (t[-1] - t[0])
        session_channel_snr['time-diff'] = session_channel_snr['time-diff'].apply(time_diff)

        # discard sessions w/   
        if len(session_channel_snr) < 2:
            continue

        print("channel-switch::extract_stats : stats for ap %s (%s-%s):" % (ap, snr_stats[ap]['info'][0], snr_stats[ap]['info'][1]))

        # E) update the in-disk cdfs 
        update_cdf(out_dir, session_channel_snr.reset_index())

        nr_valid += 1

    return nr_scans, nr_valid

def analyze_sessions(file_name, out_dir, cell_size, geo_limits):

    # keep track of the number of stacks 
    nr_scans = 0
    nr_valid = 0
    nr_sessions = 0

    # given the large size of the input data file (> 3 GB), we read the file in chunks
    chunksize = 10 ** 5

    for chunk in pd.read_csv(file_name, chunksize = chunksize):

        # find unique session ids on this chunk
        chunk_session_ids = chunk['session_id'].unique()
        print("channel_switch::analyze_sessions() : %d sessions found in chunk" % (len(chunk_session_ids)))

        for session_id in chunk_session_ids:

            print("channel_switch::analyze_sessions() : analyzing session_id %s" % (session_id))
            # to make it easier, extract session data first
            session_data = chunk.loc[chunk['session_id'] == session_id]

            # disregard sessions which completely fall out-of-the box defined by geo_limits
            if out_of_box(session_data, geo_limits):
                # print("channel-switch::analyze_sessions: skipping session_id %s (out-of-box)" % (session_id))
                continue

            s, v = extract_stats(out_dir, session_data, cell_size, geo_limits)

            nr_scans += s
            nr_valid += v
            nr_sessions += 1

        # if nr_scans > 3000:
        #     break

    print("channel_switch::analyze_sessions() : analyzed %d scans" % (nr_scans))
    print("channel_switch::analyze_sessions() : analyzed %d sessions (%d valid)" % (nr_sessions, nr_valid))

    return nr_scans, nr_sessions

def get_channel_metadata(channel_keys):

    wrong_channels = ['-1.0']
    channel_metadata = OrderedDict()

    for ck in channel_keys:

        if ck in wrong_channels:
            continue

        channel_nr = int(float(ck))
        if channel_nr < 5000:
            channel_nr = ((channel_nr - 2412) / 5) + 1
        else:
            continue
            # channel_nr = ((channel_nr - 5180) / 10) + 36

        channel_metadata[ck] = str(channel_nr)

    color_map = plt.get_cmap('Set1')
    colors = [color_map(i) for i in np.linspace(0, 1, len(channel_metadata))]

    return channel_metadata, colors

def plot_channel_times(time_cdf, fig, subfig_index):

    ax1 = fig.add_subplot(subfig_index)

    channel_metadata, colors = get_channel_metadata(time_cdf.columns)
    for i, ck in enumerate(channel_metadata):

        # cumulative sum over all column values
        acc = np.array(time_cdf[ck].cumsum(), dtype = float)
        # scale column values by total sum (last element of cum. sum)
        acc = acc / acc[-1]
        # plot channel cdf
        ax1.plot(time_cdf.reset_index()['time-diff'], acc, 
            alpha = 0.5, linewidth = 1.5, color = matplotlib.colors.rgb2hex(colors[i][:3]), 
            label = channel_metadata[ck])

    ax1.legend(fontsize = 12, ncol = 1, loc='lower right')
    ax1.set_xlim(0.0, 100.0)
    ax1.set_ylim(0.0, 1.0)

def plot_channel_sequences(time_cdf, fig,  subfig_index):

    ax1 = fig.add_subplot(subfig_index)

    channel_metadata, colors = get_channel_metadata(time_cdf.columns)
    for i, ck in enumerate(channel_metadata):

        # cumulative sum over all column values
        # FIXME : hard way of doing this...
        acc = np.array(time_cdf[ck].cumsum(), dtype = float)
        ax1.bar(i + 1, acc[-1], alpha = 0.55, width = 0.75, label = channel_metadata[ck], color = matplotlib.colors.rgb2hex(colors[i][:3]))

    ax1.legend(fontsize = 12, ncol = 1, loc='upper right')
    # ax1.set_xlim(0.0, 100.0)

def plot_channel_switches(switch_cdf, fig,  subfig_index):

    ax1 = fig.add_subplot(subfig_index)

    # cumulative sum over all column values
    acc = np.array(switch_cdf['nr-sessions'].cumsum(), dtype = float)
    # scale column values by total sum (last element of cum. sum)
    acc = acc / acc[-1]
    # plot channel cdf
    ax1.plot(switch_cdf.reset_index()['nr-switch'] - 1, acc, 
        alpha = 0.5, linewidth = 1.5, color = 'blue', label = 'nr. switches')

    ax1.legend(fontsize = 12, ncol = 1, loc='lower right')
    ax1.set_xlim(1.0, 10.0)
    ax1.set_ylim(0.0, 1.0)

def plot(
    file_name, 
    out_dir, 
    cell_size = 10.0,
    geo_limits = [PORTO_LATITUDE_LIMIT_NORTH, PORTO_LATITUDE_LIMIT_SOUTH, 
                    PORTO_LONGITUDE_LIMIT_WEST, PORTO_LONGITUDE_LIMIT_EAST]):

    reload(sys)  
    sys.setdefaultencoding('utf8')

    """extracts bunch of stats from 'sense my city' sessions"""

    # filenames for .csv files
    time_cdf_filename = os.path.join(out_dir, "time-cdf.csv")
    switch_cdf_filename = os.path.join(out_dir, "switch-cdf.csv")

    # # if files do not exists, collect data
    # if not os.path.exists(time_cdf_filename):
    #     nr_scans, nr_sessions = analyze_sessions(file_name, out_dir, cell_size, geo_limits)

    # extract raw cdfs from disk
    time_cdf    = pd.read_csv(time_cdf_filename, index_col = 'time-diff')
    switch_cdf  = pd.read_csv(switch_cdf_filename, index_col = 'nr-switch')

    fig = plt.figure(figsize = (18, 5))

    plot_channel_times(time_cdf, fig, 131)
    plot_channel_switches(switch_cdf, fig, 132)
    plot_channel_sequences(time_cdf, fig, 133)

    fig.tight_layout()
    fig.subplots_adjust(top = 0.95)

    plt.savefig(os.path.join(out_dir, "../../graphs/time-diff.pdf"), bbox_inches = 'tight', format = 'pdf')