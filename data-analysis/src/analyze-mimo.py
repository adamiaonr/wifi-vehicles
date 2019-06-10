# analyze-mimo.py : code to analyze *U-MIMO-specific wlan frames
# Copyright (C) 2018  adamiaonr@cmu.edu

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import os
import argparse
import sys
import glob
# import hashlib
import pandas as pd
import matplotlib.pyplot as plt
import json
import numpy as np

from prettytable import PrettyTable
from matplotlib.colors import BoundaryNorm

# custom imports
#   - plot utils
import plot.utils
#   - ieee 802.11ac utils
import utils.ieee80211.ac as ac

antennas = {'4x1' : {'color' : 'red',  'label' : '4x1', 'tests' : [2, 3, 7, 8, 11]}, 
            '4x2' : {'color' : 'blue', 'label' : '4x2', 'tests' : [1, 4, 5, 6, 9, 10]}}

def parse_pcaps_json(input_dir, output_dir):

    bf_dir = os.path.join(input_dir, ('filtered/beamforming/json'))
    for json_file in sorted(glob.glob(os.path.join(bf_dir, ('*.json')))):

        with open(json_file, 'r') as f:
            json_packets = json.load(f)
            
        data = []
        for pkt in json_packets:
            
            # consider only bf reports ('Action No Ack' wlan frames)
            if (pkt['_source']['layers']['wlan']['wlan.fc.type_subtype'] not in ['14']) or ('wlan-bf' not in pkt['_source']['layers']):
                continue
            
            vht_exclusive_bf_report = ''
            if 'wlan.vht.exclusive_beamforming_report' in pkt['_source']['layers']['wlan-bf']['Fixed parameters']:
                vht_exclusive_bf_report = pkt['_source']['layers']['wlan-bf']['Fixed parameters']['wlan.vht.exclusive_beamforming_report'].replace(':', '')
            
            data.append({
                'no' : pkt['_source']['layers']['frame']['frame.number'],
                'epoch time' : pkt['_source']['layers']['frame']['frame.time_epoch'],
                'frame len' : pkt['_source']['layers']['frame']['frame.len'],
                'wlan src addr' : pkt['_source']['layers']['wlan']['wlan.ta'],
                'wlan dst addr' : pkt['_source']['layers']['wlan']['wlan.ra'],
                'wlan type-subtype' : pkt['_source']['layers']['wlan']['wlan.fc.type_subtype'],
                'wlan rssi' : pkt['_source']['layers']['wlan_radio']['wlan_radio.signal_dbm'],
                'wlan seq number' : pkt['_source']['layers']['wlan']['wlan.seq'],
                'wlan frag number' : pkt['_source']['layers']['wlan']['wlan.frag'],
#                'wlan spatial streams' : pkt['_source']['layers']['wlan_radio']['wlan_radio.11ac.nss'],
                'wlan mimo nc' : int(pkt['_source']['layers']['wlan-bf']['Fixed parameters']['wlan.vht.mimo_control.control_tree']['wlan.vht.mimo_control.ncindex'], 0),
                'wlan mimo nr' : int(pkt['_source']['layers']['wlan-bf']['Fixed parameters']['wlan.vht.mimo_control.control_tree']['wlan.vht.mimo_control.nrindex'], 0),
                'wlan mimo feedbacktype' : int(pkt['_source']['layers']['wlan-bf']['Fixed parameters']['wlan.vht.mimo_control.control_tree']['wlan.vht.mimo_control.feedbacktype'], 0),
                'wlan mimo codebookinfo' : int(pkt['_source']['layers']['wlan-bf']['Fixed parameters']['wlan.vht.mimo_control.control_tree']['wlan.vht.mimo_control.codebookinfo'], 0),
                'wlan mimo grouping' : int(pkt['_source']['layers']['wlan-bf']['Fixed parameters']['wlan.vht.mimo_control.control_tree']['wlan.vht.mimo_control.grouping'], 0),
                'wlan mimo channel width' : int(pkt['_source']['layers']['wlan-bf']['Fixed parameters']['wlan.vht.mimo_control.control_tree']['wlan.vht.mimo_control.chanwidth'], 0),
                'wlan mimo vht compressed bf report' : pkt['_source']['layers']['wlan-bf']['Fixed parameters']['wlan.vht.compressed_beamforming_report'].replace(':', ''),
                'wlan mimo vht exclusive bf report' : vht_exclusive_bf_report
                })

        # save as 'filtered/beamforming/csv/test<test-nr>.csv'
        data = pd.DataFrame(data)
        data.to_csv(os.path.join(output_dir, ("%s.csv" % (json_file.split('/')[-1].rstrip('.json')))), sep = ',')

def extract_vht_compressed_bf_report(input_dir):
    
    bf_dir = os.path.join(input_dir, ('filtered/beamforming/csv'))
    for test_file in sorted(glob.glob(os.path.join(bf_dir, ('test*.csv')))):
        
        bf_ss_filename = os.path.join(bf_dir, ("vht-compressed-bf-snr-%s.csv" % (test_file.split('/')[-1]).rstrip('.csv')))
        bf_sc_filename = os.path.join(bf_dir, ("vht-compressed-bf-angles-%s.csv" % (test_file.split('/')[-1]).rstrip('.csv')))

        if os.path.exists(bf_sc_filename) and os.path.exists(bf_ss_filename):
            continue
        
        print(test_file)
        test_data = pd.read_csv(test_file)
        bf_sc_data, bf_ss_data = ac.decode_vht_compressed_bf_report(test_data)

        if not bf_sc_data.empty:
            bf_sc_data = pd.merge(test_data[['no', 'epoch time', 'wlan src addr']], bf_sc_data, on = ['no'], how = 'left').reset_index(drop = True)
            bf_sc_data.to_csv(os.path.join(bf_dir, bf_sc_filename), sep = ',')

        if not bf_ss_data.empty:
            bf_ss_data = pd.merge(test_data[['no', 'epoch time', 'wlan src addr']], bf_ss_data, on = ['no'], how = 'left').reset_index(drop = True)
            bf_ss_data.to_csv(os.path.join(bf_dir, bf_ss_filename), sep = ',')

def extract_vht_mu_exclusive_bf_report(input_dir):
    
    bf_dir = os.path.join(input_dir, ('filtered/beamforming/csv'))
    for test_file in sorted(glob.glob(os.path.join(bf_dir, ('test*.csv')))):
        
        bf_filename = os.path.join(bf_dir, ("vht-mu-exclusive-bf-%s.csv" % (test_file.split('/')[-1]).rstrip('.csv')))
        if os.path.exists(bf_filename):
            continue
        
        test_data = pd.read_csv(test_file)

        bf_data = ac.decode_vht_mu_exclusive_bf_report(test_data)
        
        if bf_data.empty:
            continue
        
        bf_data = pd.merge(bf_data, test_data[['no', 'epoch time', 'wlan src addr']], on = ['no'], how = 'left').reset_index(drop = True)
        bf_data.to_csv(os.path.join(bf_dir, bf_filename), sep = ',')

def parse_iperf3(input_dir, output_dir):

    for client in ['tp-02', 'tp-03']:

        client_dir = os.path.join(input_dir, ('orig/iperf3/%s' % (client)))
        for iperf3_file in sorted(glob.glob(os.path.join(client_dir, ('*.out')))):

            # iperf3 output in json format. convert to dict.
            with open(iperf3_file, 'r') as f:
                iperf3_output = json.load(f)

            data = []
            for intrvl in iperf3_output['intervals']:
                data.append(intrvl['sum'])

            data = pd.DataFrame(data)
            # save as 'filtered/iperf3/<client>/text<n>.out.csv'
            data.to_csv(os.path.join(os.path.join(output_dir, ('%s' % (client))), ("%s.csv" % (iperf3_file.split('/')[-1]))), sep = ',')

# type:
#   - line
#   - 1 x 2
# output:
#   - throughput of all clients vs. time
#   - packet loss of all clients vs. time
#   - background w/ MIMO usage
            
def plot_iperf3(test_nr, input_dir, graph_dir):
    
    plt.style.use('classic')
    fig = plt.figure(figsize = (5.0, 2.0))
    
    # list of ax : [throughput, pkt_loss]
    axs = []
    axs.append(fig.add_subplot(1, 2, 1))
    axs.append(fig.add_subplot(1, 2, 2))
    for ax in axs:
        ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
        ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)

    # test information : important for calculating joint elapsed time
    test_info = pd.read_csv(os.path.join(input_dir, ('tests.csv')))
    # start timestamp
    start_timestamp = min(test_info.iloc[int(test_nr) - 1]['start-time-c1'], test_info.iloc[int(test_nr) - 1]['start-time-c2'])
    # client info
    clients = {'tp-02' : {'color' : 'red', 'label' : 'c1'}, 'tp-03' : {'color' : 'blue', 'label' : 'c2'}}
    for c, client in enumerate(['tp-02', 'tp-03']):
        
        test_data = pd.read_csv(os.path.join(input_dir, ('filtered/iperf3/%s/test%d.out.csv' % (client, int(test_nr)))))
        # time elapsed since true start of the test
        test_data['start'] = test_data['start'] + test_info.iloc[int(test_nr) - 1][('start-time-%s' % (clients[client]['label']))] - start_timestamp
    
        axs[0].plot(
            test_data['start'],
            test_data['bits_per_second'] * 0.000001,
            linewidth = 1.0, linestyle = '-', color = clients[client]['color'], label = clients[client]['label'], 
            marker = None, markersize = 0.0, markeredgewidth = 0.0)

        axs[1].plot(
            test_data['start'],
            test_data['lost_percent'],
            linewidth = 1.0, linestyle = '-', color = clients[client]['color'], label = clients[client]['label'], 
            marker = None, markersize = 0.0, markeredgewidth = 0.0)        
        
        axs[0].set_ylim([0, 400])
        axs[0].set_yticks([0, 100, 200, 300, 400])
        
        axs[1].set_ylim([0, 100])
        axs[1].set_yticks([0, 25, 50, 75, 100])        
        
    for ax in axs:
        leg = ax.legend(
            fontsize = 8, 
            ncol = 1, loc = 'lower right',
            handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)
    
        for legobj in leg.legendHandles:
            legobj.set_linewidth(2.0)
            
        ax.set_xlabel('elapsed time (sec)')

    axs[0].set_ylabel('throughput (Mbps)')
    axs[1].set_ylabel('pkt loss (%)')    
    
    fig.tight_layout()
    plt.savefig(os.path.join(graph_dir, ("tghpt-pkt-loss-%d.pdf" % (int(test_nr)))), bbox_inches = 'tight', format = 'pdf')

def get_mimo_stats(data):
    
    # group by second and count frames of given type
    data['mu'] = 0
    data['su'] = 0
    data.loc[data['wlan feedback type client'].str.contains('SU'), 'su'] = 1
    data.loc[data['wlan feedback type client'].str.contains('MU'), 'mu'] = 1    

    data = data[['elapsed time', 'su', 'mu']].reset_index(drop = True)
    data['elapsed time'] = data['elapsed time'].astype(int)
    data = data.groupby(['elapsed time'])[['su', 'mu']].sum().reset_index(drop = False)
    
    return data

def categorize(data, column):
    data = data.sort_values(by = [column]).reset_index(drop = True)
    data[('%s-code' % (column))] = pd.factorize(data[column])[0]

    return data

def plot_mimo_feedback_msg(input_dir, graph_dir):

    # extract nr. of xU-MIMO feedback messages, save in .csv file 
    test_info = pd.read_csv(os.path.join(input_dir, ('tests.csv')))
    if not os.path.exists(os.path.join(input_dir, ("mimo-feedback-msgs.csv"))):

        mimo_feedback_data = []
        for i, test in test_info.iterrows():
            
            chunksize = 10 ** 5
            fb_data = pd.DataFrame()
            for chunk in pd.read_csv(os.path.join(input_dir, ('filtered/pcaps/test%d.csv' % (int(test['test-nr'])))), chunksize = chunksize):        
                chunk = chunk[chunk['wlan type-subtype'].str.contains('Action No Ack|VHT NDP Announcement')][['epoch time', 'wlan src addr', 'wlan dst addr', 'wlan type-subtype', col_ap, 'wlan feedback type ap', 'wlan sounding dialog token nr client', 'wlan feedback type client']]
                fb_data = pd.concat([fb_data, chunk], ignore_index = True)
                
            if fb_data.empty:
                continue
    
            su = len(fb_data[fb_data['wlan feedback type client'].str.contains('SU', na = False)])
            mu = len(fb_data[fb_data['wlan feedback type client'].str.contains('MU', na = False)])
            
            mimo_feedback_data.append({
                'test-nr' : test['test-nr'],
                'pos' : round(((test['c1-horiz-dist'] + test['c2-horiz-dist']) / 2.0), 1),
                'sep' : test['cx-sep'],
                'antenna' : test['ap-cx-antennas'],
                'mu' : mu,
                'su' : su})
            
        mimo_feedback_data = pd.DataFrame(mimo_feedback_data)
        mimo_feedback_data.to_csv(os.path.join(input_dir, ("mimo-feedback-msgs.csv")), sep = ',')

    else:
        mimo_feedback_data = pd.read_csv(os.path.join(input_dir, ("mimo-feedback-msgs.csv")))
    
    mimo_types = {'su' : {'linestyle' : '-', 'marker' : 'o', 'label' : 'SU', 'color' : 'red', 'alpha' : 0.5}, 
                  'mu' : {'linestyle' : '-', 'marker' : '^', 'label' : 'MU', 'color' : 'blue', 'alpha' : 0.5}}

    # FIXME: consider only 'stock' firmware tests
    mimo_feedback_data = mimo_feedback_data[mimo_feedback_data['test-nr'] < 10]
    # transform 'pos', 'sep' and 'antenna' values into integer ordinals
    for category in ['pos', 'sep', 'antenna']:
        mimo_feedback_data = categorize(mimo_feedback_data, category)
    
    # scatter plot code
    for fb_type in ['su', 'mu']:

        plt.style.use('classic')
        fig = plt.figure(figsize = (2.75, 3.25))
        
        axs = []
        axs.append(fig.add_subplot(2, 1, 1))
        axs.append(fig.add_subplot(2, 1, 2))
        for ax in axs:
            ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
            ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)
            
        axs[0].set_title('# of %s-MIMO feedback msgs' % (fb_type.upper()), fontsize = 10)
        
        #   - antenna vs. pos
        axs[0].scatter(mimo_feedback_data['pos-code'], mimo_feedback_data['antenna-code'], s = mimo_feedback_data[fb_type], c = mimo_types[fb_type]['color'], alpha = mimo_types[fb_type]['alpha'])
        #   - antenna vs. sep
        axs[1].scatter(mimo_feedback_data['sep-code'], mimo_feedback_data['antenna-code'], s = mimo_feedback_data[fb_type], c = mimo_types[fb_type]['color'], alpha = mimo_types[fb_type]['alpha'])
    
        axs[0].set_xticks(sorted(mimo_feedback_data['pos-code'].tolist()))
        axs[0].set_xticklabels(mimo_feedback_data.sort_values(by = 'pos-code')['pos'].tolist(), fontsize = 10)
        axs[0].set_yticks(sorted(mimo_feedback_data['antenna-code'].tolist()))
        axs[0].set_yticklabels(mimo_feedback_data.sort_values(by = 'antenna-code')['antenna'].tolist(), fontsize = 10)
        
        axs[0].set_xlabel('horiz. dist. (m)', fontsize = 10)
        axs[0].set_ylabel('antenna config.', fontsize = 10)
        
        axs[1].set_xticks(sorted(mimo_feedback_data['sep-code'].tolist()))
        axs[1].set_xticklabels(mimo_feedback_data.sort_values(by = 'sep-code')['sep'].tolist(), fontsize = 10)
        axs[1].set_yticks(sorted(mimo_feedback_data['antenna-code'].tolist()))
        axs[1].set_yticklabels(mimo_feedback_data.sort_values(by = 'antenna-code')['antenna'].tolist(), fontsize = 10)
        
        axs[1].set_xlabel('client sep. (m)', fontsize = 10)
        axs[1].set_ylabel('antenna config.', fontsize = 10)
        
        fig.tight_layout()
        plt.savefig(os.path.join(graph_dir, ("mimo-fb-msgs-%s.pdf" % (fb_type))), bbox_inches = 'tight', format = 'pdf')

def update_sounding_freq(data):
    
    clients = {'tp-02' : {'color' : 'red', 'label' : 'C1', 'mac_addr' : '50:c7:bf:c8:4d:22'}, 
               'tp-03' : {'color' : 'blue', 'label' : 'C2', 'mac_addr' : '50:c7:bf:3c:53:1a'}}

    ret = pd.DataFrame()
    for client in clients:

        df = data[data['wlan type-subtype'].str.contains('Action No Ack')]

        df['no'] = df.index.astype(int)
        df['pkt-interval'] = df['no'] - df['no'].shift(1)
        df['time-interval'] = df['epoch time'] - df['epoch time'].shift(1)     

        df['wlan sounding dialog token nr client'] = df['wlan sounding dialog token nr client'].fillna(value = '0x00')
        df['wlan sounding dialog token nr client'] = df['wlan sounding dialog token nr client'].apply(int, base = 16)
        
        ret = pd.concat([df, ret], ignore_index = True)
           
    return ret[['wlan src addr', 'wlan feedback type client', 'time-interval', 'pkt-interval', 'wlan sounding dialog token nr client']]

def update_sounding_times(data):
    
    df = data[data['wlan type-subtype'].str.contains('Action No Ack')]
    df['time'] = (df['frame len'] * 8.0) / df['wlan data rate']
    df['mimo-type'] = df['wlan feedback type client']
           
    return df[['wlan src addr', 'mimo-type', 'time', 'frame len', 'wlan data rate']]    

def update_sounding_contention(data):

    base = data[data['wlan type-subtype'].str.contains('QoS Data|Action No Ack')][['epoch time', 'wlan data rate', 'wlan type-subtype', 'frame len', 'wlan feedback type ap', 'wlan feedback type client', 'wlan src addr', 'wlan dst addr']]

    # 1) time gap between *U-MIMO feedback frames and subsequent frames
    lookup = data[data['wlan type-subtype'].str.contains('Action No Ack')][['epoch time', 'wlan data rate', 'wlan type-subtype', 'frame len', 'wlan feedback type ap', 'wlan feedback type client', 'wlan src addr', 'wlan dst addr', 'wlan sounding dialog token nr client']]    
    output = []
    for i, row in lookup.iterrows():
        
        if (i + 1) > base.tail(1).index[0]:
            break
        
        for j in (i + 1, i + 5):
        
            try:
                
                if base.loc[j, 'wlan type-subtype'] == 'QoS Data':
                    
                    output.append({
                        'sound-nr' : row['wlan sounding dialog token nr client'],
                        'time-gap' : int((base.loc[j, 'epoch time'] - lookup.loc[i, 'epoch time']) * 1000000.0),
                        'pkt-gap' : j - i,
                        'mimo-type' : row['wlan feedback type client'],
                        'vht feedback time' : (row['frame len'] * 8.0) / row['wlan data rate'],
                        'feedback-dev' : row['wlan src addr'],
                        'data-dev' : base.loc[j, 'wlan dst addr']
                        })
        
                    break
                
            except KeyError:
                pass
        
    # 2) time gap between wlan data frames
    baseline = data[data['wlan type-subtype'].str.contains('QoS Data')][['epoch time', 'wlan data rate', 'wlan type-subtype', 'frame len', 'wlan feedback type ap', 'wlan feedback type client', 'wlan src addr', 'wlan dst addr']]
    baseline['no'] = baseline.index.astype(int)
    baseline['diff'] = baseline['no'] - baseline['no'].shift(1)
    baseline = baseline[baseline['diff'] == 1]
    baseline['time-gap'] = (baseline['epoch time'] - baseline['epoch time'].shift(1)) * 1000000.0
    baseline = baseline.dropna(subset = ['time-gap'])
    baseline['time-gap'] = baseline['time-gap'].astype(int)
    
    return pd.DataFrame(output), baseline[['wlan dst addr', 'time-gap']]

def update_sounding_gap(data):
    
    col_ap = 'wlan sounding dialog token nr ap'
    col_client = 'wlan sounding dialog token nr client'

    df = data[data['wlan type-subtype'].str.contains('VHT NDP Announcement|Action No Ack')][['epoch time', 'wlan data rate', 'wlan type-subtype', 'frame len', 'wlan feedback type ap', 'wlan feedback type client', col_ap, col_client, 'wlan src addr', 'wlan dst addr']]

    # FIXME: remove nanswlan src addr
    # client sounding dialog nrs in int
    df[col_ap] = df[col_ap].fillna(value = 0)
    # client sounding dialog nrs in hex
    df[col_client] = df[col_client].fillna(value = '0x00')

    df[col_ap] = df[col_ap].astype(int)
    df[col_client] = df[col_client].apply(int, base = 16)
    
    output = []
    for i in np.arange(0, len(df)):
        
        if df.iloc[i]['wlan type-subtype'] == 'VHT NDP Announcement':
            
            for j in (i + 1, i + 5):
                
                if j > len(df) - 1:
                    break
                
                if (df.iloc[j]['wlan type-subtype'] == 'Action No Ack') and (df.iloc[j]['wlan src addr'] == df.iloc[i]['wlan dst addr']):
                    if df.iloc[j][col_client] == df.iloc[i][col_ap]:
                    
                        output.append({
                            'sound-nr' : df.iloc[j][col_client],
                            'client-mac-addr' : df.iloc[j]['wlan src addr'],
                            'time-gap' : df.iloc[j]['epoch time'] - df.iloc[i]['epoch time'],
                            'time-annc' : (df.iloc[i]['frame len'] * 8.0) / df.iloc[i]['wlan data rate'],
#                            'time-fb' : (df.iloc[j]['frame len'] * 8.0) / df.iloc[j]['wlan data rate'],
                            'size-annc' : df.iloc[i]['frame len'],
#                            'size-fb' : df.iloc[j]['frame len'],
                            'bitrate-annc' : df.iloc[i]['wlan data rate'],
#                            'bitrate-fb' : df.iloc[j]['wlan data rate'],
                            'mimo-type' : df.iloc[j]['wlan feedback type client']})
    
                        i = j + 1
    
                        break                        
                        
    return pd.DataFrame(output)
    
def get_mimo_overhead_report(input_dir, graph_dir):

    ap = {'mac_addr' : '50:c7:bf:97:8a:a7'}
    clients = {'tp-02' : {'color' : 'red', 'label' : 'C1', 'mac_addr' : '50:c7:bf:c8:4d:22'}, 
               'tp-03' : {'color' : 'blue', 'label' : 'C2', 'mac_addr' : '50:c7:bf:3c:53:1a'}}
    
    mimo_types = {'su' : {'linestyle' : '-', 'marker' : 'o', 'label' : 'SU'}, 
                  'mu' : {'linestyle' : '-', 'marker' : '^', 'label' : 'MU'}}

#    rssi = pd.DataFrame()
    
    processed_dir = os.path.join(input_dir, 'processed')
    if not os.path.exists(processed_dir):
        os.makedirs(processed_dir)
        
    output = {
        'sounding-freq' : os.path.join(processed_dir, ('sounding-freq.csv')),
        'sounding-gap' : os.path.join(processed_dir, ('sounding-gap.csv')),
        'sounding-times' : os.path.join(processed_dir, ('sounding-times.csv')),
        'bitrates' : os.path.join(processed_dir, ('bitrates.csv')),
        'sounding-contention' : os.path.join(processed_dir, ('sounding-contention.csv')),
        'inter-arrival-times' : os.path.join(processed_dir, ('inter-arrival-times.csv'))
    }

    test_info = pd.read_csv(os.path.join(input_dir, ('tests.csv')))    
    for test_file in sorted(glob.glob(os.path.join(input_dir, ('filtered/pcaps/test-*.csv')))):
        
        dataframes = {
            'sounding-freq' : pd.DataFrame(),
            'sounding-gap' : pd.DataFrame(),
            'sounding-times' : pd.DataFrame(),
            'bitrates' : pd.DataFrame(),
            'sounding-contention' : pd.DataFrame(),
            'inter-arrival-times' : pd.DataFrame()
        }
        
        test_nr = test_file.split('/')[-1].split('-')[1].rstrip('.csv')
        start_timestamp = min(test_info.iloc[int(test_nr) - 1]['start-time-c1'], test_info.iloc[int(test_nr) - 1]['start-time-c2'])

        chunksize = 10 ** 5
        for chunk in pd.read_csv(test_file, chunksize = chunksize):
            
            # FIXME: A-MSDUs aggergate several MSDUs (essentially 802.3 frames minus the Ethernet header)
            # as such, 'wlan data rate' values show up as '<bitrate-msdu-1>,<bitrate-msdu-2>'
            # since in all cases i've observed the msdu's bitrates are the same, we fix it by only keeping <bitrate-msdu-1>
            chunk['wlan data rate'] = chunk['wlan data rate'].astype(str)
            chunk['wlan data rate'] = chunk['wlan data rate'].apply(lambda x : x.split(',')[0]).astype(float)
            
            # q: bitrates of wlan data frames?
            br = chunk[chunk['wlan type-subtype'].str.contains('QoS Data')][['epoch time', 'wlan type-subtype', 'frame len', 'wlan duration', 'wlan data rate', 'wlan dst addr', 'wlan beamform']]
            br = br.groupby(['wlan dst addr', 'wlan data rate', 'wlan beamform']).size().reset_index(name = 'counts', drop = False)
            dataframes['bitrates'] = pd.concat([br, dataframes['bitrates']], ignore_index = True)
            
    #        # q: rssi of beacons vs. beamformed wlan dataframes?
    #        # a: due to the position at which rss is taken, this analysis is useless.
    #        r = chunk[chunk['wlan type-subtype'].str.contains('Beacon frame|QoS Data')][['epoch time', 'wlan type-subtype', 'wlan rssi', 'wlan dst addr', 'wlan beamform']]
    ##        r['wlan beamform'] = r['wlan beamform'].fillna(value = False)
    #        r = r.groupby(['wlan dst addr', 'wlan type-subtype', 'wlan rssi']).size().reset_index(name = 'counts', drop = False)
    #        rssi = pd.concat([r, rssi], ignore_index = True)
            
            wlan_dfs = chunk[chunk['wlan type-subtype'].str.contains('VHT NDP Announcement|Action No Ack|QoS Data')][['epoch time', 'wlan data rate', 'wlan type-subtype', 'frame len', 'wlan feedback type ap', 'wlan feedback type client', 'wlan sounding dialog token nr ap', 'wlan sounding dialog token nr client', 'wlan src addr', 'wlan dst addr']]

            a, b = update_sounding_contention(wlan_dfs[(wlan_dfs['wlan src addr'] == ap['mac_addr']) | (wlan_dfs['wlan dst addr'] == ap['mac_addr'])])
            dataframes['sounding-contention'] = pd.concat([a, dataframes['sounding-contention']], ignore_index = True)
            b = b.groupby(['wlan dst addr', 'time-gap']).size().reset_index(name = 'counts', drop = False)
            dataframes['inter-arrival-times'] = pd.concat([b, dataframes['inter-arrival-times']], ignore_index = True)
            
            for c, client in enumerate(['tp-02', 'tp-03']):
                
                client_df = wlan_dfs[((wlan_dfs['wlan src addr'] == clients[client]['mac_addr']) | ((wlan_dfs['wlan src addr'] == ap['mac_addr']) & (wlan_dfs['wlan dst addr'] == clients[client]['mac_addr'])))].reset_index(drop = True)
    
                # q: how much time does the whole *U-MIMO sounding procedure take?
                dataframes['sounding-gap'] = pd.concat([update_sounding_gap(client_df), dataframes['sounding-gap']], ignore_index = True)
                dataframes['sounding-times'] = pd.concat([update_sounding_times(client_df), dataframes['sounding-times']], ignore_index = True)
                # q: how many data frames between beamforming reports?
                # q: how often does it occur (in terms of time and nr. of packets)
                dataframes['sounding-freq'] = pd.concat([update_sounding_freq(client_df), dataframes['sounding-freq']], ignore_index = True)
                
        dataframes['bitrates'] = dataframes['bitrates'].groupby(['wlan dst addr', 'wlan data rate', 'wlan beamform'])['counts'].sum().reset_index(drop = False)
        dataframes['inter-arrival-times'] = dataframes['inter-arrival-times'].groupby(['wlan dst addr', 'time-gap'])['counts'].sum().reset_index(drop = False)        
    
        for cat in output:
            
            dataframes[cat]['test-nr'] = int(test_nr)
            
            for antenna in antennas:
                if int(test_nr) in antennas[antenna]['tests']:
                    dataframes[cat]['antenna'] = antenna
                    break
            
            if not os.path.isfile(output[cat]):
                dataframes[cat].to_csv(output[cat], sep = ',')
            else:
                dataframes[cat].to_csv(output[cat], sep = ',', mode = 'a', header = False)
    
def plot_mimo_frames(test_nr, input_dir, graph_dir):

    plt.style.use('classic')
    fig = plt.figure(figsize = (3.5, 3.75))
    
    # list of ax : [throughput, pkt_loss]
    axs = []
    axs.append(fig.add_subplot(2, 1, 1))
    axs.append(fig.add_subplot(2, 1, 2))
    for ax in axs:
        ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
        ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)

    test_info = pd.read_csv(os.path.join(input_dir, ('tests.csv')))
    start_timestamp = min(test_info.iloc[int(test_nr) - 1]['start-time-c1'], test_info.iloc[int(test_nr) - 1]['start-time-c2'])
    
    clients = {'tp-02' : {'color' : 'red', 'label' : 'C1', 'mac_addr' : '50:c7:bf:c8:4d:22'}, 
               'tp-03' : {'color' : 'blue', 'label' : 'C2', 'mac_addr' : '50:c7:bf:3c:53:1a'}}    
    mimo_types = {'su' : {'linestyle' : '-', 'marker' : 'o', 'label' : 'SU'}, 'mu' : {'linestyle' : '-', 'marker' : '^', 'label' : 'MU'}}

    chunksize = 10 ** 5
    td = pd.DataFrame()
    for chunk in pd.read_csv(os.path.join(input_dir, ('filtered/pcaps/test%d.csv' % (int(test_nr)))), chunksize = chunksize):        
        # only keep frames of interest : MIMO feedback req. and rsp.
        chunk = chunk[chunk['wlan type-subtype'].str.contains('Action No Ack|VHT NDP Announcement')][['epoch time', 'wlan src addr', 'wlan dst addr', 'wlan type-subtype', col_ap, 'wlan feedback type ap', 'wlan sounding dialog token nr client', 'wlan feedback type client']]
        td = pd.concat([td, chunk], ignore_index = True)
        
    if td.empty:
        return

    td['elapsed time'] = td['epoch time'] - start_timestamp
    
    for c, client in enumerate(['tp-02', 'tp-03']):
        
        data = get_mimo_stats(td[td['wlan src addr'] == clients[client]['mac_addr']])
    
        for fb_type in ['su', 'mu']:
            axs[0].plot(
                data['elapsed time'],
                data[fb_type],
                linewidth = 0.5, linestyle = mimo_types[fb_type]['linestyle'], color = clients[client]['color'], label = ('%s (%s)' % (clients[client]['label'], mimo_types[fb_type]['label'])), 
                marker = mimo_types[fb_type]['marker'], markersize = 4.5, markeredgewidth = 0.0)

        tghpt_data = pd.read_csv(os.path.join(input_dir, ('filtered/iperf3/%s/test%d.out.csv' % (client, int(test_nr)))))
        tghpt_data['start'] = tghpt_data['start'] + test_info.iloc[int(test_nr) - 1][('start-time-%s' % (clients[client]['label'].lower()))] - start_timestamp

        axs[1].plot(
            tghpt_data['start'],
            tghpt_data['bits_per_second'] * 0.000001,
            linewidth = 1.0, linestyle = '-', color = clients[client]['color'], label = clients[client]['label'], 
            marker = None, markersize = 0.0, markeredgewidth = 0.0)        

        axs[0].set_title('# of x-MIMO frames per sec', fontsize = 10)
        axs[1].set_title('throughput', fontsize = 10)
        
        axs[0].set_ylim([0, 50])
        axs[0].set_yticks([0, 10, 20, 30, 40, 50])
#        axs[0].set_ylim([0, 50])
#        axs[0].set_yticks([0, 5, 10, 15, 20, ])
 
        axs[1].set_ylim([0, 400])
        axs[1].set_yticks([0, 100, 200, 300, 400])
        
    axs[1].set_xlabel('elapsed time (sec)', fontsize = 10)

    leg = axs[0].legend(
        fontsize = 8, 
        ncol = 2, loc = 'upper left',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    for legobj in leg.legendHandles:
        legobj.set_linewidth(2.0)

    leg = axs[1].legend(
        fontsize = 8, 
        ncol = 1, loc = 'lower right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    for legobj in leg.legendHandles:
        legobj.set_linewidth(2.0)

    axs[0].set_ylabel('fps', fontsize = 10)
    axs[1].set_ylabel('thghpt (Mbps)', fontsize = 10)

    axs[0].set_xlim([0, 70])
    axs[1].set_xlim([0, 70])

    axs[0].tick_params(axis = 'both', which = 'major', labelsize = 10)
    axs[1].tick_params(axis = 'both', which = 'major', labelsize = 10)
    
    fig.tight_layout()
    plt.savefig(os.path.join(graph_dir, ("mimo-stats-%d.pdf" % (int(test_nr)))), bbox_inches = 'tight', format = 'pdf')
    
def plot_mimo_performance(test_nrs, input_dir, graph_dir):
    
    plt.style.use('classic')
    fig = plt.figure(figsize = (2.0, 2.0))
    
    # list of ax : [throughput, pkt_loss]
    axs = []
    axs.append(fig.add_subplot(1, 1, 1))
#    axs.append(fig.add_subplot(1, 2, 2))

    for ax in axs:
        ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
        ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)
    
    clients = {'tp-02' : {'color' : 'red', 'label' : 'C1', 'mac_addr' : '50:c7:bf:c8:4d:22'}, 
               'tp-03' : {'color' : 'blue', 'label' : 'C2', 'mac_addr' : '50:c7:bf:3c:53:1a'},
               'aggr.' : {'color' : 'black', 'label' : 'aggr.'}}

    # MIMO performance data (all)
    perf_data = pd.DataFrame()    
    perf_filename = os.path.join(input_dir, ("mimo-perf-stats-%s.csv" % ('-'.join([str(tn) for tn in test_nrs]))))
    
    if not os.path.exists(perf_filename):

        for test_nr in test_nrs:
            
            test_data = []
            
            chunksize = 10 ** 5
            for chunk in pd.read_csv(os.path.join(input_dir, ('filtered/pcaps/test%d.csv' % (int(test_nr)))), chunksize = chunksize):
                
                for c, client in enumerate(['tp-02', 'tp-03']):
                    cd = chunk[chunk['wlan dst addr'] == clients[client]['mac_addr']]
                    test_data.append({
                        'test-nr' : test_nr,
                        'client' : client,
                        'bitrate' : cd['wlan data rate'].mean()})
            
            test_data = pd.DataFrame(test_data).groupby(['test-nr', 'client'])['bitrate'].mean().reset_index(drop = False)
            test_data['tghpt'] = 0.0
            test_data['pkt-loss'] = 0.0
            
            for c, client in enumerate(['tp-02', 'tp-03']):
                iperf3_data = pd.read_csv(os.path.join(input_dir, ('filtered/iperf3/%s/test%d.out.csv' % (client, int(test_nr)))))
                test_data.loc[test_data['client'] == client, 'tghpt'] = iperf3_data['bits_per_second'].mean()
                test_data.loc[test_data['client'] == client, 'pkt-loss'] = iperf3_data['lost_percent'].mean()            
                
            perf_data = pd.concat([test_data, perf_data], ignore_index = True)
            
        perf_data.to_csv(perf_filename, sep = ',')

    else:
        perf_data = pd.read_csv(perf_filename)

    xx = 0.0
    xticks = []
    xtickslabels = []
    
    antennas = {1 : '4x2', 2 : '4x1', 6 : '4x2', 7 : '4x1'}
    labels = {
            'tp-02' : {'label' : 'C1'}, 
            'tp-03' : {'label' : 'C2'},
            'aggr.' : {'label' : 'aggr.'}}
    
    for test_nr in test_nrs:
        for c, case in enumerate(['tp-02', 'tp-03', 'aggr.']):
        
            val = 0.0
            if case != 'aggr.':
                val = perf_data[(perf_data['client'] == case) & (perf_data['test-nr'] == test_nr)]['tghpt']
            else:
                val = perf_data[(perf_data['test-nr'] == test_nr)]['tghpt'].sum()
                
            axs[0].bar(xx, val * 0.000001,
               width = 0.5, linewidth = 0.250, alpha = .75,
               color = clients[case]['color'], label = labels[case]['label'])
            
            labels[case]['label'] = None
            
            if c == 1:
                xticks.append(xx)
                xtickslabels.append(antennas[test_nr])
            
            xx += 0.5
        xx += 2.0 * 0.5
        
    leg = axs[0].legend(
        fontsize = 8, 
        ncol = 3, loc = 'upper left',
        handletextpad = 0.2, handlelength = 0.75, labelspacing = 0.2, columnspacing = 0.5)
        
    axs[0].set_xlabel('antenna config.')
    axs[0].set_ylabel('avg. thghpt (Mbps)')
    axs[0].set_ylim([0.0, 800.0])
    axs[0].set_yticks([0.0, 200.0, 400.0, 600.0, 800])
    axs[0].set_xticks(xticks)
    axs[0].set_xticklabels(xtickslabels)

#    xx = 0.0
#    xticks = []
#    xtickslabels = []
#
#    labels = {
#            'tp-02' : {'label' : '2'}, 
#            'tp-03' : {'label' : '3'},
#            'aggr.' : {'label' : 'aggr.'}}
#
#    for test_nr in test_nrs:
#        for c, case in enumerate(['tp-02', 'tp-03']):
#        
#            val = 0.0
#            val = perf_data[(perf_data['client'] == case) & (perf_data['test-nr'] == test_nr)]['pkt-loss']
#                
#            axs[1].bar(xx, val,
#               width = 0.5, linewidth = 0.250, alpha = .75,
#               color = clients[case]['color'], label = labels[case]['label'])
#            
#            labels[case]['label'] = None
#            
#            if c == 0:
#                xticks.append(xx + 0.25)
#                xtickslabels.append(antennas[test_nr])
#
#            xx += 0.5            
#        xx += 2.0 * 0.5
#        
#    leg = axs[1].legend(
#        fontsize = 8, 
#        ncol = 3, loc = 'upper right',
#        handletextpad = 0.2, handlelength = 0.75, labelspacing = 0.2, columnspacing = 0.5)
#        
#    axs[1].set_xlabel('antennas')
#    axs[1].set_ylabel('avg. pkt loss (%)')
#    axs[1].set_ylim([0, 100])
#    axs[1].set_yticks([0, 25, 50, 75, 100])
#    axs[1].set_xticks(xticks)
#    axs[1].set_xticklabels(xtickslabels)    
        
    fig.tight_layout()
    plt.savefig(os.path.join(graph_dir, ("mimo-perf-stats-%s.pdf" % ('-'.join([str(tn) for tn in test_nrs])))), bbox_inches = 'tight', format = 'pdf')

def plot_mimo_overhead(input_dir, graph_dir):

    processed_dir = os.path.join(input_dir, 'processed')

    sounding_gap = pd.read_csv(os.path.join(processed_dir, ('sounding-gap.csv')))
    sounding_freq = pd.read_csv(os.path.join(processed_dir, ('sounding-freq.csv')))
    sounding_times = pd.read_csv(os.path.join(processed_dir, ('sounding-times.csv')))
    sounding_contention = pd.read_csv(os.path.join(processed_dir, ('sounding-contention.csv')))
    inter_arrival = pd.read_csv(os.path.join(processed_dir, ('inter-arrival-times.csv')))
    
    table = PrettyTable(['type', '# chan sound', 'time', 'size', 'bitrate'])

    stats = []
    stats.append({
        'type' : 'vht ndp annc',
        '# chan sound' : len(sounding_gap),
        'time' : sounding_gap['time-annc'].median(),
        'size' : sounding_gap['size-annc'].median(),
        'bitrate' : sounding_gap['bitrate-annc'].median()})
    
    stats.append({
        'type' : 'vht feedback (su-mimo)',
        '# chan sound' : len(sounding_times[sounding_times['mimo-type'].str.contains('SU')]),
        'time' : sounding_times[sounding_times['mimo-type'].str.contains('SU')]['time'].median(),
        'size' : sounding_times[sounding_times['mimo-type'].str.contains('SU')]['frame len'].median(),
        'bitrate' : sounding_times[sounding_times['mimo-type'].str.contains('SU')]['wlan data rate'].median()})

    stats.append({
        'type' : 'vht feedback (mu-mimo)',
        '# chan sound' : len(sounding_times[sounding_times['mimo-type'].str.contains('MU')]),
        'time' : sounding_times[sounding_times['mimo-type'].str.contains('MU')]['time'].median(),
        'size' : sounding_times[sounding_times['mimo-type'].str.contains('MU')]['frame len'].median(),
        'bitrate' : sounding_times[sounding_times['mimo-type'].str.contains('MU')]['wlan data rate'].median()})
    
    stats.append({
        'type' : 'cs interval (su-mimo)',
        '# chan sound' : len(sounding_freq[sounding_freq['wlan feedback type client'].str.contains('SU')]) / 2,
        'time' : sounding_freq[sounding_freq['wlan feedback type client'].str.contains('SU')]['time-interval'].median(),
        'size' : '-',
        'bitrate' : '-'})
    
    stats.append({
        'type' : 'cs interval (mu-mimo)',
        '# chan sound' : len(sounding_freq[sounding_freq['wlan feedback type client'].str.contains('MU')]) / 2,
        'time' : sounding_freq[sounding_freq['wlan feedback type client'].str.contains('MU')]['time-interval'].median(),
        'size' : '-',
        'bitrate' : '-'})
    
    stats.append({
        'type' : 'gap (4x1)',
        '# chan sound' : len(sounding_gap[sounding_gap['antenna'].str.contains('4x1')]),
        'time' : sounding_gap[sounding_gap['antenna'].str.contains('4x1')]['time-gap'].median() * 1000000.0,
        'size' : '-',
        'bitrate' : '-'})

    stats.append({
        'type' : 'gap (4x2)',
        '# chan sound' : len(sounding_gap[sounding_gap['antenna'].str.contains('4x2')]),
        'time' : sounding_gap[sounding_gap['antenna'].str.contains('4x2')]['time-gap'].median() * 1000000.0,
        'size' : '-',
        'bitrate' : '-'})    

    for i, row in pd.DataFrame(stats).iterrows():
        table.add_row([
            ('%s' % (row['type'])),
            ('%d' % (row['# chan sound'])), 
            ('%s' % (row['time'])), 
            ('%s' % (row['size'])),
            ('%s' % (row['bitrate']))
            ])

    print(table)
    
    plt.style.use('classic')
    fig = plt.figure(figsize = (7.0, 2.25))
    
    axs = []
    axs.append(fig.add_subplot(1, 3, 1))
    axs.append(fig.add_subplot(1, 3, 2))
    axs.append(fig.add_subplot(1, 3, 3))    
    
    for ax in axs:
        ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
        ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)

#    clients = {'tp-02' : {'color' : 'red',  'label' : 'C1', 'mac-addr' : '50:c7:bf:c8:4d:22'}, 
#               'tp-03' : {'color' : 'blue', 'label' : 'C2', 'mac-addr' : '50:c7:bf:3c:53:1a'}}
    
    mimo_types = {'su' : {'color' : 'red', 'linestyle' : '-', 'marker' : 'o', 'label' : 'SU', 'range' : [0.0, 500.0]}, 
                  'mu' : {'color' : 'green', 'linestyle' : '-', 'marker' : '^', 'label' : 'MU', 'range' : [0.0, 50.0]}}
    
    # 1) NDP annc. <> VHT feedback gaps
    plot_configs = {
        'x-label' : 'gap (\u03BCs)',
        'coef' : 1.0,
        'linewidth' : 0.0,
        'markersize' : 1.25,
        'marker' : 'o',
        'markeredgewidth' : 0.0,
        'label' : '', 
        'color' : 'red',
        'loc' : 'lower right',
        'x-lim' : None
    }    
    
    for i, mimo_type in enumerate(['su']):
        for antenna in antennas:

            df = sounding_gap[(sounding_gap['mimo-type'] == mimo_type.upper()) & (sounding_gap['antenna'] == antenna)]
            # to microseconds
            df['time-gap'] = df['time-gap'] * (1000000.0)
            
            plot_configs['color'] = antennas[antenna]['color']
            plot_configs['label'] = antennas[antenna]['label']
            
            plot.utils.cdf(axs[0], df, metric = 'time-gap', plot_configs = plot_configs)

    axs[0].set_xlim([sounding_gap['time-gap'].min() * 1000000.0, sounding_gap['time-gap'].max() * 1000000.0])
    axs[0].set_xlim([sounding_gap['time-gap'].min() * 1000000.0, 1000.0])    
    axs[0].set_title('(a) NDP annc. - feedback\ngap', fontsize = 10)
    axs[0].set_xscale('log', nonposx = 'clip')
    
    # 2) inter-packet arrival times
    plot_configs = {
        'x-label' : 'gap (\u03BCs)',
        'coef' : 1.0,
        'linewidth' : 0.0,
        'markersize' : 1.25,
        'marker' : 'o',
        'markeredgewidth' : 0.0,
        'label' : '', 
        'color' : '',
        'loc' : 'lower right',
        'x-lim' : None
    }
    
    # 2.1) baseline : wlan data frames
    plot_configs['color'] = 'blue'
    plot_configs['label'] = 'data frames'
    plot.utils.cdf(axs[1], inter_arrival, metric = 'time-gap', plot_configs = plot_configs)

    # 2.2) su-mimo : same feedback & data dev
    plot_configs['color'] = 'red'
    plot_configs['label'] = 'vht fb <-> data'
    plot.utils.cdf(axs[1], sounding_contention, metric = 'time-gap', plot_configs = plot_configs)    

    print(len(sounding_contention[(sounding_contention['data-dev'] == sounding_contention['feedback-dev'])]))

#    # 2.3) su-mimo : diff feedback & data dev
#    plot_configs['color'] = 'green'
#    plot_configs['label'] = 'after fb (diff.)'
#    plot.utils.cdf(axs[1], sounding_contention[(sounding_contention['data-dev'] != sounding_contention['feedback-dev'])], metric = 'time-gap', plot_configs = plot_configs)

    print(len(sounding_contention[(sounding_contention['data-dev'] != sounding_contention['feedback-dev'])]))

    axs[1].set_xlim([inter_arrival['time-gap'].min(), 1000.0])
    axs[1].set_xscale('log', nonposx = 'clip')
    axs[1].set_title('(b) inter-packet arrival\ngap', fontsize = 10)

    # 3) interval between channel sounding proc.
    plot_configs = {
        'x-label' : 'interval (ms)',
        'coef' : 1.0,
        'linewidth' : 0.0,
        'markersize' : 1.25,
        'marker' : 'o',
        'markeredgewidth' : 0.0,
        'label' : '', 
        'color' : 'blue',
        'loc' : 'upper left',
        'x-lim' : None
    }    

    for i, mimo_type in enumerate(['su', 'mu']):

        df = sounding_freq[sounding_freq['wlan feedback type client'] == mimo_type.upper()]
        # to milliseconds
        df['time-interval'] = df['time-interval'] * (1000.0)
        
        plot_configs['color'] = mimo_types[mimo_type]['color']
        plot_configs['label'] = mimo_types[mimo_type]['label']
        
        plot.utils.cdf(axs[2], df, metric = 'time-interval', plot_configs = plot_configs)

    axs[2].set_xlim([sounding_freq['time-interval'].min() * 1000, sounding_freq['time-interval'].max() * 1000])
    axs[2].set_xscale('log', nonposx = 'clip')
    axs[2].set_title('(c) interval between\nNDP annc.', fontsize = 10)
    
#    overhead_file = os.path.join(input_dir, ("mimo-overhead-%d.csv" % (test_nr)))
#    if not os.path.exists(overhead_file):
#            
#        chunksize = 10 ** 5
#        td = pd.DataFrame()
#        for chunk in pd.read_csv(os.path.join(input_dir, ('filtered/pcaps/test%d.csv' % (int(test_nr)))), chunksize = chunksize):        
#            chunk = chunk[chunk['wlan type-subtype'].str.contains('Action No Ack')][['epoch time', 'wlan src addr', 'wlan dst addr', 'wlan type-subtype', 'wlan sounding dialog token nr client', 'wlan feedback type client']]
#            chunk['mimo-type'] = chunk['wlan feedback type client'].apply(lambda x : x.lower())
#            td = pd.concat([td, chunk], ignore_index = True)
#            
#        if td.empty:
#            return
#        
#        td['interval'] = 0.0
#        mimo_intrvl = pd.DataFrame()
#        for c, client in enumerate(['tp-02', 'tp-03']):
#            
#            cd = td[(td['wlan src addr'] == clients[client]['mac-addr'])].reset_index(drop = True)
#            cd['client'] = client
#            
#            for mimo_type in ['su', 'mu']:
#                cd.loc[(cd['mimo-type'].str.contains(mimo_type)), 'interval'] = cd[(cd['mimo-type'].str.contains(mimo_type))]['epoch time'] - cd[(cd['mimo-type'].str.contains(mimo_type))]['epoch time'].shift(1)
#                
#            mimo_intrvl = pd.concat([mimo_intrvl, cd[['mimo-type', 'client', 'interval']]], ignore_index = True)
#        mimo_intrvl.to_csv(overhead_file)
#        
#    else:
#        mimo_intrvl = pd.read_csv(overhead_file)
        
#    plot_configs = {
#        'x-label' : 'interval (ms)',
#        'coef' : 1000.0,
#        'linewidth' : 0.0,
#        'markersize' : 1.25,
#        'marker' : 'o',
#        'markeredgewidth' : 0.0,
#        'label' : '', 
#        'color' : '',
#        'loc' : 'lower right',
#        'x-lim' : None
#    }
#        
#    for i, mimo_type in enumerate(['su', 'mu']):
#        
#        df = mimo_intrvl[mimo_intrvl['mimo-type'] == mimo_type]
#        print(df)
#        
#        plot_configs['color'] = mimo_types[mimo_type]['color']
#        plot_configs['label'] = mimo_types[mimo_type]['label']
#        plot_configs['x-lim'] = mimo_types[mimo_type]['range']        
# 
#        plot.utils.cdf(axs[i], df, metric = 'interval', plot_configs = plot_configs)
        
    fig.tight_layout()
    plt.savefig(os.path.join(graph_dir, ("mimo-overhead.pdf")), bbox_inches = 'tight', format = 'pdf')
    
def plot_vht_compressed_bf_report(test_nr, input_dir, graph_dir):

    bf_dir = os.path.join(input_dir, ('filtered/beamforming/csv'))
    
    bf_filename = os.path.join(bf_dir, ("vht-compressed-bf-snr-test%d.csv" % (test_nr)))
    bf_data = pd.read_csv(bf_filename)

    # cdfs of avg snr per client    
    plt.style.use('classic')
    fig = plt.figure(figsize = (6.0, 2.0))
    
    # list of ax : [throughput, pkt_loss]
    axs = []
    axs.append(fig.add_subplot(1, 2, 1))
    axs.append(fig.add_subplot(1, 2, 2))
    for ax in axs:
        ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
        ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)

    clients = {'tp-02' : {'color' : 'red',  'label' : 'C1', 'mac-addr' : '50:c7:bf:c8:4d:22'},
               'tp-03' : {'color' : 'blue', 'label' : 'C2', 'mac-addr' : '50:c7:bf:3c:53:1a'}}
    
    spatial_streams = {'1' : {'color' : 'blue', 'label' : 'ss 1', 'linestyle' : '-'},
                       '2' : {'color' : 'red', 'label' : 'ss 2', 'linestyle' : ':'},
                       '3' : {'color' : 'green', 'label' : 'ss 3', 'linestyle' : '--'}}

    plot_configs = {
        'x-label' : 'snr (dB)',
        'coef' : 1.0,
        'linewidth' : 0.0,
        'markersize' : 1.25,
        'marker' : 'o',
        'markeredgewidth' : 0.0,
        'label' : '', 
        'color' : '',
        'loc' : 'upper left',
        'x-lim' : [-10.0, 60.0]
    }   
    
    for c, client in enumerate(['tp-02', 'tp-03']):
        
        df = bf_data[bf_data['wlan src addr'] == clients[client]['mac-addr']]
        
        sses = [x for x in df.columns if 'avg-snr-' in x]
        
        axs[c].set_title('avg. snr per sstream (%s)' % (clients[client]['label']), fontsize = 10)
        
        for ss in sses:

            plot_configs['color'] = spatial_streams[ss.lstrip('avg-srn-')]['color']
            plot_configs['label'] = spatial_streams[ss.lstrip('avg-srn-')]['label']
            
#            plot.utils.cdf(axs[c], df, metric = ss, plot_configs = plot_configs)
            axs[c].hist(df[ss], int((60.00 + 10) / 1.00), linewidth = 0.075, density = False, facecolor = plot_configs['color'], alpha = 0.50, label = plot_configs['label'], range = plot_configs['x-lim'])

        axs[c].set_xlim(plot_configs['x-lim'])

        axs[c].set_xlabel(plot_configs['x-label'], fontsize = 10)
        axs[c].set_ylabel('# of samples', fontsize = 10)

        axs[c].tick_params(axis = 'both', which = 'major', labelsize = 10)
        axs[c].tick_params(axis = 'both', which = 'minor', labelsize = 10)
        
        legend = axs[c].legend(
            fontsize = 8, 
            ncol = 1, loc = plot_configs['loc'],
            handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

        for legobj in legend.legendHandles:
            legobj.set_linewidth(0.075)        
            
    fig.tight_layout()
    plt.savefig(os.path.join(graph_dir, ("avg-snr-sstream-%s.pdf" % (test_nr))), bbox_inches = 'tight', format = 'pdf')

    bf_filename = os.path.join(bf_dir, ("vht-compressed-bf-angles-test%d.csv" % (test_nr)))
    bf_data = pd.read_csv(bf_filename)

    # cdfs of (avg.?) angles per client    
    plt.style.use('classic')
    fig = plt.figure(figsize = (6.0, 4.0))
    
    # list of ax : [throughput, pkt_loss]
    axs = []
    axs.append(fig.add_subplot(2, 2, 1))
    axs.append(fig.add_subplot(2, 2, 3))
    axs.append(fig.add_subplot(2, 2, 2))
    axs.append(fig.add_subplot(2, 2, 4))
    
    for ax in axs:
        ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
        ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)    

    angle_defs = {
        1 : {'color' : 'red'},
        2 : {'color' : 'green'},
        3 : {'color' : 'blue'}}
    
    angle_type_defs = {
        'phi' : {
            'prefix' : '\u03A6',
            'xlim' : np.array([0.0, 2.0]) * np.pi,
            'xticklabels' : ['0', '\u03C0', '2\u03C0'],
            'xticks' : np.array([0.0, 1.0, 2.0]) * np.pi},
        'psi' : {
            'prefix' : '\u03A8',                
            'xlim' : np.array([0.0, 0.5]) * np.pi,
            'xticklabels' : ['0', '\u03C0/4', '\u03C0/2'],
            'xticks' : np.array([0.0, 0.25, 0.5]) * np.pi},
        }

    plot_configs = {
        'x-label' : 'angle (radians)',
        'coef' : 1.0,
        'linewidth' : 0.0,
        'markersize' : 1.25,
        'marker' : 'o',
        'markeredgewidth' : 0.0,
        'label' : '', 
        'color' : '',
        'loc' : 'lower right',
        'fontsize' : 10,
        'x-lim' : None
    }   
    
    for c, client in enumerate(['tp-02', 'tp-03']):
        
        df = bf_data[bf_data['wlan src addr'] == clients[client]['mac-addr']]
        
        for at, angle_type in enumerate(['phi', 'psi']):
            
            angles = [x for x in df.columns if angle_type in x]
            angle_prefix = angle_type_defs[angle_type]['prefix']
#            angle_prefix = '\u03A6' if at == 0 else '\u03A8'
            
            axs[(2 * c) + at].set_title('%s angles (%s)' % (angle_prefix, clients[client]['label']), fontsize = 10)
            
            for angle in angles:
            
                angle_nr = int(angle.split('-')[1])
                angle_nr = angle_nr - 1 if at == 1 else angle_nr
                sstream = angle.split('-')[-1]
                
                plot_configs['linestyle'] = spatial_streams[sstream]['linestyle']
                plot_configs['label'] = ('%s-%s' % (angle_prefix, angle.split('-', 1)[-1]))
                plot_configs['color'] = angle_defs[angle_nr]['color']

                # divide by 'pi' to show multiples of pi in the x scale
                df[ss] = df[angle] / np.pi
                
                plot.utils.cdf(axs[(2 * c) + at], df, metric = angle, plot_configs = plot_configs)
                
                axs[(2 * c) + at].set_xticks(angle_type_defs[angle_type]['xticks'])
                axs[(2 * c) + at].set_xticklabels(angle_type_defs[angle_type]['xticklabels'], fontsize = 10)
                axs[(2 * c) + at].set_xlim(angle_type_defs[angle_type]['xlim'])
            
    fig.tight_layout()
    plt.savefig(os.path.join(graph_dir, ("bf-angles-%s.pdf" % (test_nr))), bbox_inches = 'tight', format = 'pdf')

def fix_ticks(data, max_tick_nr = 20):
    
    # we show the boundaries of every second in which a *U-MIMO frame occurred
    xt = data[['epoch time']].reset_index(drop = True)
    xt['time'] = xt['epoch time'].astype(int)
    xt['time'] = xt['time'] - xt.iloc[0]['time']
    # get 'same second' groups
    xt['group'] = 0
    xt['group'] = (xt['time'] != xt['time'].shift(1)).astype(int).cumsum()
    
    # FIXME: this transform() function is one of the most important 
    # thing's you've learnd about Pandas in months...
    # https://stackoverflow.com/questions/17995024/how-to-assign-a-name-to-the-a-size-column
    xt['size'] = 0
    xt['size'] = xt.groupby(['group']).transform(np.size)

    # get index & value of first rows of each 'same second' group            
    xt = xt.loc[xt.groupby(['group'])['time'].idxmin()]
    
    xt['tick'] = 0
    xt.loc[0, 'tick'] = 1
    step_size = xt.iloc[0]['size']
    n = len(data) / max_tick_nr
    for i, row in xt.iterrows():
        if (step_size > n):
            xt.loc[i, 'tick'] = 1
            step_size = 0
            
        step_size += row['size']
    
    xt = xt[xt['tick'] > 0]
    return xt

def plot_subcarrier_angles(test_nr, input_dir, graph_dir):
    
    clients = {'tp-02' : {'color' : 'red',  'label' : 'C1', 'mac-addr' : '50:c7:bf:c8:4d:22'}, 
               'tp-03' : {'color' : 'blue', 'label' : 'C2', 'mac-addr' : '50:c7:bf:3c:53:1a'}}    

    bf_dir = os.path.join(input_dir, ('filtered/beamforming/csv'))
    bf_filename = os.path.join(bf_dir, ("vht-compressed-bf-angles-test%d.csv" % (test_nr)))
    bf_data = pd.read_csv(bf_filename)

    test_dir = os.path.join(graph_dir, ('subcarrier-angles/%s' % (test_nr)))
    if not os.path.exists(test_dir):
        os.makedirs(test_dir)

    # heatmaps of subcarrier angles vs. time
    
    angles = []
    for angle_type in ['psi', 'phi']:
        angles += [x for x in bf_data.columns if angle_type in x]
    
    angle_type_defs = {
        'phi' : {
            'prefix' : '\u03A6',
            'xlim' : np.array([0.0, 2.0]) * np.pi,
            'xticklabels' : ['0', '\u03C0', '2\u03C0'],
            'xticks' : np.array([0.0, 1.0, 2.0]) * np.pi},
        'psi' : {
            'prefix' : '\u03A8',                
            'xlim' : np.array([0.0, 0.5]) * np.pi,
            'xticklabels' : ['0', '\u03C0/4', '\u03C0/2'],
            'xticks' : np.array([0.0, 0.25, 0.5]) * np.pi},
        }
    
    for angle in angles:

        plt.style.use('classic')
        fig, axs = plt.subplots(nrows = 1, ncols = 2)
#        fig = plt.figure(figsize = (8.0, 3.25))
#        # list of ax : [throughput, pkt_loss]
#        axs = []
#        axs.append(fig.add_subplot(1, 2, 1))
#        axs.append(fig.add_subplot(1, 2, 2))
        
        for ax in axs.flat:
            ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
            ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)
        
        for c, client in enumerate(['tp-02', 'tp-03']):
            
            df = bf_data[bf_data['wlan src addr'] == clients[client]['mac-addr']]
            df = df.sort_values(by = ['epoch time', 'subcarrier']).reset_index(drop = True)
            
            # make subcarrier numbers as columns, transforming the df dataframe 
            # into a <time> x <subcarrier> matrix
            _df = df[['epoch time', 'subcarrier', angle]].pivot(index = 'epoch time', columns = 'subcarrier', values = angle).reset_index()
            _df = _df.dropna(subset = [-122])
            
            # subcarrier columns
            sc_cols = list(_df.columns)
            sc_cols.remove('epoch time')
            
            angle_prefix = angle_type_defs[angle.split('-')[0]]['prefix']
            axs.flat[c].set_title('%s%s%s angle vs. time (%s)' % (angle_prefix, angle.split('-')[1], angle.split('-')[2], clients[client]['label']), fontsize = 10)
            
            im = axs.flat[c].pcolormesh(_df[sc_cols].transpose())

            axs.flat[c].set_xlabel('time (sec)', fontsize = 10)
            if not (c % 2):
                axs.flat[c].set_ylabel('subcarrier idx', fontsize = 10)

            axs.flat[c].set_xlim([0, len(_df)])
            axs.flat[c].set_ylim([0, len(_df.columns) - 1])

            # FIXME: xticks : time axis not linear. confusing.            
            xt = fix_ticks(_df)
            axs.flat[c].set_xticks(xt.index)
            axs.flat[c].set_xticklabels(xt['time'].astype(int), fontsize = 10, rotation = 45)
            
            # FIXME : hardcoded yticks?
            x = int((len(_df.columns) - 1) / 4)
            y = int((len(_df.columns) - 1) / 2) - 1
            z = int((len(_df.columns) - 1) * (3 / 4)) - 1
            axs.flat[c].set_yticks([0, x, y, z, (len(_df.columns) - 1) - 1])

            print("x : %s, y : %s, z : %s" % (x, y, z))

            labels = [
                _df.columns[1],
                _df.columns[x + 1],
                _df.columns[y + 1],
                _df.columns[z + 1],                
                _df.columns[len(_df.columns) - 1]]
            
            axs.flat[c].set_yticklabels(labels, fontsize = 10)

        fig.colorbar(im, ax = axs.ravel().tolist())
#        fig.tight_layout()
        plt.savefig(os.path.join(test_dir, ("bf-angles-heatmap-%s-%s.pdf" % (test_nr, angle))), bbox_inches = 'tight', format = 'pdf')
    
if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input-dir", 
         help = """dir w/ MIMO data""")

    parser.add_argument(
        "--graph-dir", 
         help = """dir to save graphs""")

    args = parser.parse_args()
    
    if not args.input_dir:
        sys.stderr.write("""%s: [ERROR] must provide a dir w/ input files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.graph_dir:
        sys.stderr.write("""%s: [ERROR] must provide a graph dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # read test info
    test_info = pd.read_csv(os.path.join(args.input_dir, ('tests.csv')))

    # make sure filtered dir exists
    filtered_dir = os.path.join(args.input_dir, ('filtered'))
    if not os.path.exists(filtered_dir):
        os.makedirs(filtered_dir)
    
    # parse iperf3 files (if necessary)
    if not os.path.exists(os.path.join(filtered_dir, ('iperf3'))):
        iperf3_dir = os.path.join(filtered_dir, ('iperf3'))
        os.makedirs(iperf3_dir)        
        parse_iperf3(args.input_dir, iperf3_dir)

    # parse bf json files (if necessary)
    if not os.path.exists(os.path.join(filtered_dir, ('beamforming/csv'))):
        csv_dir = os.path.join(filtered_dir, ('beamforming/csv'))
        os.makedirs(csv_dir)
        parse_pcaps_json(args.input_dir, csv_dir)

    # scatter plots w/ nr. of xU-MIMO feedback messages
#    plot_mimo_feedback_msg(args.input_dir, args.graph_dir)
    
    # mu- vs. su-mimo performance
#    plot_mimo_performance([1, 2], args.input_dir, args.graph_dir)
#    plot_mimo_performance([6, 7], args.input_dir, args.graph_dir)    
    
    # test run details
#    plot_mimo_frames(1, args.input_dir, args.graph_dir)
#    plot_mimo_frames(2, args.input_dir, args.graph_dir)
#
#    plot_mimo_frames(6, args.input_dir, args.graph_dir)
#    plot_mimo_frames(7, args.input_dir, args.graph_dir)last

#    plot_mimo_frames(10, args.input_dir, args.graph_dir)
#    plot_mimo_frames(11, args.input_dir, args.graph_dir)
    
#    extract_vht_compressed_bf_report(args.input_dir)
#    extract_vht_mu_exclusive_bf_report(args.input_dir)

#    for i in range(1, 12):
#        plot_vht_compressed_bf_report(i, args.input_dir, args.graph_dir)
#    plot_subcarrier_angles(2, args.input_dir, args.graph_dir)
        
#    get_mimo_overhead_report(args.input_dir, args.graph_dir)
    plot_mimo_overhead(args.input_dir, args.graph_dir)
