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

def analyze_connections(data_dir, mac_addr = '88:07:4b:b3:f9:7e'):

    del_data = OrderedDict()
    rtt_data = OrderedDict()

    for file_name in sorted(glob.glob(os.path.join(data_dir, '*.csv'))):

        # isolate file label 
        file_label = file_name.split(".")[0].split("/")[-1]
        # print("file : %s:" % (file_label))

        # extract location of auth server, location of recording and case
        auth_server_location = file_label.split("-")[2]
        case = int(file_label.split("-")[4])

        if auth_server_location not in del_data:
            del_data[auth_server_location] = OrderedDict()
            rtt_data[auth_server_location] = OrderedDict()

        if case not in del_data[auth_server_location]:
            del_data[auth_server_location][case] = OrderedDict()
            rtt_data[auth_server_location][case] = OrderedDict()

        # read the .csv file
        conn_data = pd.read_csv(file_name)
        # conn_data = conn_data.convert_objects(convert_numeric = True)

        # extract delays conn. phases into dict:
        #   - legacy authentication
        #   - association
        #   - 802.x authentication

        # legacy authentication
        if 'legacy_auth' not in del_data[auth_server_location][case]:
            del_data[auth_server_location][case]['legacy_auth'] = []
            rtt_data[auth_server_location][case]['legacy_auth'] = []

        # find 1st occurrence of frame w/ 'Authentication,' in Info field
        legacy_auth_data = conn_data[conn_data["Info"].str.contains("Authentication,") == True]
        # subtract first timestamp to last timestamp
        legacy_auth_delay = 0.0
        legacy_auth_rtt = 0
        if (not legacy_auth_data.empty):
            legacy_auth_delay = float(legacy_auth_data.iloc[-1]['Time'] - legacy_auth_data.iloc[0]['Time'])
            legacy_auth_rtt = ((
                len(legacy_auth_data.loc[legacy_auth_data['Source'] == mac_addr]) 
                    + len(legacy_auth_data.loc[legacy_auth_data['Destination'] == mac_addr])) / 2)

        del_data[auth_server_location][case]['legacy_auth'].append(legacy_auth_delay)
        rtt_data[auth_server_location][case]['legacy_auth'].append(legacy_auth_rtt)
        # print("\tlegacy_auth delay = %f" % (legacy_auth_delay))

        # association
        if 'association' not in del_data[auth_server_location][case]:
            del_data[auth_server_location][case]['association'] = []
            rtt_data[auth_server_location][case]['association'] = []

        association_req = conn_data[conn_data['Info'].str.contains("Association Request") == True]
        association_res = conn_data[conn_data['Info'].str.contains("Association Response") == True]

        association_delay = 0.0
        association_rtt = 0
        if (not association_req.empty) and (not association_res.empty):
            association_delay = float(association_res.iloc[-1]['Time'] - legacy_auth_data.iloc[0]['Time'])
            _df = conn_data[conn_data['Info'].str.contains("Association ") == True]
            association_rtt = ((len(_df.loc[_df['Source'] == mac_addr]) + len(_df.loc[_df['Destination'] == mac_addr])) / 2)

        del_data[auth_server_location][case]['association'].append(association_delay)
        rtt_data[auth_server_location][case]['association'].append(association_rtt)
        # print("\tassociation delay = %f" % (association_delay))

        # 802.1x authentication
        xauth_phases = {0 : 'id chlng.', 1 : 'PEAP neg.', 2 : 'TLSv1', 3 : 'key (EAPOL)'}
        if 'id chlng.' not in del_data[auth_server_location][case]:
            del_data[auth_server_location][case]['id chlng.'] = []
            del_data[auth_server_location][case]['PEAP neg.'] = []
            del_data[auth_server_location][case]['TLSv1'] = []
            del_data[auth_server_location][case]['key (EAPOL)'] = []

            rtt_data[auth_server_location][case]['id chlng.'] = []
            rtt_data[auth_server_location][case]['PEAP neg.'] = []
            rtt_data[auth_server_location][case]['TLSv1'] = []
            rtt_data[auth_server_location][case]['key (EAPOL)'] = []

        # isolate EAP, TLSv1 and EAPOL sequences (note that EAP and TLSv1 are NOT mutex) 
        eap_seq = conn_data.loc[conn_data['Protocol']   == 'EAP']
        tls_seq = conn_data.loc[conn_data['Protocol']   == 'TLSv1']
        eapol_seq = conn_data.loc[conn_data['Protocol'] == 'EAPOL']

        # list of 802.1x values
        #   0 : 802.1x identity req and res
        #   1 : 802.1x peap method negotiation
        #   2 : 802.1x tls duration
        #   3 : 802.1x key exchange (EAPOL)
        xauth_delay = [0.0, 0.0, 0.0, 0.0]
        xauth_rtt   = [0, 0, 0, 0]

        if not eap_seq.empty:

            eap_rtt = ((len(eap_seq.loc[eap_seq['Source'] == mac_addr]) + len(eap_seq.loc[eap_seq['Destination'] == mac_addr])) / 2)
            tls_rtt = ((len(tls_seq.loc[tls_seq['Source'] == mac_addr]) + len(tls_seq.loc[tls_seq['Destination'] == mac_addr])) / 2)

            # 802.1x.0 : identity req and res
            identity_req = eap_seq[eap_seq['Info'].str.contains("Request, Identity") == True]
            identity_res = eap_seq[eap_seq['Info'].str.contains("Response, Identity") == True]
            # update respective 802.1x auth delay on list of delays
            xauth_delay[0] = float(identity_res.iloc[-1]['Time'] - identity_req.iloc[0]['Time'])

            _df = eap_seq[eap_seq['Info'].str.contains(", Identity") == True]
            xauth_rtt[0] = ((len(_df.loc[_df['Source'] == mac_addr]) + len(_df.loc[_df['Destination'] == mac_addr])) / 2)

            # save the packet nr of the last EAP identity exchange packet
            identity_res_nr = int(identity_res.iloc[-1]['No.'])

            # 802.1x.1 : peap method negotiation
            peap_method_req = eap_seq.loc[eap_seq['No.'] > identity_res_nr]
            peap_method_res = eap_seq.loc[eap_seq['No.'] < tls_seq.iloc[0]['No.']]
            xauth_delay[1] = float(peap_method_res.iloc[-1]['Time'] - peap_method_req.iloc[0]['Time'])

            _df = eap_seq.loc[(eap_seq['No.'] > identity_res_nr) & (eap_seq['No.'] < tls_seq.iloc[0]['No.'])]
            xauth_rtt[1] = ((len(_df.loc[_df['Source'] == mac_addr]) + len(_df.loc[_df['Destination'] == mac_addr])) / 2)

            # 802.1x.2 : tlsv1 phase (eap-peap)
            xauth_delay[2] = float(eap_seq.iloc[-1]['Time'] - tls_seq.iloc[0]['Time'])
            xauth_rtt[2] = tls_rtt

            # 802.1x.3 : key exchange in-between client and AP (EAPOL)
            xauth_delay[3] = float(eapol_seq.iloc[-1]['Time'] - eap_seq.iloc[-1]['Time'])

        else:
            xauth_delay[3] = float(eapol_seq.iloc[-1]['Time'] - eapol_seq.iloc[0]['Time'])

        eapol_rtt = ((len(eapol_seq.loc[eapol_seq['Source'] == mac_addr]) + len(eapol_seq.loc[eapol_seq['Destination'] == mac_addr])) / 2)
        xauth_rtt[3] = eapol_rtt

        for i, xdel in enumerate(xauth_delay):
            del_data[auth_server_location][case][xauth_phases[i]].append(xdel)

        for i, xrtt in enumerate(xauth_rtt):
            rtt_data[auth_server_location][case][xauth_phases[i]].append(xrtt)

    return del_data, rtt_data

def plot(data_dir, out_dir):

    data = defaultdict()
    data['delay'], data['rtt'] = analyze_connections(data_dir)

    print(data['delay'])
    print(data['rtt'])

    df = defaultdict()
    df['delay'] = pd.DataFrame(columns = ['legacy_auth', 'association', 'id chlng.', 'PEAP neg.', 'TLSv1', 'key (EAPOL)'])
    df['rtt'] = pd.DataFrame(columns = ['legacy_auth', 'association', 'id chlng.', 'PEAP neg.', 'TLSv1', 'key (EAPOL)'])

    for var in data:
        for auth_server_location in data[var]:
            for case in data[var][auth_server_location]:

                # calculate the mean for each key
                for key in data[var][auth_server_location][case]:
                    data[var][auth_server_location][case][key] = np.median(data[var][auth_server_location][case][key])

                # add mean to df
                df[var].loc[str(auth_server_location) + "." + str(case)] = data[var][auth_server_location][case].values()

    print(df['delay'])
    print(df['rtt'])

    # plot session ap stats histograms (per mac addr.)
    fig_1 = plt.figure(figsize = (12, 10))

    # get a suitable color map for multiple bars
    # color_map = plt.get_cmap('rainbow')
    # colors = [color_map(i) for i in np.linspace(0, 1, len(df['delay'].columns.values))]
    colors = ['black', 'white', 'red', 'green', 'blue', 'yellow']

    # auth. server locations
    auth_server_locations = ['cmu', 'feup']
    variables = ['delay', 'rtt']
    cases = ['1st conn.', '2nd conn.\n(forget + conn.)', 'disc. + conn.']

    graph_titles = {
        'delay' : 'wifi connection setup time \n(eduroam +', 
        'rtt' : 'rtts per conn. phase \n(eduroam +'
        }

    yaxis_label = {
        'delay' : 'time (sec)', 
        'rtt' : '# of rtts'
    }

    bar_width = 0.65

    for k, var in enumerate(['delay', 'rtt']):
        for i, loc in enumerate(auth_server_locations):

            # only select data for auth server location
            _df = df[var][df[var].index.to_series().str.contains(loc)]
            bottom = _df.cumsum(axis = 1)

            ax1 = fig_1.add_subplot(221 + i + (k * 2))
            ax1.set_title(graph_titles[var] +  (' %s auth. server)' % (loc.upper())))

            ax1.xaxis.grid(False)
            ax1.yaxis.grid(True)

            # positions of left boundaries of bars
            bar_left = [(i + 1) for i in range(len(_df['legacy_auth']))]

            prev_c = ""
            for i, c in enumerate(list(_df.columns.values)):

                if prev_c == "":
                    ax1.bar(bar_left, _df[c], width = bar_width, label = c, alpha = 0.5, color = colors[i])
                else:
                    ax1.bar(bar_left, _df[c], width = bar_width, bottom = bottom[prev_c], label = c, alpha = 0.5, color = colors[i])

                prev_c = c

            ax1.legend(fontsize = 12, ncol = 1, loc = 'upper right')

            # xtick positions
            ax1.set_xticks([(i + (bar_width / 2)) for i in bar_left])
            # xtick labels
            print([int(s.split(".")[-1]) for s in _df.index.values])
            xticklabels = [cases[int(s.split(".")[-1]) - 1] for s in _df.index.values]
            ax1.set_xticklabels(xticklabels)

            ax1.set_xlabel("conn. use case")
            ax1.set_ylabel(yaxis_label[var])

            ax1.set_xlim(bar_left[0] - (1.0 - bar_width), bar_left[-1] + 1)

    fig_1.tight_layout()
    fig_1.subplots_adjust(top = 0.95)

    plt.savefig(os.path.join(out_dir, "wifi-connections.pdf"), bbox_inches = 'tight', format = 'pdf')
