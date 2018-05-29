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
# 
import urllib
import geopandas as gp
import geopandas_osm.osm
import shapely.geometry

import timeit

from random import randint
from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict
from scapy.all import *
from prettytable import PrettyTable

matplotlib.rcParams.update({'font.size': 16})

def packet_delivery_ratio(input_dir, output_dir):

    folders = ['macbook', 'eeepc']
    bands = { 'macbook' : ['2.4', '5.0'], 'eeepc' : ['2.4'] }

    # prepare the graph parameters
    bar_width = 0.10
    # use the classic plot style
    plt.style.use('classic')
    # fig
    fig = plt.figure(figsize=(5, 3.5))

    colors = {'2.4' : 'red', '5.0' : 'blue'}
    for _f, f in enumerate(folders):

        ax1 = fig.add_subplot(211 + _f)
        ax1.xaxis.grid(False)
        ax1.yaxis.grid(True)

        ax1.set_title(f, fontsize = 12)

        pos = 0.0
        xbf = defaultdict()
        for i in xrange(5):

            if not os.path.exists(os.path.join(input_dir, ("%s/pos%d/2.4/sent.tsv" % (f, i)))):
                continue

            for b in bands[f]:

                print(("%s/pos%d/%s/" % (f, i, b)))
                sent = pd.read_csv(os.path.join(input_dir, ("%s/pos%d/%s/sent.tsv" % (f, i, b))), sep = "\t", dtype = object)
                rcvd = pd.read_csv(os.path.join(input_dir, ("%s/pos%d/%s/rcvd.tsv" % (f, i, b))), sep = "\t", dtype = object)

                n = float(len(set(sent['timestamp'].values)))
                r = float(len(set(sent['timestamp'].values) - set(rcvd['timestamp'].values)))
                # print("positioning::packet_delivery_ratio() : [INFO] sent - rcvd : %s" % (set(sent['timestamp'].values) - set(rcvd['timestamp'].values)))
                # print("positioning::packet_delivery_ratio() : [INFO] rcvd - sent : %s" % (set(rcvd['timestamp'].values) - set(sent['timestamp'].values)))

                if i == 0:
                    label = b
                else:
                    label = ''

                ax1.bar(
                    pos, 
                    ((n - r) / n) * 100.0,
                    color = colors[b], linewidth = 0.5, width = bar_width, label = label)

                pos += bar_width

            if f == 'macbook':
                xbf[pos - bar_width] = (('pos%d' % (i)))
            else:
                print(i)
                xbf[pos - (bar_width / 2.0)] = (('pos%d' % (i)))

            pos += bar_width

        leg = []
        leg.append(ax1.legend(
            fontsize = 12, 
            ncol = 1, loc = 'upper right', title = 'freq. bands',
            handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5))
        for l in leg:
            plt.setp(l.get_title(), fontsize = 12)

        ax1.set_xlabel("locations")
        ax1.set_ylabel("PDR (%)")
        ax1.set_xticks(xbf.keys())
        ax1.set_xticklabels(xbf.values())

        ax1.set_xlim(0.0 - (bar_width / 2.0), pos + (bar_width * 4.0))

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, ("pdr.pdf")), bbox_inches = 'tight', format = 'pdf')

def rssi(input_dir, output_dir):

    folders = ['eeepc']
    bands = { 'eeepc' : ['2.4'] }

    # prepare the graph parameters
    bar_width = 0.10
    # use the classic plot style
    plt.style.use('classic')
    # fig frame
    fig = plt.figure(figsize=(5, 7))

    ax1 = fig.add_subplot(211)
    ax1.xaxis.grid(False)
    ax1.yaxis.grid(True)

    # extract .pcap data passed to .csv
    data = pd.DataFrame()
    for _f, f in enumerate(folders):
        for i in xrange(1):
            for b in bands[f]:

                _data = pd.read_csv(os.path.join(input_dir, ("%s/pos%d/%s/wifi.csv" % (f, i, b)))).convert_objects(convert_numeric = True)
                data = pd.concat([data, _data], ignore_index = True)

    data = data.loc[(data['Protocol'] == 802.11) & (data['Type'] == 'Data frame')]
    _data = data.groupby(['Signal strength (dBm)'])['Data rate'].apply(list).reset_index()
    __data = data.groupby(['Signal strength (dBm)', 'Data rate', 'Retry'])['No.'].agg('count').reset_index()
    print(__data)

    for index, row in _data.iterrows():

        qty = defaultdict(int)
        for v in row['Data rate']:
            qty[v] += 1

        for v in qty:
            ax1.scatter(int(row['Signal strength (dBm)']), float(v), qty[v])

    #     leg = []
    #     leg.append(ax1.legend(
    #         fontsize = 12, 
    #         ncol = 1, loc = 'upper right', title = 'freq. bands',
    #         handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5))
    #     for l in leg:
    #         plt.setp(l.get_title(), fontsize = 12)

    #     ax1.set_xlabel("locations")
    #     ax1.set_ylabel("PDR")
    #     ax1.set_xticks(xbf.keys())
    #     ax1.set_xticklabels(xbf.values())

    ax1 = fig.add_subplot(212)
    ax1.xaxis.grid(False)
    ax1.yaxis.grid(True)

    colors = ['red', 'green', 'blue', 'yellow', 'black', 'gray', 'cyan', 'magenta']
    markers = ['*', 'o']

    for index, row in __data.iterrows():

        qty = defaultdict()
        if row['Data rate'] not in qty:
            qty[row['Data rate']] = {'Frame is being retransmitted' : 0, 'Frame is not being retransmitted' : 0}
        qty[row['Data rate']][row['Retry']] += row['No.']

    for j, v in enumerate(qty):
        ax1.scatter(int(row['Signal strength (dBm)']) - 0.125, float(v), qty[v]['Frame is being retransmitted'], c = colors[j], marker = markers[1])
        ax1.scatter(int(row['Signal strength (dBm)']) + 0.125, float(v), qty[v]['Frame is not being retransmitted'], c = colors[j], marker = markers[0])

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, ("rssis.pdf")), bbox_inches = 'tight', format = 'pdf')

def print_reports(input_dir, output_dir):

    folders = ['eeepc', 'macbook']
    bands = { 'macbook' : ['2.4', '5.0'], 'eeepc' : ['2.4'] }
    colors = {'2.4' : 'red', '5.0' : 'blue'}
    reports = pd.DataFrame()

    # prepare the graph parameters
    bar_width = 0.10
    # use the classic plot style
    plt.style.use('classic')
    # fig
    fig = plt.figure(figsize=(5, 3.5))

    for _f, f in enumerate(folders):

        ax1 = fig.add_subplot(211 + _f)
        ax1.xaxis.grid(False)
        ax1.yaxis.grid(True)

        ax1.set_title(f, fontsize = 12)

        pos = 0.0
        xbf = defaultdict()

        for i in xrange(5):

            if not os.path.exists(os.path.join(input_dir, ("%s/pos%d/2.4/sent.tsv" % (f, i)))):
                continue

            for b in bands[f]:

                print(("%s/pos%d/%s/" % (f, i, b)))
                report = pd.read_csv(os.path.join(input_dir, ("%s/pos%d/%s/report.tsv" % (f, i, b))), sep = "\t", dtype = object)
                report['pos'] = i
                report['client'] = f
                report['band'] = b

                reports = pd.concat([reports, report], ignore_index = True)

                if i == 0:
                    label = b
                else:
                    label = ''

                ax1.bar(
                    pos, 
                    float(report['avg bitrate']),
                    color = colors[b], linewidth = 0.5, width = bar_width, label = label)

                pos += bar_width

            if f == 'macbook':
                xbf[pos - bar_width] = (('pos%d' % (i)))
            else:
                print(i)
                xbf[pos - (bar_width / 2.0)] = (('pos%d' % (i)))

            pos += bar_width

        leg = []
        leg.append(ax1.legend(
            fontsize = 12, 
            ncol = 1, loc = 'upper right', title = 'freq. bands',
            handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5))
        for l in leg:
            plt.setp(l.get_title(), fontsize = 12)

        ax1.set_xlabel("locations")
        ax1.set_ylabel("avg. throughput\n(bps)")
        ax1.set_xticks(xbf.keys())
        ax1.set_xticklabels(xbf.values())

        ax1.set_xlim(0.0 - (bar_width / 2.0), pos + (bar_width * 5.0))
        ax1.set_ylim(0.0, 4200.0)
        ax1.set_yticks(np.arange(0.0, 4200.0, 1000.0))

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, ("bw.pdf")), bbox_inches = 'tight', format = 'pdf')

    print(reports)

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--input-dir", 
         help = """dir w/ .tsv files""")
    parser.add_argument(
        "--output-dir", 
         help = """output data dir""")

    args = parser.parse_args()

    if not args.input_dir:
        sys.stderr.write("""%s: [ERROR] please supply a dir w/ .tsv files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        args.output_dir = "../data/output"

    packet_delivery_ratio(args.input_dir, args.output_dir)
    print_reports(args.input_dir, args.output_dir)
    rssi(args.input_dir, args.output_dir)

    sys.exit(0)