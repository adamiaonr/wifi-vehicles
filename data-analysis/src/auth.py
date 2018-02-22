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

matplotlib.rcParams.update({'font.size': 16})

def plot_netlist(output_dir):

    # read netlist file
    netlist = pd.read_hdf(os.path.join(output_dir, "netlist.h5"), 'networks')
    # remove lines w/ auth = 0
    netlist = netlist[netlist['auth'] > 0]
    # FIXME : other filtering needs to be done here

    # collect % of auth per category
    auth_types = OrderedDict([('open', 0.0), ('captive', 0.0), ('wep', 0.0), ('wpa/wpa2', 0.0), ('802.1x', 0.0)])
    # calc nr of captive portal networks
    for essid in ['FON_ZON_FREE_INTERNET', 'MEO-WiFi', 'PT-WIFI']:
        auth_types['captive'] += netlist[(netlist['essid'] == essid) & (netlist['auth'] == 1)]['encode'].count()

    # other types
    auth_types['open'] = netlist[netlist['auth'] == 1]['essid'].count() - auth_types['captive']
    auth_types['wep'] = netlist[netlist['auth'] == 2]['essid'].count()
    auth_types['wpa/wpa2'] = netlist[(netlist['auth'] > 2) & (netlist['auth'] < 5)]['essid'].count()
    auth_types['802.1x'] = netlist[netlist['auth'] == 5]['essid'].count()

    auth_total = 0.0
    for auth_type in auth_types:
        auth_total += auth_types[auth_type]

    table = PrettyTable(['auth-type', 'abs', 'perc. (%)'])
    for i, auth_type in enumerate(auth_types):
        table.add_row([
            ('%d:%s' % (i + 1, auth_type)),
            ('%.2f' % (auth_types[auth_type])), 
            ('%.2f' % (float(auth_types[auth_type]) / auth_total * 100.0))])

    print(table)

    # plot bar chart
    # plt.style.use('seaborn-white')
    fig = plt.figure(figsize = (5, 4))
    ax = fig.add_subplot(111)

    ax.xaxis.grid(True, ls = 'dotted', lw = 0.75)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.75)

    labels = {'open' : 'Open', 'captive' : 'Capt. portal', 'wep' : 'WEP', 'wpa/wpa2' : 'WPA/WPA2', '802.1x' : 'WPA Enter.'}
    for i, auth_type in enumerate(auth_types):
        # print("%s : %d" % (auth_type, auth_types[auth_type]))
        plt.bar(i, ((float(auth_types[auth_type]) / auth_total) * 100.0), alpha = 0.55, width = 0.75, label = labels[auth_type], color = 'blue')

    ax.set_xlabel("Authentication type")
    ax.set_ylabel("% of APs")
    ax.set_xticks([0, 1, 2, 3, 4])
    ax.set_xticklabels(['Open', 'Capt.\nportal', 'WEP', 'WPA/\nWPA2', '802.1x'])

    ax.set_ylim(0.0, 100.0)

    fig.tight_layout()
    fig.subplots_adjust(top = 0.95)
    plt.savefig(os.path.join(output_dir, "graphs/auth.pdf"), bbox_inches = 'tight', format = 'pdf')

def build_netlist(input_file, output_dir):

    # netlist file, kept in disk
    netlist = pd.HDFStore(os.path.join(output_dir, "netlist.h5"))
    # read .csv file in chunks
    chunksize = 10 ** 5
    for chunk in pd.read_csv(input_file, chunksize = chunksize):

        # a unique net is defined as a {mac addr, essid, auth} tuple 
        nets = chunk[['encode', 'essid', 'auth']].drop_duplicates()
        # save nets on netlist.h5 file
        netlist.append(
            'networks',
            nets,
            data_columns = ['mac', 'ssid', 'auth'],
            format = 'table',
            min_itemsize = {'values' : 64})

    netlist.close()
    nets = pd.read_hdf(os.path.join(output_dir, "netlist.h5"), 'networks')
    nets.drop_duplicates().to_hdf(os.path.join(output_dir, "netlist.h5"), 'networks', append = False)

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--data-file", 
         help = """.csv file w/ session data""")
    parser.add_argument(
        "--output-dir", 
         help = """output data dir""")

    args = parser.parse_args()

    if not args.data_file:
        sys.stderr.write("""%s: [ERROR] please supply a .csv file w/ input data\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        args.output_dir = "../data/output"

    # build list of different networks 
    # build_netlist(args.data_file, args.output_dir)
    plot_netlist(args.output_dir)

    sys.exit(0)