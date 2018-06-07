import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import os
import csv
import json
import argparse
import subprocess
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

def test(time, ip_server, proto = 'udp', bitrate = '54M'):
    # iperf3 -t <time> -c <ip_server> -u (or nothing) -b <bitrate>M
    cmd = ["iperf3", "-V", "-J", "-t", str(time), "-c", str(ip_server), ("-u" if proto == 'udp' else ''), "-b", str(bitrate) + 'M']
    output = subprocess.check_output(cmd, stdin = None, stderr = None, shell = False, universal_newlines = False)
    return output

def plot(filename):
    results = pd.read_csv(filename)
    results['loss'] = (results['lost'] / results['total']) * 100.0
    results['trgt-bw'] = results['trgt-bw'] / 1000000.0
    results['res-bw'] = results['res-bw'] / 1000000.0

    # collect data to plot in a dict
    xx = results['trgt-bw'].unique()
    yy1 = results.groupby(['trgt-bw'])['res-bw'].apply(list).reset_index()
    yy1b = results.groupby(['trgt-bw'])['res-bw'].agg('median').reset_index()
    yy2 = results.groupby(['trgt-bw'])['loss'].agg('median').reset_index()
    yy3 = results.groupby(['trgt-bw'])['cpu-sndr'].agg('median').reset_index()
    yy4 = results.groupby(['trgt-bw'])['cpu-rcvr'].agg('median').reset_index()
    print(yy1)
    print(yy2)
    print(yy3)
    print(yy4)

    plt.style.use('classic')
    fig = plt.figure(figsize=(5, 3.75))

    ax1 = fig.add_subplot(1, 1, 1)
    ax1.xaxis.grid(True)
    ax1.yaxis.grid(True)

    ax2 = ax1.twinx()
    ax2.yaxis.grid(True, ls = 'dotted', lw = 0.50)
    ax1.set_zorder(ax2.get_zorder() + 1)
    ax1.patch.set_visible(False)

    ax1.set_title("channel : 36 (5.18 GHz),\nbw : 40 MHz, proto : UDP", fontsize = 11)
    # scatter plot w/ measured bw
    for tb in yy1['trgt-bw']:
        y = yy1.loc[yy1['trgt-bw'] == tb]['res-bw'].values[0]
        ax1.scatter([tb] * len(y), y, color = 'red', marker = 'o')

    # line plot crossing medians of measured bw
    ax1.plot(
        xx,
        yy1b['res-bw'].values,
        linewidth = 1.0, color = 'red', linestyle = '-', label = 'meas. bitrate')

    # bar chart w/ loss rate, cpu % (rcvr side)
    colors = ['black', 'lightgray', '#708090']
    for tb in xx:
        ax2.bar(
            tb - 2.5 - (2.5 / 2.0),
            float(yy2.loc[yy2['trgt-bw'] == tb]['loss']),
            color = colors[0], linewidth = 0.25, width = 2.5, label = ('packet loss' if tb == xx[0] else ''))

        ax2.bar(
            tb - (2.5 / 2.0),
            float(yy3.loc[yy3['trgt-bw'] == tb]['cpu-sndr']),
            color = colors[1], linewidth = 0.25, width = 2.5, label = ('cpu util. (@sender)' if tb == xx[0] else ''))

        ax2.bar(
            tb + (2.5 / 2.0),
            float(yy4.loc[yy4['trgt-bw'] == tb]['cpu-rcvr']),
            color = colors[2], linewidth = 0.25, width = 2.5, label = ('cpu util. (@RPi)' if tb == xx[0] else ''))

    ax1.set_xlabel("iperf3 target bitrate (Mbps)")
    ax1.set_ylabel("iperf3 meas. bitrate (Mbps)")
    ax2.set_ylabel("packet loss / cpu util. (%)")

    ax2.legend(fontsize = 10, ncol = 1, loc = 'upper left', handletextpad = 0.2)
    ax1.legend(fontsize = 10, ncol = 1, loc = 'upper right', handletextpad = 0.2)

    ax1.set_xlim(xx[0] - 10, xx[-1] + 10)
    ax1.set_ylim(0, 150)
    ax2.set_ylim(0, 100)

    ax1.set_xticks(xx)
    ax1.set_yticks(np.arange(0, 150, 150 / 5))
    ax2.set_yticks(np.arange(0, 120, 100 / 5))

    plt.tight_layout()
    plt.savefig(filename.rstrip('.csv') + '.pdf', bbox_inches = 'tight', format = 'pdf')

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--bitrates", 
         help = """list of iperf3 bitrates (in Mbps) to try out, separated by ','. e.g.: '--bitrates 11,54,72'""")

    parser.add_argument(
        "--protocols", 
         help = """list of protocols (UDP or TCP), separated by ','. e.g.: '--protocols UDP,TCP'""")

    parser.add_argument(
        "--duration", 
         help = """duration of the test (in seconds). e.g.: '--duration 120'""")

    parser.add_argument(
        "--ip-server", 
         help = """ip addr of iperf3 server. e.g.: '--ip-server 10.10.10.111'""")

    parser.add_argument(
        "--rounds", 
         help = """number of rounds for each parameter combination. e.g.: '--rounds 5'""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save .csv files""")

    parser.add_argument(
        "--plot", 
         help = """plot results""",
         action = "store_true")

    args = parser.parse_args()

    if not args.bitrates:
        args.bitrates = "54"

    if not args.duration:
        args.duration = "5"

    if not args.rounds:
        args.rounds = "5"

    if not args.protocols:
        args.protocols = "udp"

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    results_file = os.path.join(args.output_dir, ("rpi-wifi.csv"))

    if args.plot:
        plot(results_file)
        sys.exit(0)

    if not args.ip_server:
        sys.stderr.write("""%s: [ERROR] please supply an iperf3 server ip\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    results = pd.DataFrame(columns = ['proto', 'duration', 'transfer', 'trgt-bw', 'res-bw', 'jitter', 'lost', 'total', 'cpu-sndr', 'cpu-rcvr'])
    for protocol in [p.lower() for p in args.protocols.split(',')]:
        for bitrate in [b for b in args.bitrates.split(',')]:
            for r in xrange(int(args.rounds)):

                output = test(int(args.duration), args.ip_server, protocol, bitrate)
                output = json.loads(output)

                if output['start']['test_start']['protocol'] == 'UDP':

                    results = results.append({
                        'proto'     : output['start']['test_start']['protocol'], 
                        'duration'  : output['end']['sum']['seconds'],
                        'transfer'  : output['end']['sum']['bytes'], 
                        'trgt-bw'   : float(bitrate) * 1000000.0, 
                        'res-bw'    : output['end']['sum']['bits_per_second'],
                        'jitter'    : output['end']['sum']['jitter_ms'],
                        'lost'      : output['end']['sum']['lost_packets'],
                        'total'     : output['end']['sum']['packets'],
                        'cpu-sndr'  : output['end']['cpu_utilization_percent']['host_total'],
                        'cpu-rcvr'  : output['end']['cpu_utilization_percent']['remote_total']}, ignore_index = True)

                else:

                    results = results.append({
                        'proto'     : output['start']['test_start']['protocol'], 
                        'duration'  : output['end']['sum_received']['seconds'],
                        'transfer'  : output['end']['sum_received']['bytes'], 
                        'trgt-bw'   : float(bitrate) * 1000000.0, 
                        'res-bw'    : output['end']['sum_received']['bits_per_second'],
                        'lost'      : output['end']['sum_sent']['retransmits'],
                        'cpu-sndr'  : output['end']['cpu_utilization_percent']['host_total'],
                        'cpu-rcvr'  : output['end']['cpu_utilization_percent']['remote_total']}, ignore_index = True)

                print(results)

    results.to_csv(results_file)
    sys.exit(0)
