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

reload(sys)
sys.setdefaultencoding('utf8')

matplotlib.rcParams.update({'font.size': 16})

# gps coords for a 'central' pin on porto, portugal
PORTO_LATITUDE  = 41.163158
PORTO_LONGITUDE = -8.6127137
# north, south, west, east limits of map, in terms of geo coordinates
PORTO_LATITUDE_LIMIT_NORTH = PORTO_LATITUDE  + 0.03
PORTO_LATITUDE_LIMIT_SOUTH = PORTO_LATITUDE  - 0.03
PORTO_LONGITUDE_LIMIT_EAST = PORTO_LONGITUDE + 0.06
PORTO_LONGITUDE_LIMIT_WEST = PORTO_LONGITUDE - 0.06

# x and y span (in meters) of the map, derived from geo coordinate limits
# NOTE : y is the vertical axis (latitude), x is the horizontal axis (longitude)
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

# dict of wifi providers. structure is as follows:
#   [id of provider] : ['<public/private flag>:<common essid prefix>']
WIFI_PROVIDERS = {
    1 : ['meo', '0:MEO-WiFi', '1:MEO-', '1:Thomson', '0:PT-WIFI'], 
    2 : ['zon', '0:FON_ZON', '1:ZON-'], 
    3 : ['eduroam', '0:eduroam'],
    4 : ['porto-digital', '0:WiFi Porto Digital'],
    5 : ['vodafone', '1:Vodafone-', '1:VodafoneFibra-' '1:VodafoneMobileWiFi-'],
    6 : ['lab-cc', '0:LabCC'],
    7 : ['unknown']
}
# columns of .hdf5 stores for different wifi bands (2.4 and 5.0 ghz)
WIFI_BANDS_COLUMNS = {
    1 : ['ts', 'session_id', 'xy', 'provider', 'mac_addr', 'essid', 'access', 'segment_type', 'f2412','f2417','f2422','f2427','f2432','f2437','f2442','f2447','f2452','f2457','f2462','f2467','f2472'],
    2 : ['ts', 'session_id', 'xy', 'provider', 'mac_addr', 'essid', 'access', 'segment_type', 'f5180','f5200','f5220','f5240','f5260','f5280','f5300','f5320','f5500','f5520','f5560','f5580','f5600','f5620']
}
# translation between wifi band indexes and textual representation
WIFI_BANDS = {1 : '2.4', 2 : '5.0', '2.4' : 1, '5.0' : 2}
# translation between wifi band channel # and frequencies
WIFI_CHANNELS = {   
    1 : {'f2412' : 1, 'f2417' : 2, 'f2422' : 3, 'f2427' : 4, 'f2432' : 5, 'f2437' : 6, 'f2442' : 7, 'f2447' : 8, 'f2452' : 9, 'f2457' : 10, 'f2462' : 11, 'f2467' : 12, 'f2472' : 13 },
    2 : {'f5180' : 5180, 'f5200' : 5200, 'f5220' : 5220, 'f5240' : 5240, 'f5260' : 5260, 'f5280' : 5280, 'f5300' : 5300, 'f5320' : 5320, 'f5500' : 5500, 'f5520' : 5520, 'f5560' : 5560, 'f5580' : 5580, 'f5600' : 5600, 'f5620' : 5620}
}

# segment types according to speed. translation between indexes and textual 
# representation
SEGMENT_TYPES = {0 : 'stationary', 1 : 'pedestrian-speed', 2 : 'vehicular-speed'}

def get_provider(essid):
    # provider is inferred via essid
    for provider in WIFI_PROVIDERS:
        for prefix in WIFI_PROVIDERS[provider][1:]:

            if not isinstance(essid, basestring):
                continue

            # check if the essid prefix (after the ':') is in the record's essid
            if prefix.split(":")[1] in essid:
                # return provider id and access type
                return provider, int(prefix.split(":")[0])

    # default is 'unknown' provider (always last key), and private access
    return WIFI_PROVIDERS.keys()[-1], 1

def get_analysis_id(args):
    analysis_str = str([str(a).strip() for a in args]).encode()
    return hashlib.md5(analysis_str).hexdigest()

def get_ap_id(mac_addr, mac_prefix = 6, essid = "", hashed = True):

    # discard any public wifi essid from commercial isps (e.g. meo or nos)
    provider, access_type = get_provider(essid)
    if access_type == 0:
        if (WIFI_PROVIDERS[provider][0] not in ['eduroam', 'porto-digital']):
            return None

    if hashed == True:
        return hashlib.md5((str(essid).strip() + str(mac_addr[:(2 * mac_prefix)]).strip()).encode()).hexdigest()
    else:
        return (str(essid).strip() + str(mac_addr[:(2 * mac_prefix)]).strip()).encode()

# get (x,y) coords of cell w/ side cell_size
def calc_cell(lat, lon, cell_size):

    # calc y (latitude) and x (longitude) coords of cell
    y = ((lat - PORTO_LATITUDE_LIMIT_SOUTH) / (PORTO_LATITUDE_LIMIT_NORTH - PORTO_LATITUDE_LIMIT_SOUTH)) * (Y_SPAN / cell_size)
    x = ((lon - PORTO_LONGITUDE_LIMIT_WEST) / (PORTO_LONGITUDE_LIMIT_EAST - PORTO_LONGITUDE_LIMIT_WEST)) * (X_SPAN / cell_size)

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

# pick cell with max. snr values for any of the channels, as an approximation
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

# # update the cell gps accuracy
# def update_gps_accuracy(out_dir, session_gps_acc):

#     filename = os.path.join(out_dir, "gps-accuracy.csv")
    
#     if os.path.exists(filename):
#         gps_acc = pd.read_csv(filename)
#     else:
#         gps_acc = pd.DataFrame()
#         gps_acc = gps_acc.append({
#             'cell' : (0,0),
#             'n' : 0.0,
#             'mean' : 0.0,
#             'var' : 0.0
#             }, ignore_index = True)

#     for cell in session_gps_acc:

#         # row w/ index cell
#         if cell not in gps_acc.index:
#             gps_acc = gps_acc.append({
#                 'cell' : cell,
#                 'n' : 0.0,
#                 'mean' : 0.0,
#                 'var' : 0.0
#                 }, ignore_index = True)

#         cell_row = gps_acc.loc[gps_acc['cell'] == cell]

#         # nr. of samples in-disk and in the session dataframe
#         k = len(session_gps_acc[cell])
#         n = cell_row['n']

#         # update mean 
#         # print("k : %f" % (k))
#         # print("n : %f" % (n))
#         # print("sum : %f" % (np.sum(session_gps_acc[cell]['gps-acc'].values)))
#         mean = ((n * cell_row['mean']) + np.sum(session_gps_acc[cell]['gps-acc'].values)) / (n + k)
#         gps_acc.loc[gps_acc['cell'] == cell, 'mean'] = mean
#         # print("mean %.3f vs running mean : %.3f" % (np.mean(session_gps_acc[cell]['gps-acc'].values), mean))

#         # update variance using Welford's method
#         # http://jonisalonen.com/2013/deriving-welfords-method-for-computing-variance
#         samples = session_gps_acc[cell]['gps-acc'].values

#         # initial values for mean and variance taken from general 
#         m = cell_row['mean']
#         v = cell_row['var']

#         for i, x in enumerate(samples):
#             old_m = m
#             m = m + (x - m) / (n + (i + 1.0))
#             v = v + ((x - m) * (x - old_m))

#         v = v / (n + k)
#         # print("var %.3f vs running var : %.3f" % (np.var(session_gps_acc[cell]['gps-acc'].values), v))

#         gps_acc.loc[gps_acc['cell'] == cell, 'var'] = v
#         gps_acc.loc[gps_acc['cell'] == cell, 'n'] = n + k

#     gps_acc.to_csv(filename, sep = ',', index = False)

# def handle_gps_data(cell, record, session_gps_acc):

#     if cell not in session_gps_acc:
#         session_gps_acc[cell] = pd.DataFrame()

#     session_gps_acc[cell] = session_gps_acc[cell].append({
#         'ts' : record['seconds'], 
#         'gps-acc' : record['acc_scan']
#         }, ignore_index = True)

# # find the cell w/ max median snr for each particular mac address (remember, the
# # ration between mac addresses and frequencies is 1:1)
# def find_best_cell(ap_stats, out_dir):

#     cols = ("[%s]" % (", ".join([("'%s'" % f) for f in WIFI_BANDS_COLUMNS[1][0:]])))

#     # get unique mac addresses
#     for provider in ap_stats.keys():
#         mac_addrs = ap_stats.select_column(provider, 'mac_addr').unique()

#         for mac_addr in mac_addrs:
#             snrs = ap_stats.select(provider, where = ("""columns = %s and mac_addr == '%s'""" % (cols, mac_addr)))

# extract wifi scan ap stats indexed by cell (x,y) indeces
def extract_stats(session_data, cell_size, geo_limits, ap_stats):

    # general stats:
    #   - total nr. of scans in the session (and within the geo limits box)
    #   - set of aps visible in session (and which match the constraints 
    #     passed in arg)
    #   - set of essids visible in session (and which match the constraints 
    #     passed in arg)
    nr_scans = 0
    nr_valid_scans = 0
    aps = set([])
    essids = set([])

    df = defaultdict()

    # we collect 2 things:
    #   - snr stats per channel (frequency)
    #   - gps error stats per region of the map
    # session_gps_acc = defaultdict()

    for index, row in session_data.iterrows():

        # update nr. scans
        nr_scans += 1

        # don't consider points which fall out of the box defined by geo_limits
        if out_of_box(row, geo_limits):
            continue
        # x,y coords of cell in which the wifi scan was made.
        # this is important, because we want to analyze snr readings on the 
        # cell with max. mean snr (i.e. ideally the the closest to the ap as 
        # possible).
        x, y = calc_cell(row['new_lat'], row['new_lon'], cell_size)
        if x >= (int(X_SPAN / cell_size)) or y >= (int(Y_SPAN / cell_size)):
            continue

        # handle_gps_data((x,y), row, session_gps_acc)
        ts = row['seconds']
        freq = row['frequency']
        essid = row['essid']
        mac_addr = row['encode']

        # if essid is not a valid string, e.g. NaN, abort
        if not isinstance(essid, basestring):
            continue

        # get the ap id
        ap_id = get_ap_id(mac_addr, essid = essid)
        # add ap id and essid to return sets
        if ap_id is not None:
            aps.add(ap_id)
        essids.add(essid)

        # ignore frequencies below 2.4 ghz band (which only show up by mistake)
        if (int(freq) < 2412):
            continue

        # get the provider and type ('prv' or 'pub') of the record
        provider, access_type = get_provider(essid)

        # find which columns to use for dataframe, which vary depending on the 
        # frequency band of the signal
        band_col = 1 if (int(freq) < 5000) else 2
        if band_col not in df:
            df[band_col] = pd.DataFrame(columns = WIFI_BANDS_COLUMNS[band_col])

        # append row to 'snr' dataframe, setting the snr value on the 
        # freq column
        df[band_col] = df[band_col].append({
            'ts' : ts,
            'session_id' : int(row['session_id']),
            'xy' : ('%04d:%04d' % (int(x), int(y))),
            'provider' : int(provider),
            'mac_addr' : str(mac_addr),
            'essid' : str(essid[0:15]),
            'access' : access_type,
            'segment_type': float(row['segment_type']),
            ('f%d' % (freq)) : float(row['snr'])
            }, ignore_index = True)

        # update nr. valid scans
        nr_valid_scans += 1

    # append to hdfs store 'channels/<band>'
    for band_col in df:

        try:

            t_i = time.clock()
            # append dataframe to correct dataset in the .hdf5 store ('channels/<band>')
            ap_stats.append(
                ('channels/%s' % (WIFI_BANDS[band_col])),   # 'channels/<band>'
                df[band_col],                               # data to append
                data_columns = WIFI_BANDS_COLUMNS[band_col],
                format = 'table',
                min_itemsize = {'values' : 16})
            # keep track of write times w/ hdfs
            print("channel_switch::extract_stats() : wrote %d rows to channels/%s in %.3f ms" % 
                (len(df[band_col]), WIFI_BANDS[band_col], (time.clock() - t_i) * 1000.0))

        except Exception as e:

            print("channel_switch::extract_stats() : [ERROR] append() to channels/%s failed" % (WIFI_BANDS[band_col]))
            print(e)
            print("channel_switch::extract_stats() : band %s, band_col = %d" % (WIFI_BANDS[band_col], band_col))
            print("channel_switch::extract_stats() : df[%d] : " % (band_col))
            print(df[band_col])

    # do this to force garbage collection and free memory
    # FIXME: does this really do anything useful?
    del df

    return aps, essids, nr_scans, nr_valid_scans

def fill_segment(row):

    if row['speeds'] == 0.0:
        return 0
    elif row['speeds'] < 2.0:
        return 1
    else:
        return 2

# identify and mark segments of different speeds in session data, in 
# a new column named 'segment_type'. the types are : 
#   - 0 : 0.0 : stationary
#   - 1 : 0.0 < speed < 2.0 m.sec-1 : walking speed
#   - 2 : 2.0 < speed : vehicular speed (including bikes)
def classify_segments(session_data):

    s = session_data[['seconds', 'new_lat', 'new_lon']]
    s['delta_t'] = s['seconds'].diff()

    lats   = s['new_lat']
    lons   = s['new_lon']
    # calculate distances between scans, given the 1st order differences
    # of latitude and longitudes
    # FIXME : we insert a dummy 0.0 value at the start of the array w/ np.insert()
    dist = np.insert(np.array(gps_to_dist(lats, lons, lats.shift(-1), lons.shift(-1))), 0, 0.0)
    # add distance and speed columns to s
    s['dist'] = dist[:-1]
    s['speeds'] = s['dist'] / s['delta_t']
    # add the speeds to session_data
    session_data['speeds'] = s['speeds']

    # isolate rows for which delta t > 0.0
    s = s[s['delta_t'] > 0.0]
    # identify segments of different speeds in s
    s['segment_type'] = s.apply(fill_segment, axis = 1)
    s['segments'] = (s.segment_type.shift(1) != s.segment_type).astype(int).cumsum()

    # find the indexes of the segments, and apply them to session_data
    segment_ixs = s.reset_index().groupby(['segment_type', 'segments'])['index'].apply(np.array)
    # finally, update session data w/ the segment type for the appropriate 
    # ranges of rows
    session_data['segment_type'] = 0
    for k, v in segment_ixs.iteritems():
        session_data.loc[v[0]:v[-1], 'segment_type'] = k[0]

def analyze_sessions(
    input_filename, 
    out_dir, 
    cell_size = 10.0,
    geo_limits = [PORTO_LATITUDE_LIMIT_NORTH, PORTO_LATITUDE_LIMIT_SOUTH, 
                    PORTO_LONGITUDE_LIMIT_WEST, PORTO_LONGITUDE_LIMIT_EAST]):

    """extracts selective stats from 'sense my city' sessions"""

    # keep track of general stats 
    # FIXME: keeping a list of essids and aps will take a lot of memory. also, 
    # our method to track aps isn't very accurate.
    aps = set([])
    essids = set([])
    scans = 0
    valid_scans = 0
    sessions = 0

    # ap stats stored in HDF5 format. here's why:
    #   - since ap_stats will involve the collection and manipulation of a 
    #     large amount of data (taken from the 'sense my city' dataset), we 
    #     keep it in disk instead of keeping it in memory.
    #   - the data can be left stored in a convenient way for further processing,
    #     without having to re-run the data collection again.
    ap_stats = pd.HDFStore(os.path.join(out_dir, "ap-stats.hdf5"))

    # given the large size of the input data file (> 3 GB), we read the file in chunks
    chunksize = 10 ** 5

    for chunk in pd.read_csv(input_filename, chunksize = chunksize):

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

            # identify and mark segments of different speeds in session data, in 
            # a new column named 'segment_type'. the types are : 
            #   - 0 : 0.0 : stationary
            #   - 1 : 0.0 < speed < 2.0 m.sec-1 : walking speed
            #   - 2 : 2.0 < speed : vehicular speed (including bikes)
            classify_segments(session_data)

            # extract statistics from dataset, which will be saved in an HDF5 
            # format
            a, e, s, v = extract_stats(session_data, cell_size, geo_limits, ap_stats)

            # FIXME : this will increase memory as script runs
            aps = aps.union(a)
            essids = essids.union(e)
            scans += s
            valid_scans += v
            sessions += 1

            print("channel_switch::analyze_sessions() : nr. of scans (valid scans) so far : %d (%d)" % (scans, valid_scans))

        if valid_scans > 500000:
            break

    # close .hdf5 file
    print(ap_stats)
    ap_stats.close()

    # append general statistics to a .csv file. each line indexed by a 
    # 'collection' id, which is an hash of the input parameters
    general_analysis = pd.DataFrame()
    general_analysis = general_analysis.append({
        'id' : get_analysis_id(
            [sys.argv[0], input_filename, cell_size, geo_limits, len(aps), len(essids), scans, valid_scans, sessions]),
        'gps-limits' : str(geo_limits),
        'nr-aps' : len(aps),
        'nr-essids' : len(essids),
        'nr-scans' : scans,
        'nr-valid' : valid_scans,
        'nr-sessions' : sessions 
        }, ignore_index = True)

    general_analysis_filename = os.path.join(out_dir, "general-analysis.csv")
    if os.path.exists(general_analysis_filename):
        general_analysis.to_csv(general_analysis_filename, mode = 'a', sep = ',', header = False)
    else:
        general_analysis.to_csv(general_analysis_filename, sep = ',')

# lambda function to calculate time differences in a list of timestamps
t_diff = lambda t : (t[-1] - t[0])

# extract data from an .hdf5 store to plot cdfs of:
#   - time intervals w/ same # of visible channels w/ rssi > threshold, per 10 x 10 m cell
#   - # of channels in said time intervals
# the data for each plot is subsequently saved in a separate .csv file
def extract_channel_conditions(out_dir, ap_stats, threshold = -65, band = 1):

    # find unique sessions in 'channels/<band>' dataset
    dataset = ('channels/%s' % (WIFI_BANDS[band]))
    sessions = ap_stats.select_column(dataset, 'session_id').unique()

    cdf_block_sizes = pd.DataFrame(columns = ['nr-freqs', 'cdf'])
    cdf_block_intervals = pd.DataFrame(columns = ['interval', 'cdf'])

    # collect snr intervals per session
    for session_id in sessions:
        # pull session data into memory
        sd = ap_stats.select(dataset, ("""session_id == '%d'""" % (session_id)))
        # sort the session data by cell and timestamp
        sd = sd.sort_values(['xy', 'ts'])

        for freq in WIFI_BANDS_COLUMNS[band][8:]:
            # get data for particular channel (freq) in sd
            fd = sd[['ts', 'xy', 'provider', 'mac_addr', 'essid', 'segment_type', freq]]
            # mark rows (above / below threshold) AND w/ (stationary / non-stationary 
            # category) as 1 / 0
            fd['above'] = 0
            fd.loc[(fd[freq] > threshold) & (fd['segment_type'] == 0), 'above'] = 1

            # finally, replace the freq column in sd w/ the 'above' column in fd
            sd[freq] = fd['above']

            del fd

        # to determine the nr. of channels w/ snr > threshold for a particular 
        # ['xy', 'ts'], we:
        #   - isolate columns 'ts', 'xy' and freqs in session data (just to 
        #     make things simple)
        sd = sd[['ts', 'xy'] + WIFI_BANDS_COLUMNS[band][8:]]
        #   - we aggregate rows by 'xy' and 'ts', summing the freq column values 
        #     (which have either 0 or 1, meaning snr > threshold on that freq 
        #     for ['xy', 'ts'])
        sd = sd.groupby(['xy', 'ts']).sum().reset_index()
        #   - since we may have more than 1 snr > threshold for the same 
        #     ['xy', 'ts'] on some freq, we sum the values on each row astype(bool)
        sd['nr_freqs'] = sd[WIFI_BANDS_COLUMNS[band][8:]].astype(bool).sum(axis = 1)
        print("channel_switch::freq_switches() : *** outlook for session %d ***" % (session_id))
        # print(sd['nr_freqs'])

        # now, we can collect 2 important statistics:
        #   - Q : for any cell (x,y), what is the distribution of simultaneous 
        #         channels w/ snr > threshold? 
        #     A : this looks at the values in sd['nr-freqs']

        #   - Q : for any cell (x,y), what is the duration of periods w/ 
        #         simultaneous channels?
        #     A : here we look at the duration of intervals of consecutive 
        #         rows w/ same sd['nr-freqs'] values

        if sd[sd['nr_freqs'] > 0].empty:
            print("channel_switch::freq_switches() : no snrs above %d dbm in session %d" % (threshold, session_id))
            del sd
            continue

        sd['block'] = (sd.nr_freqs.shift(1) != sd.nr_freqs).astype(int).cumsum()
        blocks = sd.reset_index().groupby(['xy', 'nr_freqs', 'block'])['ts'].apply(np.array).to_frame('interval').reset_index()
        blocks['interval'] = blocks['interval'].apply(t_diff)

        for index, row in blocks.iterrows():

            # for some reason, i keep getting negative intervals...
            if row['interval'] < 0.0:
                continue

            cdf_block_sizes = cdf_block_sizes.append({
                'nr-freqs' : row['nr_freqs'],
                'cdf' : 1.0
                }, ignore_index = True)

            cdf_block_intervals = cdf_block_intervals.append({
                'interval' : row['interval'],
                'cdf' : 1.0
                }, ignore_index = True)

        cdf_block_sizes = cdf_block_sizes.groupby('nr-freqs').sum().reset_index()
        cdf_block_intervals = cdf_block_intervals.groupby('interval').sum().reset_index()

        del blocks
        del sd

    # print(cdf_block_sizes)
    # print(cdf_block_intervals)

    # save in .csv file for quick plotting
    cdf_block_sizes.to_csv(os.path.join(out_dir, "block-sizes.csv"), sep = ',')
    cdf_block_intervals.to_csv(os.path.join(out_dir, "block-intervals.csv"), sep = ',')

def channel_conditions(out_dir, ap_stats, threshold = -65, band = 1):

    filenames = [os.path.join(out_dir, "block-sizes.csv"), os.path.join(out_dir, "block-intervals.csv")]
    if (not os.path.exists(filenames[0])) or (not os.path.exists(filenames[1])):
        extract_channel_conditions(out_dir, ap_stats, threshold, band)

    # load data from plot .csv files
    cdf_block_sizes = pd.read_csv(filenames[0])
    cdf_block_intervals = pd.read_csv(filenames[1])

    # the actual plots
    fig = plt.figure(figsize = (12, 5))    

    ax1 = fig.add_subplot(121)
    ax1.xaxis.grid(True)
    ax1.yaxis.grid(True)
    ax1.set_title("""time intervals w/ same # of channels\n > %d dBm, per 10 x 10 m cell\n""" % (threshold))

    # cumulative sum over all column values
    acc = np.array(cdf_block_intervals.loc[1:, 'cdf'].cumsum(), dtype = float)
    # scale column values by total sum (last element of cum. sum)
    acc = acc / acc[-1]
    # plot channel cdf
    ax1.plot(cdf_block_intervals.reset_index().loc[1:, 'interval'], acc, 
        alpha = 0.5, linewidth = 1.5, color = 'blue')

    ax1.set_xlabel("interval (seconds)")
    ax1.set_ylabel("cdf")

    ax1.legend(fontsize = 12, ncol = 1, loc='lower right')
    ax1.set_xlim(0.0, 500.0)
    ax1.set_ylim(0.0, 1.0)

    ax2 = fig.add_subplot(122)
    ax2.xaxis.grid(True)
    ax2.yaxis.grid(True)
    ax2.set_title("""# channels in time intervals,\nper 10 x 10 m cell\n""")

    # cumulative sum over all column values
    acc = np.array(cdf_block_sizes.loc[1:, 'cdf'].cumsum(), dtype = float)
    # scale column values by total sum (last element of cum. sum)
    acc = acc / acc[-1]
    # plot channel cdf
    ax2.plot(cdf_block_sizes.reset_index().loc[1:, 'nr-freqs'], acc, 
        alpha = 0.5, linewidth = 1.5, color = 'blue')

    ax2.set_xlabel("# of channels in time interval")
    ax2.set_ylabel("cdf")

    ax2.legend(fontsize = 12, ncol = 1, loc='lower right')
    ax2.set_xticks(np.arange(1, 7, 1))
    ax2.set_xlim(1, 5)
    ax2.set_ylim(0.0, 1.0)

    fig.tight_layout()
    fig.subplots_adjust(top = 0.95)

    plt.savefig(os.path.join(out_dir, "../../graphs/channel-variation.pdf"), bbox_inches = 'tight', format = 'pdf')
    plt.close('all')

# extract data from an .hdf5 store to plot cdfs of:
#   - time intervals for which channel x's rssi > threshold, per 10 x 10 m cell
# the data for each plot is subsequently saved in a separate .csv file
def extract_channel_intervals(out_dir, ap_stats, threshold = -65, band = 1):

    cdf = pd.DataFrame(columns = ['interval'] + WIFI_BANDS_COLUMNS[band][8:])

    # find unique sessions in 'channels/<band>' dataset
    dataset = ('channels/%s' % (WIFI_BANDS[band]))
    sessions = ap_stats.select_column(dataset, 'session_id').unique()
    # print("channel_switch::snr_intervals_cdf() : %d sessions identified" % (len(sessions)))

    # collect snr intervals per session
    for session_id in sessions:
        # pull session data into memory
        sd = ap_stats.select(dataset, ("""session_id == '%d'""" % (session_id)))

        for freq in WIFI_BANDS_COLUMNS[band][8:]:

            # get data for particular channel (freq) in sd
            fd = sd[['ts', 'xy', 'provider', 'mac_addr', 'essid', 'segment_type', freq]]
            # sort fd by ts, for each visible 'ap'
            # we approx. an ap by the combo [mac addr, essid]
            fd = fd.sort_values(['essid', 'mac_addr', 'ts'])
            # mark rows (above / below threshold) AND w/ (stationary / non-stationary 
            # category) as 1 / 0
            fd['above'] = 0
            fd.loc[(fd[freq] > threshold) & (fd['segment_type'] == 0), 'above'] = 1
            # if no rows above threshold, abort
            if fd[fd['above'] == 1].empty:
                # print("channel_switch::snr_intervals_cdf() : no rows above %d dbm for session (%d, %s)" % (threshold, session_id, freq))
                del fd
                continue

            print("channel_switch::snr_intervals_cdf() : *** looking at (session id, freq) : (%d, %s) ***" % (session_id, freq))
            
            # identify the periods of time for which the channel is above the 
            # threshold, i.e. we identify the segments of contiguous rows which 
            # have the same value in the column 'above' have the same value. 
            # the next 2 lines are based on this great post on stackoverflow.com :
            # https://stackoverflow.com/questions/14358567/finding-consecutive-segments-in-a-pandas-data-frame
            fd['block'] = (fd.above.shift(1) != fd.above).astype(int).cumsum()
            snr_intervals = fd.reset_index().groupby(['above', 'block'])['ts'].apply(np.array).to_frame('interval').reset_index()
            # print(snr_intervals)

            # for each row (w/ a collection of timestamps in column 'interval'), 
            # calculate the interval duration by applying difference between 
            # final and initial timestamps in column 'interval'
            snr_intervals['interval'] = snr_intervals['interval'].apply(t_diff)
            
            # print(snr_intervals[snr_intervals['above'] == 1])
            # print("channel_switch::snr_intervals_cdf() : max. snr interval : %.1f" % (snr_intervals[snr_intervals['above'] == 1]['interval'].max()))
            # print("channel_switch::snr_intervals_cdf() : session duration : %d" % (sd['ts'].iloc[-1] - sd['ts'].iloc[0]))
            # max_snr_interval = snr_intervals[snr_intervals['above'] == 1]['interval'].max()
            # session_duration = float(sd['ts'].iloc[-1] - sd['ts'].iloc[0])
            # print("channel_switch::snr_intervals_cdf() : Q : max snr interval < session duration ? A : %s" % 
            #     ("TRUE" if (max_snr_interval <= session_duration) else "FALSE"))
        
            # finally, update the cdf dataframe
            snr_intervals = snr_intervals[snr_intervals['above'] == 1]
            for index, row in snr_intervals.iterrows():

                # for some reason, i keep getting negative intervals...
                if row['interval'] < 0.0:
                    continue

                cdf = cdf.append({
                    'interval' : row['interval'],
                    freq : 1.0
                    }, ignore_index = True)

            cdf = cdf.groupby('interval').sum().reset_index()

            del fd
            del snr_intervals

        del sd

    # print(cdf)
    cdf = cdf.fillna(0.0)
    cdf.to_csv(os.path.join(out_dir, "channel-intervals.csv"), sep = ',')

def channel_intervals(out_dir, ap_stats, threshold = -65, band = 1):

    filenames = [os.path.join(out_dir, "channel-intervals.csv")]
    if (not os.path.exists(filenames[0])):
        extract_channel_intervals(out_dir, ap_stats, threshold, band)

    # load data from plot .csv files
    cdf = pd.read_csv(filenames[0])

    # the actual plots
    fig = plt.figure(figsize = (6, 5))    

    ax = fig.add_subplot(111)
    ax.xaxis.grid(True)
    ax.yaxis.grid(True)

    ax.set_title("""time intervals w/ signal strength > %d dBm,\nper channel and [essid, MAC] combo\n""" % (threshold))

    # freqs = WIFI_BANDS_COLUMNS[band][8:10] + WIFI_BANDS_COLUMNS[band][13:15] + [WIFI_BANDS_COLUMNS[band][18]] + [WIFI_BANDS_COLUMNS[band][20]]
    freqs = WIFI_BANDS_COLUMNS[band][8:]

    color_map = plt.get_cmap('RdYlGn')
    colors = [color_map(i) for i in np.linspace(0, 1, len(freqs))]

    for i, freq in enumerate(freqs):

        # cumulative sum over all column values : nr. of intervals collected 
        # for given frequency
        acc = np.array(cdf.loc[1:, freq].cumsum(), dtype = float)
        print("channels::channel_intervals() : %s : %d" % (freq, acc[-1]))
        # scale column values by total sum (last element of cum. sum)
        acc = acc / acc[-1]
        # plot channel cdf
        ax.plot(cdf.reset_index().loc[1:, 'interval'], acc, 
            alpha = 0.5, linewidth = 2.0, color = matplotlib.colors.rgb2hex(colors[i][:3]), label = WIFI_CHANNELS[band][freq])

    ax.set_xlabel("interval (seconds)")
    ax.set_ylabel("cdf")

    ax.legend(fontsize = 12, ncol = 1, loc='lower right')
    ax.set_xlim(0.0, 80.0)
    ax.set_ylim(0.0, 1.0)

    fig.tight_layout()
    fig.subplots_adjust(top = 0.95)

    plt.savefig(os.path.join(out_dir, "../../graphs/channel-intervals.pdf"), bbox_inches = 'tight', format = 'pdf')
    plt.close('all')

# print a box plot of channel signal strengths, divided by public and private networks
def channel_ss(out_dir, ap_stats, band = 1):

    # space in-between boxes
    space = 0.5
    # colors for public and private boxes
    colors = ['lightgreen', 'lightblue']

    for provider in WIFI_PROVIDERS.keys() + ['all']:

        # set provider string
        provider_str = ""
        if provider == 'all':
            provider_str = 'all'
        else:
            provider_str = WIFI_PROVIDERS[provider][0]

        print("channels::channel_ss() : plotting provider : %s" % (provider_str))

        fig = plt.figure(figsize = (12, 12))
        # save ax objects in a list, for a posteriori editing
        axes = []

        # plot a different graph for each segment type
        for segment_type in SEGMENT_TYPES:

            ax = fig.add_subplot(311 + segment_type)
            axes.append(ax)
            ax.xaxis.grid(True)
            ax.yaxis.grid(True)
            if segment_type == 0:
                if provider == 'all':
                    ax.set_title("""signal strength for all wifi networks\nstationary""")
                else:
                    ax.set_title("""signal strength for wifi networks of provider '%s'\nstationary""" 
                        % (provider_str))
            else:
                ax.set_title("""%s scanner""" % (SEGMENT_TYPES[segment_type].replace("-", " ")))

            xticklabels = []
            medians = []
            i = 0
            for freq in WIFI_BANDS_COLUMNS[band][8:]:

                # alternate between snr values of public and private essids
                f = 0
                for access in xrange(2):

                    # query differs if a specific provider is specified
                    query = ""
                    if provider == 'all':
                        query = ("""segment_type == %d and columns == ['%s'] and access == '%d.0'""" 
                            % (segment_type, freq, access))
                    else:
                        query = ("""provider == %d and segment_type == %d and columns == ['%s'] and access == '%d.0'""" 
                            % (provider, segment_type, freq, access))
                    # extract snrs specific freq. (and drop the NaN values w/ dropna())
                    snrs = ap_stats.select(('channels/%s' % (WIFI_BANDS[band])), query).dropna()
                    # some sessions are polluted w/ 0.0 snrs : filter them
                    snrs = snrs[snrs[freq] < 0.0]

                    if not snrs.empty:
                        # a boxplot
                        bxplot = ax.boxplot(
                            snrs.values, 
                            positions = [ (2 * i) + (access * space) ],
                            showfliers = False,
                            patch_artist = True,
                            widths = 0.25)

                        # keep track of the medians for each box
                        medians.append(bxplot['medians'][0].get_ydata()[0])
                        
                        # flags an added box
                        f += 1
                        
                        # add color to the boxes
                        for patch, color in zip(bxplot['boxes'], colors):
                            patch.set_facecolor(colors[access])

                    # do this to force garbage collection and free memory
                    # FIXME: does this really do anything?
                    del snrs

                # add an xtick label for freq if at least 1 box has been added
                if f > 0:
                    if band == 1:
                        xticklabels.append(((int(freq.lstrip('f')) - int(WIFI_BANDS_COLUMNS[band][8].lstrip('f'))) / 5) + 1)
                    else:
                        xticklabels.append(int(freq.lstrip('f')))
                    i += 1

            # custom legend using matplotlib.patches
            # https://stackoverflow.com/questions/39500265/manually-add-legend-items-python-matplotlib
            patches = [matplotlib.patches.Patch(color='lightgreen', label = 'public'), matplotlib.patches.Patch(color='lightblue', label = 'private')]
            ax.legend(handles = patches, fontsize = 16, ncol = 1, loc='upper right')

            ax.set_xlim(-1.0, (2 * i))
            ax.set_xticks(np.arange((space / 2.0), (2 * i + 1) + (space / 2.0), 2))
            ax.set_xticklabels(xticklabels)

            ax.set_xlabel("channels")
            ax.set_ylabel("signal strength (dBm)")

            if medians:
                # plot an horizontal span of the median range
                ax.axhspan(min(medians), max(medians), linewidth = 0.0, facecolor = 'pink', alpha = 0.35)

        # set the same axis limits, ticks and labels for all ax in axes
        
        # # x_lim
        # x_max = []
        # x_min = []
        # y_lim
        y_max = []
        y_min = []
        # # xticks and labels
        # xticks_pos = 0
        # xticks_len = -1

        for i, ax in enumerate(axes):
            # x_min.append(ax.get_xlim()[0])
            # x_max.append(ax.get_xlim()[1])
            y_min.append(ax.get_ylim()[0])
            y_max.append(ax.get_ylim()[1])
            # if len(ax.get_xticks()) > xticks_len:
            #     xticks_pos = i

        for ax in axes:
            # ax.set_xlim(min(x_min), max(x_max))
            ax.set_ylim(min(y_min), max(y_max))
            # ax.set_xticks(axes[xticks_pos].get_xticks())
            # ax.set_xticks(axes[xticks_pos].get_xticks())

        fig.tight_layout()
        fig.subplots_adjust(top = 0.95)

        plt.savefig(os.path.join(out_dir, ("../../graphs/channel-snrs/channel-snr-%s.pdf" % (provider_str))), bbox_inches = 'tight', format = 'pdf')
        plt.close('all')

def plot(out_dir, cell_size = 10.0, geo_limits = []):

    """plots stats from 'sense my city' sessions"""

    if not geo_limits:
        map_ctr = [PORTO_LATITUDE, PORTO_LONGITUDE, 14.5]
    else:
        map_ctr = [((geo_limits[0] + geo_limits[1]) / 2.0), ((geo_limits[2] + geo_limits[3]) / 2.0), 16]

    # load the .hdf5 store
    ap_stats = None
    filename = os.path.join(out_dir, 'ap-stats.hdf5')
    if (not os.path.exists(filename)):
        sys.stderr.write("""%s: [ERROR] no .hdf5 files found\n""" % sys.argv[0]) 
        sys.exit(1)
    else:
        ap_stats = pd.HDFStore(os.path.join(out_dir, 'ap-stats.hdf5'))

    # channel_ss(out_dir, ap_stats, band = 2)
    channel_intervals(out_dir, ap_stats, band = 2)
    channel_conditions(out_dir, ap_stats, band = 2)
