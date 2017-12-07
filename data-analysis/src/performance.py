import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.pylab as pl
import os
import argparse
import sys
import glob
import math
import gmplot
import time
import datetime
import pytz

# for mysql db
import MySQLdb as mysql

from random import randint
from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict

# for ap location estimation
from shapely.geometry import Point
# custom imports
from plot_utils import *

reload(sys)
sys.setdefaultencoding('utf8')

# how much does the max differ from the previous best?
def calc_change(ts_data, stat, prev_ap, is_switch, diff, to_print = False):
    
    up = ('%s_bw_up' % (stat))
    down = ('%s_bw_down' % (stat))

    curr_bw = (np.amax(ts_data[down]), np.amax(ts_data[up]))
    prev_bw = [ts_data[ts_data['bssid'] == prev_ap[0]][down].values, ts_data[ts_data['bssid'] == prev_ap[1]][up].values]

    if to_print:
        print(prev_bw)
        print(curr_bw)

    if prev_bw[0] and is_switch[0]:
        diff[stat][down].append(((curr_bw[0] - prev_bw[0][0]) / prev_bw[0][0]) * 100.0)
    if prev_bw[1] and is_switch[1]:
        diff[stat][up].append(((curr_bw[1] - prev_bw[1][0]) / prev_bw[1][0]) * 100.0)

def count_switches(num_switches):
    n = 0
    for stat in num_switches:
        n += np.sum(num_switches[stat])
    return n

def best_ap(data, out_dir):

    bw_barwidth = .4
    fig = plt.figure(figsize = (10, 6))

    ax1 = fig.add_subplot(211)
    # ax1.xaxis.grid(True)
    ax1.yaxis.grid(True)
    ax2 = fig.add_subplot(212)
    # ax2.xaxis.grid(True)
    ax2.yaxis.grid(True)

    # drop NaN values in stats of interest and power
    df = data
    # df = df[(df.udp_bw_up.notnull()) & (df.udp_bw_down.notnull())]
    # df = df[(df.tcp_bw_up.notnull()) & (df.tcp_bw_down.notnull())]
    # df = df[df.rtt_avg.notnull()]

    num_switch = defaultdict()
    diff = defaultdict()

    subtract = []
    loc_names = df['loc_name'].unique()
    for i, loc_name in enumerate(loc_names):

        loc_data = df.loc[df['loc_name'] == loc_name]

        # if loc_name == 'lounjin':
        #     print("***\n%d loc_name = %s" % (i, loc_name))

        prev_udp = ('0','0')
        prev_tcp = ('0','0')
        prev_rtt = '0'

        num_switch[loc_name] = defaultdict()
        num_switch[loc_name]['udp'] = np.array([0.0, 0.0])
        num_switch[loc_name]['tcp'] = np.array([0.0, 0.0])
        num_switch[loc_name]['rtt'] = 0

        diff[loc_name] = defaultdict()
        diff[loc_name]['udp'] = defaultdict(list)
        diff[loc_name]['tcp'] = defaultdict(list)
        diff[loc_name]['rtt'] = defaultdict(list)

        tss = loc_data['unixtime'].unique()
        if len(tss) < 2:
            subtract.append(i)
            continue

        for j, ts in enumerate(tss):

            ts_data = loc_data.loc[loc_data['unixtime'] == ts]
            # if loc_name == 'lounjin':
            #     print(ts_data['bssid'].unique())
            #     print(ts_data['ssid'].unique())

            # if best ap changed vs. the last measurement, +1 switch
            _ts_data = ts_data[(ts_data.udp_bw_up.notnull()) & (ts_data.udp_bw_down.notnull())]
            if len(_ts_data['udp_bw_down']) and len(_ts_data['udp_bw_up']):
                curr_udp = (_ts_data.ix[_ts_data['udp_bw_down'].idxmax()]['bssid'], _ts_data.ix[_ts_data['udp_bw_up'].idxmax()]['bssid'])
                is_switch = np.array([float(int(curr_udp[0] != prev_udp[0]))  / float(len(tss)), float(int(curr_udp[1] != prev_udp[1]))  / float(len(tss))])
                num_switch[loc_name]['udp'] += is_switch
                # record change in throughput
                if j > 0:
                    calc_change(_ts_data, 'udp', prev_udp, is_switch, diff[loc_name])
                # update prev_ap
                prev_udp = curr_udp

            _ts_data = ts_data[(ts_data.tcp_bw_up.notnull()) & (ts_data.tcp_bw_down.notnull())]
            if len(_ts_data['tcp_bw_down']) and len(_ts_data['tcp_bw_up']):
                curr_tcp = (_ts_data.ix[_ts_data['tcp_bw_down'].idxmax()]['bssid'], _ts_data.ix[_ts_data['tcp_bw_up'].idxmax()]['bssid'])
                is_switch = np.array([float(int(curr_tcp[0] != prev_tcp[0]))  / float(len(tss)), float(int(curr_tcp[1] != prev_tcp[1])) / float(len(tss))])
                num_switch[loc_name]['tcp'] += is_switch
                if j > 0:
                    # if loc_name == 'lounjin':
                    #     calc_change(_ts_data, 'tcp', prev_tcp, is_switch, diff, to_print = True)
                    # else:
                    calc_change(_ts_data, 'tcp', prev_tcp, is_switch, diff[loc_name], to_print = False)

                # if loc_name == 'lounjin':
                #     print(prev_tcp)
                #     print(curr_tcp)
                #     print(diff['tcp'])
                #     print('---\n')

                prev_tcp = curr_tcp

            _ts_data = ts_data[ts_data.rtt_avg.notnull()]
            if len(_ts_data['rtt_avg']):
                curr_rtt = _ts_data.ix[_ts_data['rtt_avg'].idxmax()]['bssid']
                is_switch = float(int(curr_rtt != prev_rtt)) / float(len(tss))
                num_switch[loc_name]['rtt'] += is_switch

                if j > 0:
                    curr = np.amin(_ts_data['rtt_avg'])
                    prev = _ts_data[_ts_data['bssid'] == prev_rtt]['rtt_avg'].values
                    if prev and is_switch:
                        diff[loc_name]['rtt']['rtt_avg'].append((-(curr - prev[0]) / prev[0]) * 100.0)

                prev_rtt = curr_rtt

        if count_switches(num_switch[loc_name]) < 1:
            subtract.append(i)
            continue

        ax1.bar(
            ((i - len(subtract)) * 3) - (bw_barwidth * 3.0), float(num_switch[loc_name]['udp'][0]), 
            alpha = .50, 
            width = bw_barwidth, 
            label = 'udp bw down',
            color = 'palegreen')

        ax1.bar(
            ((i - len(subtract)) * 3) - (bw_barwidth * 2.0), float(num_switch[loc_name]['udp'][1]), 
            alpha = .70, 
            width = bw_barwidth, 
            label = 'udp bw up',
            color = 'green')

        ax1.bar(
            ((i - len(subtract)) * 3) - (bw_barwidth * .5), float(num_switch[loc_name]['tcp'][0]), 
            alpha = .50, 
            width = bw_barwidth, 
            label = 'tcp bw down',
            color = 'skyblue')

        ax1.bar(
            ((i - len(subtract)) * 3) + (bw_barwidth * .5), float(num_switch[loc_name]['tcp'][1]), 
            alpha = .50, 
            width = bw_barwidth, 
            label = 'tcp bw up',
            color = 'blue')

        ax1.bar(
            ((i - len(subtract)) * 3) + (bw_barwidth * 2.0), float(num_switch[loc_name]['rtt']), 
            alpha = .50, 
            width = bw_barwidth, 
            label = 'rtt',
            color = 'gold')

        # variation vs. previous ap

        ax2.bar(
            ((i - len(subtract)) * 3) - (bw_barwidth * 3.0), float(np.mean(diff[loc_name]['udp']['udp_bw_down'])), 
            alpha = .50, 
            width = bw_barwidth,
            label = 'udp bw down',
            color = 'palegreen')

        ax2.bar(
            ((i - len(subtract)) * 3) - (bw_barwidth * 2.0), float(np.mean(diff[loc_name]['udp']['udp_bw_up'])), 
            alpha = .70, 
            width = bw_barwidth,
            label = 'udp bw up',
            color = 'green')

        ax2.bar(
            ((i - len(subtract)) * 3) - (bw_barwidth * .5), float(np.mean(diff[loc_name]['tcp']['tcp_bw_down'])), 
            alpha = .50, 
            width = bw_barwidth,
            label = 'tcp bw down',
            color = 'skyblue')

        ax2.bar(
            ((i - len(subtract)) * 3) + (bw_barwidth * .5), float(np.mean(diff[loc_name]['tcp']['tcp_bw_up'])), 
            alpha = .50, 
            width = bw_barwidth,
            label = 'tcp bw up',
            color = 'blue')

        ax2.bar(
            ((i - len(subtract)) * 3) + (bw_barwidth * 2.0), float(np.mean(diff[loc_name]['rtt']['rtt_avg'])), 
            alpha = .50, 
            width = bw_barwidth,
            label = 'rtt',
            color = 'gold')

        if i < 1:
            ax1.legend(fontsize = 12, ncol = 7, loc = 'upper center')
            ax2.legend(fontsize = 12, ncol = 7, loc = 'upper center')

    ax1.set_title("""best ap changes between meas., per location""")
    ax2.set_title("""mean improv. vs. previous best ap (%)""")

    ax1.set_xlabel('location')
    ax1.set_ylabel('frac. of meas.')
    ax2.set_xlabel('location')
    ax2.set_ylabel('improv. (%)')

    ax1.set_xticks(np.arange(0, (3.0 * (len(loc_names) - len(subtract))), 3))
    ax2.set_xticks(np.arange(0, (3.0 * (len(loc_names) - len(subtract))), 3))
    ax1.set_xticklabels(np.arange(0, len(loc_names) + 1, 1))
    ax2.set_xticklabels(np.arange(0, len(loc_names) + 1, 1))

    # ax1.set_xlim(-1, ts_days.values()[-1][0] + ts_days.values()[-1][1])
    ax1.set_xlim(-1.75, (3.0 * (len(loc_names) - len(subtract))) - 1.25)
    ax2.set_xlim(-1.75, (3.0 * (len(loc_names) - len(subtract))) - 1.25)

    ax1.set_ylim(0.0, 1.30)
    ax1.set_yticks(np.arange(0.0, 1.2, 0.2))
    ax2.set_yscale('log', nonposx='clip')
    ax2.set_ylim(1, 1000000.0)

    fig.tight_layout()
    fig.subplots_adjust(top = 0.95)
    fig.subplots_adjust(hspace = 0.45)

    plt.savefig(os.path.join(out_dir, "ap-switches.pdf"), bbox_inches = 'tight', format = 'pdf')
    plt.close('all')

    return num_switch, diff

def plot_avg_switches(out_dir, num_switch, diff):

    bw_barwidth = .5
    fig = plt.figure(figsize = (5, 6))

    ax1 = fig.add_subplot(111)
    # ax1.xaxis.grid(True)
    ax1.yaxis.grid(True)

    # ax2 = fig.add_subplot(212)
    # # ax2.xaxis.grid(True)
    # ax2.yaxis.grid(True)    

    sw = defaultdict()
    for loc_name in num_switch:
        for stat in num_switch[loc_name]:

            if stat not in sw:
                sw[stat] = defaultdict(list)

            if stat in ['udp', 'tcp']:
                sw[stat][('%s_bw_down' % (stat))].append(num_switch[loc_name][stat][0])
                sw[stat][('%s_bw_up' % (stat))].append(num_switch[loc_name][stat][1])
            else:
                sw[stat]['rtt'].append(num_switch[loc_name][stat])

    i = 0
    ax1.bar(
        ((i) * 3) - (bw_barwidth * 3.0), float(np.mean(sw['udp']['udp_bw_down'])), 
        alpha = .50, 
        width = bw_barwidth, 
        label = 'udp bw down',
        color = 'palegreen')

    ax1.bar(
        ((i) * 3) - (bw_barwidth * 2.0), float(np.mean(sw['udp']['udp_bw_up'])), 
        alpha = .70, 
        width = bw_barwidth, 
        label = 'udp bw up',
        color = 'green')

    ax1.bar(
        ((i) * 3) - (bw_barwidth * .5), float(np.mean(sw['tcp']['tcp_bw_down'])), 
        alpha = .50, 
        width = bw_barwidth, 
        label = 'tcp bw down',
        color = 'skyblue')

    ax1.bar(
        ((i) * 3) + (bw_barwidth * .5), float(np.mean(sw['tcp']['tcp_bw_up'])), 
        alpha = .50, 
        width = bw_barwidth, 
        label = 'tcp bw up',
        color = 'blue')

    ax1.bar(
        ((i) * 3) + (bw_barwidth * 2.0), float(np.mean(sw['rtt']['rtt'])), 
        alpha = .50, 
        width = bw_barwidth, 
        label = 'rtt',
        color = 'gold')

    ax1.set_title("""mean # of times the best ap changes, per location""")
    ax1.set_ylabel('frac. of meas.')

    ax1.set_ylim(0.0, 0.5)

    fig.tight_layout()
    fig.subplots_adjust(top = 0.95)

    plt.savefig(os.path.join(out_dir, "avg-ap-switches.pdf"), bbox_inches = 'tight', format = 'pdf')
    plt.close('all')


def extract(in_dir, out_dir):

    # open 'wifi' database
    db = mysql.connect(host = "localhost", user = "root", passwd = "xpto12x1", db = "wifi" )
    # read the ap table into a pandas dataframe for easier handling
    df = pd.read_sql('SELECT * FROM ap INNER JOIN trial ON ap.trial_id = trial.id WHERE associate_success = 1 ORDER BY unixtime ASC', 
        con = db)

    return df

def profile(data, out_dir):

    # drop NaN values at tcp_bw and power
    df = data
    df = df[(df.tcp_bw_up.notnull()) & (df.tcp_bw_down.notnull()) & (df.power.notnull())]

    # unique locations
    loc_names = df['loc_name'].unique()

    # timestamp limits
    ts_limits = []
    ts_limits.append(np.amin(df['unixtime']))
    ts_limits.append(np.amax(df['unixtime']))

    # unique timestamps, basis for unique xx in our graphs
    tss = df['unixtime'].unique()
    ts_pos = OrderedDict()
    # unix timestamps which mark a new day of trials
    ts_days = defaultdict(list)
    # need to set the time zone of Seattle, WA
    timezone = pytz.timezone('America/Vancouver')
    i = 0
    for ts in tss:

        # pos of ts in xx array
        ts_pos[ts - ts_limits[0]] = (i, len(df[df['unixtime'] == ts]))

        # update the pos of day this ts translates to
        day = int(datetime.fromtimestamp(int(ts), tz = timezone).strftime('%d'))
        if day not in ts_days:
            ts_days[day] = [i, 0]
        ts_days[day][1] += ts_pos[ts - ts_limits[0]][1]

        i = i + len(df[df['unixtime'] == ts])

    # bw limits
    bw_limit = max(np.amax(df['tcp_bw_up']), np.amax(df['tcp_bw_down']))
    bw_barwidth = .375

    fig = plt.figure(figsize = (12, 3 * len(loc_names)))

    # 1 graph per location
    for i, loc_name in enumerate(loc_names):

        ax1 = fig.add_subplot(len(loc_names), 1, (i + 1))
        ax1.xaxis.grid(True)
        ax1.yaxis.grid(True)

        ax2 = ax1.twinx()

        # if loc_name == 'lounjin':
        print("***\nloc_name = %s" % (loc_name))

        ax1.set_title("""%s""" % (loc_name))

        # show different days in different shades of gray
        graycolor = ['gray', 'lightgray']
        for k, pos in enumerate(ts_days.values()):
            ax1.axvspan(
                pos[0], pos[0] + pos[1],
                linewidth = 0.0, facecolor = graycolor[(k % 2)], alpha = 0.50)

        # isolate data related to a particular location
        loc_data = df.loc[df['loc_name'] == loc_name]

        # plot the tcp bws (upload and download), per [unixtimestamp, ssid]
        tss = loc_data['unixtime'].unique()
        for j, ts in enumerate(tss):

            ts_data = loc_data.loc[loc_data['unixtime'] == ts]
            # order by bssid (i.e. mac addr)
            ts_data = ts_data.sort_values(by = ['bssid'])

            # if loc_name == 'lounjin':
            print(datetime.fromtimestamp(int(ts), tz = timezone).strftime('%Y-%m-%d %H:%M:%S'))
            # print(ts_data['bssid'].unique())
            # print(ts_data.ix[ts_data['tcp_bw_down'].idxmax()][['channel', 'tcp_bw_down', 'ssid', 'bssid']].values)
            # print(ts_data.ix[ts_data['tcp_bw_up'].idxmax()][['channel', 'tcp_bw_up', 'ssid', 'bssid']].values)

            ts = ts - ts_limits[0]
            xx = np.arange(ts_pos[ts][0], ts_pos[ts][0] + ts_pos[ts][1], 1)

            ax1.bar(
                xx - (bw_barwidth), ts_data['tcp_bw_down'], 
                alpha = .50, 
                width = bw_barwidth, 
                color = 'red')

            ax1.bar(
                xx, ts_data['tcp_bw_up'], 
                alpha = .50, 
                width = bw_barwidth, 
                color = 'blue')

            ax2.scatter(xx, ts_data['power'], color = 'green', linewidth = 1.5, marker = 'x')

            # ax1.set_xlim(-1, ts_days.values()[-1][0] + ts_days.values()[-1][1])
            ax1.set_xlim(-1, ts_days.values()[1][0] + ts_days.values()[1][1])
            ax1.set_ylim(0.0, math.ceil(bw_limit))

    fig.tight_layout()
    fig.subplots_adjust(top = 0.95)

    plt.savefig(os.path.join(out_dir, "loc-bw-power.pdf"), bbox_inches = 'tight', format = 'pdf')
    plt.close('all')

def plot(in_dir, out_dir):

    """analysis of wifi-reports dataset"""

    df = extract(in_dir, out_dir)
    profile(df, out_dir)
    best_ap(df, out_dir)