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

matplotlib.rcParams.update({'font.size': 16})

def read_csv(input_dir):

    data = OrderedDict()
    last_timestamps = defaultdict()
    for file_name in sorted(glob.glob(os.path.join(input_dir, '*.csv'))):

        # extract:
        #   - iface
        cap_id = file_name.split("/")[-1]
        iface = cap_id.split("-")[0]
        #   - nr. of capture
        cap_nr = cap_id.split("-")[1].rstrip('.csv')

        if cap_nr not in data:
            data[cap_nr] = defaultdict()

        # read .csv file into dataframe
        data[cap_nr][iface] = pd.read_csv(file_name)
        last_timestamps[cap_nr] = data[cap_nr][iface][data[cap_nr][iface]['Protocol'] == 'ICMP']['Epoch Time'].max()

    return data, last_timestamps

def print_stats(data, case = 'ethernet'):

    if case == 'ethernet':
        columns = ['iface', 'cap. nr.', 'mean', 'median', 'std. dev.']
        table = PrettyTable(columns)
        for cap_nr in data:
            for iface in data[cap_nr]:
                # RTT is taken from the 'Response time' field of ICMP packets
                _data = data[cap_nr][iface][(data[cap_nr][iface]['Protocol'] == 'ICMP')]['Response time'].dropna()
                table.add_row([
                    ('%s' % (iface)),
                    ('%s' % (cap_nr)), 
                    ('%f' % (_data.mean())),
                    ('%f' % (_data.median())),
                    ('%f' % (_data.std()))
                    ])
        print(table)

def get_switch_timestamps(data, start_timestamp, protocol = 'OpenVPN'):

    _data = defaultdict()
    for iface in data:

        if iface not in _data:
            _data[iface] = defaultdict()

        __data = data[iface]
        __data = __data[(__data['Epoch Time'] > start_timestamp) & (__data['Protocol'] == protocol)]

        _data[iface]['sent'] = __data[__data['Source'] != '52.58.108.87'].reset_index()
        _data[iface]['rcvd'] = __data[__data['Source'] == '52.58.108.87'].reset_index()

    # find time overlaps of ping pairs between the wlan0 and wwan0 ifaces
    # we define the following times to calculate the overlaps:
    #   - wwan0_t1 : first ping request sent by 'wwan0'
    #   - wwan0_t2 : last ping reply received by 'wwan0'
    #   - wlan0_t1 : last ping reply received by 'wlan0' on its 1st round 
    #   - wlan0_t2 : first ping request sent by 'wlan0' on its 2nd round
    #
    # the time order of these events should be:
    #   wwan0_ti -> wlan0_t1 -> wlan0_t2 -> wwan0_t2

    # wwan0_tx are easy to obtain
    wwan0_t1 = _data['wwan0']['sent']['Epoch Time'].values[0]
    wwan0_t2 = _data['wwan0']['rcvd']['Epoch Time'].values[-1]

    # to identify wlan0_tx, we first calculate the time gaps between ping requests
    _data['wlan0']['sent']['gap'] = _data['wlan0']['sent']['Epoch Time'] - _data['wlan0']['sent']['Epoch Time'].shift(1)
    # check for gaps larger than 2 seconds : that will be wlan0_t2
    gap_indeces = _data['wlan0']['sent'].index[_data['wlan0']['sent']['gap'] > 2.0].tolist()
    wlan0_t2 = _data['wlan0']['sent'].iloc[gap_indeces[0]]['Epoch Time']
    # wlan0_t1 (...)
    wlan0_t1 = _data['wlan0']['rcvd'][_data['wlan0']['rcvd']['Epoch Time'] < wlan0_t2]['Epoch Time'].values[-1]

    return _data, wwan0_t1, wwan0_t2, wlan0_t1, wlan0_t2

def plot_latency(input_dir, output_dir, protocol = 'OpenVPN', start_timestamps = {}):

    # first, gather the RTTs after and before switch for the 'ethernet' case
    data, _ = read_csv(input_dir)
    # present stats (mean, median and stdev) in table format
    print("\t*** NO VPN ***")
    print_stats(data)

    # calculate the same stats for the remaining cases: openvpn and wireguard
    for protocol in ['OpenVPN', 'DCERPC']:

        # save results in a dataframe
        columns = ['cap. nr.', 'iface', 'switch #', 'mean', 'median', 'std. dev.']
        results = pd.DataFrame(columns = columns)
        # present results in table format
        table = PrettyTable(columns)

        for cap_nr in data:

            _data, wwan0_t1, wwan0_t2, wlan0_t1, wlan0_t2 = get_switch_timestamps(data[cap_nr], start_timestamps[cap_nr], protocol = protocol)

            k = 2
            # switch 1 : @ wwan0_t1
            switch = _data['wwan0']['rcvd'][(_data['wwan0']['rcvd']['Epoch Time'] >= wwan0_t1)].reset_index()['Epoch Time'][:k] - _data['wwan0']['sent'][(_data['wwan0']['sent']['Epoch Time'] >= wwan0_t1)].reset_index()['Epoch Time'][:k]
            # print("%s.%s.switch_%d :" % (protocol, cap_nr, 1))
            # print(switch)

            table.add_row([
                ('%s' % (cap_nr)), 
                ('-'), 
                ('1'), 
                ('%f' % (switch.mean() * 1000.0)),
                ('%f' % (switch.median() * 1000.0)),
                ('%f' % (switch.std() * 1000.0))
                ])

            # switch 2 : @ wlan0_t2
            switch = _data['wlan0']['rcvd'][(_data['wlan0']['rcvd']['Epoch Time'] >= wlan0_t2)].reset_index()['Epoch Time'][:k] - _data['wlan0']['sent'][(_data['wlan0']['sent']['Epoch Time'] >= wlan0_t2)].reset_index()['Epoch Time'][:k]
            # print("%s.%s.switch_%d :" % (protocol, cap_nr, 2))
            # print(switch)
            # print(_data['wlan0']['rcvd'][(_data['wlan0']['rcvd']['Epoch Time'] >= wlan0_t2)]['Epoch Time'][:k])
            # print(_data['wlan0']['sent'][(_data['wlan0']['sent']['Epoch Time'] >= wlan0_t2)]['Epoch Time'][:k])

            table.add_row([
                ('%s' % (cap_nr)), 
                ('-'), 
                ('2'), 
                ('%f' % (switch.mean() * 1000.0)),
                ('%f' % (switch.median() * 1000.0)),
                ('%f' % (switch.std() * 1000.0))
                ])

            # total RTT statistics per iface
            for iface in _data:

                if iface == 'wlan0':

                    # round 1
                    sent = _data['wlan0']['sent'][(_data['wlan0']['sent']['Epoch Time'] <= wlan0_t1)].reset_index()['Epoch Time']
                    rcvd = _data['wlan0']['rcvd'][(_data['wlan0']['rcvd']['Epoch Time'] <= wlan0_t1)].reset_index()['Epoch Time']
                    # print("%s.%s.%s.round_%d : %d vs. %d" % (protocol, cap_nr, iface, 1, len(sent), len(rcvd)))
                    n = min(len(sent), len(rcvd))
                    diff = rcvd[:n] - sent[:n]

                    # round 2
                    sent = _data['wlan0']['sent'][(_data['wlan0']['sent']['Epoch Time'] >= wlan0_t2)].reset_index()['Epoch Time']
                    rcvd = _data['wlan0']['rcvd'][(_data['wlan0']['rcvd']['Epoch Time'] >= wlan0_t2)].reset_index()['Epoch Time']
                    # print("%s.%s.%s.round_%d : %d vs. %d" % (protocol, cap_nr, iface, 2, len(sent), len(rcvd)))
                    n = min(len(sent), len(rcvd))
                    # concat 'diff'
                    diff = pd.concat([diff, rcvd[:n] - sent[:n]], ignore_index = True)
                    
                    # look for large or negative gaps, and remove them from the data
                    gap_indeces = diff.index[(diff > 5.0) | (diff < 0.0)].tolist()
                    if gap_indeces:
                        diff.drop(diff.index[gap_indeces], inplace = True)

                else:

                    sent = _data['wwan0']['sent'][(_data['wwan0']['sent']['Epoch Time'] >= wwan0_t1) & (_data['wwan0']['sent']['Epoch Time'] <= wwan0_t2)].reset_index()['Epoch Time']
                    rcvd = _data['wwan0']['rcvd'][(_data['wwan0']['rcvd']['Epoch Time'] >= wwan0_t1) & (_data['wwan0']['rcvd']['Epoch Time'] <= wwan0_t2)].reset_index()['Epoch Time']
                    # print("%s.%s.%s : %d vs. %d" % (protocol, cap_nr, iface, len(sent), len(rcvd)))
                    n = min(len(sent), len(rcvd))
                    diff = rcvd[:n] - sent[:n]

                table.add_row([
                    ('%s' % (cap_nr)), 
                    (iface), 
                    ('-'), 
                    ('%f' % (diff.mean() * 1000.0)),
                    ('%f' % (diff.median() * 1000.0)),
                    ('%f' % (diff.std() * 1000.0))
                    ])

            start_timestamps[cap_nr] = wwan0_t2

        print("\n\t*** %s ***" % (protocol.upper()))
        print(table)

def plot_overlaps_proto(input_dir, output_dir, protocol = 'OpenVPN', start_timestamps = {}):

    last_timestamps = defaultdict()
    data, _ = read_csv(input_dir)

    # wrap it up in a nice table form
    columns = [
        'test nr.', '-', 'overlap #', 
        'overlap start', 'overlap end', 'overlap duration', '# pings sent within overlap', '# pings received within overlap']
    table = PrettyTable(columns)
    # save results in a dataframe
    results = pd.DataFrame(columns = columns)

    for cap_nr in data:

        _data, wwan0_t1, wwan0_t2, wlan0_t1, wlan0_t2 = get_switch_timestamps(data[cap_nr], start_timestamps[cap_nr], protocol = protocol)

        # overlaps
        #   - overlap 1 : pings sent or received over wlan0, after wwan0 started sending pings
        overlap = defaultdict()
        overlap['sent'] = _data['wlan0']['sent'][(_data['wlan0']['sent']['Epoch Time'] > wwan0_t1) & (_data['wlan0']['sent']['Epoch Time'] < wlan0_t2)]
        overlap['rcvd'] = _data['wlan0']['rcvd'][(_data['wlan0']['rcvd']['Epoch Time'] > wwan0_t1) & (_data['wlan0']['rcvd']['Epoch Time'] < wlan0_t2)]

        table.add_row([
                    ('%s' % (cap_nr)),
                    ('-'), 
                    ('1'), 
                    ('%f' % (wwan0_t1)),
                    ('%f' % (overlap['rcvd']['Epoch Time'].values[-1])),
                    ('%f' % (overlap['rcvd']['Epoch Time'].values[-1] - wwan0_t1)),
                    ('%d' % (len(overlap['sent']['Epoch Time']))),
                    ('%d' % (len(overlap['rcvd']['Epoch Time'])))
                    ])

        results = results.append({
            columns[0] : cap_nr,
            columns[1] : '-',
            columns[2] : '1',
            columns[3] : wwan0_t1,
            columns[4] : overlap['rcvd']['Epoch Time'].values[-1],
            columns[5] : overlap['rcvd']['Epoch Time'].values[-1] - wwan0_t1,
            columns[6] : len(overlap['sent']['Epoch Time']),
            columns[7] : len(overlap['rcvd']['Epoch Time']),
            }, ignore_index = True)

        #   - overlap 2 : pings sent or received over wwan0, after wlan0 re-started sending pings
        overlap['sent'] = _data['wwan0']['sent'][(_data['wwan0']['sent']['Epoch Time'] > wlan0_t2) & (_data['wwan0']['sent']['Epoch Time'] <= wwan0_t2)]
        overlap['rcvd'] = _data['wwan0']['rcvd'][(_data['wwan0']['rcvd']['Epoch Time'] > wlan0_t2)]

        table.add_row([
                    (''),
                    ('-'), 
                    ('2'), 
                    ('%f' % (wlan0_t2)),
                    ('%f' % (overlap['rcvd']['Epoch Time'].values[-1])),
                    ('%f' % (overlap['rcvd']['Epoch Time'].values[-1] - wlan0_t2)),
                    ('%d' % (len(overlap['sent']['Epoch Time']))),
                    ('%d' % (len(overlap['rcvd']['Epoch Time'])))
                    ])

        results = results.append({
            columns[0] : cap_nr,
            columns[1] : '-',
            columns[2] : '2',
            columns[3] : wlan0_t2,
            columns[4] : overlap['rcvd']['Epoch Time'].values[-1],
            columns[5] : overlap['rcvd']['Epoch Time'].values[-1] - wlan0_t2,
            columns[6] : len(overlap['sent']['Epoch Time']),
            columns[7] : len(overlap['rcvd']['Epoch Time']),
            }, ignore_index = True)


        last_timestamps[cap_nr] = wwan0_t2

    # print the results as a table
    print(table)
    # save results as .csv file
    results.to_csv(os.path.join(output_dir, (("overlaps.%s." % (protocol.lower())) + str(time.time()).split('.')[0] + ".csv")))

    return last_timestamps

def plot_overlaps(input_dir, output_dir):

    data, last_timestamps = read_csv(input_dir)

    # answer a few questions:
    #   - how many ping pairs have been exchanged in overlap, when a switch occurred?
    #   - what was the duration of the overlap?
    #   - are there common seq. numbers between ifaces?

    # wrap it up in a nice table form
    columns = [
        'test nr.', '# of common seq. numbers', 'overlap #', 
        'overlap start', 'overlap end', 'overlap duration', '# pings sent within overlap', '# pings received within overlap']
    table = PrettyTable(columns)
    # save results in a dataframe
    results = pd.DataFrame(columns = columns)

    for cap_nr in data:
        
        _data = defaultdict()

        # find ping pairs (and respective timestamps) by pd.merge()
        for iface in data[cap_nr]:

            # we want ping pairs w/ same seq. number
            echo_req = data[cap_nr][iface][data[cap_nr][iface]['Type.1'] == 8][['Epoch Time', 'Sequence number (LE)']]
            echo_rep = data[cap_nr][iface][data[cap_nr][iface]['Type.1'] == 0][['Epoch Time', 'Sequence number (LE)']]

            _data[iface] = pd.merge(echo_req, echo_rep, on = 'Sequence number (LE)')

        common_seq_nums = len( set(_data['wlan0']['Sequence number (LE)']) & set(_data['wwan0']['Sequence number (LE)']) )

        # find time overlaps of ping pairs between the wlan0 and wwan0 ifaces
        # we define the following times to calculate the overlaps:
        #   - wwan0_t1 : first ping request sent by 'wwan0'
        #   - wwan0_t2 : last ping reply received by 'wwan0'
        #   - wlan0_t1 : last ping reply received by 'wlan0' on its first round 
        #   - wlan0_t2 : first ping request sent by 'wlan0' on its second round
        #
        # the time order of these events should be:
        #   wwan0_ti -> wlan0_t1 -> wlan0_t2 -> wwan0_t2

        # wwan0_tx are easy to obtain
        wwan0_t1 = _data['wwan0']['Epoch Time_x'].values[0]
        wwan0_t2 = _data['wwan0']['Epoch Time_x'].values[-1]
        # to identify wlan0_tx, we first calculate the time gaps between ping pairs
        _data['wlan0']['gap'] = _data['wlan0']['Epoch Time_x'] - _data['wlan0']['Epoch Time_x'].shift(1)
        # check for gaps larger than 2 seconds : that will be wlan0_t2
        gap_indeces = _data['wlan0'].index[_data['wlan0']['gap'] > 2.0].tolist()
        wlan0_t2 = _data['wlan0'].iloc[gap_indeces[0]]['Epoch Time_x']
        # wlan0_t1 will be taken from the row which precedes that of wlan0_t2
        wlan0_t1 = _data['wlan0'].iloc[gap_indeces[0] - 1]['Epoch Time_x']

        # overlaps
        #   - overlap 1 : pings sent or received over wlan0, after wwan0 started sending pings
        overlap = defaultdict()
        overlap['sent'] = _data['wlan0'][(_data['wlan0']['Epoch Time_x'] > wwan0_t1) & (_data['wlan0']['Epoch Time_x'] < wlan0_t2)]
        overlap['rcvd'] = _data['wlan0'][(_data['wlan0']['Epoch Time_y'] > wwan0_t1) & (_data['wlan0']['Epoch Time_y'] < wlan0_t2)]

        table.add_row([
                    ('%s' % (cap_nr)),
                    ('%d' % (common_seq_nums)), 
                    ('1'), 
                    ('%f' % (wwan0_t1)),
                    ('%f' % (overlap['rcvd']['Epoch Time_y'].values[-1])),
                    ('%f' % (overlap['rcvd']['Epoch Time_y'].values[-1] - wwan0_t1)),
                    ('%d' % (len(overlap['sent']['Epoch Time_x']))),
                    ('%d' % (len(overlap['rcvd']['Epoch Time_x'])))
                    ])

        results = results.append({
            columns[0] : cap_nr,
            columns[1] : common_seq_nums,
            columns[2] : '1',
            columns[3] : wwan0_t1,
            columns[4] : overlap['rcvd']['Epoch Time_y'].values[-1],
            columns[5] : overlap['rcvd']['Epoch Time_y'].values[-1] - wwan0_t1,
            columns[6] : len(overlap['sent']['Epoch Time_x']),
            columns[7] : len(overlap['rcvd']['Epoch Time_x']),
            }, ignore_index = True)

        #   - overlap 2 : pings sent or received over wwan0, after wlan0 re-started sending pings
        overlap['sent'] = _data['wwan0'][(_data['wwan0']['Epoch Time_x'] > wlan0_t2) & (_data['wwan0']['Epoch Time_x'] <= wwan0_t2)]
        overlap['rcvd'] = _data['wwan0'][(_data['wwan0']['Epoch Time_y'] > wlan0_t2)]

        table.add_row([
                    (''),
                    (''), 
                    ('2'), 
                    ('%f' % (wlan0_t2)),
                    ('%f' % (overlap['rcvd']['Epoch Time_y'].values[-1])),
                    ('%f' % (overlap['rcvd']['Epoch Time_y'].values[-1] - wlan0_t2)),
                    ('%d' % (len(overlap['sent']['Epoch Time_x']))),
                    ('%d' % (len(overlap['rcvd']['Epoch Time_x'])))
                    ])

        results = results.append({
            columns[0] : cap_nr,
            columns[1] : common_seq_nums,
            columns[2] : '2',
            columns[3] : wlan0_t2,
            columns[4] : overlap['rcvd']['Epoch Time_y'].values[-1],
            columns[5] : overlap['rcvd']['Epoch Time_y'].values[-1] - wlan0_t2,
            columns[6] : len(overlap['sent']['Epoch Time_x']),
            columns[7] : len(overlap['rcvd']['Epoch Time_x']),
            }, ignore_index = True)

        # last_timestamps[cap_nr] = wwan0_t2

    # print the results as a table
    print(table)
    # save results as .csv file
    results.to_csv(os.path.join(output_dir, ("overlaps.ethernet." + str(time.time()).split('.')[0] + ".csv")))

    return last_timestamps

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--input-dir", 
         help = """dir w/ capture files (.csv format)""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save graphs""")

    args = parser.parse_args()

    if not args.input_dir:
        sys.stderr.write("""%s: [ERROR] please supply a dir w/ .csv files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    print("**** OVERLAP ANALYSIS ****")
    print("\t*** NO VPN ***")
    _start_timestamps = plot_overlaps(args.input_dir, args.output_dir)
    print("\n\t*** OPEN-VPN ***")
    start_timestamps = plot_overlaps_proto(args.input_dir, args.output_dir, protocol = 'OpenVPN', start_timestamps = _start_timestamps)
    print("\n\t*** WIREGUARD ***")
    start_timestamps = plot_overlaps_proto(args.input_dir, args.output_dir, protocol = 'DCERPC', start_timestamps = start_timestamps)

    print("\n**** LATENCY ANALYSIS ****")
    plot_latency(args.input_dir, args.output_dir, start_timestamps = _start_timestamps)

    sys.exit(0)