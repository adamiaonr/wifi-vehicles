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

from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict

# custom imports
from plot_utils import *

matplotlib.rcParams.update({'font.size': 16})

# gps coords for a 'central' pin on porto, portugal
porto_lat = 41.163158
porto_lon = -8.6127137

# ds - distance travelled by the user during the scanning period
# acc_scan - mean accuracy from the GPS during the scanning period
# new_err - mean error related to the map matching process (was conducted by others)
# new_lat | new_lot - location where the scan was associated
# g_lat | g_lon - cell location
# auth - authentication mode (0 - Unknown, 1 - Open, 2 - WEP, 3 - WPA, 4 - WPA2, 5 - Enterprise (RADIUS/.11x/Other).)
# session_id - identifies the trip

def to_radians(degrees):
    return (degrees * math.pi / 180.0)

def dist_gps(lat_start, lon_start, lat_end, lon_end):

    # we use the haversine formula to calculate the great-circle distance between two points. 
    # in other words, this calculates the lenght of the shortest arch in-between 2 points, in 
    # a 'great' circle of radius equal to 6371 (the radius of the earth) 
    # source : http://www.movable-type.co.uk/scripts/latlong.html

    # earth radius, in m
    earth_radius = 6371000

    delta_lat = to_radians(lat_end - lat_start)
    delta_lon = to_radians(lon_end - lon_start)

    lat_start = to_radians(lat_start)
    lat_end = to_radians(lat_end)

    a = (np.sin(delta_lat / 2.0) * np.sin(delta_lat / 2.0)) + (np.sin(delta_lon / 2.0) * np.sin(delta_lon / 2.0)) * np.cos(lat_start) * np.cos(lat_end)
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))

    return earth_radius * c

def extract_scanning_distances(data, session_id, median_scanning_dist):

    # extract (valid) scanning distances
    scanning_dist = float(data['ds'].median())
    if scanning_dist > 0.0 and not math.isnan(scanning_dist):
        median_scanning_dist[session_id] = scanning_dist

def extract_median_speeds(data, session_id, median_speeds):

    # get start and end latitudes and longitudes of the scans
    #   - we measure the distance in-between data points. 
    #   - we use the .shift(-1) method to align the start and end columns, and feed them directly to 
    #     the dist_gps() method
    lat_start   = np.array(data['new_lat'])
    lon_start   = np.array(data['new_lon'])
    lat_end     = np.array(data['new_lat'].shift(-1))
    lon_end     = np.array(data['new_lon'].shift(-1))

    # get start and end timestamps (using the .shift(-1) method as above)
    time_start = np.array(data['seconds'])
    time_end = np.array(data['seconds'].shift(-1))

    # calculate and extract (valid) median speeds for the session
    speeds = dist_gps(lat_start[:-1], lon_start[:-1], lat_end[:-1], lon_end[:-1]) / (time_end[:-1] - time_start[:-1])
    # print("session_analysis::extract_median_speeds() : speeds[%s] = %s" % (session_id, str([s for s in np.sort(speeds) if not math.isnan(s)])))
    median_speed = float(np.nanmedian(speeds))

    if median_speed > 0.0 and not math.isnan(median_speed):
        median_speeds[session_id] = median_speed

def extract_ap_stats(data, session_id, ap_mapping_info):

    # get unique mac addresses of aps
    mac_addrs = data['encode'].unique()

    # get data sorted by mac addr and time
    ap_data = data.sort(['encode', 'seconds'])

    print("session_analysis::extract_ap_stats() : (session_id %s) getting ap records %d macs addrs..." % (session_id, len(mac_addrs)))
    start = time.time()

    # for each unique ap mac address, extract first and last 'sensing' event
    ap_stats = []

    for mac in mac_addrs:

        # get data for a specific mac address
        mac_data = ap_data.loc[ap_data['encode'] == mac]
    
        if len(mac_data) < 2:
            continue

        # extract start and end data for mac
        start_time, start_lat, start_lon = mac_data.iloc[0][['seconds', 'new_lat', 'new_lon']]
        end_time, end_lat, end_lon = mac_data.iloc[-1][['seconds', 'new_lat', 'new_lon']]

        # update the ap_mapping_info table
        if mac not in ap_mapping_info:

            ap_mapping_info[mac] = defaultdict()

            ap_mapping_info[mac]['auth'] = ''
            ap_mapping_info[mac]['essid'] = str(mac_data.iloc[0]['essid']).lower().replace("_", "-")
            ap_mapping_info[mac]['gps_lat'] = ''
            ap_mapping_info[mac]['gps_lon'] = ''

        # build the authentication method set for this mac addr
        auth = set(ap_mapping_info[mac]['auth'].split(':'))
        for a in mac_data['auth']:
            auth.add(str(a))
        ap_mapping_info[mac]['auth'] = ':'.join([a for a in auth])
        # add measured gps coords to a list of observed coords
        ap_mapping_info[mac]['gps_lat'] += ':' + ':'.join([str(l) for l in mac_data['new_lat']])
        ap_mapping_info[mac]['gps_lon'] += ':' + ':'.join([str(l) for l in mac_data['new_lon']])

        # we use the list of dicts method to fill pandas dataframe
        coverage_dist = dist_gps(start_lat, start_lon, end_lat, end_lon)
        coverage_time = (end_time - start_time)

        ap_stats.append({
            'session_id' : session_id, 
            'essid' : mac_data.iloc[0]['essid'],
            'mac_addr' : mac,
            'auth' : mac_data.iloc[0]['auth'],
            'coverage_time' : coverage_time, 
            'coverage_dist' : coverage_dist, 
            'coverage_speed' : (coverage_dist / coverage_time)})

    print("... done (%d secs)" % (time.time() - start))

    return pd.DataFrame(ap_stats)

def draw_on_map(ap_mapping_info, top_networks, out_dir):

    # authentication gps coordinates
    auth_gps_lats = defaultdict(list)
    auth_gps_lons = defaultdict(list)

    # top wifi networks gps coordinates
    nw_gps_lats = defaultdict(list)
    nw_gps_lons = defaultdict(list)

    # auth - authentication mode (0 - unknown, 1 - open, 2 - WEP, 3 - WPA, 4 - WPA2, 5 - enterprise (RADIUS/.11x/Other).)
    auth_colors = { '0' : 'gray', '1' : 'green', '2' : 'black', '3' : 'red', '4' : 'blue', '5' : 'orange' }

    # for each ap, extract the auth method and then median of the observed gps coordinates
    ap_locations = []
    top_networks_locations = []

    for ap in ap_mapping_info:

        auth = ap_mapping_info[ap]['auth'].lstrip(':').split(':')

        if len(auth) > 1:

            # in case the first authentication method is 'unknown', use the 'other' one
            if auth[0] == '0':
                auth[0] = auth[1]
            else:
                print("session_analysis::draw_on_map() : [WARNING] (mac addr : %s) auth list w/ more than 1 value : %s" % (ap, ap_mapping_info[ap]['auth']))
                continue

        # extract gps location of ap (from median of 'sensed' coords)
        gps_lat = np.median(np.array([float(l) for l in  ap_mapping_info[ap]['gps_lat'].lstrip(':').split(':')]))
        gps_lon = np.median(np.array([float(l) for l in  ap_mapping_info[ap]['gps_lon'].lstrip(':').split(':')]))

        # update the gps coord arrays which will be used in the gmap plots
        auth_gps_lats[auth[0]].append(gps_lat)
        auth_gps_lons[auth[0]].append(gps_lon)

        # if the ap belongs to the list of top networks, add it
        if ap_mapping_info[ap]['essid'] in top_networks:
            nw_gps_lats[ap_mapping_info[ap]['essid']].append(gps_lat)
            nw_gps_lons[ap_mapping_info[ap]['essid']].append(gps_lon)

        # update ap_locations
        ap_locations.append({'mac_addr' : ap, 'auth' : auth[0], 'gps_lat' : gps_lat, 'gps_lon' : gps_lon})

    # save ap_locations in .csv file
    ap_locations = pd.DataFrame(ap_locations)
    processed_dir = os.path.join(out_dir, 'processed')
    ap_locations.to_csv(os.path.join(processed_dir, 'ap_locations.csv'), sep = ',')

    # print the ap locations on the map
    for auth in auth_gps_lats:

        gmap = gmplot.GoogleMapPlotter(porto_lat, porto_lon, 14)
        gmap.scatter(auth_gps_lats[auth], auth_gps_lons[auth], auth_colors[auth], marker = False)
        gmap.draw(os.path.join(out_dir, 'ap_locations_' + str(auth) + '.html'))


    # get a suitable color map for multiple bars
    color_map = plt.get_cmap('jet')
    colors = [color_map(i) for i in np.linspace(0, 1, len(top_networks))]

    for i, network in enumerate(top_networks):

        gmap = gmplot.GoogleMapPlotter(porto_lat, porto_lon, 14)
        # gmap.scatter(nw_gps_lats[network], nw_gps_lons[network], str(matplotlib.colors.rgb2hex(colors[i])), marker = False)
        gmap.heatmap(nw_gps_lats[network], nw_gps_lons[network])
        gmap.draw(os.path.join(out_dir, 'top_network_locations_' + network.replace(" ", "_") + '.html'))

    return ap_locations

def analyze_sessions(file_name, out_dir, session_stats, processed_files, median_speed_thrshld = 5.5):

    session_ids = set()

    # we use hash tables to gather data, convert them to dataframes later
    session_stats['median_scanning_dist'] = defaultdict()
    session_stats['median_speeds'] = defaultdict()

    # map on which to draw 'fast' ap locations
    ap_mapping_info = defaultdict()

    # given the large size of the input data file (> 3 GB), we read the file in chunks
    chunksize = 10 ** 5
    for chunk in pd.read_csv(file_name, chunksize = chunksize):

        # # some pandas bs about numeric values...
        # chunk = chunk.convert_objects(convert_numeric = True)
        # find unique session ids on this chunk
        chunk_session_ids = chunk['session_id'].unique()

        # find if any of the session ids overlaps, update the median scanning dist value 
        # if that's the case
        intersection = list(session_ids & set(chunk_session_ids))

        if len(intersection) > 0:
            print("session_analysis::analyze_sessions() : found %d intersections : %s" % (len(intersection), str(intersection)))

        # for each overlapping session_id, update the ds value
        for session_id in intersection:

            # FIXME: idk why, but the code crashes for these session ids. easy way out...
            if session_id in ['117971']:
                continue

            # update the median scanning distance for session_id
            dfs = [prev_chunk.loc[chunk['session_id'] == session_id]['ds'], chunk.loc[chunk['session_id'] == session_id]['ds']]
            session_stats['median_scanning_dist'][session_id] = float(pd.concat(dfs).median())

            # FIXME: do the same for median speeds

        print("session_analysis::analyze_sessions() : %d sessions found in chunk" % (len(chunk_session_ids)))

        # for each session, find the median scanning_dist values, add it to a list
        for session_id in chunk_session_ids:

            print("session_analysis::analyze_sessions() : analyzing session_id %s" % (session_id))

            # add session id to visited session id list
            session_ids.add(session_id)

            # to make it easier, extract session data first
            session_data = chunk.loc[chunk['session_id'] == session_id]

            # extract scanning distances and median speeds for the session
            extract_scanning_distances(session_data, session_id, session_stats['median_scanning_dist'])
            extract_median_speeds(session_data, session_id, session_stats['median_speeds'])

            # stats about aps (for sessions w/ median speeds above 20 km/h)
            if (session_id in session_stats['median_speeds']) and (session_stats['median_speeds'][session_id] > median_speed_thrshld):
                
                # extract statistics about aps
                print("session_analysis::analyze_sessions() : [%s] %s" % (session_id, session_stats['median_speeds'][session_id]))
                session_stats['ap_stats'] = session_stats['ap_stats'].append(extract_ap_stats(session_data, session_id, ap_mapping_info), ignore_index = True)

        # if 303 in session_ids:
        #     break

        # keep track of pervious chunk to keep track of overlapping 
        # sessions in-between chunks
        prev_chunk = chunk

    # convert dict to pandas dataframes
    session_stats['median_scanning_dist'] = pd.DataFrame(session_stats['median_scanning_dist'].items(), columns = ['session_id', 'ds'])
    session_stats['median_speeds'] = pd.DataFrame(session_stats['median_speeds'].items(), columns = ['session_id', 'speed'])

    # save processed data in .csv files
    session_stats['median_scanning_dist'].to_csv(processed_files['median_scanning_dist'], sep = ',')
    session_stats['median_speeds'].to_csv(processed_files['median_speeds'], sep = ',')
    session_stats['ap_stats'].to_csv(processed_files['ap_stats'], sep = ',')

    # draw map in html file

    # wifi networks, sorted by nr. of aps
    top_networks = session_stats['ap_stats'].groupby('essid')['essid'].count().sort_values()
    # labels of top 10 wifi networks, by nr. of aps
    top_networks = [str(ssid.lower().replace("_", "-")) for ssid in top_networks.iloc[-10:].index.format()]

    session_stats['ap_locations'] = draw_on_map(ap_mapping_info, top_networks, out_dir)

def plot(file_name, out_dir):

    """extracts bunch of stats from 'sense my city' sessions"""

    # save post-processed data in dict of pandas dataframes
    session_stats = defaultdict()
    session_stats['ap_stats'] = pd.DataFrame()

    # in order to save time, we save the post-processed data used in plots 
    # on .csv files 
    processed_dir = os.path.join(out_dir, "processed")
    processed_files = {
        'median_scanning_dist' : os.path.join(processed_dir, 'session_median_scanning_dist.csv'),
        'median_speeds' : os.path.join(processed_dir, 'session_median_speeds.csv'),
        'ap_stats' : os.path.join(processed_dir, 'session_ap_stats.csv'),
        'ap_locations' : os.path.join(processed_dir, 'ap_locations.csv')
    }

    # check if .csv files already exist in out_dir/processed. if that's the case, 
    # we just read these files and plot
    if not (set(processed_files.values()).issubset(set([f for f in sorted(glob.glob(os.path.join(processed_dir, '*.csv')))]))):
        analyze_sessions(file_name, out_dir, session_stats, processed_files)

    print("session_analysis::plot() : reading data from processed .csv files")

    for stat in processed_files:
        session_stats[stat] = pd.read_csv(processed_files[stat])

    # get a suitable color map for multiple bars
    color_map = plt.get_cmap('Blues')
    colors = [color_map(i) for i in np.linspace(0, 1, 10)]

    # plot session ap stats histograms (per mac addr.)
    fig_1 = plt.figure(figsize = (18, 10))

    ax1 = fig_1.add_subplot(231)
    ax1.set_title('(a) median time within range \nof AP, over all sessions')

    ax1.xaxis.grid(True)
    ax1.yaxis.grid(True)

    ax1.hist(session_stats['ap_stats']['coverage_time'], bins = np.arange(0, max(session_stats['ap_stats']['coverage_time']), 1), normed = 1, histtype = 'step', cumulative = True, rwidth = 0.8, color = 'darkblue')
    ax1.set_xlabel("time within range (s)")
    ax1.set_ylabel("CDF")
    # ax1.set_xticks(np.arange(0, 200 + 20, step = 20))
    ax1.set_xticks([0, 10, 20, 30, 40, 50, 100, 150, 200])
    ax1.set_xticklabels([0, 10, 20, 30, 40, 50, 100, 150, 200], rotation = 45)


    ax1.set_xlim(0, 150)
    ax1.set_ylim(0, 1.0)

    ax2 = fig_1.add_subplot(232)
    ax2.set_title('(b) median distance covered while within \nrange of AP, over all sessions')

    ax2.xaxis.grid(True)
    ax2.yaxis.grid(True)
    ax2.hist(session_stats['ap_stats']['coverage_dist'], bins = np.arange(0, max(session_stats['ap_stats']['coverage_dist']), 1), normed = 1, histtype = 'step', cumulative = True, rwidth = 0.8, color = 'darkblue')
    ax2.set_xlabel("distance (m)")
    ax2.set_ylabel("CDF")
    ax2.set_xticks(np.arange(0, 700 + 100, step = 100))

    ax2.set_xlim(0, 700)
    ax2.set_ylim(0, 1.0)

    ax3 = fig_1.add_subplot(233)
    ax3.set_title('(c) median speed while in range \nof AP, over all sessions')

    ax3.xaxis.grid(True)
    ax3.yaxis.grid(True)
    ax3.hist(session_stats['ap_stats']['coverage_speed'], bins = np.arange(0, max(session_stats['ap_stats']['coverage_speed']), 1), normed = 1, histtype = 'step', cumulative = True, rwidth = 0.8, color = 'darkblue')
    ax3.set_xlabel("contact speed (m/s)")
    ax3.set_ylabel("CDF")
    ax3.set_xticks(np.arange(0, 100 + 5, step = 10))

    ax3.set_xlim(0, 100)
    ax3.set_ylim(0, 1.0)

    # get unique mac addresses of aps
    ax4 = fig_1.add_subplot(234)
    ax4.set_title('(d) # of APs w/ \nauthentication method x')

    ax4.xaxis.grid(False)
    ax4.yaxis.grid(True)
    ax4.hist(session_stats['ap_locations']['auth'], bins = np.arange(0, 6 + 1, 1), histtype = 'bar', rwidth = 0.8, alpha = 0.55, color = 'darkblue')
    ax4.set_xlabel("authentication method")
    ax4.set_ylabel("# of APs")

    ax4.set_xticks([0.5, 1.5, 2.5, 3.5, 4.5, 5.5])
    ax4.set_xticklabels(['n/a', 'open', 'wep', 'wpa', 'wpa2', 'enter.'])

    # nr. of APs per WiFi network (identified by SSID)
    ax5 = fig_1.add_subplot(235)
    ax5.set_title('(e) # of APs per WiFi \nnetwork (per SSID)')

    ax5.xaxis.grid(True)
    ax5.yaxis.grid(True)

    df = session_stats['ap_stats'].groupby('essid')['essid'].count()

    ax5.hist(df, bins = np.arange(0, max(df), 1), normed = 1, histtype = 'step', cumulative = True, rwidth = 0.8, color = 'darkblue')
    ax5.set_xlabel("# of APs per WiFi network")
    ax5.set_ylabel("CDF")
    ax5.set_xticks(np.arange(0, 50 + 5, step = 5))

    ax5.set_xlim(0, 50)
    ax5.set_ylim(0, 1.0)

    ax6 = fig_1.add_subplot(236)
    ax6.set_title('(f) # of APs on 10 \nlargest WiFi networks')

    ax6.xaxis.grid(False)
    ax6.yaxis.grid(True)

    # wifi networks, sorted by nr. of aps
    df = session_stats['ap_stats'].groupby('essid')['essid'].count().sort_values()
    # labels of top 10 wifi networks, by nr. of aps
    labels = df.iloc[-10:].index.format()

    for i in np.arange(0, 10, 1):
        ax6.bar(i, df.iloc[len(df) - (10 - i) - 1], alpha = 0.55, width = 0.75, label = labels[i].lower().replace("_", "-"), color = colors[i])

    ax6.legend(fontsize = 12, ncol = 1, loc='upper left')

    ax6.set_xlabel("wifi network")
    ax6.set_ylabel("# of APs")
    ax6.set_xticks(np.arange(0, 10, 1) + (0.75 / 2.0))
    ax6.set_xticklabels(np.arange(0, 10, 1))

    ax6.set_yscale("log")
    # ax6.tick_params(axis = 'y', which = 'minor')

    ax6.set_xlim(-(0.25 / 1.0), 10)
    ax6.set_ylim(100, 1000000)

    fig_1.tight_layout()
    fig_1.subplots_adjust(top = 0.95)

    plt.savefig(os.path.join(out_dir, "sessions-aps.pdf"), bbox_inches = 'tight', format = 'pdf')    