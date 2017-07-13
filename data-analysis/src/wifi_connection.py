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

    data = defaultdict()
    variables = ['delay', 'rtt']

    for var in variables:
        data[var] = OrderedDict()

    for file_name in sorted(glob.glob(os.path.join(data_dir, '*.csv'))):

        # isolate the file label to then extract location of auth server, 
        # location of recording and measurement case
        file_label = file_name.split(".")[0].split("/")[-1]
        auth_server_location = file_label.split("-")[2]
        case = int(file_label.split("-")[4])

        for var in variables:
            if auth_server_location not in data[var]:
                data[var][auth_server_location] = OrderedDict()
            if case not in data[var][auth_server_location]:
                data[var][auth_server_location][case] = OrderedDict()

        # read the .csv file
        conn_data = pd.read_csv(file_name)
        # conn_data = conn_data.convert_objects(convert_numeric = True)

        # extract delays conn. phases into dict:
        #   1) legacy authentication
        #   2) association
        #   3) 802.x authentication

        # 1) legacy authentication
        for var in variables:
            if 'legacy auth' not in data[var][auth_server_location][case]:
                data[var][auth_server_location][case]['legacy auth'] = []

        # find occurrences of frame w/ 'Authentication
        legacy_auth_data = conn_data[conn_data["Info"].str.contains("Authentication,") == True]
        legacy_auth_delay = 0.0
        legacy_auth_rtt = 0

        if (not legacy_auth_data.empty):
            # find occurrences of frame w/ 'Authentication,' in Info field, subtract 
            # first timestamp to last timestamp
            legacy_auth_delay = float(legacy_auth_data.iloc[-1]['Time'] - legacy_auth_data.iloc[0]['Time'])
            # for rtts, sum messages sent to / from the mac_addr of client, then divide by 2
            legacy_auth_rtt = int((
                len(legacy_auth_data.loc[legacy_auth_data['Source'] == mac_addr]) 
                    + len(legacy_auth_data.loc[legacy_auth_data['Destination'] == mac_addr])) / 2)

        data['delay'][auth_server_location][case]['legacy auth'].append(legacy_auth_delay)
        data['rtt'][auth_server_location][case]['legacy auth'].append(legacy_auth_rtt)

        # 2) association
        for var in variables:
            if 'association' not in data[var][auth_server_location][case]:
                data[var][auth_server_location][case]['association'] = []

        association_req = conn_data[conn_data['Info'].str.contains("Association Request") == True]
        association_res = conn_data[conn_data['Info'].str.contains("Association Response") == True]

        association_delay = 0.0
        association_rtt = 0

        if (not association_req.empty) and (not association_res.empty):
            association_delay = float(association_res.iloc[-1]['Time'] - legacy_auth_data.iloc[0]['Time'])
            _df = conn_data[conn_data['Info'].str.contains("Association ") == True]
            association_rtt = int((len(_df.loc[_df['Source'] == mac_addr]) + len(_df.loc[_df['Destination'] == mac_addr])) / 2)

        data['delay'][auth_server_location][case]['association'].append(association_delay)
        data['rtt'][auth_server_location][case]['association'].append(association_rtt)

        # 3) 802.1x authentication
        xauth_phases = {0 : 'id chllng', 1 : 'PEAP negot', 2 : 'TLSv1', 3 : 'key (EAPOL)'}
        if xauth_phases.values()[0] not in data[var][auth_server_location][case]:

            for var in variables:
                for xauth_phase in xauth_phases.values():
                    data[var][auth_server_location][case][xauth_phase] = []

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

            eap_rtt = int((len(eap_seq.loc[eap_seq['Source'] == mac_addr]) + len(eap_seq.loc[eap_seq['Destination'] == mac_addr])) / 2)

            # 802.1x.0 : identity req and res
            identity_req = eap_seq[eap_seq['Info'].str.contains("Request, Identity") == True]
            identity_res = eap_seq[eap_seq['Info'].str.contains("Response, Identity") == True]
            # update respective 802.1x auth delay on list of delays
            xauth_delay[0] = float(identity_res.iloc[-1]['Time'] - identity_req.iloc[0]['Time'])

            _df = eap_seq[eap_seq['Info'].str.contains(", Identity") == True]
            xauth_rtt[0] = int((len(_df.loc[_df['Source'] == mac_addr]) + len(_df.loc[_df['Destination'] == mac_addr])) / 2)

            # save the packet nr of the last EAP identity exchange packet
            identity_res_nr = int(identity_res.iloc[-1]['No.'])

            # 802.1x.1 : peap method negotiation
            peap_method_req = eap_seq.loc[eap_seq['No.'] > identity_res_nr]
            peap_method_res = eap_seq.loc[eap_seq['No.'] < tls_seq.iloc[0]['No.']]
            xauth_delay[1] = float(peap_method_res.iloc[-1]['Time'] - peap_method_req.iloc[0]['Time'])

            _df = eap_seq.loc[(eap_seq['No.'] > identity_res_nr) & (eap_seq['No.'] < tls_seq.iloc[0]['No.'])]
            xauth_rtt[1] = int((len(_df.loc[_df['Source'] == mac_addr]) + len(_df.loc[_df['Destination'] == mac_addr])) / 2)

            # 802.1x.2 : tlsv1 phase (eap-peap)
            xauth_delay[2] = float(eap_seq.iloc[-1]['Time'] - tls_seq.iloc[0]['Time'])
            tls_rtt = int((len(tls_seq.loc[tls_seq['Source'] == mac_addr]) + len(tls_seq.loc[tls_seq['Destination'] == mac_addr])) / 2)
            xauth_rtt[2] = tls_rtt

            # 802.1x.3 : key exchange in-between client and AP (EAPOL)
            xauth_delay[3] = float(eapol_seq.iloc[-1]['Time'] - eap_seq.iloc[-1]['Time'])

        else:
            xauth_delay[3] = float(eapol_seq.iloc[-1]['Time'] - eapol_seq.iloc[0]['Time'])

        eapol_rtt = int((len(eapol_seq.loc[eapol_seq['Source'] == mac_addr]) + len(eapol_seq.loc[eapol_seq['Destination'] == mac_addr])) / 2)
        xauth_rtt[3] = eapol_rtt

        for i, xdel in enumerate(xauth_delay):
            data['delay'][auth_server_location][case][xauth_phases[i]].append(xdel)

        for i, xrtt in enumerate(xauth_rtt):
            data['rtt'][auth_server_location][case][xauth_phases[i]].append(xrtt)

    return data

def plot(data_dir, out_dir):

    data = analyze_connections(data_dir)
    # print(data['delay'])
    # print(data['rtt'])

    df = defaultdict()
    columns = ['legacy auth', 'association', 'id chllng', 'PEAP negot', 'TLSv1', 'key (EAPOL)']
    df['delay'] = pd.DataFrame(columns = columns)
    df['rtt'] = pd.DataFrame(columns = columns)

    for var in data:
        for auth_server_location in data[var]:
            for case in data[var][auth_server_location]:
                # calculate the mean for each key
                for key in data[var][auth_server_location][case]:
                    data[var][auth_server_location][case][key] = np.median(data[var][auth_server_location][case][key])
                # add mean to df
                df[var].loc[str(auth_server_location) + "." + str(case)] = data[var][auth_server_location][case].values()

    # print(df['delay'])
    # print(df['rtt'])

    # plot session ap stats histograms (per mac addr.)
    fig_1 = plt.figure(figsize = (12, 10))

    # get a suitable color map for multiple bars
    color_map = plt.get_cmap('Blues')
    colors = [color_map(i) for i in np.linspace(0, 1, len(df['delay'].columns.values))]
    # hatches for filling bars. tip: using '///' instead of '//' makes hashes more dense
    hatches = ['ooo', '///', 'xxx', '\\\\\\', '...', '---', '***', '0']

    # auth. server locations
    auth_server_locations = ['cmu', 'feup']
    # variables to plot
    variables = ['delay', 'rtt']
    # connection cases, i.e. the procedure used to collect measurements 
    cases = ['1st cnnct', '2nd cnnct\n(forget + cnnct)', 'disc. \n+ cnnct']

    # titles for each variable graph
    graph_titles = {
        'delay' : 'wifi connection setup time \n(', 
        'rtt' : 'rtts per cnnct phase \n('
        }
    # axis labels for each variable
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
            ax1.set_title(graph_titles[var] +  ('auth. server @%s)' % (loc.upper())))

            ax1.xaxis.grid(False)
            ax1.yaxis.grid(True)

            # positions of left boundaries of bars
            bar_left = [(i + 1) for i in range(len(_df['legacy auth']))]

            prev_c = ""
            for i, c in enumerate(list(_df.columns.values)):

                if prev_c == "":
                    ax1.bar(bar_left, _df[c], width = bar_width, label = c, alpha = 0.5, color = colors[i])
                else:
                    ax1.bar(bar_left, _df[c], width = bar_width, bottom = bottom[prev_c], label = c, alpha = 0.5, color = colors[i], hatch = hatches[i - 1])

                prev_c = c

            ax1.legend(fontsize = 12, ncol = 1, loc = 'upper right')

            # set xtick positions for each index
            ax1.set_xticks([(i + (bar_width / 2)) for i in bar_left])
            # # set xtick labels according to the nr. in data frame indexes
            # xticklabels = [cases[int(s.split(".")[-1]) - 1] for s in _df.index.values]
            ax1.set_xticklabels(cases)

            ax1.set_xlabel("use case")
            ax1.set_ylabel(yaxis_label[var])

            ax1.set_xlim(bar_left[0] - (1.0 - bar_width), bar_left[-1] + 1)

    fig_1.tight_layout()
    fig_1.subplots_adjust(top = 0.95)

    plt.savefig(os.path.join(out_dir, "wifi-connections.pdf"), bbox_inches = 'tight', format = 'pdf')
