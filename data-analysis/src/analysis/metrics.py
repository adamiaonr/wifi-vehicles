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

def process_metric(data, metric, interval = 0.5):

    proc_data = None
    if metric == 'throughput':
            
        # throughput calculated based on wlan frame length
        proc_data = data[['interval-tmstmp', 'frame len']]
        # groupby() 'interval-tmstmp', and SUM() size of frames, in byte
        proc_data = proc_data[['interval-tmstmp', 'frame len']].groupby(['interval-tmstmp']).sum().reset_index().sort_values(by = ['interval-tmstmp'])
        proc_data['throughput'] = (proc_data['frame len'] * 8.0) / interval

    elif metric == 'wlan data rate':

        proc_data = data[['interval-tmstmp', 'wlan data rate']]
        # groupby() 'interval-tmstmp', and get MEAN() wlan data rate over the interval
        proc_data = proc_data[['interval-tmstmp', 'wlan data rate']].groupby(['interval-tmstmp']).mean().reset_index().sort_values(by = ['interval-tmstmp'])
        # multiply by 10^6 for bps
        proc_data['wlan data rate'] = proc_data['wlan data rate'] * 1000000.0

    elif metric == 'wlan rssi':

        proc_data = data[['interval-tmstmp', 'wlan rssi']]
        # groupby() 'interval-tmstmp', and get mean rssi over the interval
        proc_data = proc_data[['interval-tmstmp', 'wlan rssi']].groupby(['interval-tmstmp']).mean().reset_index().sort_values(by = ['interval-tmstmp'])
        proc_data['wlan rssi'] = proc_data['wlan rssi'].astype(float)

    return proc_data

def calc_frame_duration(wlan_frames):
    duration = (( 8.0 * (wlan_frames['frame len'].values)) / wlan_frames['wlan data rate'].values) + wlan_frames['wlan preamble']
    return duration

def calc_cbt(input_file):

    # dataframe to contain all cbt info for some channel
    cbt = pd.DataFrame(columns = ['timestamp', 'cbt', 'utilization'])
    frame_types = pd.DataFrame()

    chunksize = 10 ** 5
    for chunk in pd.read_csv(input_file, chunksize = chunksize):

        # divide chunk in 1 sec periods:
        #   - calculate the end transmission times (epoch time + frame duration), in micro sec
        chunk['end-time'] = chunk['epoch time'] + (chunk['wlan duration'] / 1000000.0)
        #   - we calculate cbt per each 1 sec block
        chunk['timestamp'] = chunk['epoch time'].astype(int)
        # get count of type / subtypes per 1 sec period
        counts = chunk.groupby(['timestamp', 'wlan phy', 'wlan preamble', 'wlan type-subtype', 'frame len', 'wlan data rate', 'wlan duration'])['no'].agg('count').reset_index()
        counts.columns = ['timestamp', 'wlan phy', 'wlan preamble', 'wlan type-subtype', 'frame len', 'wlan data rate', 'wlan duration', 'count']
        counts['frame duration'] = calc_frame_duration(counts)
        frame_types = pd.concat([frame_types, counts], ignore_index = True)
        # print(counts[['period-no', 'wlan type-subtype', 'count']])

        # calc cbt per 1 sec period
        for ts in counts['timestamp'].unique():
            _counts = counts[counts['timestamp'] == ts]
            # _cbt = np.sum(_counts['count'].values * _counts['wlan duration'].values)
            _cbt = np.sum(_counts['count'].values * _counts['frame duration'].values)
            # append result to final dataframe
            cbt = cbt.append({'timestamp' : ts, 'cbt' : _cbt, 'utilization' : ((_cbt / 1000000.0) * 100.0)}, ignore_index = True)

    return cbt, frame_types

def extract_ip_id(ip_id):
    return float(ip_id.split(' ')[-1].lstrip('(').rstrip(')'))

def add_ip_seq(data):

    # add extra 0 to ip id
    data['ip seq'] = (data.loc[~data['ip id'].isnull()]['ip id'].apply(extract_ip_id)) * 10.0
    # increment by 1 for each fragment w/ the same ip id
    # note : ip fragments increment in multiples of 1480.0
    data['ip seq'] += (data.loc[~data['ip id'].isnull()]['ip frag offset'].astype(float) / 1480.0)

    return data

def custom_round(x, prec = 1, base = .5):
    return round(base * round(float(x) / base), prec)

def calc_wlan_seq_number_stats(data, prev_seq_numbers, mode = 'rx'):

    # stats reported as dict()
    stats = {
        'interval-tmstmp' : data.iloc[0]['interval-tmstmp'],
        'rcvd' : 0.0, 
        'snt' : 0.0, 
        # 'unique' : 0.0,
        # 'dup' : 0.0,
        're-tx' : 0.0,
        'lost' : 0.0
    }

    _data = data.reset_index(drop = True)

    # unique_seq_numbers = set(_data['wlan seq number'].values)
    stats['rcvd'] = len(_data)
    # stats['unique'] = len(unique_seq_numbers)
    # stats['dup'] = (stats['rcvd'] - stats['unique'])
    stats['re-tx'] = len(_data[_data['wlan retry'] == 'Frame is being retransmitted'])

    if mode == 'tx':
        stats['snt'] = stats['rcvd']
    else:
        # we don't know exactly the nr. of packets which were sent by the client
        # we estimate nr. of sent packets based on the *received* seq numbers roughly as :
        #   snt = rcvd + ~rcvd
        # in which ~rcvd is estimated by considering the seq nrs which are missing on the 
        # packet range pckt[0:len - 1]
        stats['snt'] = 0
        # since 12 bit seq nums can wrap around (i.e., max. seq num is 4095), we need to 
        # split the list of wlan seq numbers in monotonically increasing sequences
        # then, we can safely calculate the range of expected seq nums as pckt[len - 1] - pckt[0]
        _data['gap'] = _data['wlan seq number'].astype(int) - _data['wlan seq number'].astype(int).shift(1)
        segments = list(_data.index[_data['gap'] < -10.0])
        segments.append(len(_data))
        # print("segments : %s" % (segments))

        # for each segment
        prev_seg = 0
        not_rcvd = 0
        for seg in segments:

            # print("[%d:%d]" % (prev_seg, seg))
            # set of seq numbers rcvd in segment 
            seg_data = _data.iloc[prev_seg:seg][['wlan seq number', 'wlan frag number']].sort_values(by = ['wlan seq number', 'wlan frag number']).reset_index(drop = True)
            if seg_data.empty:
                continue

            seq_number_range = seg_data.iloc[-1]['wlan seq number'].astype(float) - seg_data.iloc[0]['wlan seq number'].astype(float) + 1.0
            # print("\t\t[wlan seq number] : range [%s:%s] (%s)" % 
            #     (seg_data.iloc[0]['wlan seq number'].astype(float), seg_data.iloc[-1]['wlan seq number'].astype(float), seq_number_range))

            # remove any seq numbers which have been previously received
            # we do this so that the range of ~rcvd packets doesn't include 
            # duplicate packets from a previous time interval
            seg_data = seg_data[~seg_data['wlan seq number'].isin(prev_seq_numbers)]
            # filter rows w/ gaps larger than 1 (and take 1 from the gap value, to get the nr. of missing frames)
            seg_data['gap'] = seg_data['wlan seq number'].astype(int) - seg_data['wlan seq number'].astype(int).shift(1) - 1.0
            seg_data = seg_data[seg_data['gap'] > 0.0]
            # print(seg_data)
            # sum the gaps to get ~rcvd 
            not_rcvd += seg_data['gap'].sum()

            prev_seg = seg

        # print("\t\t[wlan seq number] : ~rcvd : %s" % (not_rcvd))
        stats['snt'] = stats['rcvd'] + not_rcvd
        # print("\t\t[wlan seq number] : stats[snt] : %s + %s = %s" % (stats['rcvd'], not_rcvd, stats['snt']))

    return stats, _data[~_data['wlan seq number'].isin(prev_seq_numbers)]['wlan seq number'].values

def calc_wlan_frame_stats(data, intervals = [1.0, .25], mode = 'rx'):

    # calculates stats related to wlan frame delivery, which can later be used to calc packet loss
    stats = defaultdict(pd.DataFrame)
    # sort by epoch time, seq num and frag num
    _data = data[['epoch time', 'interval-tmstmp', 'wlan seq number', 'wlan frag number', 'wlan retry']].sort_values(by = ['epoch time', 'wlan seq number', 'wlan frag number']).reset_index(drop = True)

    # collect # of packets stats, per interval
    for interval in intervals:

        # dataframe to aggregate interval stats
        _stats = pd.DataFrame(columns = ['interval-tmstmp', 'rcvd', 'snt', 're-tx', 'lost'])
        grouped = _data.groupby(['interval-tmstmp'])
        # account w/ discontinuities in wlan seq numbers between intervals
        prev_seq_num = _data.iloc[0]['wlan seq number'].astype(float) - 1
        # useful to calc # of not rcvd packets in an interval
        prev_seq_numbers = []

        # print("total packets: %s" % (len(_data)))
        for name, interval_data in grouped:

            # print("\n\tinterval : %s" % (name))
            # print("\tinterval.size : %s" % (len(interval_data)))

            # extract interval stats from each group (update rcvd_seq_numbers)
            interval_stats, prev_seq_numbers = calc_wlan_seq_number_stats(interval_data, prev_seq_numbers, mode)

            if (mode == 'rx') and (len(prev_seq_numbers) > 0):
                # adjust 'snt' w/ gap in wlan seq number between intervals
                interval_gap = prev_seq_numbers[0] - prev_seq_num - 1
                # print("\tinterval.gap : %s - %s = %s" % (prev_seq_numbers[0], prev_seq_num, interval_gap))
                # update prev_seq_num
                prev_seq_num = prev_seq_numbers[-1]
                interval_stats['snt'] = (interval_stats['snt'] + interval_gap) if (interval_gap > 0) else interval_stats['snt']
                # print("\tinterval.snt : %s" % (interval_stats['snt']))

            # calc 'lost' stat w/ updated 'expected'
            interval_stats['lost'] = (interval_stats['snt'] - interval_stats['rcvd']) + interval_stats['re-tx']
            # print("\tinterval.lost : (%s - %s) + %s = %s" % (interval_stats['snt'], interval_stats['rcvd'], interval_stats['re-tx'], interval_stats['lost']))

            _stats = _stats.append(interval_stats, ignore_index = True)

        # print(stats)
        # print(stats[['rcvd', 'snt', 'unique', 'dup', 're-tx', 'lost']].sum())
        # print(stats[['rcvd', 'snt', 're-tx', 'lost']].sum())
        stats[interval] = _stats

    return stats

def calc_pckt_loss_interval(data, metric = 'wlan seq number', groupby_metrics = ['time'], interval = 1.0):

    # special index to be later used for time intervals
    data['time'] = ((data['epoch time'] * (1.0 / interval)).astype(int) / (1.0 / interval)).astype(float)

    interval_data = data.groupby(groupby_metrics)[metric].apply(list).reset_index()
    interval_data['span'] = interval_data[metric].apply(lambda x : [x[0], x[-1]])
    # FIXME : is this correct?
    interval_data[metric] = interval_data[metric].apply(lambda x : sorted(x))
    interval_data['range'] = interval_data[metric].apply(lambda x : (x[-1] - x[0]) + 1)
    interval_data['# unique'] = interval_data[metric].apply(lambda x : len(set(x))).astype(float)
    interval_data['pckt-loss'] = (1.0 - (interval_data['# unique'] / interval_data['range'])) * 100.0

    # m = np.amin(interval_data['pckt-loss'])
    # if m < 0.00:
    #     print(interval_data[['span', 'range', '# unique', 'pckt-loss']])
    return interval_data[['time', 'pckt-loss']]

# secondary method, if calc_pckt_loss() can't be used due to lack of data
def calc_pckt_loss_2(data, method = 'wlan seq number', protocol = 'tcp', interval = 1.0):

    # more indirect methods to calculate packet loss
    pckt_loss = pd.DataFrame()
    # print(method)

    if method == 'ip seq':

        # algorithm : 
        #   - divide data in segments according ip src/dst, src/dst port, interval timestamp
        #   - for each interval:
        #       - pckt_loss = 1.0 - (interval_data['# of unique ip seq'] / interval_data['ip seq range'])
        #       - FIXME : this doesn't work w/ udp and ip frag
        
        _data = data[['epoch time', 'ip seq', 'ip src', 'ip dst', ('%s src' % (protocol.lower())), ('%s dst' % (protocol.lower()))]]

        # calculate packet loss per interval
        interval_data = calc_pckt_loss_interval(
            _data, 
            metric = 'ip seq', 
            groupby_metrics = ['ip src', 'ip dst', ('%s src' % (protocol.lower())), ('%s dst' % (protocol.lower())), 'time'], 
            interval = interval)

        pckt_loss = pd.concat([pckt_loss, interval_data], ignore_index = True)

    elif method == 'wlan seq number':

        # algorithm : 
        #   - divide data in increasingly monotonic segments of wlan seq number
        #   - for each each segment:
        #       - divide data in segments of time equal to 'interval'
        #       - for each interval:
        #           - pckt_loss = 1.0 - (interval_data['# of unique seq numbers'] / interval_data['seq number range'])
    
        _gaps = data[['epoch time', 'wlan seq number']].reset_index()
        # get segments of increasingly monotonic 'wlan seq number'
        # FIXME : due to wlan re-transmissions, we divide segments when an arbitrary negative seq gap of 
        # 100 is found. 
        # despite arbitrary, this seems to work well in practice
        thrshld = -100.0
        _gaps['seq gap'] = _gaps['wlan seq number'].astype(int) - _gaps['wlan seq number'].astype(int).shift(1)
        segments = list(_gaps.index[_gaps['seq gap'] < thrshld])
        # add a final segment, equal to the length of _gaps
        segments.append(len(_gaps) - 1)

        # for each segment [prev_seg, (segment - 1)], we calculate packet loss
        prev_seg = 0
        for seg in segments:

            # print("[%d:%d]" % (prev_seg, (seg - 1)))
            seg_data = _gaps.iloc[prev_seg:(seg - 1)]
            # print("max gap : %s" % (np.amin(seg_data['seq gap'])))
            
            if len(seg_data) > 1:

                # print("seg_data[%d] = %d" % (prev_seg, _gaps.iloc[prev_seg]['wlan seq number']))
                # print("seg_data[%d] = %d" % ((seg - 1), _gaps.iloc[seg - 1]['wlan seq number']))

                # calculate packet loss per interval
                interval_data = calc_pckt_loss_interval(
                    seg_data, 
                    metric = 'wlan seq number', 
                    groupby_metrics = ['time'], 
                    interval = interval)

                pckt_loss = pd.concat([pckt_loss, interval_data], ignore_index = True)

            prev_seg = seg

    return pckt_loss

def find_peaks(data, x_metric = 'timestamp', y_metric = 'dist', thrshld = 120.0):

    # this is too trivial of a solution btw, but it does the job...
    # algorithm : 
    #   - go through the signal with a sliding window of size 3, [x, y, z]
    #   - for every pattern [x, y, z] in which x < y > z, we mark a peak
    #   - return the indexes of the peaks

    peaks = defaultdict(list)
    wndw_pos = 0
    # print("n = %d" % (len(data)))
    while (wndw_pos + 3) < len(data):

        wndw = data.iloc[wndw_pos:(wndw_pos + 3)][y_metric].values
        if ((wndw[0] < wndw[1]) and (wndw[1] > wndw[2])) and (wndw[1] > thrshld):
            # print("[%d, %d]" % (wndw_pos, wndw_pos + 3))
            # print(wndw)
            peaks['start'].append(data.iloc[wndw_pos + 1][x_metric])

        # FIXME : hardcoded threshold
        if ((wndw[0] < wndw[1]) and (wndw[1] > wndw[2])) and (wndw[1] < 40.0):
            # print("[%d, %d]" % (wndw_pos, wndw_pos + 3))
            # print(wndw)
            peaks['turn'].append(data.iloc[wndw_pos + 1][x_metric])

        wndw_pos += 1

    return peaks