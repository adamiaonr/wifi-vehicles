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
from datetime import timedelta

from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple

from matplotlib.gridspec import GridSpec

from prettytable import PrettyTable

# list of metrics : 
# ['no', 'Arrival Time', 'time', 'Protocol', 'src mac', 'dst mac', 
# 'Source', 'Destination', 'Type/Subtype', 'Length', 'Retry', 'Signal strength (dBm)', 
# 'Type', 'radiotap.length', 'wlan_radio.duration', 'Data rate', 'SSI Signal', 'PHY type', 
# 'wlan_radio.preamble', 'wlan.duration', 'Info']

# list of wlan frame types : 
# set(['VHT NDP Announcement', 'Reassociation Response', 'QoS Data', 
#     'Authentication', 'Action No Ack', 'Reassociation Request', 
#     '802.11 Block Ack', 'Data + CF-Ack + CF-Poll', 'Probe Response', 
#     '45', 'CF-Ack/Poll (No data)', 'Association Response', 'Measurement Pilot', 
#     'QoS CF-Ack + CF-Poll (No data)', 'QoS Data + CF-Poll', 'Request-to-send', '7', 
#     'Beamforming Report Poll', 'QoS Null function (No data)', 'Association Request', 
#     'Data', 'CF-Poll (No data)', 'CF-End (Control-frame)', 'Power-Save poll', 'Deauthentication', 
#     'Beacon frame', 'Action', 'Probe Request', 'Acknowledgement (No data)', '802.11 Block Ack Req', 
#     'QoS Data + CF-Acknowledgment', 'QoS CF-Poll (No Data)', 'Disassociate', 'Data + CF-Ack', 
#     'CF-End + CF-Ack (Control-frame)', 'ATIM', 'Null function (No data)', 'Data + CF-Poll', 
#     'QoS Data + CF-Ack + CF-Poll', 'Service Period Request', 'Aruba Management'])

matplotlib.rcParams.update({'font.size': 16})

# mac address of ap
ap = '24:05:0f:61:51:14'
# mac addresses of clients (side-of-the-road)
clients = OrderedDict()
clients['24:05:0f:9e:2c:b1'] = {'id' : 0, 'label' : 'pos. 0', 'color' : 'red',     'lat' : 41.178433, 'lon' : -8.594942}
clients['24:05:0f:aa:ab:5d'] = {'id' : 1, 'label' : 'pos. 1', 'color' : 'green',   'lat' : 41.178516, 'lon' : -8.595371}
clients['b8:27:eb:1e:2b:6a'] = {'id' : 2, 'label' : 'pos. 2', 'color' : 'blue',    'lat' : 41.178599, 'lon' : -8.595299}

def to_radians(degrees):
    return (degrees * math.pi / 180.0)

def to_degrees(radians):
    return (radians / (math.pi / 180.0))

def gps_to_dist(lat_start, lon_start, lat_end, lon_end):

    # use the Haversine formula to calculate the great-circle distance between two points on a sphere. 
    # in other words, this calculates the lenght of the shortest arch in-between 2 points in 
    # a 'great' circle of radius equal to 6371 km (the approximate radius of the Earth).
    # source : http://www.movable-type.co.uk/scripts/latlong.html

    # approx. earth radius, in meters
    earth_radius = 6371000

    delta_lat = to_radians(lat_end - lat_start)
    delta_lon = to_radians(lon_end - lon_start)

    lat_start = to_radians(lat_start)
    lat_end   = to_radians(lat_end)

    # Haversine formula
    a = (np.sin(delta_lat / 2.0) * np.sin(delta_lat / 2.0)) + (np.sin(delta_lon / 2.0) * np.sin(delta_lon / 2.0)) * np.cos(lat_start) * np.cos(lat_end)
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))

    return earth_radius * c

def update_limits(limits, array):

    if not limits:
        limits.append(np.amin(array))
        limits.append(np.amax(array))
    else:
        if np.amin(array) < limits[0]:
            limits[0] = np.amin(array)
        if np.amax(array) > limits[1]:
            limits[1] = np.amax(array)

def get_best_ap(data, metric = 'SSI Signal'):

    # cstr : column name which identifies a client
    # tstr : column name for timestamp
    cstr = ''
    tstr = ''
    if 'src mac' in data.columns:
        cstr = 'src mac'
        tstr = 'timestamp'
    else:
        cstr = 'client'
        tstr = 'timestamp'

    best_ap = pd.DataFrame(columns = [tstr])
    for client in clients:
        
        # filter wlan frames sent by client
        _bap = data[data[cstr] == client][[tstr, metric]]
        # get 'best' metric value per timestamp (10 ms precision) 
        _bap[client] = _bap.groupby([tstr])[metric].transform(max)
        # merge all 'best' values of all clients
        best_ap = pd.merge(_bap.drop_duplicates(subset = tstr)[[tstr, client]], best_ap, on = tstr, how = 'outer')

    # get mac of client w/ 'best' metric value for each timestamp
    best_ap[metric] = best_ap[[client for client in clients]].idxmax(axis = 1)
    return best_ap[[tstr, metric]]

def get_metrics(input_dir, output_dir, 
    metrics = { 'link-data' : ['SSI Signal', 'Data rate'], 'iperf3' : ['res-bw', 'loss', 'total'] }, 
    channels = {'2.4' : ['1', '11'], '5.1' : ['36'], '5.2' : ['40']},
    ap = ap, limits = None, seconds = 120):

    """extracts metrics from .csv files of traces, returns a dictionary of DataFrame"""

    pcap_file   = os.path.join(args.input_dir, ("link-data.csv"))
    gps_file    = os.path.join(args.input_dir, ("gps-log.csv"))

    # best aps per timestamp, for each metric
    # best_aps = defaultdict(pd.DataFrame)
    # save results as .hdf5 file instead
    best_aps = pd.HDFStore(os.path.join(input_dir, "processed/best-aps.hdf5"))
    # aux. variable holds reference timestamp
    the_epoch = datetime.utcfromtimestamp(0)

    # 1) data from pcap files (in .csv format)
    chunksize = 10 ** 5
    for chunk in pd.read_csv(pcap_file, chunksize = chunksize):

        # consider frames directed at the mobile ap only
        chunk = chunk[chunk['dst mac'] == ap]
        # discard empty rssi values
        chunk = chunk[np.isfinite(chunk['SSI Signal'])]
        # isolate UNIX timestamps w/ 10 msec precision
        chunk['timestamp'] = chunk['Arrival Time'].map(lambda x : str((datetime.strptime(str(x)[:-12], '%b %d, %Y %H:%M:%S.%f') - the_epoch).total_seconds()))

        # determine which client has the 'best' for each metric of interest
        for metric in metrics['link-data']:

            if metric not in chunk.columns:
                continue

            # best_aps[metric] = pd.concat([best_aps[metric], get_best_ap(chunk, metric)], ignore_index = True)
            baps = get_best_ap(chunk, metric).sort_values(by = ['timestamp'])
            best_aps.append(
                ('%s' % (metric)),
                baps,
                data_columns = baps.columns,
                format = 'table')

        del chunk

    # 2) data from iperf3 files
    data = defaultdict()
    for client in clients:
        for freq in ['2.4', '5.1', '5.2']:

            if freq not in data:
                data[freq] = defaultdict()

            for channel in channels[freq]:

                if channel not in data[freq]:
                    data[freq][channel] = pd.DataFrame()

                # FIXME: if the client is the raspberry pi, remove the '.' from the <freq>
                _freq = freq
                if client == 'b8:27:eb:1e:2b:6a':
                    _freq = _freq.replace('.', '')

                # FIXME: it's just gonna be one file per <freq.>/<channel> combination
                for fn in sorted(glob.glob(os.path.join(os.path.join(args.input_dir, ("%s/%s/%s" % (client, _freq, channel))), 'iperf3-to-mobile.report.*.csv'))):

                    chunksize = 10 ** 5
                    for chunk in pd.read_csv(fn, chunksize = chunksize):
                        chunk['client'] = client
                        # chunk['pdr'] = 1.0 - (chunk['lost'].astype(float) / chunk['total'].astype(float))
                        chunk['timestamp'] = [ float(ts[:13]) for ts in chunk['time'].astype(str) ]
                        data[freq][channel] = pd.concat([data[freq][channel], chunk], ignore_index = True)

    # determine 'best' client for each metric
    for freq in data:
        for channel in data[freq]:
            for metric in metrics['iperf3']:
        
                if metric not in data[freq][channel].columns:
                    continue

                # best_aps[metric] = pd.concat([best_aps[metric], get_best_ap(data, metric)], ignore_index = True)
                # best_aps[metric] = best_aps[metric].sort_values(by = ['timestamp'])
                baps = get_best_ap(data[freq][channel], metric).sort_values(by = ['timestamp'])
                best_aps.append(
                    ('%s/%s/%s' % (freq, channel, metric)),
                    baps,
                    data_columns = baps.columns,
                    format = 'table')

    # close .hdf5 store
    best_aps.close()

def time_analysis(input_dir, output_dir, 
    metrics = { 'link-data' : ['SSI Signal', 'Data rate'], 'iperf3' : ['res-bw', 'loss', 'total'] },
    channels = {'2.4' : ['1', '11'], '5.1' : ['36'], '5.2' : ['40']},
    ap = ap):

    filename = os.path.join(input_dir, 'processed/best-aps.hdf5')
    # print(filename)

    if (not os.path.exists(filename)):
        sys.stderr.write("""%s: [ERROR] no .hdf5 files found\n""" % sys.argv[0]) 
        sys.exit(1)
    else:
        best_aps = pd.HDFStore(os.path.join(input_dir, 'processed/best-aps.hdf5'))

    # print(best_aps.info())
    # print(best_aps.keys())

    for metric in metrics['link-data']:

        dataset = ('/%s' % (metric))
        if dataset not in best_aps.keys():
            continue
        data = best_aps.select(dataset)

    for freq in channels:
        for channel in channels[freq]:
            for metric in metrics['iperf3']:

                dataset = ('/%s/%s/%s' % (freq, channel, metric))
                if dataset not in best_aps.keys():
                    continue
                data = best_aps.select(dataset)

def plot_best_ap(input_dir, output_dir, metric = 'SSI Signal', ap = ap, limits = None, seconds = 120, interval = None):

    # FIXME: filenames should not be hardcoded (there should be only 1 link-data.csv file in the input folder)
    pcap_file = os.path.join(args.input_dir, ("link-data.csv"))
    gps_file = os.path.join(args.input_dir, ("gps-log.csv"))

    plt.style.use('classic')
    fig = plt.figure(figsize = (12, (2 * 3.0)))
    # use GridSpec() to get similar aspect of WGTT paper
    gs = GridSpec(2, 3)

    ax = []
    # data (all time)
    # ax[0] : gs[0:1, :-1]
    ax.append(fig.add_subplot(gs[0, :-1]))
    # data (interval)
    # ax[1] : gs[0:1, 2]
    ax.append(fig.add_subplot(gs[0, 2]))
    # best ap (all time)
    # ax[2] : gs[2, :-1]
    ax.append(fig.add_subplot(gs[1, :-1]))
    # best ap (interval)
    # ax[3] : gs[2, 2]
    ax.append(fig.add_subplot(gs[1, 2]))

    for x in ax:
        x.xaxis.grid(True)
        x.yaxis.grid(True)

    Range = namedtuple('Range', ['start', 'end'])
    epoch = datetime.utcfromtimestamp(0)
    already_labeled = defaultdict(bool)
    chunksize = 10 ** 5
    for chunk in pd.read_csv(pcap_file, chunksize = chunksize):

        # consider frames directed at the mobile ap only
        chunk = chunk[chunk['dst mac'] == ap]
        # discard empty metric values
        chunk = chunk[np.isfinite(chunk[metric])]

        # isolate UNIX timestamps w/ 100 msec precision
        chunk['timestamp'] = chunk['Arrival Time'].map(lambda x : str((datetime.strptime(str(x)[:-13], '%b %d, %Y %H:%M:%S.%f') - epoch).total_seconds()))
        # get max metric value per timestamp, for all clients
        bap = pd.DataFrame(columns = ['timestamp'])
        for m in clients:
            _bap = chunk[chunk['src mac'] == m][['timestamp', metric]]
            _bap[m] = _bap.groupby(['timestamp'])[metric].transform(max)
            bap = pd.merge(_bap.drop_duplicates(subset = 'timestamp')[['timestamp', m]], bap, on = 'timestamp', how = 'outer')

        # get mac of client w/ best metric for each timestamp
        bap['max'] = bap[[m for m in clients]].idxmax(axis = 1)
        print(bap[['timestamp', 'max']])
        # bap['max'] = bap['max'].map(lambda x : clients[x]['id'])
        # now plot it!
        for m in clients:

            data = bap[bap['max'] == m]
            dates = [datetime.fromtimestamp(float(dt) - 3600.0) for dt in data['timestamp']]

            if not dates:
                continue

            n = len(dates)
            # ax[2].fill_between(
            #     dates, 
            #     clients[m]['id'], clients[m]['id'] + 1, 
            #     facecolor = clients[m]['color'], label = clients[m]['label'], linewidth = .01)
            ax[2].scatter(
                dates,
                [clients[m]['id']] * n,
                color = clients[m]['color'], label = clients[m]['label'], marker = 'o')

            r1 = Range(start = dates[0], end = dates[-1])
            r2 = Range(start = interval[0], end = interval[-1])
            if max(0.0, (min(r1.end, r2.end) - max(r1.start, r2.start)).seconds) > 0.0:
                # ax[3].fill_between(
                #     dates, 
                #     clients[m]['id'], clients[m]['id'] + 1, 
                #     facecolor = clients[m]['color'], label = clients[m]['label'], linewidth = .01)
                ax[3].scatter(
                    dates,
                    [clients[m]['id']] * n,
                    color = clients[m]['color'], label = clients[m]['label'], marker = 'o')

        # extract metric values, group by 'src mac' (and include other fields such as 'Arrival Time' and 'Type/Subtype')
        chunk = chunk.groupby(['no', 'Arrival Time', 'Type/Subtype', 'src mac'])[metric].apply(float).reset_index()

        # plot metric values for each client
        for m in clients:
            data = chunk[chunk['src mac'] == m]
            # exit if data is empty
            if data.empty:
                continue

            # transform arrival times in date objects (disregard the last 8 digits of the date strings, always '000 WEST')
            dates = [ datetime.strptime(dt[:-8], '%b %d, %Y %H:%M:%S.%f') for dt in data['Arrival Time'] ]
            # keep track of labels
            if m not in already_labeled:
                already_labeled[m] = False

            # plot metric values for the complete collection time
            ax[0].plot_date(
                dates,
                data[metric],
                linewidth = 1.0, color = clients[m]['color'], linestyle = '-', label = (clients[m]['label'] if not already_labeled[m] else ''), marker = None)
            
            already_labeled[m] = True

            # if dates and interval overlap, plot ax[1]
            r1 = Range(start = dates[0], end = dates[-1])
            r2 = Range(start = interval[0], end = interval[-1])
            if max(0.0, (min(r1.end, r2.end) - max(r1.start, r2.start)).seconds) > 0.0:
                ax[1].plot_date(
                    dates,
                    data[metric],
                    linewidth = 1.0, color = clients[m]['color'], linestyle = '-', marker = None)

    ax[0].set_title("rssi (at mobile) ap", fontsize = 12)
    ax[0].set_xlabel("time")
    ax[0].set_ylabel("rssi at mobile ap (dBm)")

    ax[0].axvspan(interval[0], interval[1], linewidth = 0.0, facecolor = '#bebebe', alpha = 0.75)

    ax[0].legend(
            fontsize = 12, 
            ncol = 3, loc = 'upper right',
            handletextpad = 0.2, handlelength = 2.0, labelspacing = 0.2, columnspacing = 0.5)

    ax[0].set_ylim([-95 , -40])
    ax[1].set_ylim([-95 , -40])

    ax[1].set_title("rssi (at mobile) ap (detail)", fontsize = 12)
    ax[1].set_xlabel("time")

    ax[2].set_title("best pos.", fontsize = 12)
    ax[2].set_xlabel("time")
    ax[2].set_ylabel("pos.")

    ax[3].set_title("best pos. (detail)", fontsize = 12)
    ax[3].set_xlabel("time")

    ax[0].set_xlim(limits[0], limits[1])
    ax[1].set_xlim(interval[0], interval[1])
    ax[2].set_xlim(limits[0], limits[1])
    ax[3].set_xlim(interval[0], interval[1])

    ax[2].set_ylim([-1, 3])
    ax[3].set_ylim([-1, 3])

    delta = timedelta(seconds = seconds)
    xticks = np.arange(limits[0], limits[1] + delta, delta)
    ax[2].set_xticks(xticks)
    ax[2].set_xticklabels([str(xt)[11:-7] for xt in xticks])

    delta = timedelta(seconds = 30)
    xticks = np.arange(interval[0], interval[1] + delta, delta)
    ax[3].set_xticks(xticks)
    ax[3].set_xticklabels([str(xt)[11:-7] for xt in xticks])

    ax[2].set_yticks([0, 1, 2])
    ax[2].set_yticklabels(['0', '1', '2'])
    ax[3].set_yticks([0, 1, 2])
    ax[3].set_yticklabels(['0', '1', '2'])

    plt.gcf().autofmt_xdate()
    # plt.tight_layout()
    plt.savefig(os.path.join(output_dir, ("wgtt-graph-1.pdf")), bbox_inches = 'tight', format = 'pdf')

def plot_rssi(input_dir, output_dir, ap = ap, limits = None, seconds = 120):

    # FIXME: filenames should not be hardcoded (there should be only 1 link-data.csv file in the input folder)
    scan_file = os.path.join(args.input_dir, ("link-data.csv"))
    gps_file = os.path.join(args.input_dir, ("gps-log.csv"))

    plt.style.use('classic')
    fig = plt.figure(figsize = (12.5, (3.5 * 2.0)))

    ax1 = fig.add_subplot(211)
    ax1.xaxis.grid(True)
    ax1.yaxis.grid(True)

    done = defaultdict(bool)
    date_limits = []
    chunksize = 10 ** 5
    for chunk in pd.read_csv(scan_file, chunksize = chunksize):

        # consider frames directed at the mobile ap only
        chunk = chunk[chunk['dst mac'] == ap]
        # discard empty rssi values
        chunk = chunk[np.isfinite(chunk['SSI Signal'])]
        # extract rssis, group by 'src mac' (and include other fields such as 'Arrival Time' and 'Type/Subtype')
        chunk = chunk.groupby(['no', 'Arrival Time', 'Type/Subtype', 'src mac'])['SSI Signal'].apply(float).reset_index()

        # plot rssis for each client
        for m in clients:

            # extract rssis from specific client m
            data = chunk[chunk['src mac'] == m]
            # exit if data is empty
            if data.empty:
                continue

            # transform arrival times in date objects (disregard the last 8 digits of the date strings, always '000 WEST')
            dates = [ datetime.strptime(dt[:-8], '%b %d, %Y %H:%M:%S.%f') for dt in data['Arrival Time'] ]
            if m not in done:
                done[m] = False

            ax1.plot_date(
                dates,
                data['SSI Signal'],
                linewidth = 1.0, color = clients[m]['color'], linestyle = '-', label = (clients[m]['label'] if not done[m] else ''), marker = None)

            done[m] = True

    ax1.legend(
            fontsize = 12, 
            title = 'client',
            ncol = 3, loc = 'upper right',
            handletextpad = 0.2, handlelength = 2.0, labelspacing = 0.2, columnspacing = 0.5)

    ax1.set_title("rssi (at mobile) ap vs. time", fontsize = 12)
    ax1.set_xlabel("time")
    ax1.set_ylabel("rssi at mobile ap (dBm)")

    ax1.set_ylim(-95, -40)

    ax2 = fig.add_subplot(212)
    ax2.xaxis.grid(True)
    ax2.yaxis.grid(True)

    chunksize = 10 ** 5
    for chunk in pd.read_csv(gps_file, chunksize = chunksize):

        # FIXME: the +3600 serves to add 1 hr (the gps device uses the wrong timezone?)
        dates = [datetime.fromtimestamp(dt + 3600.0) for dt in chunk['time']]
        # get a list of gps positions (latitude, longitude), for each datapoint in the .csv file
        gps_pos = [ [row['lat'], row['lon'] ] for index, row in chunk.iterrows()]

        # update limits for xx axis
        update_limits(date_limits, dates)

        # plot the distance of the (lat, lon) datapoints to each the n client positions, indexed 
        # by the date & time at which datapoints were collected
        for m in clients:
            ax2.plot_date(
                dates,
                [ gps_to_dist(clients[m]['lat'], clients[m]['lon'], gps[0], gps[1]) for gps in gps_pos],
                linewidth = 1.0, color = clients[m]['color'], linestyle = '-', label = clients[m]['label'], marker = None)

    ax2.set_title("distance from mobile ap to client pos.", fontsize = 12)
    ax2.set_xlabel("time")
    ax2.set_ylabel("dist. from mobile ap to client pos. (m)")

    # set xx limits to align with those of the rssi graph
    if limits is not None:
        date_limits = limits

    ax1.set_xlim(date_limits[0], date_limits[1])
    ax2.set_xlim(date_limits[0], date_limits[1])
    ax2.set_ylim(0, 100)

    # get xticks every 120 seconds
    delta = timedelta(seconds = seconds)
    xticks = np.arange(date_limits[0], date_limits[1] + delta, delta)
    ax1.set_xticks(xticks)
    ax2.set_xticks(xticks)
    ax1.set_xticklabels([str(xt)[11:-7] for xt in xticks])
    ax2.set_xticklabels([str(xt)[11:-7] for xt in xticks])

    plt.gcf().autofmt_xdate()
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, ("rssi-traces.pdf")), bbox_inches = 'tight', format = 'pdf')

def plot_iperf(input_dir, output_dir, ap = ap, limits = None, seconds = 120):

    date_limits = []
    # FIXME: filenames should not be hardcoded (there should be only 1 link-data.csv file in the input folder)
    scan_file = os.path.join(args.input_dir, ("link-data.csv"))
    gps_file = os.path.join(args.input_dir, ("gps-log.csv"))

    # plot losses for each position
    plt.style.use('classic')
    fig = plt.figure(figsize = (12.5, (3.5 * 3.0)))

    ax1 = fig.add_subplot(311)
    ax1.xaxis.grid(True)
    ax1.yaxis.grid(True)

    ax2 = fig.add_subplot(312)
    ax2.xaxis.grid(True)
    ax2.yaxis.grid(True)

    done = defaultdict(bool)
    date_limits = []
    chunksize = 10 ** 5
    for chunk in pd.read_csv(scan_file, chunksize = chunksize):

        # consider frames directed at the mobile ap only
        chunk = chunk[chunk['dst mac'] == ap]
        # discard empty rssi values
        chunk = chunk[np.isfinite(chunk['SSI Signal'])]
        # # extract rssis, group by 'src mac' (and include other fields such as 'Arrival Time' and 'Type/Subtype')
        # chunk = chunk.groupby(['no', 'Arrival Time', 'Type/Subtype', 'src mac'])[['SSI Signal', 'Data rate']].count().reset_index()
        # print(chunk)

        # plot rssis for each client
        for m in clients:

            # extract rssis from specific client m
            data = chunk[chunk['src mac'] == m]
            # exit if data is empty
            if data.empty:
                continue

            # transform arrival times in date objects (disregard the last 8 digits of the date strings, always '000 WEST')
            dates = [ datetime.strptime(dt[:-8], '%b %d, %Y %H:%M:%S.%f') for dt in data['Arrival Time'] ]
            if m not in done:
                done[m] = False

            ax1.plot_date(
                dates,
                data['SSI Signal'],
                linewidth = 1.0, color = clients[m]['color'], linestyle = '-', label = (clients[m]['label'] if not done[m] else ''), marker = None)

            ax2.scatter(
                dates,
                data['Data rate'],
                linewidth = 1.0, color = clients[m]['color'], label = clients[m]['label'], s = 25, marker = 'o')

            done[m] = True

    ax1.legend(
            fontsize = 12, 
            title = 'client',
            ncol = 3, loc = 'upper right',
            handletextpad = 0.2, handlelength = 2.0, labelspacing = 0.2, columnspacing = 0.5)

    ax1.set_title("rssi (at mobile ap) vs. time", fontsize = 12)
    ax1.set_xlabel("time")
    ax1.set_ylabel("rssi at mobile ap (dBm)")
    ax1.set_ylim(-95, -40)

    # for m in clients:
    #     for file_name in sorted(glob.glob(os.path.join(input_dir, ('%s/*.csv' % (m))))):
    #         chunksize = 10 ** 5
    #         for chunk in pd.read_csv(file_name, chunksize = chunksize):

    #             dates = [datetime.fromtimestamp(dt) for dt in chunk['time']]
    #             ax2.scatter(
    #                 dates,
    #                 chunk['res-bw'] / 1000000.0,
    #                 linewidth = 1.0, color = clients[m]['color'], label = clients[m]['label'], s = 25, marker = '^')

    ax2.set_title("802.11n bitrates (Mbps)", fontsize = 12)
    ax2.set_xlabel("time")
    ax2.set_ylabel("802.11n bitrates (Mbps)")

    # ax2.set_ylim(0.0, 12.0)

    ax3 = fig.add_subplot(313)
    ax3.xaxis.grid(True)
    ax3.yaxis.grid(True)

    chunksize = 10 ** 5
    for chunk in pd.read_csv(gps_file, chunksize = chunksize):

        # FIXME: the +3600 serves to add 1 hr (the gps device uses the wrong timezone?)
        dates = [datetime.fromtimestamp(dt + 3600.0) for dt in chunk['time']]
        # get a list of gps positions (latitude, longitude), for each datapoint in the .csv file
        gps_pos = [ [row['lat'], row['lon'] ] for index, row in chunk.iterrows()]

        # update limits for xx axis
        update_limits(date_limits, dates)

        # plot the distance of the (lat, lon) datapoints to each the n client positions, indexed 
        # by the date & time at which datapoints were collected
        for m in clients:
            ax3.plot_date(
                dates,
                [ gps_to_dist(clients[m]['lat'], clients[m]['lon'], gps[0], gps[1]) for gps in gps_pos],
                linewidth = 1.0, color = clients[m]['color'], linestyle = '-', label = clients[m]['label'], marker = None)

    ax3.set_title("distance from mobile ap to client pos.", fontsize = 12)
    ax3.set_xlabel("time")
    ax3.set_ylabel("dist. from mobile ap\nto client pos. (m)")

    ax3.set_ylim(0, 100)

    # set xx limits to align with those of the rssi graph
    if limits is not None:
        date_limits = limits

    ax1.set_xlim(date_limits[0], date_limits[1])
    ax2.set_xlim(date_limits[0], date_limits[1])
    ax3.set_xlim(date_limits[0], date_limits[1])

    # get xticks every 120 seconds
    delta = timedelta(seconds = seconds)
    xticks = np.arange(date_limits[0], date_limits[1] + delta, delta)
    ax1.set_xticks(xticks)
    ax2.set_xticks(xticks)
    ax3.set_xticks(xticks)
    ax1.set_xticklabels([str(xt)[11:-7] for xt in xticks])
    ax2.set_xticklabels([str(xt)[11:-7] for xt in xticks])
    ax3.set_xticklabels([str(xt)[11:-7] for xt in xticks])

    plt.gcf().autofmt_xdate()
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, ("iperf-stats.pdf")), bbox_inches = 'tight', format = 'pdf')

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--input-dir", 
         help = """dir w/ .csv files""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save graphs""")

    args = parser.parse_args()

    if not args.input_dir:
        sys.stderr.write("""%s: [ERROR] please supply a dir w/ input files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # plot_rssi(args.input_dir, args.output_dir, limits = [datetime(2018, 6, 19, 16, 36), datetime(2018, 6, 19, 16, 38)], seconds = 10)
    # plot_rssi(args.input_dir, args.output_dir, limits = [datetime(2018, 6, 19, 16, 44), datetime(2018, 6, 19, 16, 46)], seconds = 10)
    # plot_rssi(args.input_dir, args.output_dir, limits = [datetime(2018, 6, 19, 16, 27), datetime(2018, 6, 19, 16, 49)], seconds = 60)
    # plot_iperf(args.input_dir, args.output_dir, limits = [datetime(2018, 6, 19, 16, 44), datetime(2018, 6, 19, 16, 46)], seconds = 10)
    # plot_best_ap(
    #     args.input_dir, args.output_dir, 
    #     limits = [datetime(2018, 6, 19, 16, 27), datetime(2018, 6, 19, 16, 49)], 
    #     interval = [datetime(2018, 6, 19, 16, 44), datetime(2018, 6, 19, 16, 46)])
    # get_metrics(args.input_dir, args.output_dir)
    time_analysis(args.input_dir, args.output_dir)

    sys.exit(0)