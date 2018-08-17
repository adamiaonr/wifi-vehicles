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

from random import randint

from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple
from matplotlib.gridspec import GridSpec
from prettytable import PrettyTable

matplotlib.rcParams.update({'font.size': 16})

# mac address of mobile ap
ap = '24:05:0f:61:51:14'
# mac addresses of clients (side-of-the-road)
clients = OrderedDict()
clients['24:05:0f:6d:ae:36'] = {'id' : 0, 'label' : 'pos. 0', 'color' : 'blue',     'lat' : 41.178456, 'lon' : -8.594501, 'ip' : '10.10.10.250'}
clients['fc:ec:da:1b:63:a6'] = {'id' : 1, 'label' : 'pos. 1', 'color' : 'red',      'lat' : 41.178518, 'lon' : -8.595366, 'ip' : '10.10.10.53'}
clients['24:05:0f:9e:2c:b1'] = {'id' : 2, 'label' : 'pos. 2', 'color' : 'green',    'lat' : 41.178563, 'lon' : -8.596012, 'ip' : '10.10.10.113'}

peers = {
    'mobile' : {'color' : 'black'}, 
    'pos0'   : {'color' : 'blue',   'lat' : 41.178518, 'lon' : -8.595366}, 
    'pos1'   : {'color' : 'red',    'lat' : 41.178518, 'lon' : -8.595366}, 
    'pos2'   : {'color' : 'green',  'lat' : 41.178563, 'lon' : -8.596012}
}

t_diff = lambda t : (float(t[-1]) - float(t[0]))
Range = namedtuple('Range', ['start', 'end'])

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

    if ( (limits[0] is None) or (min(array) < limits[0]) ):
        limits[0] = np.amin(array)

    if ( (limits[1] is None) or (max(array) > limits[1]) ):
        limits[1] = np.amax(array)

def get_values_per_client(data, metric = 'SSI Signal'):

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

    values = pd.DataFrame(columns = [tstr])
    for client in clients:

        # filter wlan frames sent by client
        _values = data[data[cstr] == client][[tstr, metric]]
        # get 'best' metric value per timestamp (10 ms precision) 
        _values[client] = _values.groupby([tstr])[metric].transform(max)
        # merge all 'best' values of all clients
        values = pd.merge(_values.drop_duplicates(subset = tstr)[[tstr, client]], values, on = tstr, how = 'outer')

        # print(metric)
        # print(values)

    return values

def get_best_client(data, metric = 'SSI Signal'):
    # get mac of client w/ 'best' metric value for each timestamp
    data[metric] = data[[client for client in clients]].idxmax(axis = 1)

    return data[['timestamp', metric]]

def to_cdf(data, bins = 100):
    counts, bin_edges = np.histogram(data, bins = bins, normed = True)
    cdf = np.cumsum(counts)
    return cdf, bin_edges

def to_hdf5(
    data, 
    freq, channel, metric, 
    link_data):

    link_data.append(
        ('/%s/%s/%s' % (freq, channel, metric)),
        values,
        data_columns = values.columns,
        format = 'table')

def extract_metrics(
    input_dir, 
    metrics = { 'link-data' : ['SSI Signal', 'Data rate'], 'iperf3' : ['res-bw', 'loss', 'total'] }, 
    channels = {'2.4' : ['01', '11'], '5.1' : ['36'], '5.2' : ['40']},
    ap = ap, limits = None, seconds = 120):

    """extracts vehicular metrics from .csv files into .hdf5 files."""

    # aux. variable holds reference timestamp
    the_epoch = datetime.utcfromtimestamp(0)

    # metrics indexed by timestamp, for each client (or ap, whichever way you wanna look at it)

    # we save x diff. types of link data:
    #   - pkt captures at each of the iperf3 clients (senders)
    #   - pkt captures at the iperf3 server (receiver)
    #   - pkt capture in monitor mode (i.e. wlan frames), at the receiver
    link_data = pd.HDFStore(os.path.join(input_dir, "processed/link-data.hdf5"))
    # we also save gps positions indexed by timestamp
    gps_pos = pd.HDFStore(os.path.join(input_dir, "processed/gps-pos.hdf5"))

    mobile_ap_data = pd.DataFrame()
    for freq in ['2.4', '5.1', '5.2']:
        for channel in channels[freq]:

            channel_dir = os.path.join(args.input_dir, ("link-data/%s/%s" % (freq, channel)))
            for fname in sorted(glob.glob(os.path.join(channel_dir, '*.csv'))):

                ftype = fname.split('/')[-1].split('.')[0]
                chunksize = 10 ** 5
                print(fname)
                for chunk in pd.read_csv(fname, chunksize = chunksize):

                    if ftype in ['monitor']:

                        # consider frames directed at the mobile ap only
                        chunk = chunk[chunk['dst mac'] == ap]
                        # discard empty rssi values
                        # FIXME: many of the wlan data frames have a 'Greenfield' bit on, and 
                        # don't have rssi values
                        chunk = chunk[np.isfinite(chunk['SSI Signal'])]

                        # isolate UNIX timestamps w/ 10 msec precision
                        chunk['timestamp'] = chunk['Epoch Time']
                        # chunk['timestamp'] = chunk['Arrival Time'].map(lambda x : str((datetime.strptime(str(x)[:-12], '%b %d, %Y %H:%M:%S.%f') - the_epoch).total_seconds()))

                        # save metric data per client, indexed by timestamp, on .hdf5
                        for metric in metrics['link-data']:
                            values_per_client = get_values_per_client(chunk, metric).sort_values(by = ['timestamp'])
                            to_hdf5(values_per_client, freq, channel, metric, link_data)

                        # add instantaneous throughput to each rcvd udp packet
                        # chunk['throughput'] = (chunk['Length'] * 8.0) / chunk['time delta']
                        # print(chunk['throughput'].astype(str))
                        # link_data.append(
                        #     ('/%s/%s/wlan-throughput' % (freq, channel)),
                        #     chunk[['Epoch Time', 'time', 'time delta', 'Length', 'Header length', 'src mac', 'dst mac', 'Protocol', 'Type', 'Type/Subtype', 'PHY type', 'SSI Signal', 'Signal strength (dBm)', 'Sequence number', 'Data rate', 'MCS index', 'Duration', 'Preamble', 'throughput']],
                        #     data_columns = ['Epoch Time', 'time', 'time delta', 'Length', 'Header length', 'src mac', 'dst mac', 'Protocol', 'Type', 'Type/Subtype', 'PHY type', 'SSI Signal', 'Signal strength (dBm)', 'Sequence number', 'Data rate', 'MCS index', 'Duration', 'Preamble', 'throughput'],
                        #     format = 'table')

                        del chunk

                    elif ftype in ['gps-log']:

                        gps_pos.append(
                            ('/%s/%s' % (freq, channel)),
                            chunk[['timestamp', 'time', 'lon', 'lat', 'alt', 'speed', 'epx', 'epy', 'epv', 'eps']],
                            data_columns = chunk[['timestamp', 'time', 'lon', 'lat', 'alt', 'speed', 'epx', 'epy', 'epv', 'eps']].columns,
                            format = 'table')

                    elif ftype in ['ap']:

                        # only consider udp and ipv4 packets
                        chunk = chunk[chunk['Protocol'].str.contains('IPv4|UDP') == True]
                        # consider frames directed at the mobile ap only
                        chunk = chunk[chunk['dst mac'] == ap]

                        mobile_ap_data = pd.concat([mobile_ap_data, chunk], ignore_index = True)
                        # # add instantaneous throughput to each rcvd udp packet
                        # chunk['throughput'] = (chunk['Length'] * 8.0) / chunk['time delta']
                        # link_data.append(
                        #     ('/%s/%s/app-throughput' % (freq, channel)),
                        #     chunk[['Epoch Time', 'time delta', 'Length', 'Header Length', 'src mac', 'dst mac', 'Protocol', 'Source', 'Destination', 'Identification', 'throughput']],
                        #     data_columns = ['Epoch Time', 'time delta', 'Length', 'Header Length', 'src mac', 'dst mac', 'Protocol', 'Source', 'Destination', 'Identification', 'throughput'],
                        #     format = 'table')

                    else:
                        sys.stderr.write("""%s::extract_metrics() : [ERROR] unrecognized link-data .csv type.\n""" % sys.argv[0])

    # 2) use ap.*.csv and sndr.csv captures at each of the clients to calculate packet loss
    # and throughput averaged over 100 ms
    for client in clients:

        rcvd_pkt_ids = mobile_ap_data[mobile_ap_data['src mac'] == client][['no', 'Epoch Time', 'Identification', 'Fragment offset', 'Reassembled IPv4 in frame']]

        for freq in ['2.4', '5.1', '5.2']:
            for channel in channels[freq]:

                # FIXME: if the client is the raspberry pi, remove the '.' from the <freq>
                _freq = freq
                if client == 'b8:27:eb:1e:2b:6a':
                    _freq = _freq.replace('.', '')

                fname = os.path.join(args.input_dir, ("%s/%s/%s/sndr.csv" % (client, _freq, channel)))
                if not os.path.isfile(fname): 
                    continue

                chunksize = 10 ** 5
                for chunk in pd.read_csv(fname, chunksize = chunksize):

                    # only consider udp and ipv4 packets
                    chunk = chunk[chunk['Protocol'].str.contains('IPv4|UDP') == True]
                    # consider frames directed at the mobile ap only
                    chunk = chunk[chunk['dst mac'] == ap]

                    # 1) check sent packets which aren't in the receiver logs 
                    # this is easily done w/ the 'ip.id' field
                    # https://www.cellstream.com/intranet/reference-reading/tipsandtricks/314-the-purpose-of-the-ip-id-field-demystified.html
                    snt_pkt_ids = chunk[['no', 'Epoch Time', 'Identification', 'Fragment offset', 'Reassembled IPv4 in frame']]
                    snt_pkt_ids['lost'] = ~(snt_pkt_ids['Identification'].isin(rcvd_pkt_ids['Identification']))

                    # # add instantaneous throughput to each rcvd udp packet
                    # chunk['throughput'] = (chunk['Length'] * 8.0) / chunk['time delta']
                    # link_data.append(
                    #     ('/%s/%s/app-throughput' % (freq, channel)),
                    #     chunk[['Epoch Time', 'time delta', 'Length', 'Header Length', 'src mac', 'dst mac', 'Protocol', 'Source', 'Destination', 'Identification', 'throughput']],
                    #     data_columns = ['Epoch Time', 'time delta', 'Length', 'Header Length', 'src mac', 'dst mac', 'Protocol', 'Source', 'Destination', 'Identification', 'throughput'],
                    #     format = 'table')

    # close .hdf5 store
    link_data.close()

def get_periods(data, metric = 'SSI Signal', mode = 'max'):

    if mode == 'max':
        data[metric] = data[[client for client in clients]].idxmax(axis = 1)
    else:
        data[metric] = data[[client for client in clients]].idxmin(axis = 1)

    data['block'] = (data[metric].shift(1) != data[metric]).astype(int).cumsum()
    periods = data.reset_index().groupby([metric, 'block'])['timestamp'].apply(np.array).to_frame('interval').reset_index()
    periods['start'] = [ tss[0] for tss in periods['interval'] ]
    periods['end'] = [ tss[-1] for tss in periods['interval'] ]
    periods['duration'] = periods['interval'].apply(t_diff) + 0.01
    periods = periods.sort_values(by = ['start']).reset_index()

    return periods

def get_laps(input_dir, output_dir, freq, channel):

    # laps are decided according to the dist. to pos. 2
    ref = '24:05:0f:aa:ab:5d'
    gps_data  = pd.HDFStore(os.path.join(input_dir, 'processed/gps-pos.hdf5'))

    if ('/%s/%s' % (freq, channel)) not in gps_data.keys():
        return

    print(('/%s/%s' % (freq, channel)))

    data = gps_data.select(('/%s/%s' % (freq, channel)))
    # consider data points which indicate movement
    data = data[data['speed'] > 3.0].sort_values(by = 'timestamp').reset_index()
    # identify laps by sign of longitude difference:
    #   * -1.0 means that lon increases over time
    #   * 1.0 means that lon decreases over time
    data['lon-diff'] = data['lon'].shift(1) - data['lon']
    # only consider non-zero longitude diffs 
    data = data[data['lon-diff'] != 0.0].reset_index()
    data['lon-diff'] = abs(data['lon-diff']) / data['lon-diff']
    # print(data[['timestamp', 'lon', 'lon-diff']][data['lon-diff'] > 0.0])
    # print(data[['timestamp', 'lon', 'lon-diff']][data['lon-diff'] < 0.0])
    data['block'] = (data['lon-diff'].shift(1) != data['lon-diff']).astype(int).cumsum()
    # print(data[['timestamp', 'lon', 'lon-diff', 'block']])
    laps = data.groupby(['lon-diff', 'block'])['timestamp'].apply(np.array).to_frame('interval').reset_index()
    laps['start'] = [ tss[0] for tss in laps['interval'] ]
    laps['end'] = [ tss[-1] for tss in laps['interval'] ]
    laps['duration'] = laps['interval'].apply(t_diff)
    laps = laps.sort_values(by = 'block').reset_index()
    # print(laps)
    laps = laps[(laps['duration'] > 10.0) & (laps['duration'] < 100.0)][['duration', 'lon-diff', 'start', 'end']]
    print(laps)

    _laps = []
    for i, row in laps.iterrows():

        if row['lon-diff'] < 0.0:
            _laps.append({'start' : row['start']})
        elif row['lon-diff'] > 0.0:
            _laps[-1]['end'] = row['end']

    print(_laps)

    return 0

def get_overlap(
    predictor, ground_truth,
    predictor_data, gt_data):

    # FIXME: this is ugly... but it works!
    overlap = []
    prev_j = 0
    for i, gt_row in gt_data.iterrows():

        gt_range = Range(start = float(gt_row['start']), end = float(gt_row['end']))
        # print("analyzing gt interval : %s - %s" % ([gt_range.start, gt_range.end], gt_row[ground_truth]))
        overlap.append(0.0)
        for j, predictor_row in predictor_data.iloc[prev_j:].iterrows():

            predictor_range = Range(start = float(predictor_row['start']), end = float(predictor_row['end']))
            # print("\tpredictor interval [%d]: %s - %s (%s)" % (j, [predictor_range.start, predictor_range.end], predictor_row[predictor], predictor_row['duration']))
            if (predictor_range.start < gt_range.start):
                continue

            if (predictor_range.end <= gt_range.end):

                if (gt_row[ground_truth] == predictor_row[predictor]):
                    # print("\tpredictor interval : %s - %s (%s) chosen" % ([predictor_range.start, predictor_range.end], predictor_row[predictor], predictor_row['duration']))
                    overlap[-1] += predictor_row['duration']
                # else:
                #     print("\tpredictor interval : %s - %s (%s) not chosen" % ([predictor_range.start, predictor_range.end], predictor_row[predictor], predictor_row['duration']))

            else:
                # overlap is calculated as % of duration of predictor intervals on the duration of gt intervals
                overlap[-1] = overlap[-1] / gt_row['duration']
                # update the previous predictor index
                prev_j = j
                # advance to the next gt interval
                break

    return overlap

def predict_performance(input_dir, output_dir,
    predictor = {'label' : 'SSI Signal', 'mode' : 'max'},
    ground_truth = {'label' : 'res-bw', 'mode' : 'max'},
    channels = { '2.4' : ['01', '11'], '5.1' : ['36'] },
    parameters = {
        'x-axis-label' : 'throughput (Mbps)', 'y-axis-label' : 'rssi (dBm)', 
        'x-limits' : [0.0, 10.0], 'y-limits' : [-100.0, -30.0], 
        'x-scale-by' : 1.0, 'y-scale-by' : 1000000.0}):

    # use the classic plot style
    plt.style.use('classic')
    # figs
    fig = plt.figure(figsize = (5, 3.5))
    spnum = 111
    
    _channels = {
        '01' : {'label' : '1', 'color' : 'red'},
        '11' : {'label' : '11', 'color' : 'green'},
        '36' : {'label' : '36', 'color' : 'blue'}}

    # load link data
    link_data = pd.HDFStore(os.path.join(input_dir, 'processed/link-data.hdf5'))
    # results shown in < <freq.>, <channel> > pairs
    for freq in channels:
        for channel in channels[freq]:

            # 1) find consecutive periods during which the same ap remains the 'best',
            # for both the gt and predictor variable
            periods = defaultdict(pd.DataFrame)
            for metric in [ground_truth, predictor]:

                if ('/%s/%s/%s' % (freq, channel, metric['label'])) not in link_data.keys():
                    continue

                print(('/%s/%s/%s' % (freq, channel, metric['label'])))

                # FIXME: you should understand what's going on w/ timestamps and timezones.
                # there seem to be 3 different timestamp offsets:
                #   - from .pcap files, collected w/ wireshark (mac os)
                #   - from iperf3 files, collected in the eeepcs 
                #   - from gps devices
                ts_offset = 0.0
                if (metric['label'] not in ['SSI Signal', 'Data rate']):
                    ts_offset = 3600.0

                # load metric data into dataframe
                df = link_data.select(('/%s/%s/%s' % (freq, channel, metric['label'])))
                # FIXME: timestamp offset fix
                df['timestamp'] = (df['timestamp'].astype(float) + ts_offset).astype(str)
                periods[metric['label']] = get_periods(df, metric['label'], mode = metric['mode'])

            # 2) how do the intervals correlate ?
            #   - take the ground truth intervals as base for the 'best'
            #   - then, for each gt interval, check the % of 10 ms intervals for which
            #     there's a 'best ap' overlap between gt and predictor

            # find initial and final analysis timestamps (we're only interested in the overlapping region)
            r1 = Range(start = periods[ground_truth['label']]['start'].values[0], end = periods[ground_truth['label']]['start'].values[-1])
            r2 = Range(start = periods[predictor['label']]['start'].values[0], end = periods[predictor['label']]['start'].values[-1])
            its = max(r1.start, r2.start)
            fts = min(r1.end, r2.end)
            periods[ground_truth['label']] = periods[ground_truth['label']][(periods[ground_truth['label']]['start'].values >= its) & (periods[ground_truth['label']]['start'].values <= fts)].reset_index()
            periods[predictor['label']] = periods[predictor['label']][(periods[predictor['label']]['start'].values >= its) & (periods[predictor['label']]['start'].values <= fts)].reset_index()

            # FIXME: this is ugly... but it works!
            periods[ground_truth['label']]['overlap'] = get_overlap(
                predictor['label'], ground_truth['label'], 
                periods[predictor['label']], periods[ground_truth['label']])
            # print(periods[ground_truth['label']][['start', 'end', 'duration', ground_truth['label'], 'overlap']])
            # print(periods[predictor['label']][['start', 'end', 'duration', predictor['label']]])

            # plot a cdf of overlap values
            # plot cdf of interval durations
            ax1 = fig.add_subplot(spnum)
            ax1.xaxis.grid(False)
            ax1.yaxis.grid(True)

            ax1.set_title("overlap %% per 10 ms interval\n%s (base) vs. %s" % (ground_truth['label'].lower(), predictor['label'].lower()), fontsize = 12)
            cdf, bin_edges = to_cdf(periods[ground_truth['label']]['overlap'].values)
            ax1.plot(bin_edges[1:], cdf / cdf[-1], 
                    alpha = 0.75, linewidth = 1.5, color = _channels[channel]['color'], label = _channels[channel]['label'])

            ax1.legend(
                fontsize = 12, 
                ncol = 1, loc = 'upper left', title = 'channel',
                handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

            ax1.set_xlabel("overlap %")
            ax1.set_ylabel("cdf [0.0, 1.0]")
            ax1.set_xlim([0.0, 1.0])
            ax1.set_ylim([0.0, 1.0])

            fig.tight_layout()
            fig.savefig(os.path.join(output_dir, ("%s-vs-%soverlap-perc.pdf" % (ground_truth['label'].replace(' ', '-').lower(), predictor['label'].replace(' ', '-').lower()))), bbox_inches = 'tight', format = 'pdf')
                        
def metric_analysis(input_dir, output_dir,
    metric = 'SSI Signal',
    channels = {'2.4' : ['01', '11'], '5.1' : ['36']},
    parameters = {
        'cdf' : {'y-axis-label' : 'CDF', 'x-limits' : [0.0, 5.0], 'y-limits' : [0.75, 1.0], 'scale-by' : 1.0},
        'duration-vs-dist' : {'x-limits' : [0.0, 200.0], 'y-limits' : [0.0, 0.250], 'scale-by' : 1.0}}):

    # here are the numbers we want to extract from the data:
    #   1) duration of periods as 'best ap', for each ap (CDF format)
    #   2) duration of periods vs. distance to respective ap
    #   3) # of switches vs. distance to respective ap (is this relevant? for what?)
    #   4)  

    # load link data
    link_data = pd.HDFStore(os.path.join(input_dir, 'processed/link-data.hdf5'))
    gps_data  = pd.HDFStore(os.path.join(input_dir, 'processed/gps-pos.hdf5'))

    # use the classic plot style
    plt.style.use('classic')
    # figs
    fig = defaultdict()
    fig['cdf'] = plt.figure(figsize=(15, 3.5))
    fig['duration-vs-dist'] = plt.figure(figsize=(15, 3.5))

    spnum = 131
    # results shown in < <freq.>, <channel> > pairs
    for freq in channels:
        for channel in channels[freq]:

            if ('/%s/%s/%s' % (freq, channel, 'SSI Signal')) not in link_data.keys():
                continue

            print(('/%s/%s/%s' % (freq, channel, metric)))

            # FIXME: you should understand what's going on w/ timestamps...
            ts_offset = 0
            if (channel == '36') and (metric not in ['SSI Signal']):
                ts_offset = 3600

            # load datasets into dataframe
            data = defaultdict()
            data['link'] = link_data.select(('/%s/%s/%s' % (freq, channel, metric)))
            data['gps'] = gps_data.select(('/%s/%s' % (freq, channel)))

            # determine 'best' ap per row ('best' according to metric)
            periods = get_periods(data['link'], metric)

            # plot cdf of interval durations
            ax1 = fig['cdf'].add_subplot(spnum)
            ax1.xaxis.grid(False)
            ax1.yaxis.grid(True)

            ax1.set_title('channel : %d' % (int(channel)), fontsize = 12)
            for c in clients:
                cdf, bin_edges = to_cdf(periods[periods[metric] == c]['duration'].values)
                ax1.plot(bin_edges[1:], cdf / cdf[-1], 
                        alpha = 0.75, linewidth = 1.5, color = clients[c]['color'], label = clients[c]['label'])

            ax1.legend(
                fontsize = 12, 
                ncol = 1, loc = 'lower right',
                handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

            ax1.set_xlabel("interval duration (sec)")
            ax1.set_ylabel("cdf [0.0, 1.0]")
            ax1.set_xlim(parameters['cdf']['x-limits'])
            ax1.set_ylim(parameters['cdf']['y-limits'])

            fig['cdf'].tight_layout()
            fig['cdf'].savefig(os.path.join(output_dir, ("%s-interval-durations.pdf" % (metric.replace(' ', '-').lower()))), bbox_inches = 'tight', format = 'pdf')

            # 2) duration of periods vs. distance to each ap
            #   - save sec part of start timestamp in an individual column
            periods['timestamp'] = [ (int(x.split('.')[0]) + ts_offset) for x in periods['start'].values ]
            #   - merge gps positions and period dataframes
            _periods = pd.merge(periods, data['gps'], on = 'timestamp', how = 'inner')
            #   - for each period, calculate distance (in m) to respective ap
            for i, row in _periods.iterrows():
                _periods.at[i, 'dist'] = gps_to_dist(clients[row[metric]]['lat'], clients[row[metric]]['lon'], row['lat'], row['lon'])

            ax2 = fig['duration-vs-dist'].add_subplot(spnum)
            ax2.xaxis.grid(False)
            ax2.yaxis.grid(True)
            spnum += 1

            ax2.set_title('channel : %d' % (int(channel)), fontsize = 12)

            for c in clients:
                df = _periods[_periods[metric] == c]
                ax2.scatter(df['dist'].values, df['duration'].astype(float).values / parameters['duration-vs-dist']['scale-by'], 
                    c = clients[c]['color'], marker = 'o', linewidths = 0.0, label = clients[c]['label'], s = 10.0, alpha = 0.25)

            ax2.set_xlabel("dist. of bicycle to pos. (m)")
            ax2.set_ylabel("interval duration (sec)")
            ax2.set_xlim(parameters['duration-vs-dist']['x-limits'])
            ax2.set_ylim(parameters['duration-vs-dist']['y-limits'])

            ax2.legend(
                fontsize = 12, 
                ncol = 1, loc = 'upper right',
                handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

            fig['duration-vs-dist'].tight_layout()
            fig['duration-vs-dist'].savefig(os.path.join(output_dir, ("%s-duration-vs-dist.pdf" % (metric.replace(' ', '-').lower()))), bbox_inches = 'tight', format = 'pdf')

            # 3) 

def vs_distance(input_dir, output_dir,
    metric = 'SSI Signal',
    channels = {'2.4' : ['01', '11'], '5.1' : ['36']},
    parameters = {'y-axis-label' : 'rssi (dBm)', 'x-limits' : [0.0, 200.0], 'y-limits' : [-100.0, -30.0], 'scale-by' : 1.0}):

    link_data = pd.HDFStore(os.path.join(input_dir, 'processed/link-data.hdf5'))
    gps_data  = pd.HDFStore(os.path.join(input_dir, 'processed/gps-pos.hdf5'))

    # use the classic plot style
    plt.style.use('classic')

    # fig frame
    fig = plt.figure(figsize=(15, 3.5))

    markers = ['*', 'o']
    spnum = 131
    for freq in channels:

        # if freq != '2.4':
        #     continue

        for channel in channels[freq]:

            if ('/%s/%s/%s' % (freq, channel, 'SSI Signal')) not in link_data.keys():
                continue

            # FIXME: you should understand what's going on w/ timestamps...
            ts_offset = 0
            if (channel == '36') and (metric not in ['SSI Signal']):
                ts_offset = 3600

            ax1 = fig.add_subplot(spnum)
            ax1.xaxis.grid(False)
            ax1.yaxis.grid(True)
            spnum += 1
            ax1.set_title('channel : %d' % (int(channel)), fontsize = 12)

            print(('/%s/%s/%s' % (freq, channel, metric)))

            data = defaultdict()
            data['link'] = link_data.select(('/%s/%s/%s' % (freq, channel, metric)))
            data['gps'] = gps_data.select(('/%s/%s' % (freq, channel)))

            for c in clients:

                # merge positions between data['link'] and data['gps'] for a particular client
                df = data['link'][np.isfinite(data['link'][c])][['timestamp', c]]
                df['timestamp'] = [ (int(x.split('.')[0]) + ts_offset) for x in df['timestamp'].values ]
                _df = pd.merge(df, data['gps'], on = 'timestamp', how = 'inner')

                # quick stats for client
                print("quick metric stats for client %s :" % (c))
                print("\tMETRIC : %s" % (metric))
                print("\t[MIN, MAX] : [%f, %f]" % (df[c].min(), df[c].max()))
                print("\t[MEAN, STD. DEV.] : [%f, %f]" % (df[c].mean(), df[c].std()))

                # calculate distances from mobile node to client
                gps_pos = [ [row['lat'], row['lon'] ] for index, row in _df.iterrows()]
                _df['dist'] = [ gps_to_dist(clients[c]['lat'], clients[c]['lon'], gps[0], gps[1]) for gps in gps_pos ]

                # add rssi vs. dist (m) scatter plot
                ax1.scatter(_df['dist'].values, _df[c].astype(float).values / parameters['scale-by'], 
                    c = clients[c]['color'], marker = 'o', linewidths = 0.0, label = clients[c]['label'], s = 5.0, alpha = 0.25)

            ax1.set_xlabel("dist. of bicycle to pos. (m)")
            ax1.set_ylabel(parameters['y-axis-label'])
            ax1.set_xlim(parameters['x-limits'])
            ax1.set_ylim(parameters['y-limits'])

            ax1.legend(
                fontsize = 12, 
                ncol = 1, loc = 'upper right',
                handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, ("%s-distance.pdf" % (metric.replace(' ', '-').lower()))), bbox_inches = 'tight', format = 'pdf')

# def plot_best_ap(input_dir, output_dir, metric = 'SSI Signal', ap = ap, limits = None, seconds = 120, interval = None):

#     # FIXME: filenames should not be hardcoded (there should be only 1 link-data.csv file in the input folder)
#     pcap_file = os.path.join(args.input_dir, ("link-data.csv"))
#     gps_file = os.path.join(args.input_dir, ("gps-log.csv"))

#     plt.style.use('classic')
#     fig = plt.figure(figsize = (12, (2 * 3.0)))
#     # use GridSpec() to get similar aspect of WGTT paper
#     gs = GridSpec(2, 3)

#     ax = []
#     # data (all time)
#     # ax[0] : gs[0:1, :-1]
#     ax.append(fig.add_subplot(gs[0, :-1]))
#     # data (interval)
#     # ax[1] : gs[0:1, 2]
#     ax.append(fig.add_subplot(gs[0, 2]))
#     # best ap (all time)
#     # ax[2] : gs[2, :-1]
#     ax.append(fig.add_subplot(gs[1, :-1]))
#     # best ap (interval)
#     # ax[3] : gs[2, 2]
#     ax.append(fig.add_subplot(gs[1, 2]))

#     for x in ax:
#         x.xaxis.grid(True)
#         x.yaxis.grid(True)

#     Range = namedtuple('Range', ['start', 'end'])
#     epoch = datetime.utcfromtimestamp(0)
#     already_labeled = defaultdict(bool)
#     chunksize = 10 ** 5
#     for chunk in pd.read_csv(pcap_file, chunksize = chunksize):

#         # consider frames directed at the mobile ap only
#         chunk = chunk[chunk['dst mac'] == ap]
#         # discard empty metric values
#         chunk = chunk[np.isfinite(chunk[metric])]

#         # isolate UNIX timestamps w/ 100 msec precision
#         chunk['timestamp'] = chunk['Arrival Time'].map(lambda x : str((datetime.strptime(str(x)[:-13], '%b %d, %Y %H:%M:%S.%f') - epoch).total_seconds()))
#         # get max metric value per timestamp, for all clients
#         bap = pd.DataFrame(columns = ['timestamp'])
#         for m in clients:
#             _bap = chunk[chunk['src mac'] == m][['timestamp', metric]]
#             _bap[m] = _bap.groupby(['timestamp'])[metric].transform(max)
#             bap = pd.merge(_bap.drop_duplicates(subset = 'timestamp')[['timestamp', m]], bap, on = 'timestamp', how = 'outer')

#         # get mac of client w/ best metric for each timestamp
#         bap['max'] = bap[[m for m in clients]].idxmax(axis = 1)
#         print(bap[['timestamp', 'max']])
#         # bap['max'] = bap['max'].map(lambda x : clients[x]['id'])
#         # now plot it!
#         for m in clients:

#             data = bap[bap['max'] == m]
#             dates = [datetime.fromtimestamp(float(dt) - 3600.0) for dt in data['timestamp']]

#             if not dates:
#                 continue

#             n = len(dates)
#             # ax[2].fill_between(
#             #     dates, 
#             #     clients[m]['id'], clients[m]['id'] + 1, 
#             #     facecolor = clients[m]['color'], label = clients[m]['label'], linewidth = .01)
#             ax[2].scatter(
#                 dates,
#                 [clients[m]['id']] * n,
#                 color = clients[m]['color'], label = clients[m]['label'], marker = 'o')

#             r1 = Range(start = dates[0], end = dates[-1])
#             r2 = Range(start = interval[0], end = interval[-1])
#             if max(0.0, (min(r1.end, r2.end) - max(r1.start, r2.start)).seconds) > 0.0:
#                 # ax[3].fill_between(
#                 #     dates, 
#                 #     clients[m]['id'], clients[m]['id'] + 1, 
#                 #     facecolor = clients[m]['color'], label = clients[m]['label'], linewidth = .01)
#                 ax[3].scatter(
#                     dates,
#                     [clients[m]['id']] * n,
#                     color = clients[m]['color'], label = clients[m]['label'], marker = 'o')

#         # extract metric values, group by 'src mac' (and include other fields such as 'Arrival Time' and 'Type/Subtype')
#         chunk = chunk.groupby(['no', 'Arrival Time', 'Type/Subtype', 'src mac'])[metric].apply(float).reset_index()

#         # plot metric values for each client
#         for m in clients:
#             data = chunk[chunk['src mac'] == m]
#             # exit if data is empty
#             if data.empty:
#                 continue

#             # transform arrival times in date objects (disregard the last 8 digits of the date strings, always '000 WEST')
#             dates = [ datetime.strptime(dt[:-8], '%b %d, %Y %H:%M:%S.%f') for dt in data['Arrival Time'] ]
#             # keep track of labels
#             if m not in already_labeled:
#                 already_labeled[m] = False

#             # plot metric values for the complete collection time
#             ax[0].plot_date(
#                 dates,
#                 data[metric],
#                 linewidth = 1.0, color = clients[m]['color'], linestyle = '-', label = (clients[m]['label'] if not already_labeled[m] else ''), marker = None)
            
#             already_labeled[m] = True

#             # if dates and interval overlap, plot ax[1]
#             r1 = Range(start = dates[0], end = dates[-1])
#             r2 = Range(start = interval[0], end = interval[-1])
#             if max(0.0, (min(r1.end, r2.end) - max(r1.start, r2.start)).seconds) > 0.0:
#                 ax[1].plot_date(
#                     dates,
#                     data[metric],
#                     linewidth = 1.0, color = clients[m]['color'], linestyle = '-', marker = None)

#     ax[0].set_title("rssi (at mobile) ap", fontsize = 12)
#     ax[0].set_xlabel("time")
#     ax[0].set_ylabel("rssi at mobile ap (dBm)")

#     ax[0].axvspan(interval[0], interval[1], linewidth = 0.0, facecolor = '#bebebe', alpha = 0.75)

#     ax[0].legend(
#             fontsize = 12, 
#             ncol = 3, loc = 'upper right',
#             handletextpad = 0.2, handlelength = 2.0, labelspacing = 0.2, columnspacing = 0.5)

#     ax[0].set_ylim([-95 , -40])
#     ax[1].set_ylim([-95 , -40])

#     ax[1].set_title("rssi (at mobile) ap (detail)", fontsize = 12)
#     ax[1].set_xlabel("time")

#     ax[2].set_title("best pos.", fontsize = 12)
#     ax[2].set_xlabel("time")
#     ax[2].set_ylabel("pos.")

#     ax[3].set_title("best pos. (detail)", fontsize = 12)
#     ax[3].set_xlabel("time")

#     ax[0].set_xlim(limits[0], limits[1])
#     ax[1].set_xlim(interval[0], interval[1])
#     ax[2].set_xlim(limits[0], limits[1])
#     ax[3].set_xlim(interval[0], interval[1])

#     ax[2].set_ylim([-1, 3])
#     ax[3].set_ylim([-1, 3])

#     delta = timedelta(seconds = seconds)
#     xticks = np.arange(limits[0], limits[1] + delta, delta)
#     ax[2].set_xticks(xticks)
#     ax[2].set_xticklabels([str(xt)[11:-7] for xt in xticks])

#     delta = timedelta(seconds = 30)
#     xticks = np.arange(interval[0], interval[1] + delta, delta)
#     ax[3].set_xticks(xticks)
#     ax[3].set_xticklabels([str(xt)[11:-7] for xt in xticks])

#     ax[2].set_yticks([0, 1, 2])
#     ax[2].set_yticklabels(['0', '1', '2'])
#     ax[3].set_yticks([0, 1, 2])
#     ax[3].set_yticklabels(['0', '1', '2'])

#     plt.gcf().autofmt_xdate()
#     # plt.tight_layout()
#     plt.savefig(os.path.join(output_dir, ("wgtt-graph-1.pdf")), bbox_inches = 'tight', format = 'pdf')

# def plot_rssi(input_dir, output_dir, ap = ap, limits = None, seconds = 120):

#     # FIXME: filenames should not be hardcoded (there should be only 1 link-data.csv file in the input folder)
#     scan_file = os.path.join(args.input_dir, ("link-data.csv"))
#     gps_file = os.path.join(args.input_dir, ("gps-log.csv"))

#     plt.style.use('classic')
#     fig = plt.figure(figsize = (12.5, (3.5 * 2.0)))

#     ax1 = fig.add_subplot(211)
#     ax1.xaxis.grid(True)
#     ax1.yaxis.grid(True)

#     done = defaultdict(bool)
#     date_limits = []
#     chunksize = 10 ** 5
#     for chunk in pd.read_csv(scan_file, chunksize = chunksize):

#         # consider frames directed at the mobile ap only
#         chunk = chunk[chunk['dst mac'] == ap]
#         # discard empty rssi values
#         chunk = chunk[np.isfinite(chunk['SSI Signal'])]
#         # extract rssis, group by 'src mac' (and include other fields such as 'Arrival Time' and 'Type/Subtype')
#         chunk = chunk.groupby(['no', 'Arrival Time', 'Type/Subtype', 'src mac'])['SSI Signal'].apply(float).reset_index()

#         # plot rssis for each client
#         for m in clients:

#             # extract rssis from specific client m
#             data = chunk[chunk['src mac'] == m]
#             # exit if data is empty
#             if data.empty:
#                 continue

#             # transform arrival times in date objects (disregard the last 8 digits of the date strings, always '000 WEST')
#             dates = [ datetime.strptime(dt[:-8], '%b %d, %Y %H:%M:%S.%f') for dt in data['Arrival Time'] ]
#             if m not in done:
#                 done[m] = False

#             ax1.plot_date(
#                 dates,
#                 data['SSI Signal'],
#                 linewidth = 1.0, color = clients[m]['color'], linestyle = '-', label = (clients[m]['label'] if not done[m] else ''), marker = None)

#             done[m] = True

#     ax1.legend(
#             fontsize = 12, 
#             title = 'client',
#             ncol = 3, loc = 'upper right',
#             handletextpad = 0.2, handlelength = 2.0, labelspacing = 0.2, columnspacing = 0.5)

#     ax1.set_title("rssi (at mobile) ap vs. time", fontsize = 12)
#     ax1.set_xlabel("time")
#     ax1.set_ylabel("rssi at mobile ap (dBm)")

#     ax1.set_ylim(-95, -40)

#     ax2 = fig.add_subplot(212)
#     ax2.xaxis.grid(True)
#     ax2.yaxis.grid(True)

#     chunksize = 10 ** 5
#     for chunk in pd.read_csv(gps_file, chunksize = chunksize):

#         # FIXME: the +3600 serves to add 1 hr (the gps device uses the wrong timezone?)
#         dates = [datetime.fromtimestamp(dt + 3600.0) for dt in chunk['time']]
#         # get a list of gps positions (latitude, longitude), for each datapoint in the .csv file
#         gps_pos = [ [row['lat'], row['lon'] ] for index, row in chunk.iterrows()]

#         # update limits for xx axis
#         update_limits(date_limits, dates)

#         # plot the distance of the (lat, lon) datapoints to each the n client positions, indexed 
#         # by the date & time at which datapoints were collected
#         for m in clients:
#             ax2.plot_date(
#                 dates,
#                 [ gps_to_dist(clients[m]['lat'], clients[m]['lon'], gps[0], gps[1]) for gps in gps_pos],
#                 linewidth = 1.0, color = clients[m]['color'], linestyle = '-', label = clients[m]['label'], marker = None)

#     ax2.set_title("distance from mobile ap to client pos.", fontsize = 12)
#     ax2.set_xlabel("time")
#     ax2.set_ylabel("dist. from mobile ap to client pos. (m)")

#     # set xx limits to align with those of the rssi graph
#     if limits is not None:
#         date_limits = limits

#     ax1.set_xlim(date_limits[0], date_limits[1])
#     ax2.set_xlim(date_limits[0], date_limits[1])
#     ax2.set_ylim(0, 100)

#     # get xticks every 120 seconds
#     delta = timedelta(seconds = seconds)
#     xticks = np.arange(date_limits[0], date_limits[1] + delta, delta)
#     ax1.set_xticks(xticks)
#     ax2.set_xticks(xticks)
#     ax1.set_xticklabels([str(xt)[11:-7] for xt in xticks])
#     ax2.set_xticklabels([str(xt)[11:-7] for xt in xticks])

#     plt.gcf().autofmt_xdate()
#     plt.tight_layout()
#     plt.savefig(os.path.join(output_dir, ("rssi-traces.pdf")), bbox_inches = 'tight', format = 'pdf')

# def plot_iperf(input_dir, output_dir, ap = ap, limits = None, seconds = 120):

#     date_limits = []
#     # FIXME: filenames should not be hardcoded (there should be only 1 link-data.csv file in the input folder)
#     scan_file = os.path.join(args.input_dir, ("link-data.csv"))
#     gps_file = os.path.join(args.input_dir, ("gps-log.csv"))

#     # plot losses for each position
#     plt.style.use('classic')
#     fig = plt.figure(figsize = (12.5, (3.5 * 3.0)))

#     ax1 = fig.add_subplot(311)
#     ax1.xaxis.grid(True)
#     ax1.yaxis.grid(True)

#     ax2 = fig.add_subplot(312)
#     ax2.xaxis.grid(True)
#     ax2.yaxis.grid(True)

#     done = defaultdict(bool)
#     date_limits = []
#     chunksize = 10 ** 5
#     for chunk in pd.read_csv(scan_file, chunksize = chunksize):

#         # consider frames directed at the mobile ap only
#         chunk = chunk[chunk['dst mac'] == ap]
#         # discard empty rssi values
#         chunk = chunk[np.isfinite(chunk['SSI Signal'])]
#         # # extract rssis, group by 'src mac' (and include other fields such as 'Arrival Time' and 'Type/Subtype')
#         # chunk = chunk.groupby(['no', 'Arrival Time', 'Type/Subtype', 'src mac'])[['SSI Signal', 'Data rate']].count().reset_index()
#         # print(chunk)

#         # plot rssis for each client
#         for m in clients:

#             # extract rssis from specific client m
#             data = chunk[chunk['src mac'] == m]
#             # exit if data is empty
#             if data.empty:
#                 continue

#             # transform arrival times in date objects (disregard the last 8 digits of the date strings, always '000 WEST')
#             dates = [ datetime.strptime(dt[:-8], '%b %d, %Y %H:%M:%S.%f') for dt in data['Arrival Time'] ]
#             if m not in done:
#                 done[m] = False

#             ax1.plot_date(
#                 dates,
#                 data['SSI Signal'],
#                 linewidth = 1.0, color = clients[m]['color'], linestyle = '-', label = (clients[m]['label'] if not done[m] else ''), marker = None)

#             ax2.scatter(
#                 dates,
#                 data['Data rate'],
#                 linewidth = 1.0, color = clients[m]['color'], label = clients[m]['label'], s = 25, marker = 'o')

#             done[m] = True

#     ax1.legend(
#             fontsize = 12, 
#             title = 'client',
#             ncol = 3, loc = 'upper right',
#             handletextpad = 0.2, handlelength = 2.0, labelspacing = 0.2, columnspacing = 0.5)

#     ax1.set_title("rssi (at mobile ap) vs. time", fontsize = 12)
#     ax1.set_xlabel("time")
#     ax1.set_ylabel("rssi at mobile ap (dBm)")
#     ax1.set_ylim(-95, -40)

#     # for m in clients:
#     #     for file_name in sorted(glob.glob(os.path.join(input_dir, ('%s/*.csv' % (m))))):
#     #         chunksize = 10 ** 5
#     #         for chunk in pd.read_csv(file_name, chunksize = chunksize):

#     #             dates = [datetime.fromtimestamp(dt) for dt in chunk['time']]
#     #             ax2.scatter(
#     #                 dates,
#     #                 chunk['res-bw'] / 1000000.0,
#     #                 linewidth = 1.0, color = clients[m]['color'], label = clients[m]['label'], s = 25, marker = '^')

#     ax2.set_title("802.11n bitrates (Mbps)", fontsize = 12)
#     ax2.set_xlabel("time")
#     ax2.set_ylabel("802.11n bitrates (Mbps)")

#     # ax2.set_ylim(0.0, 12.0)

#     ax3 = fig.add_subplot(313)
#     ax3.xaxis.grid(True)
#     ax3.yaxis.grid(True)

#     chunksize = 10 ** 5
#     for chunk in pd.read_csv(gps_file, chunksize = chunksize):

#         # FIXME: the +3600 serves to add 1 hr (the gps device uses the wrong timezone?)
#         dates = [datetime.fromtimestamp(dt + 3600.0) for dt in chunk['time']]
#         # get a list of gps positions (latitude, longitude), for each datapoint in the .csv file
#         gps_pos = [ [row['lat'], row['lon'] ] for index, row in chunk.iterrows()]

#         # update limits for xx axis
#         update_limits(date_limits, dates)

#         # plot the distance of the (lat, lon) datapoints to each the n client positions, indexed 
#         # by the date & time at which datapoints were collected
#         for m in clients:
#             ax3.plot_date(
#                 dates,
#                 [ gps_to_dist(clients[m]['lat'], clients[m]['lon'], gps[0], gps[1]) for gps in gps_pos],
#                 linewidth = 1.0, color = clients[m]['color'], linestyle = '-', label = clients[m]['label'], marker = None)

#     ax3.set_title("distance from mobile ap to client pos.", fontsize = 12)
#     ax3.set_xlabel("time")
#     ax3.set_ylabel("dist. from mobile ap\nto client pos. (m)")

#     ax3.set_ylim(0, 100)

#     # set xx limits to align with those of the rssi graph
#     if limits is not None:
#         date_limits = limits

#     ax1.set_xlim(date_limits[0], date_limits[1])
#     ax2.set_xlim(date_limits[0], date_limits[1])
#     ax3.set_xlim(date_limits[0], date_limits[1])

#     # get xticks every 120 seconds
#     delta = timedelta(seconds = seconds)
#     xticks = np.arange(date_limits[0], date_limits[1] + delta, delta)
#     ax1.set_xticks(xticks)
#     ax2.set_xticks(xticks)
#     ax3.set_xticks(xticks)
#     ax1.set_xticklabels([str(xt)[11:-7] for xt in xticks])
#     ax2.set_xticklabels([str(xt)[11:-7] for xt in xticks])
#     ax3.set_xticklabels([str(xt)[11:-7] for xt in xticks])

#     plt.gcf().autofmt_xdate()
#     plt.tight_layout()
#     plt.savefig(os.path.join(output_dir, ("iperf-stats.pdf")), bbox_inches = 'tight', format = 'pdf')

def parse_syslog(input_dir, trace_nr):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    filename = os.path.join(trace_dir, ("pos1/syslog"))

    cbt_file = csv.writer(open(os.path.join(trace_dir, ("pos1/cbt.csv")), 'wb+', 0))
    cbt_file.writerow(['timestamp', 'mac-addr', 'channel', 'freq', 'bitrate', 'noise', 'channel-active-time', 'channel-busy-time', 'channel-receive-time', 'channel-transmit-time'])

    iperf3_file = csv.writer(open(os.path.join(trace_dir, ("pos1/iperf3-to-mobile.results.csv")), 'wb+', 0))
    iperf3_file.writerow(['time', 'cpu-sndr', 'cpu-rcvr'])

    iperf3_dict = defaultdict()
    epoch = datetime.datetime.utcfromtimestamp(0)
    f = open(filename, "r")
    for line in f:
        if (re.search("cb", line) and re.search(('\|%03d\|' % (int(trace_nr))), line)):
            
            line = line.replace('\n', '').split()

            # parse timestamp from date
            dt = ("%s %02d 2018 %s" % (line[0], int(line[1]), line[2]))
            timestamp = (datetime.datetime.strptime(dt, '%b %d %Y %H:%M:%S') - epoch).total_seconds()
            # parse trace params
            mac_addr = line[5].split('|')[0]
            channel = line[5].split('|')[2]
            freq = line[6].split(',')[0]
            bitrate = line[5].split('|')[3]
            # parse cbt params
            noise = line[6].split(',')[1]
            cat = line[6].split(',')[2]
            cbt = line[6].split(',')[3]
            crt = line[6].split(',')[4]
            ctt = line[6].split(',')[5]

            cbt_file.writerow([timestamp, mac_addr, channel, freq, bitrate, noise, cat, cbt, crt, ctt])

        elif (re.search("ipe", line) and re.search(('\|%03d\|' % (int(trace_nr))), line)):

            line = line.replace('\n', '').split()

            dt = ("%s %02d 2018 %s" % (line[0], int(line[1]), line[2]))
            timestamp = (datetime.datetime.strptime(dt, '%b %d %Y %H:%M:%S') - epoch).total_seconds()

            if re.search(('remote_total'), line[-1]):

                val = float(line[-1].split('#011')[-1].rstrip(','))
                if timestamp in iperf3_dict:
                    iperf3_dict[timestamp]['cpu-rcvr'] = val
                else:
                    iperf3_dict[timestamp] = {'cpu-sndr' : 0.0, 'cpu-rcvr' : val}

            elif re.search(('host_total'), line[-1]):

                val = float(line[-1].split('#011')[-1].rstrip(','))
                if timestamp in iperf3_dict:
                    iperf3_dict[timestamp]['cpu-sndr'] = val
                else:
                    iperf3_dict[timestamp] = {'cpu-sndr' : val, 'cpu-rcvr' : 0.0}

    for timestamp in iperf3_dict:
        iperf3_file.writerow( [ timestamp, iperf3_dict[timestamp]['cpu-sndr'], iperf3_dict[timestamp]['cpu-rcvr'] ] )

def extract_ip_id(ip_id):
    return float(ip_id.split(' ')[-1].lstrip('(').rstrip(')'))

def plot_time(input_dir, trace_nr, output_dir,
    zoom = None):

    plt.style.use('classic')
    fig = plt.figure(figsize = (5, 4.0))

    # keep track of xx axis min and max so that all data for each pos series is shown
    xx_limits = [None, None]
    if zoom is None:
        xx_limits = [None, None]
    else:
        xx_limits = zoom

    labels = defaultdict(str)
    for mac in clients:
        labels[mac] = clients[mac]['label']

    plot_configs = OrderedDict([
        ('wlan rssi', { 
            'metrics' : ['wlan rssi'], 
            'linewidth' : 0.75,
            'marker' : None,
            'markersize' : 0.0,
            'markeredgewidth' : 0.0, 
            'axis-labels' : ['time', 'rssi (dBm)'] }), 
        # 'inter-arrival' : { 
        #     'metrics' : ['diff'], 
        #     'linewidth' : 0.75,
        #     'marker' : None,
        #     'markersize' : 0.0,
        #     'markeredgewidth' : 0.0, 
        #     'axis-labels' : ['time', 'pkt inter-arr. time (s)'], 
        #     'scale' : ['linear', 'log'] }, 
        # ('seq', { 
        #     'metrics' : ['ip seq'], 
        #     'linewidth' : 0.00,
        #     'marker' : 'o',
        #     'markersize' : 2.00,
        #     'markeredgewidth' : 0.0, 
        #     'axis-labels' : ['time', 'ip id.frag offset'] }),
        ('bitrate', { 
            'metrics' : ['bitrate'], 
            'linewidth' : 0.00,
            'marker' : 'o',
            'markersize' : 2.0,
            'markeredgewidth' : 0.0,
            'scale' : ['linear', 'log'],
            'y-limits' : [400000, 50000000],
            'axis-labels' : ['time', 'bitrate (bps)'] })
    ])

    ax = OrderedDict()
    for m, category in enumerate(plot_configs.keys()):
        ax[category] = fig.add_subplot(211 + m)
        ax[category].xaxis.grid(True)
        ax[category].yaxis.grid(True)

    # all rssi data that matters is in the monitor.*.csv file in mobile/
    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    for fname in sorted(glob.glob(os.path.join(trace_dir, 'mobile/monitor.wlx24050faaab5d.*.csv'))):

        chunksize = 10 ** 5
        for chunk in pd.read_csv(fname, chunksize = chunksize):
            for mac in clients:

                # we only care about rows w/ src station being the client
                data = chunk[(chunk['mac src'] == mac) & (chunk['mac dst'] == ap) & (chunk['ip proto'] == 'UDP')].reset_index()
                if data.empty:
                    continue

                data['diff'] = data['epoch time'].astype(float) - data['epoch time'].shift(1).astype(float)
                # seq numbers
                data['ip seq'] = data.loc[~data['ip id'].isnull()]['ip id'].apply(extract_ip_id)
                data['ip seq'] += (data.loc[~data['ip id'].isnull()]['ip frag offset'].astype(float) / 10000.0)
                data['ip seq'] /= 1000.0
                # for bitrate
                timestamp_ref = data.iloc[0]['epoch time'].astype(float)
                data['bitrate'] = (data['frame len'].cumsum(axis = 0) * 8.0) / (data['epoch time'].astype(float) - timestamp_ref)

                for category in plot_configs:
                    for metric in plot_configs[category]['metrics']:

                        # extract data for plot
                        df = data[np.isfinite(data[metric])]

                        # re-sampling to reduce amoung 
                        if category == 'bitrate':
                            df = df.iloc[::50, :]

                        # x axis should be in datetime objects, for plot_date()
                        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in df['epoch time'] ]

                        if not dates:
                            continue

                        # update the x axis limits
                        if zoom is None:
                            update_limits(xx_limits, dates)

                        ax[category].plot_date(
                            dates,
                            df[metric],
                            linewidth = plot_configs[category]['linewidth'], linestyle = '-', 
                            color = clients[mac]['color'], label = labels[mac], 
                            markersize = plot_configs[category]['markersize'], 
                            marker = plot_configs[category]['marker'], 
                            markeredgewidth = plot_configs[category]['markeredgewidth'])

                # only add labels once per pos series
                labels[mac] = ''

    # divide xx axis in 5 ticks
    delta = datetime.timedelta(seconds = ((xx_limits[1] - xx_limits[0]).total_seconds() / 5))
    xticks = np.arange(xx_limits[0], xx_limits[1] + delta, delta)

    for category in plot_configs:

        ax[category].legend(
            fontsize = 12, 
            ncol = 3, loc = 'upper right',
            handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

        # set axis labels
        ax[category].set_xlabel(plot_configs[category]['axis-labels'][0])
        ax[category].set_ylabel(plot_configs[category]['axis-labels'][1])

        # set x axis limits according to xx_limits
        ax[category].set_xlim(xx_limits[0], xx_limits[1])

        if 'scale' in plot_configs[category]:
            ax[category].set_yscale(plot_configs[category]['scale'][1])
        if 'y-limits' in plot_configs[category]:
            ax[category].set_ylim(plot_configs[category]['y-limits'])

        ax[category].set_xticks(xticks)
        ax[category].set_xticklabels([str(xt)[11:-7] for xt in xticks])

    plt.gcf().autofmt_xdate()
    plt.tight_layout()

    # create output dir for trace (if not existent)
    trace_output_dir = os.path.join(output_dir, ("trace-%03d" % (int(trace_nr))))
    if not os.path.isdir(trace_output_dir):
        os.makedirs(trace_output_dir)

    plt.savefig(os.path.join(trace_output_dir, ("rssi-%s.pdf" % (trace_nr))), bbox_inches = 'tight', format = 'pdf')                


def plot_cbt(input_dir, trace_nr, output_dir,
    zoom = None):

    # FIXME: for now, only pos1 collects cbt directly
    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    filename = os.path.join(trace_dir, ("pos1/cbt.csv"))

    # get cbt data
    if not os.path.isfile(filename):
        parse_syslog(input_dir, trace_nr)

    cbt_data = pd.read_csv(filename)

    plt.style.use('classic')
    fig = plt.figure(figsize = (5, 3.0))
    ax = fig.add_subplot(111)
    ax.xaxis.grid(True)
    ax.yaxis.grid(True)

    # identify segments of increasingly monotonic cat
    cbt_data['diff'] = cbt_data['channel-active-time'] - cbt_data['channel-active-time'].shift(1)
    segments = list(cbt_data.index[cbt_data['diff'] < 0.0])
    segments.append(len(cbt_data) - 1)

    channel = int(cbt_data.iloc[0]['channel'])
    prev_seg = 0

    # keep track of xx axis min and max so that all data for each pos series is shown
    xx_limits = [None, None]
    if zoom is None:
        xx_limits = [None, None]
    else:
        xx_limits = zoom

    labels = ['busy time', 'rx time', 'tx time']
    for seg in segments:

        data = cbt_data.iloc[prev_seg:seg]
        if len(data) == 1:
            continue

        diff_cat = data['channel-active-time'] - data['channel-active-time'].shift(1)
        diff_cbt = data['channel-busy-time'] - data['channel-busy-time'].shift(1)

        # FIXME : fixes an error in cbt.csv of trace-009
        if (channel == 20):
            channel = 1

        if (channel > 13):
            diff_crt = data['channel-receive-time']
            diff_ctt = data['channel-transmit-time']
        else:
            diff_crt = data['channel-receive-time'] - data['channel-receive-time'].shift(1)
            diff_ctt = data['channel-transmit-time'] - data['channel-transmit-time'].shift(1)

        data['cbt'] = diff_cbt / diff_cat
        data['crt'] = diff_crt / diff_cat
        data['ctt'] = diff_ctt / diff_cat

        dates = [ datetime.datetime.fromtimestamp(float(dt) - 3600) for dt in data['timestamp'] ]

        ax.plot_date(
            dates,
            data['cbt'],
            linewidth = 0.75, linestyle = '-', color = 'red', label = labels[0], marker = None)

        ax.plot_date(
            dates,
            data['crt'],
            linewidth = 0.75, linestyle = '-', color = 'green', label = labels[1], marker = None)

        ax.plot_date(
            dates,
            data['ctt'],
            linewidth = 0.75, linestyle = '-', color = 'blue', label = labels[2], marker = None)

        # update the x axis limits
        if zoom is None:
            update_limits(xx_limits, dates)

        prev_seg = seg
        labels = ['', '', '']

    ax.legend(
        fontsize = 12, 
        ncol = 3, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    ax.set_xlabel("time")
    ax.set_ylabel("% of 1 sec")

    ax.set_xlim(xx_limits[0], xx_limits[1])
    ax.set_ylim([0.0, 1.3])
    ax.set_yticks(np.arange(0.0, 1.2, 0.2))

    # divide xx axis in 5 ticks
    delta = datetime.timedelta(seconds = ((xx_limits[1] - xx_limits[0]).total_seconds() / 5))
    xticks = np.arange(xx_limits[0], xx_limits[1] + delta, delta)
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(xt)[11:-7] for xt in xticks])

    plt.gcf().autofmt_xdate()
    plt.tight_layout()

    # create output dir for trace (if not existent)
    trace_output_dir = os.path.join(output_dir, ("trace-%03d" % (int(trace_nr))))
    if not os.path.isdir(trace_output_dir):
        os.makedirs(trace_output_dir)

    plt.savefig(os.path.join(trace_output_dir, ("ct-%s.pdf" % (trace_nr))), bbox_inches = 'tight', format = 'pdf')

def plot_ntp(input_dir, trace_nr, output_dir):

    plt.style.use('classic')
    fig = plt.figure(figsize = (5, 3.0))
    ax = fig.add_subplot(111)
    ax.xaxis.grid(True)
    ax.yaxis.grid(True)

    xx_limits = [None, None]
    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    for peer in peers.keys():

        peer_dir = os.path.join(trace_dir, ("%s" % (peer)))
        for filename in sorted(glob.glob(os.path.join(peer_dir, 'ntpstat.*.csv'))):

            ntp_data = pd.read_csv(filename)
            dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in ntp_data['timestamp'] ]

            if not dates:
                continue

            update_limits(xx_limits, dates)

            # TODO: add a line marking the start of the experiment  
            ax.plot_date(
                dates,
                ntp_data['delta'],
                linewidth = 0.75, linestyle = '-', color = peers[peer]['color'], label = peer, marker = None)

    ax.legend(
        fontsize = 12, 
        ncol = 2, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    ax.set_xlabel("time")
    ax.set_ylabel("ntp offset (ms)")

    # log scale due to major differences in yy axis
    ax.set_yscale('log')
    ax.set_xlim(xx_limits[0], xx_limits[1])

    # divide xx axis in 5 ticks
    delta = datetime.timedelta(seconds = ((xx_limits[1] - xx_limits[0]).total_seconds() / 5))
    xticks = np.arange(xx_limits[0], xx_limits[1] + delta, delta)
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(xt)[11:-7] for xt in xticks])

    plt.gcf().autofmt_xdate()
    plt.tight_layout()

    # create output dir for trace (if not existent)
    trace_output_dir = os.path.join(output_dir, ("trace-%03d" % (int(trace_nr))))
    if not os.path.isdir(trace_output_dir):
        os.makedirs(trace_output_dir)

    plt.savefig(os.path.join(trace_output_dir, ("ntp-stats-%s.pdf" % (trace_nr))), bbox_inches = 'tight', format = 'pdf')

def plot_cpu(input_dir, trace_nr, output_dir,
    zoom = None):

    plt.style.use('classic')
    fig = plt.figure(figsize = (5, 3.0))
    ax = fig.add_subplot(111)
    ax.xaxis.grid(True)
    ax.yaxis.grid(True)

    # keep track of xx axis min and max so that all data for each pos series is shown
    xx_limits = [None, None]
    if zoom is None:
        xx_limits = [None, None]
    else:
        xx_limits = zoom

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    label_mobile = 'mobile'
    for peer in peers.keys():

        if peer == 'mobile':
            continue

        peer_dir = os.path.join(trace_dir, ("%s" % (peer)))
        for filename in sorted(glob.glob(os.path.join(peer_dir, 'iperf3-to-mobile.results*.csv'))):

            cpu_data = pd.read_csv(filename)

            offset = 0.0
            if peer == 'pos1':
                offset = 3600.0
                cpu_data = cpu_data.sort_values(by = ['time'])
            dates = [ datetime.datetime.fromtimestamp(float(dt) - offset) for dt in cpu_data['time'] ]

            if not dates:
                continue

            # update the x axis limits
            if zoom is None:
                update_limits(xx_limits, dates)

            # TODO: add a line marking the start of the experiment  
            ax.plot_date(
                dates,
                cpu_data['cpu-sndr'],
                linewidth = 0.75, linestyle = '-', color = peers[peer]['color'], label = peer, marker = None)

            ax.plot_date(
                dates,
                cpu_data['cpu-rcvr'],
                linewidth = 0.0, linestyle = None, color = peers['mobile']['color'], label = label_mobile,
                marker = 'o', markersize = 2.50, markeredgewidth = 0.0)

            label_mobile = ''

    ax.legend(
        fontsize = 12, 
        ncol = 2, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    ax.set_xlabel("time")
    ax.set_ylabel("cpu usage (%)")

    # log scale due to major differences in yy axis
    # ax.set_yscale('log')
    ax.set_xlim(xx_limits[0], xx_limits[1])
    ax.set_ylim([0.0, 20.0])

    # divide xx axis in 5 ticks
    delta = datetime.timedelta(seconds = ((xx_limits[1] - xx_limits[0]).total_seconds() / 5))
    xticks = np.arange(xx_limits[0], xx_limits[1] + delta, delta)
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(xt)[11:-7] for xt in xticks])

    plt.gcf().autofmt_xdate()
    plt.tight_layout()

    # create output dir for trace (if not existent)
    trace_output_dir = os.path.join(output_dir, ("trace-%03d" % (int(trace_nr))))
    if not os.path.isdir(trace_output_dir):
        os.makedirs(trace_output_dir)

    plt.savefig(os.path.join(trace_output_dir, ("cpu-stats-%s.pdf" % (trace_nr))), bbox_inches = 'tight', format = 'pdf')    

def list_traces(input_dir):

    filename = os.path.join(input_dir, ("trace-info.csv"))
    if not os.path.isfile(filename):
        sys.stderr.write("""%s: [ERROR] no 'trace-info.csv' at %s\n""" % (sys.argv[0], input_dir))
        return -1

    trace_info = pd.read_csv(filename)
    table = PrettyTable(list(trace_info.columns))
    for i, row in trace_info.iterrows():
        table.add_row([
            ('%s' % (row['trace-nr'])),
            ('%d' % (row['channel'])), 
            ('%d' % (row['bw'])),
            ('%dM' % (row['bitrate']))
            ])

    print(table)
    return 0

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--input-dir", 
         help = """dir w/ trace data""")

    parser.add_argument(
        "--list-traces", 
         help = """lists available traces""",
         action = 'store_true')

    parser.add_argument(
        "--trace-nr", 
         help = """nr of trace to analyze. e.g., '--trace-nr 009'""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save graphs & other output data""")

    args = parser.parse_args()

    if not args.input_dir:
        sys.stderr.write("""%s: [ERROR] must provide a dir w/ input files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if args.list_traces:
        list_traces(args.input_dir)
        sys.exit(0)

    if not args.trace_nr:
        sys.stderr.write("""%s: [ERROR] must provide a trace nr. to analyze\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] must provide an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    plot_ntp(args.input_dir, args.trace_nr, args.output_dir)
    # plot_time(args.input_dir, args.trace_nr, args.output_dir,
    #     zoom = [ datetime.datetime(2018, 8, 7, 16, 58), datetime.datetime(2018, 8, 7, 17, 02) ])
    # plot_cbt(args.input_dir, args.trace_nr, args.output_dir,
    #     zoom = [ datetime.datetime(2018, 8, 7, 16, 58), datetime.datetime(2018, 8, 7, 17, 02) ])
    # plot_cpu(args.input_dir, args.trace_nr, args.output_dir,
    #     zoom = [ datetime.datetime(2018, 8, 7, 16, 58), datetime.datetime(2018, 8, 7, 17, 02) ])

    plot_time(args.input_dir, args.trace_nr, args.output_dir)
    plot_cbt(args.input_dir, args.trace_nr, args.output_dir)
    plot_cpu(args.input_dir, args.trace_nr, args.output_dir)

    # plot_rssi(args.input_dir, args.output_dir, limits = [datetime(2018, 6, 19, 16, 36), datetime(2018, 6, 19, 16, 38)], seconds = 10)
    # plot_rssi(args.input_dir, args.output_dir, limits = [datetime(2018, 6, 19, 16, 44), datetime(2018, 6, 19, 16, 46)], seconds = 10)
    # plot_rssi(args.input_dir, args.output_dir, limits = [datetime(2018, 6, 19, 16, 27), datetime(2018, 6, 19, 16, 49)], seconds = 60)
    # plot_iperf(args.input_dir, args.output_dir, limits = [datetime(2018, 6, 19, 16, 44), datetime(2018, 6, 19, 16, 46)], seconds = 10)
    # plot_best_ap(
    #     args.input_dir, args.output_dir, 
    #     limits = [datetime(2018, 6, 19, 16, 27), datetime(2018, 6, 19, 16, 49)], 
    #     interval = [datetime(2018, 6, 19, 16, 44), datetime(2018, 6, 19, 16, 46)])
    # extract_metrics(args.input_dir)
    # time_analysis(args.input_dir, args.output_dir)
    # vs_distance(args.input_dir, args.output_dir)
    # vs_distance(args.input_dir, args.output_dir, 'loss', 
    #     parameters = {'y-axis-label' : 'packet loss (%)', 'x-limits' : [0.0, 200.0], 'scale-by' : 1.0, 'y-limits' : [-0.05, 1.0]})
    # vs_distance(args.input_dir, args.output_dir, 'res-bw', 
    #     parameters = {'y-axis-label' : 'meas. bandwidth (Mbps)', 'x-limits' : [0.0, 200.0], 'scale-by' : 1000000.0, 'y-limits' : [0.0, 10.5]})
    # metric_analysis(args.input_dir, args.output_dir,
    #     metric = 'SSI Signal',
    #     channels = {'2.4' : ['01', '11'], '5.1' : ['36']},
    #     parameters = {
    #         'cdf' : {'y-axis-label' : 'CDF', 'x-limits' : [0.0, 5.0], 'y-limits' : [0.75, 1.0], 'scale-by' : 1.0},
    #         'duration-vs-dist' : {'x-limits' : [0.0, 200.0], 'y-limits' : [0.0, 0.250], 'scale-by' : 1.0}})
    # metric_analysis(args.input_dir, args.output_dir,
    #     metric = 'res-bw',
    #     channels = {'2.4' : ['01', '11'], '5.1' : ['36']},
    #     parameters = {
    #         'cdf' : {'y-axis-label' : 'CDF', 'x-limits' : [0.0, 10.0], 'y-limits' : [0.75, 1.0], 'scale-by' : 1.0},
    #         'duration-vs-dist' : {'x-limits' : [0.0, 200.0], 'y-limits' : [0.0, 0.100], 'scale-by' : 1.0}})
    # predict_performance(args.input_dir, args.output_dir)
    # get_laps(args.input_dir, args.output_dir, freq = '5.1', channel = '36')

    sys.exit(0)