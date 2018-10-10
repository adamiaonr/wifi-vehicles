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

channel_yy = {1 : 3000.0, 6 : 3000.0, 11 : 3000.0}

def plot_cbt(cbt, frame_types, ax1, output_dir, channel = -1):

    ax1.xaxis.grid(False)
    ax1.yaxis.grid(True)
    ax2 = ax1.twinx()
    ax2.yaxis.grid(True, ls = 'dotted', lw = 0.50)
    ax1.set_zorder(ax2.get_zorder() + 1)
    ax1.patch.set_visible(False)

    # ax1.set_title("channel utilization (1 client)", fontsize = 10)

    ax1.plot(
        cbt['period'].values,
        cbt['utilization'].values,
        linewidth = 1.0, color = 'red', linestyle = '-', label = 'channel utilization')

    # print a stacked bar chart w/ nr. of frames, discriminated by type
    # get the unique wifi frame types
    types = ['Management frame', 'Control frame', 'Data frame']
    colors = ['lightgray', 'black', '#708090']
    # get the counts by type
    counts =  frame_types.groupby(['period.no', 'Type'])['no'].agg('sum').reset_index()

    # print the stacked bars
    y = []
    for i, p in enumerate(counts['period.no'].unique()):

        if i < p:
            y.append([0, 0, 0])
            continue
        else:
            y.append([])

        sel = counts[counts['period.no'] == p]
        prev = 0.0
        for c, t in enumerate(types):
            v = (sel[sel['Type'] == t]['no'].values[0] if sel[sel['Type'] == t]['no'].values else 0.0)
            y[p].append(v + prev)
            prev = v

    # stacked line chart for packet qtys.
    x = counts['period.no'].unique()
    y = np.array(y)

    ax2.fill_between(x, 0.0, y[:,0], facecolor = colors[0], label = types[0], linewidth = .25)
    ax2.fill_between(x, y[:,0], y[:,1], facecolor = colors[1], label = types[1], linewidth = .25)
    ax2.fill_between(x, y[:,1], y[:,2], facecolor = colors[2], label = types[2], linewidth = .25)

    leg = []
    leg.append(ax2.legend(fontsize = 10, ncol = 1, loc = 'upper right', handletextpad = 0.2))
    ax1.legend(fontsize = 10, ncol = 1, loc = 'upper left', handletextpad = 0.2)

    ax1.set_xlabel("time (seconds)")
    ax1.set_ylabel("channel utilization (%)")
    ax2.set_ylabel("# of frames")

    ax1.set_yscale("log", nonposy = 'clip')

    # adjust max for ax2
    max_ax2 = 0
    if channel in channel_yy:
        max_ax2 = channel_yy[channel]
    else:
        max_ax2 = np.amax(y[:,0] + y[:,1] + y[:,2])
        power = 1
        while ((max_ax2 / 10.0) > 1.0):
            power += 1
            max_ax2 = max_ax2 / 10.0
        max_ax2 = (10.0**power)

    # ax1.set_xticks(np.arange(0, cbt['period'].values[-1] + 1, 1))
    ax1.set_yticks([0.01, 0.1, 1.0, 10.0, 100.0])
    ax2.set_yticks(np.arange(0, max_ax2, (max_ax2) / 5))
    ax1.set_xlim(-1, cbt['period'].values[-1] + 1)
    ax1.set_ylim(0.01, 1000)
    ax2.set_ylim(0, max_ax2)

def calc_frame_duration(wlan_frames):
    # print("cbt::calc_frame_duration() : [INFO]  : phy type : %s, wlan type : %s, wlan subtype : %s, length : %s, data rate : %s" 
    #     % (phy_type, wlan_type, wlan_sub_type, frame_length, data_rate))
    duration = ((8.0 * (wlan_frames['Length'].values - wlan_frames['radiotap.length'].values)) / wlan_frames['Data rate'].values) + wlan_frames['wlan_radio.preamble']
    return duration

def calc_cbt(input_file):

    # dataframe to contain all cbt info for some channel
    cbt = pd.DataFrame(columns = ['period', 'cbt', 'utilization'])
    frame_types = pd.DataFrame()

    chunksize = 10 ** 5
    for chunk in pd.read_csv(input_file, chunksize = chunksize):

        # # calculate frame durations for the chunk
        # chunk['frame.duration'] = calc_frame_duration(chunk)

        # divide chunk in 1 sec periods:
        #   - calculate the end transmission times (epoch time + frame duration), in micro sec
        chunk['endtime'] = chunk['epoch time'].values + (chunk['wlan duration'].values / 1000000.0)
        #   - get period nr. from integer part of endtime
        chunk['period.no'] = chunk['epoch time'].values.astype(int)
        # print(chunk[['period.no', 'PHY type', 'Type', 'Type/Subtype', 'Length', 'Data rate', 'wlan_radio.duration']])

        # get count of type / subtypes per period
        counts = chunk.groupby(['period.no', 'PHY type', 'Type', 'Type/Subtype', 'Length', 'Data rate', 'wlan_radio.duration'])['no'].agg('count').reset_index()
        frame_types = pd.concat([frame_types, counts], ignore_index = True)
        print(counts[['period.no', 'Type', 'Type/Subtype', 'no']])

        # calc cbt per period
        for p in counts['period.no'].unique():
            # isolate stats for period p
            sel = counts[counts['period.no'] == p]
            # calculate cbt for period p
            _cbt = np.sum(sel['no'].values * sel['wlan_radio.duration'].values)
            # append result to final dataframe
            cbt = cbt.append({'period' : p, 'cbt' : _cbt, 'utilization' : ((_cbt / 1000000.0) * 100.0)}, ignore_index = True)

    return cbt, frame_types

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
        sys.stderr.write("""%s: [ERROR] please supply a dir w/ .csv files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    plt.style.use('classic')
    # cycle through all files
    pcap_files = []
    channels = [1, 6, 11, 36, 40, 44, 48, 99]
    for file_name in sorted(glob.glob(os.path.join(args.input_dir, '*.csv'))):

        if int(file_name.split('/')[-1].split('-')[2].rstrip('.csv')) not in channels:
            continue

        pcap_files.append(file_name)

    # figs:
    #   - fig 1 : detailed per channel
    #   - fig 2 : all channels
    n = len(pcap_files)
    fig1 = plt.figure(figsize=(2 * 7.25, n * 3.5))
    for i, pcfile in enumerate(pcap_files):
        
        # calc cbt values        
        cbt, frame_types = calc_cbt(pcfile)
        # plot
        ax1 = fig1.add_subplot(math.ceil(n / 2) + 1, 2, (i + 1))
        channel_nr = int(pcfile.split('/')[-1].split('-')[2].rstrip('.csv'))
        ax1.set_title(("channel %d" % (channel_nr if channel_nr != 99 else 48)), fontsize = 10)
        plot_cbt(cbt, frame_types, ax1, args.output_dir, channel_nr)

    plt.tight_layout()
    plt.savefig(os.path.join(args.output_dir, ("cbt.pdf")), bbox_inches = 'tight', format = 'pdf')

    # fig2 = plt.figure(figsize=(5, 3.5))

    sys.exit(0)