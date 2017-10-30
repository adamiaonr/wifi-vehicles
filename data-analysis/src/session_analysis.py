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

# for maps
import pdfkit

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
PORTO_LATITUDE = 41.163158
PORTO_LONGITUDE = -8.6127137

# for Tomas et al. trilateration technique
PWR_TRNSMT = 17.00 # avg. transmit power
PATH_LOSS_CONSTANT = -147.55
PATH_LOSS_EXPONENT = 3.0
FREQ_WIFI = (2450.0 * 1000000.0)

TOP_NETWORK_SSIDS = [
    'guestsmp',
    'meo-casa',
    'minedu',
    'wifi porto digital',
    'meo-wifi.x'
    'stcp-mp',
    'meo-wifi-premium'
    'eduroam'
    'meo-wifi',
    'fon-zon-free-internet']

# in order to save time, we save the post-processed data used in plots 
# on .csv files 
OUTPUT_DIR = '/home/adamiaonr/workbench/wifi-authentication/data-analysis/graphs'

processed_dir = os.path.join(OUTPUT_DIR, "processed")
processed_files = {
    'median_scanning_dist' : os.path.join(processed_dir, 'session_median_scanning_dist.csv'),
    'median_speeds' : os.path.join(processed_dir, 'session_median_speeds.csv'),
    'ap_stats' : os.path.join(processed_dir, 'session_ap_stats.csv'),
    'ap_locations' : os.path.join(processed_dir, 'ap_locations.csv'),
    'rssi' : os.path.join(processed_dir, 'rssi.csv')
}

file_lock = mp.Lock()

# info about the sense-my-city dataset
#   ds : distance travelled by the user during the scanning period
#   acc_scan : mean accuracy from the GPS during the scanning period
#   new_err : mean error related to the map matching process (was conducted by others)
#   new_lat | new_lot : location where the scan was associated
#   g_lat | g_lon : cell location
#   auth : authentication mode (0 - Unknown, 1 - Open, 2 - WEP, 3 - WPA, 4 - WPA2, 5 - Enterprise (RADIUS/.11x/Other).)
#   session_id : identifies the trip

def ap_location_merge(a, b):

    for mac in b:

        if mac not in a:
            a[mac] = b[mac]

        else:

            # find the set of authentication methods detected on this mac addr
            auth = set(a[mac]['auth'].split(':'))
            for ath in b[mac]['auth'].split(':'):
                auth.add(str(ath))
            a[mac]['auth'] = ':'.join([ath for ath in auth])

            for speed_profile in ['p', 'v']:

                if speed_profile not in b[mac]['data']:
                    continue

                prev_lat    = a[mac]['data'][speed_profile]['gps_lat']
                prev_lon    = a[mac]['data'][speed_profile]['gps_lon']
                prev_radius = a[mac]['data'][speed_profile]['radius']

                # x, y, min_radius = calc_ap_location({
                #                                 'gps_lat': prev_lat     + list(mac_data['new_lat']), 
                #                                 'gps_lon': prev_lon     + list(mac_data['new_lon']),
                #                                 'radius' : prev_radius  + list(calc_radius(mac_data['snr'].values))})

                next_lat, next_lon, min_radius = calc_ap_location_median({
                                                'gps_lat': prev_lat     + b[mac]['data'][speed_profile]['gps_lat'], 
                                                'gps_lon': prev_lon     + b[mac]['data'][speed_profile]['gps_lon']})

                # print("""session_analysis::draw_on_map() : [INFO] location of ap w/ mac %s : 
                #     \t[GPS COORDS] = {%f, %f}
                #     \t[AREA] = %f""" % (
                #     ap,
                #     ap_location.y, ap_location.x,
                #     ap_location.area))

                a[mac]['data'][speed_profile]['gps_lat'] = [next_lat]
                a[mac]['data'][speed_profile]['gps_lon'] = [next_lon]
                a[mac]['data'][speed_profile]['radius']  = [min_radius]

def rssi_merge_and_sum(a, b):

    for rssi in b['p']:
        a['p'][rssi] += b['p'][rssi]

    for rssi in b['v']:
        a['v'][rssi] += b['v'][rssi]

def extract_rssi(data, median_speed):

    rssi_data = {'p': defaultdict(int), 'v': defaultdict(int)}

    for rssi in data['snr'].values:

        if median_speed < 4:
            rssi_data['p'][rssi] += 1
        else:
            rssi_data['v'][rssi] += 1

    # rssi_rows = []
    # for speed_profile in rssi_data:
    #     for dbm in rssi_data[speed_profile]:
    #         rssi_rows.append({'dbm': dbm, 'nr_scans': rssi_data[speed_profile][dbm], 'speed_profile': speed_profile})

    # rssi_data = pd.DataFrame(rssi_rows)

    # if os.path.exists(processed_files['rssi']):
    #     print("file name %s exists" % (processed_files['rssi']))
    #     rssi_data.to_csv(processed_files['rssi'], mode = 'a', sep = ',', header = False)
    # else:
    #     print("file name %s does NOT exist" % (processed_files['rssi']))
    #     rssi_data.to_csv(processed_files['rssi'], sep = ',')

    return rssi_data

def extract_scanning_distances(data, session_id):

    median_scanning_dist = defaultdict()

    # extract (valid) scanning distances
    scanning_dist = float(data['ds'].median())

    if scanning_dist > 0.0 and not math.isnan(scanning_dist):
        median_scanning_dist[session_id] = scanning_dist

    median_scanning_dist = pd.DataFrame(median_scanning_dist.items(), columns = ['session_id', 'ds'])

    if os.path.exists(processed_files['median_scanning_dist']):
        median_scanning_dist.to_csv(processed_files['median_scanning_dist'], mode = 'a', sep = ',', header = False)
    else:
        median_scanning_dist.to_csv(processed_files['median_scanning_dist'], sep = ',')

def extract_median_speeds(data, session_id):

    median_speeds = defaultdict()

    # get start and end latitudes and longitudes of the scans
    #   - we measure the distance in-between data points. 
    #   - we use the .shift(-1) method to align the start and end columns, and feed them directly to 
    #     the gps_to_dist() method
    lat_start   = np.array(data['new_lat'])
    lon_start   = np.array(data['new_lon'])
    lat_end     = np.array(data['new_lat'].shift(-1))
    lon_end     = np.array(data['new_lon'].shift(-1))

    # get start and end timestamps (using the .shift(-1) method as above)
    time_start = np.array(data['seconds'])
    time_end = np.array(data['seconds'].shift(-1))

    # calculate and extract (valid) median speeds for the session
    speeds = gps_to_dist(lat_start[:-1], lon_start[:-1], lat_end[:-1], lon_end[:-1]) / (time_end[:-1] - time_start[:-1])
    # print("session_analysis::extract_median_speeds() : speeds[%s] = %s" % (session_id, str([s for s in np.sort(speeds) if not math.isnan(s)])))
    median_speed = float(np.nanmedian(speeds))

    if median_speed > 0.0 and not math.isnan(median_speed):
        median_speeds[session_id] = median_speed

    median_speeds_df = pd.DataFrame(median_speeds.items(), columns = ['session_id', 'speed'])

    if os.path.exists(processed_files['median_speeds']):
        median_speeds_df.to_csv(processed_files['median_speeds'], mode = 'a', sep = ',', header = False)
    else:
        median_speeds_df.to_csv(processed_files['median_speeds'], sep = ',')

    return median_speeds

def calc_radius(
    measured_snrs, 
    power_transmit = PWR_TRNSMT, 
    path_loss_constant = PATH_LOSS_CONSTANT, 
    freq_wifi = FREQ_WIFI, 
    path_loss_exponent = PATH_LOSS_EXPONENT):

    e = math.log(10.0) * (power_transmit - measured_snrs - path_loss_constant - (20.0 * math.log10(freq_wifi)))
    e = e / (10.0 * path_loss_exponent)
    radius = np.power(10, e)

    # if any(x > -50 for x in measured_snrs):
    #     print("session_analysis::calc_radius() : measured snrs = %s" % (str(measured_snrs)))
    #     print("session_analysis::calc_radius() : exponents = %s" % (str(e)))
    #     print("session_analysis::calc_radius() : radius = %s" % (str(radius)))

    return radius

def plot_radius(out_dir, ax = None):

    measured_snrs = np.arange(0, -120, -1)

    # create a new figure() if a axis object is not
    # passed as argument
    new_plot = False
    if ax is None:

        # set guard variable
        new_plot = True

        fig = plt.figure(figsize = (6, 5))

        ax = fig.add_subplot(111)
        ax.xaxis.grid(True)
        ax.yaxis.grid(True)

    ax.plot(measured_snrs, calc_radius(measured_snrs), color = 'blue', label = 'path loss exp. = 3')
    ax.plot(measured_snrs, calc_radius(measured_snrs, path_loss_exponent = 4), color = 'red', label = 'ple = 4')

    ax.legend(fontsize = 12, ncol = 1, loc='upper right')

    if new_plot:
        ax.set_title('log distance path loss model')
    else:
        ax.set_title('(h) log distance path loss model')

    ax.set_xlabel("rssi (dBm)")
    ax.set_ylabel("dist. from source (m)")

    # ax1.set_xticks(np.arange(0, 200 + 20, step = 20))
    ax.set_xticks([0, -20, -40, -60, -80, -100, -120])

    ax.set_xlim(-120, 0)
    ax.set_ylim(0.01, math.pow(10, 8))
    ax.set_yscale("log")

    if new_plot is True:
        fig.tight_layout()
        fig.subplots_adjust(top = 0.95)
        plt.savefig(os.path.join(out_dir, "path-loss-distances.pdf"), bbox_inches = 'tight', format = 'pdf')

# implementation of trilateration procedure by Tomas et al.
def calc_ap_location(ap_location_data, mode = 'scf'):

    # get list of gps coordinates of ap
    gps_lat = ap_location_data['gps_lat']
    gps_lon = ap_location_data['gps_lon']

    # get the corresponding delta in coordinates. to do this, 
    # we use the radius value as a great circle distance. we convert 
    # the radius value to calculate the central angle between the gps 
    # coordinates given above and any point in a circunference of 
    # radius centered on the same coordinates. 
    delta_angle = central_angle(np.array(ap_location_data['radius']))

    # select the starting circle ('smallest circle first' strategy)
    start_circle_index = ap_location_data['radius'].index(min(ap_location_data['radius']))
    # set initial state of the intersection to the scf circle
    intersection = Point(gps_lon[start_circle_index], gps_lat[start_circle_index]).buffer(delta_angle[start_circle_index])
    # save the intersection of scf with all other circles
    for i in np.arange(1, len(gps_lat)):

        # generate current circle
        curr_circle = Point(gps_lon[i], gps_lat[i]).buffer(delta_angle[i])

        # if the curr circle and intersection aren't disjoint,
        # update the intersection
        if curr_circle.disjoint(intersection):
            continue

        intersection = intersection.intersection(curr_circle)

        # print("""session_analysis::calc_ap_location() : [INFO] intersection info : 
        #     \t[GPS COORDS] = {%f, %f}
        #     \t[AREA] = %f""" % (
        #     intersection.centroid.x, intersection.centroid.y,
        #     intersection.area))

    # the centroid of intersection is the most probable location of the ap
    return intersection.centroid.x, intersection.centroid.y, ap_location_data['radius'][start_circle_index]

def calc_ap_location_median(ap_location_data, mode = 'scf'):

    # get list of gps coordinates of ap
    gps_lat = ap_location_data['gps_lat']
    gps_lon = ap_location_data['gps_lon']

    # the centroid of intersection is the most probable location of the ap
    return np.median(ap_location_data['gps_lat']), np.median(ap_location_data['gps_lon']), 0.0

def extract_ap_stats(session_id, session_data, median_speed, ap_location_data):

    # get unique mac addresses of aps
    mac_addrs = session_data['encode'].unique()
    # get data sorted by mac addr and time
    ap_data = session_data.sort(['encode', 'seconds'])

    print("session_analysis::extract_ap_stats() : (session_id %s) getting ap records %d macs addrs..." % (session_id, len(mac_addrs)))
    start = time.time()

    # for each unique ap mac address, extract first and last 'sensing' event
    ap_stats = []
    for mac in mac_addrs:

        # get ap data for a specific mac address
        mac_data = ap_data.loc[ap_data['encode'] == mac]
        # skip ap data with less than 2 records
        if len(mac_data) < 2:
            continue

        # extract start and end data for mac
        start_time, start_lat, start_lon = mac_data.iloc[0][['seconds', 'new_lat', 'new_lon']]
        end_time, end_lat, end_lon = mac_data.iloc[-1][['seconds', 'new_lat', 'new_lon']]

        speed_profile = ''
        if median_speed < 4:
            speed_profile = 'p'
        else:
            speed_profile = 'v'

        # extract the wifi ssi for the current mac addr (why?)
        # newtork_ssid = str(mac_data.iloc[0]['essid']).lower().replace("_", "-")

        # update the ap_location_data table
        if mac not in ap_location_data:

            ap_location_data[mac] = defaultdict()

            ap_location_data[mac]['auth'] = ''
            ap_location_data[mac]['essid'] = str(mac_data.iloc[0]['essid']).lower().replace("_", "-")

            # location data per AP includes 3 lists of variables. each i-th value of the
            # list corresponds to the same i-th scanning record:
            #   - list of gps coordinates where the mac addr detected (note: NOT the location of 
            #     the ap itself), both latitude (gps_lat) and longitude (gps_lon)
            #   - list of radius of a circle on which the ap might likely be located, derived 
            #     from the log distance path loss formula
            ap_location_data[mac]['data'] = defaultdict()
            ap_location_data[mac]['data']['p'] = {'gps_lat': [], 'gps_lon': [], 'radius': []}
            ap_location_data[mac]['data']['v'] = {'gps_lat': [], 'gps_lon': [], 'radius': []}

        # find the set of authentication methods detected on this mac addr
        auth = set(ap_location_data[mac]['auth'].split(':'))
        for a in mac_data['auth']:
            auth.add(str(a))
        ap_location_data[mac]['auth'] = ':'.join([a for a in auth])

        # to avoid excessive memory consumption, we apply Boris' trilateration algo
        # partially, over each session
        prev_lat    = ap_location_data[mac]['data'][speed_profile]['gps_lat']
        prev_lon    = ap_location_data[mac]['data'][speed_profile]['gps_lon']
        prev_radius = ap_location_data[mac]['data'][speed_profile]['radius']

        # x, y, min_radius = calc_ap_location({
        #                                 'gps_lat': prev_lat     + list(mac_data['new_lat']), 
        #                                 'gps_lon': prev_lon     + list(mac_data['new_lon']),
        #                                 'radius' : prev_radius  + list(calc_radius(mac_data['snr'].values))})

        next_lat, next_lon, min_radius = calc_ap_location_median({
                                        'gps_lat': prev_lat     + list(mac_data['new_lat']), 
                                        'gps_lon': prev_lon     + list(mac_data['new_lon'])})

        # print("""session_analysis::draw_on_map() : [INFO] location of ap w/ mac %s : 
        #     \t[GPS COORDS] = {%f, %f}
        #     \t[AREA] = %f""" % (
        #     ap,
        #     ap_location.y, ap_location.x,
        #     ap_location.area))

        # add location data
        ap_location_data[mac]['data'][speed_profile]['gps_lat'] = [next_lat]
        ap_location_data[mac]['data'][speed_profile]['gps_lon'] = [next_lon]
        ap_location_data[mac]['data'][speed_profile]['radius']  = [min_radius]

        # we use the list of dicts method to fill pandas dataframe
        coverage_dist = gps_to_dist(start_lat, start_lon, end_lat, end_lon)
        coverage_time = (end_time - start_time)

        ap_stats.append({
            'session_id' : session_id, 
            'essid' : mac_data.iloc[0]['essid'],
            'mac_addr' : mac,
            'auth' : mac_data.iloc[0]['auth'],
            'coverage_time' : coverage_time, 
            'coverage_dist' : coverage_dist, 
            'coverage_speed' : (coverage_dist / coverage_time),
            'speed_profile': speed_profile})

    ap_stats = pd.DataFrame(ap_stats)

    if os.path.exists(processed_files['ap_stats']):
        ap_stats.to_csv(processed_files['ap_stats'], mode = 'a', sep = ',', header = False)
    else:
        ap_stats.to_csv(processed_files['ap_stats'], sep = ',')

    print("... done (%d secs)" % (time.time() - start))

    return ap_location_data

def draw_on_map(ap_location_data, out_dir = OUTPUT_DIR):

    # extract top wifi networks
    ap_stats = pd.read_csv(processed_files['ap_stats'])
    # wifi networks, sorted by nr. of aps
    top_networks = ap_stats.groupby('essid')['essid'].count().sort_values()
    # labels of top 10 wifi networks, by nr. of aps
    top_networks = [str(ssid.lower().replace("_", "-")) for ssid in top_networks.iloc[-10:].index.format()]

    # authentication gps coordinates
    auth_lats = defaultdict(list)
    auth_lons = defaultdict(list)

    # top wifi networks locations
    top_network_locations = defaultdict()

    # auth - authentication mode (0 - unknown, 1 - open, 2 - WEP, 3 - WPA, 4 - WPA2, 5 - enterprise (RADIUS/.11x/Other).)
    auth_colors = { '0' : 'gray', '1' : 'green', '2' : 'black', '3' : 'red', '4' : 'blue', '5' : 'orange' }

    # for each ap, extract the auth method and then median of the observed gps coordinates
    ap_locations = []

    for ap in ap_location_data:

        # if the ap belongs to the list of top networks, add it
        if ap_location_data[ap]['essid'] in top_networks:

            if ap_location_data[ap]['essid'] not in top_network_locations:
                top_network_locations[ap_location_data[ap]['essid']] = defaultdict()

                top_network_locations[ap_location_data[ap]['essid']]['p'] = {'lat': [], 'lon': []}
                top_network_locations[ap_location_data[ap]['essid']]['v'] = {'lat': [], 'lon': []}

            for speed_profile in ['p', 'v']:

                if len(ap_location_data[ap]['data'][speed_profile]['gps_lat']) > 0:
                    top_network_locations[ap_location_data[ap]['essid']][speed_profile]['lat'].append(
                        ap_location_data[ap]['data'][speed_profile]['gps_lat'][0])
                    top_network_locations[ap_location_data[ap]['essid']][speed_profile]['lon'].append(
                        ap_location_data[ap]['data'][speed_profile]['gps_lon'][0])

        # update ap_locations
        auth = ap_location_data[ap]['auth'].lstrip(':').split(':')

        for a in auth:

            if len(ap_location_data[ap]['data']['p']['gps_lat']) > 0:
                ap_locations.append({'mac_addr' : ap, 'auth' : a, 
                    'gps_lat' : ap_location_data[ap]['data']['p']['gps_lat'][0], 
                    'gps_lon' : ap_location_data[ap]['data']['p']['gps_lon'][0]})
            else:
                ap_locations.append({'mac_addr' : ap, 'auth' : a, 
                    'gps_lat' : ap_location_data[ap]['data']['v']['gps_lat'][0], 
                    'gps_lon' : ap_location_data[ap]['data']['v']['gps_lon'][0]})

    # save ap_locations in .csv file
    ap_locations = pd.DataFrame(ap_locations)
    processed_dir = os.path.join(out_dir, 'processed')
    ap_locations.to_csv(os.path.join(processed_dir, 'ap_locations.csv'), sep = ',')

    # # print the ap locations on the map
    # for auth in auth_lats:
    #     gmap = gmplot.GoogleMapPlotter(PORTO_LATITUDE, PORTO_LONGITUDE, 14)
    #     gmap.scatter(auth_lats[auth], auth_lons[auth], auth_colors[auth], marker = False)
    #     gmap.draw(os.path.join(out_dir, 'ap_locations_' + str(auth) + '.html'))

    # get a suitable color map for multiple bars
    color_map = plt.get_cmap('jet')
    colors = [color_map(i) for i in np.linspace(0, 1, len(top_networks))]

    for i, network in enumerate(top_networks):

        gmap = gmplot.GoogleMapPlotter(PORTO_LATITUDE, PORTO_LONGITUDE, 14)

        # print heatmap of scan locations
        # gmap.heatmap(top_network_locations[network]['scan_lat'], top_network_locations[network]['scan_lon'], threshold = 5)
        # gmap.scatter(top_network_locations[network]['scan_lat'], top_network_locations[network]['scan_lon'], size = 5, color = 'darkblue', marker = False)

        # print ap locations
        speed_profile_colors = {'p': 'red', 'v': 'green'}
        for speed_profile in ['p', 'v']:
            gmap.scatter(top_network_locations[network][speed_profile]['lat'], top_network_locations[network][speed_profile]['lon'], 
                size = 5, color = speed_profile_colors[speed_profile], marker = False)

        # save .html version of map
        filename = os.path.join(out_dir, 'top_network_locations_' + network.replace(" ", "_"))
        gmap.draw(filename + '.html')

    return ap_locations

def handle_session(session_id, chunk, ap_location_data):

    print("session_analysis::handle_session() : analyzing session_id %s" % (session_id))

    # extract session data first
    session_data = chunk.loc[chunk['session_id'] == session_id]

    # extract scanning distances and median speeds for the session
    extract_scanning_distances(session_data, session_id)
    median_speeds = extract_median_speeds(session_data, session_id)

    # print("data structs lenght: ")
    # print("\tmedian_scanning_dist : %d" % (len(session_stats['median_scanning_dist'])))
    # print("\tmedian_speeds : %d" % (len(session_stats['median_speeds'])))

    rssi_data = {'p': defaultdict(int), 'v': defaultdict(int)}

    if session_id in median_speeds:

        # extract statistics about aps
        print("session_analysis::handle_session() : [%s] %s" % (session_id, median_speeds[session_id]))
        extract_ap_stats(session_id, session_data, median_speeds[session_id], ap_location_data)
        # extract rssi from valid sessions
        rssi_data = extract_rssi(session_data, median_speeds[session_id])

    return (session_id, ap_location_data, rssi_data)

def analyze_sessions(file_name, out_dir, session_stats, processed_files, median_speed_thrshld = 5.5):

    session_ids = set()

    # we use hash tables to gather data, convert them to dataframes later
    session_stats['median_scanning_dist'] = defaultdict()
    session_stats['median_speeds'] = defaultdict()
    session_stats['rssi'] = {'p': defaultdict(int), 'v': defaultdict(int)}

    # map on which to draw 'fast' ap locations
    ap_location_data = defaultdict()

    # given the large size of the input data file (> 3 GB), we read the file in chunks
    chunksize = 10 ** 5
    prev_chunk = None

    for chunk in pd.read_csv(file_name, chunksize = chunksize):

        # find unique session ids on this chunk
        chunk_session_ids = chunk['session_id'].unique()

        # find if any of the session ids overlaps, update the median scanning dist value 
        # if that's the case
        intersection = list(session_ids & set(chunk_session_ids))

        if len(intersection) > 0:
            print("session_analysis::analyze_sessions() : found %d intersections : %s" % (len(intersection), str(intersection)))

        # # for each overlapping session_id, update the ds value
        # for session_id in intersection:

        #     # FIXME: idk why, but the code crashes for these session ids. easy way out...
        #     if session_id in ['117971']:
        #         continue

        #     # update the median scanning distance for session_id
        #     dfs = [prev_chunk.loc[chunk['session_id'] == session_id]['ds'], chunk.loc[chunk['session_id'] == session_id]['ds']]
        #     session_stats['median_scanning_dist'][session_id] = float(pd.concat(dfs).median())

        #     # FIXME: do the same for median speeds, you might be losing a lot of data here...

        print("session_analysis::analyze_sessions() : %d sessions found in chunk" % (len(chunk_session_ids)))

        # create pool of threads for multiprocessing of sessions
        pool = mp.Pool(mp.cpu_count())
        # add session analysis tasks to a list, which will then be handled 
        # in parallel by different threads
        session_tasks = []

        for session_id in chunk_session_ids:

            # add session id to visited session id list
            session_ids.add(session_id)
            # add a session handling task to the list of tasks
            session_tasks.append((session_id, chunk, ap_location_data))

        # unleash the parallel processing!
        jobs_remaining = len(session_tasks)
        results = [pool.apply_async(handle_session, t) for t in session_tasks]

        # print status of parallel processing
        for result in results:
            jobs_remaining = jobs_remaining - 1
            (_session_id, _ap_location_data, _rssi_data) = result.get()

            if _session_id is not None:
                
                print("finished processing session_id %s. %d jobs remaining." 
                    % (_session_id, jobs_remaining))

                ap_location_merge(ap_location_data, _ap_location_data)
                rssi_merge_and_sum(session_stats['rssi'], _rssi_data)

        pool.close()
        pool.join()

        if 303 in session_ids:
            break

        # keep track of pervious chunk to keep track of overlapping 
        # sessions in-between chunks
        prev_chunk = chunk

    # # convert dict to pandas dataframes
    # session_stats['median_scanning_dist'] = pd.DataFrame(session_stats['median_scanning_dist'].items(), columns = ['session_id', 'ds'])
    # session_stats['median_speeds'] = pd.DataFrame(session_stats['median_speeds'].items(), columns = ['session_id', 'speed'])

    rssi_rows = []
    for speed_profile in session_stats['rssi']:
        for dbm in session_stats['rssi'][speed_profile]:
            rssi_rows.append({'dbm': dbm, 'nr_scans': session_stats['rssi'][speed_profile][dbm], 'speed_profile': speed_profile})
    session_stats['rssi'] = pd.DataFrame(rssi_rows)
    session_stats['rssi'].to_csv(processed_files['rssi'], sep = ',')

    # # save processed data in .csv files
    # session_stats['median_scanning_dist'].to_csv(processed_files['median_scanning_dist'], sep = ',')
    # session_stats['median_speeds'].to_csv(processed_files['median_speeds'], sep = ',')
    # session_stats['ap_stats'].to_csv(processed_files['ap_stats'], sep = ',')

    # draw map in html file
    session_stats['ap_locations'] = draw_on_map(ap_location_data, out_dir)

def plot_coverage_time(figure, session_stats):

    ax1 = figure.add_subplot(331)
    ax1.set_title('(a) median time within range \nof AP, over all sessions')

    ax1.xaxis.grid(True)
    ax1.yaxis.grid(True)

    ax1.hist(session_stats['coverage_time'], 
        bins = np.arange(0, max(session_stats['coverage_time']), 1), normed = 1, histtype = 'step', cumulative = True, 
        rwidth = 0.8, color = 'darkblue', label = 'total')

    # pedestrian and vehicular median speeds
    speed_profile_colors = {'p': 'red', 'v': 'green'}
    speed_profile_labels = {'p': 'pedestrian', 'v': 'vehicular'}
    for speed_profile in ['p', 'v']:

        df = session_stats.loc[session_stats['speed_profile'] == speed_profile]
        ax1.hist(df['coverage_time'], 
            bins = np.arange(0, max(session_stats['coverage_time']), 1), normed = 1, histtype = 'step', cumulative = True, 
            rwidth = 0.8, color = speed_profile_colors[speed_profile], label = speed_profile_labels[speed_profile])

    ax1.legend(fontsize = 12, ncol = 1, loc='lower right')

    ax1.set_xlabel("time within range (s)")
    ax1.set_ylabel("CDF")
    # ax1.set_xticks(np.arange(0, 200 + 20, step = 20))
    ax1.set_xticks([0, 10, 20, 30, 40, 50, 100, 150, 200])
    ax1.set_xticklabels([0, 10, 20, 30, 40, 50, 100, 150, 200], rotation = 45)

    ax1.set_xlim(0, 150)
    ax1.set_ylim(0, 1.0)

def plot_coverage_dist(figure, session_stats):

    ax2 = figure.add_subplot(332)
    ax2.set_title('(b) median distance covered while within \nrange of AP, over all sessions')

    ax2.xaxis.grid(True)
    ax2.yaxis.grid(True)

    ax2.hist(session_stats['coverage_dist'], 
        bins = np.arange(0, max(session_stats['coverage_dist']), 1), normed = 1, histtype = 'step', cumulative = True, 
        rwidth = 0.8, color = 'darkblue', label = 'total')

    # pedestrian and vehicular median speeds
    speed_profile_colors = {'p': 'red', 'v': 'green'}
    speed_profile_labels = {'p': 'pedestrian', 'v': 'vehicular'}
    for speed_profile in ['p', 'v']:

        df = session_stats.loc[session_stats['speed_profile'] == speed_profile]
        ax2.hist(df['coverage_dist'], 
            bins = np.arange(0, max(session_stats['coverage_dist']), 1), normed = 1, histtype = 'step', cumulative = True, 
            rwidth = 0.8, color = speed_profile_colors[speed_profile], label = speed_profile_labels[speed_profile])

    ax2.legend(fontsize = 12, ncol = 1, loc='lower right')

    ax2.set_xlabel("distance (m)")
    ax2.set_ylabel("CDF")
    ax2.set_xticks(np.arange(0, 700 + 100, step = 100))

    ax2.set_xlim(0, 700)
    ax2.set_ylim(0, 1.0)

def plot_coverage_speed(figure, session_stats):

    ax3 = figure.add_subplot(333)
    ax3.set_title('(c) median speed while in range \nof AP, over all sessions')

    ax3.xaxis.grid(True)
    ax3.yaxis.grid(True)

    ax3.hist(session_stats['coverage_speed'], 
        bins = np.arange(0, max(session_stats['coverage_speed']), 1), normed = 1, histtype = 'step', cumulative = True, 
        rwidth = 0.8, color = 'darkblue', label = 'total')

    # pedestrian and vehicular median speeds
    speed_profile_colors = {'p': 'red', 'v': 'green'}
    speed_profile_labels = {'p': 'pedestrian', 'v': 'vehicular'}
    for speed_profile in ['p', 'v']:

        df = session_stats.loc[session_stats['speed_profile'] == speed_profile]
        ax3.hist(df['coverage_speed'], 
            bins = np.arange(0, max(session_stats['coverage_speed']), 1), normed = 1, histtype = 'step', cumulative = True, 
            rwidth = 0.8, color = speed_profile_colors[speed_profile], label = speed_profile_labels[speed_profile])

    ax3.legend(fontsize = 12, ncol = 1, loc='lower right')

    ax3.set_xlabel("contact speed (m/s)")
    ax3.set_ylabel("CDF")
    ax3.set_xticks(np.arange(0, 100 + 5, step = 10))

    ax3.set_xlim(0, 100)
    ax3.set_ylim(0, 1.0)

def plot(file_name, out_dir):

    """extracts bunch of stats from 'sense my city' sessions"""

    # save post-processed data in dict of pandas dataframes
    session_stats = defaultdict()
    session_stats['ap_stats'] = pd.DataFrame()

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
    fig_1 = plt.figure(figsize = (18, 15))

    plot_coverage_time(fig_1, session_stats['ap_stats'])
    plot_coverage_dist(fig_1, session_stats['ap_stats'])
    plot_coverage_speed(fig_1, session_stats['ap_stats'])

    # get unique mac addresses of aps
    ax4 = fig_1.add_subplot(334)
    ax4.set_title('(d) # of APs w/ \nauthentication method x')

    ax4.xaxis.grid(False)
    ax4.yaxis.grid(True)
    ax4.hist(session_stats['ap_locations']['auth'], 
        bins = np.arange(0, 6 + 1, 1), histtype = 'bar', rwidth = 0.8, alpha = 0.55, color = 'darkblue')
    ax4.set_xlabel("authentication method")
    ax4.set_ylabel("# of APs")

    ax4.set_xticks([0.5, 1.5, 2.5, 3.5, 4.5, 5.5])
    ax4.set_xticklabels(['n/a', 'open', 'wep', 'wpa', 'wpa2', 'enter.'])

    # nr. of APs per WiFi network (identified by SSID)
    ax5 = fig_1.add_subplot(335)
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

    ax6 = fig_1.add_subplot(336)
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

    # # distribution of scanned snrs
    # fig_2 = plt.figure(figsize = (6, 5))

    ax7 = fig_1.add_subplot(337)
    ax7.xaxis.grid(True)
    ax7.yaxis.grid(True)

    # total
    df = session_stats['rssi'].groupby(['dbm'])['nr_scans'].sum()
    acc = np.array(df.cumsum(), dtype = float)
    acc = acc / acc[-1]
    ax7.plot(df.index.values.tolist(), acc, alpha = 0.5, linewidth = 1.5, color = 'darkblue', label = 'total')

    # pedestrian and vehicular median speeds
    speed_profile_colors = {'p': 'red', 'v': 'green'}
    speed_profile_labels = {'p': 'pedestrian', 'v': 'vehicular'}
    for speed_profile in ['p', 'v']:

        df = session_stats['rssi'].loc[session_stats['rssi']['speed_profile'] == speed_profile]
        acc = np.array(df['nr_scans'].cumsum(), dtype = float)
        print(acc)
        acc = acc / acc[-1]
        ax7.plot(df['dbm'], acc, 
            alpha = 0.5, linewidth = 1.5, color = speed_profile_colors[speed_profile], 
            label = speed_profile_labels[speed_profile])

    ax7.legend(fontsize = 12, ncol = 1, loc='lower right')

    ax7.set_title("(g) freq. of measured rssi values")
    ax7.set_xlabel("rssi value (dBm)")
    ax7.set_ylabel("CDF")

    ax8 = fig_1.add_subplot(338)
    ax8.xaxis.grid(True)
    ax8.yaxis.grid(True)

    plot_radius(out_dir, ax8)

    # fig_2.tight_layout()
    # fig_2.subplots_adjust(top = 0.95)

    # plt.savefig(os.path.join(out_dir, "rssi-distribution.pdf"), bbox_inches = 'tight', format = 'pdf')

    fig_1.tight_layout()
    fig_1.subplots_adjust(top = 0.95)

    plt.savefig(os.path.join(out_dir, "sessions-aps.pdf"), bbox_inches = 'tight', format = 'pdf')
