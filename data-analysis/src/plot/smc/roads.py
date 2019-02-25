import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import os
import re
import argparse
import sys
import glob
import math
import gmplot
import time
import timeit
import subprocess
import csv
# for parallel processing of sessions
import multiprocessing as mp 
import hashlib
import datetime
import json

import mapping.utils
import mapping.openstreetmap

import geopandas as gp

import plot.utils
import plot.trace
import plot.ap_selection
import plot.gps

import parsing.utils

import analysis.metrics
import analysis.trace
import analysis.gps
import analysis.ap_selection.rssi
import analysis.ap_selection.gps

import analysis.smc.sessions
import analysis.smc.utils
import analysis.smc.data

import analysis.smc.roads.main
import analysis.smc.roads.utils

import mapping.utils

import shapely.geometry

from random import randint

from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple

from prettytable import PrettyTable

from sklearn import linear_model

# road ref points for xx calculation
ref_points = {
    57 : [41.158179, -8.630399], 
    960 : [41.157160, -8.624431],
    978 : [41.160477, -8.593205],
    67 : [41.148925, -8.599117]}

def timespan(road_id, input_dir, output_dir):

    database = analysis.smc.utils.get_db(input_dir)

    # (1) load data
    # - get subset of selected aps
    coverage_db = ('/roads/%s/coverage' % (road_id))
    coverage_data = database.select(coverage_db)
    ap_ids = coverage_data['ap_id'].drop_duplicates()
    # - get ap data for ap subset
    data_db = ('/roads/%s/data' % (road_id))
    data = database.select(data_db)
    data = data[data['ap_id'].isin(ap_ids)].reset_index(drop = True)
    # - add column w/ 'day' timestamp
    data['day'] = data['timestamp'].apply(lambda x : (int(x / (3600 * 24)) * (3600 * 24)))
    # print(len(data['timestamp'].drop_duplicates()))
    # print((data['timestamp'].max() - data['timestamp'].min()) / (3600 * 24))
    # print(len(data['day'].drop_duplicates()))
    # print(len(data['session_id'].drop_duplicates()))
    # - add road xx position, in increments of 50 m
    pos = [ [ row['lat'], row['lon'] ] for index, row in data[['lat', 'lon']].iterrows() ]
    data['xx'] = [ mapping.utils.gps_to_dist(ref_points[road_id][0], ref_points[road_id][1], p[0], p[1]) for p in pos ]
    data['xx'] = data['xx'].apply(lambda x : int(round(x)))
    data['xx'] = ((data['xx'] / 50).astype(int) * 50).astype(int)

    # (2) pick top 3 stretches of road w/ longest data span
    strtch = data.groupby(['xx'])['day'].apply(set).reset_index(drop = False)
    strtch['time-span'] = strtch['day'].apply(lambda x : sorted(x)[-1] - sorted(x)[0])
    strtch['n-aps'] = data.groupby(['xx'])['ap_id'].apply(set).reset_index(drop = False)['ap_id'].apply(lambda x : len(x))
    strtch['n-days'] = strtch['day'].apply(lambda x : len(x))
    strtch = strtch[['xx', 'time-span', 'n-days', 'n-aps']].sort_values(by = ['n-aps', 'n-days', 'time-span'], ascending = False)

    # (3) find aps detected in selected stretches of road and extract timestamps
    # xx = np.arange(data['xx'].min(), data['xx'].max() + 50, 50)
    ap_passages = pd.DataFrame()
    ap_passages['xx'] = strtch['xx'].iloc[:3]
    ap_passages.set_index('xx', inplace = True)

    for ap in set(data['ap_id']):

        psg = data[(data['ap_id'] == ap) & (data['xx'].isin(strtch['xx']))][['xx', 'timestamp']].drop_duplicates().groupby(['xx'])['timestamp'].apply(list).reset_index(drop = False)
        # strtch['day'] = strtch['day'].apply(lambda x : sorted(x))
        # strtch['day'] = strtch['day'].astype(str)
        psg.rename(index = str, columns = {'timestamp' : ap}, inplace = True)
        psg.set_index('xx', inplace = True)

        ap_passages = ap_passages.join(psg, how = 'left')

    # (4) generate graph w/ timelines for all APs
    plt.style.use('classic')

    fig = plt.figure(figsize = (3.0, 5.0))
    time_limits = [None, None]
    ap_passages = ap_passages.reset_index(drop = False)
    for i, row in ap_passages.iterrows():

        ax = fig.add_subplot(3, 1, i + 1)
        ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
        ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)

        if i == 0:
            ax.set_title("road %s\n[%s, %s] m" % (road_id, row.iloc[0], row.iloc[0] + 50))
        else:
            ax.set_title("[%s, %s] m" % (row.iloc[0], row.iloc[0] + 50))

        #   - order aps by timespan
        aps = row.iloc[1:].reset_index(drop = True).to_frame(name = 'timestamp')
        aps['timestamp'] = aps['timestamp'].astype(list)
        aps.dropna(inplace = True)
        aps['time-span'] = aps['timestamp'].apply(lambda x : sorted(x)[-1] - sorted(x)[0])
        # aps['min-timestamp'] = aps['timestamp'].apply(lambda x : min(x))
        aps = aps.sort_values(by = ['time-span'], ascending = True).reset_index(drop = True)
        for j, ap in aps.iterrows():

            dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in ap['timestamp'] ]
            plot.utils.update_time_limits(time_limits, dates)

            ax.plot(
                dates, [j + 1] * len(dates),
                linewidth = 1.0, 
                linestyle = '-', 
                color = 'blue', 
                label = '', 
                alpha = 0.75,
                markersize = 0.0, 
                marker = None, 
                markeredgewidth = 0.0)

        time_limits = [datetime.datetime.fromtimestamp(1325376000.0), datetime.datetime.fromtimestamp(1483228800.0)]
        xticks = plot.utils.get_time_xticks(time_limits, num = 5.0)
        ax.set_xticks(xticks[-5:])
        ax.set_xlim(time_limits[0], time_limits[1])
        ax.set_xlabel('ap timespan')

        # disable y tikcks
        ap_num = len(aps)
        # ax.set_yticklabels([])
        ax.set_ylim([0, ap_num + 1])
        ax.set_yticks([0, ap_num + 1])
        ax.set_yticklabels(['1', ap_num])
        ax.set_ylabel('ap ids')
        # ax.set_xticklabels([str(xt)[11:-7] for xt in xticks])
        # xticklabels = [''] * len(xticks)
        # for i in list(np.arange(0, len(xticklabels), 5)):
        #     xticklabels[i] = (((xticks[i].astype('uint64') / 1e6).astype('uint32')) - ((xticks[0].astype('uint64') / 1e6).astype('uint32')))
        # ax.set_xticklabels(xticklabels, ha = 'center')

    fig.autofmt_xdate()
    fig.tight_layout()
    plt.savefig(os.path.join(output_dir, ("roads/time/%s/ap-timespan.pdf" % (road_id))), bbox_inches = 'tight', format = 'pdf')

def signal_quality(input_dir, output_dir,
    roads = {
        960 : {
            'color' : 'blue',
            'label' : 'road C',
            'length' : 960.0
        },
        57 : {
            'color' : 'red',
            'label' : 'road A',
            'length' : 2140.0
        },
        978 : {
            'color' : 'green',
            'label' : 'road D',
            'length' : 3180.0
        },
        67 : {
            'color' : 'orange',
            'label' : 'road B',
            'length' : 3080.0
        }        
    }):

    plot_configs = {
        'x-label' : 'RSS (dBm)',
        'title' : 'RSS per road',
        'coef' : 1.0,
        'linewidth' : 0.0,
        'markersize' : 1.25,
        'marker' : 'o',
        'markeredgewidth' : 0.0,
        'label' : '', 
        'color' : '',
        'loc' : 'lower right',
        # 'x-ticks' : [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
        'x-lim' : [-80.0, -30.0]
    }

    plt.style.use('classic')
    fig = plt.figure(figsize = (3.0, 3.0))
    ax = fig.add_subplot(1, 1, 1)
    ax.set_title('%s' % (plot_configs['title']))

    for road in sorted(roads.keys()):
    
        database = analysis.smc.utils.get_db(input_dir)
        db_name = ('/roads/%s/data' % (road))

        if (db_name not in database.keys()):
            sys.stderr.write("""[ERROR] %s not in database. skipping.\n""" % (db_name))
            continue

        data = database.select(db_name)
        data.loc[data['rss'] > -30, 'rss'] = -30
        plot_configs['color'] = roads[road]['color']
        plot_configs['label'] = roads[road]['label']
        plot.utils.cdf(ax, data, metric = 'rss', plot_configs = plot_configs)

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, ("roads/road-rss.pdf")), bbox_inches = 'tight', format = 'pdf')

def map(input_dir, output_dir, 
    roads = {
        960 : {
            'color' : 'blue',
            'label' : 'road C',
            'length' : 960.0
        },
        57 : {
            'color' : 'red',
            'label' : 'road A',
            'length' : 2140.0
        },
        978 : {
            'color' : 'green',
            'label' : 'road D',
            'length' : 3180.0
        },
        67 : {
            'color' : 'orange',
            'label' : 'road B',
            'length' : 3080.0
        }        
    },
    bbox = [-8.650, 41.140, -8.575, 41.175]):

    database = analysis.smc.utils.get_db(input_dir)

    for road in roads:

        db = ('/roads/%s/data' % (road))
        data = database.select(db)

        maps_dir = os.path.join(output_dir, ("roads/maps/%s" % (road)))
        if not os.path.isdir(maps_dir):
            os.makedirs(maps_dir)

        center_lat = (bbox[1] + bbox[3]) / 2.0
        center_lon = (bbox[0] + bbox[2]) / 2.0
        plot.gps.heatmap(data.groupby(['lat', 'lon']).size().reset_index(name = 'counts'), maps_dir, 
            map_cntr = [center_lat, center_lon], map_types = ['heatmap', 'clustered-marker'])

def rss(input_dir, output_dir, road_id, strategy, plan):

    # load rss data of the aps involved in the handoff plan
    database = analysis.smc.utils.get_db(input_dir)

    hp_db = ('/roads/%s/handoff/%s/%s/%s' % (road_id, strategy, plan['type'], plan['operator']))
    if (hp_db not in database.keys()):
        sys.stderr.write("""[ERROR] %s not in database. aborting.\n""" % (hp_db))
        return

    ap_data_db = ('/roads/%s/handoff/%s/%s/%s/data' % (road_id, strategy, plan['type'], plan['operator']))
    if (ap_data_db not in database.keys()):
        sys.stderr.write("""[ERROR] %s not in database. aborting.\n""" % (ap_data_db))
        return

    ap_data = database.select(ap_data_db)

    # fill any nan w/ -80 dBm
    ap_data.fillna(-80.0, inplace = True)
    # downsample distances to n meter granularity (only keep max RSS in n meter periods)
    n = 10
    ap_data['xx'] = ap_data['xx'].apply(lambda x : (int(x / (n)) * (n)))
    ap_data = ap_data.groupby(['xx']).max().reset_index(drop = True)

    # we want to plot horizontal strips for each ap, w/ heatmaps of rss (the higher the rss, the 'red'-ider)
    # https://stackoverflow.com/questions/33260045/python-using-pcolor-with-panda-dataframes

    plt.style.use('classic')
    fig = plt.figure(figsize = (3.0, 3.0))

    ax = fig.add_subplot(1, 1, 1)
    # ax.set_title('%s' % (plot_configs['title']))
    ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)

    print(len(ap_data))

    mplt = ax.pcolor(ap_data)
    plt.colorbar(mplt)

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, ("roads/handoff/%s/%s/rss.pdf" % (strategy, road_id))), bbox_inches = 'tight', format = 'pdf')

def handoff(input_dir, output_dir,
    roads = {
        960 : {
            'color' : 'blue',
            'label' : 'road C',
            'length' : 960.0
        },
        57 : {
            'color' : 'red',
            'label' : 'road A',
            'length' : 2140.0
        },
        978 : {
            'color' : 'green',
            'label' : 'road D',
            'length' : 3180.0
        },
        67 : {
            'color' : 'orange',
            'label' : 'road B',
            'length' : 3080.0
        }        
    },
    strategy = 'greedy',
    handoff_plans = [
        {'type' : 'any', 'operator' : 'any', 'label' : 'any', 'color' : ['red', 'lightsalmon']},
        {'type' : 'public', 'operator' : 'any', 'label' : 'any pub.', 'color' : ['blue', 'lightblue']},
        {'type' : 'public', 'operator' : 2, 'label' : 'pub. zon', 'color' : ['orange', 'peachpuff']},
        {'type' : 'public', 'operator' : 3, 'label' : 'pub. meo', 'color' : ['green', 'lightgreen']},
        # {'type' : 'public', 'operator' : 4, 'label' : 'vodaf.'},
        # {'type' : 'public', 'operator' : 5, 'label' : 'plan 5', 'color' : 'pink'}
        ]
    ):

    plt.style.use('classic')
    plot_configs = {
        'x-label' : '',
        'title' : ('# of handoffs (%s)' % (strategy)),
        'coef' : 1.0,
        'linewidth' : 0.0,
        'markersize' : 1.25,
        'marker' : 'o',
        'markeredgewidth' : 0.0,
        'label' : '', 
        'color' : '',
        'loc' : 'upper left'
        # 'x-ticks' : [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
        # 'x-lim' : [-80.0, -30.0]
    }

    fig = plt.figure(figsize = (1.5 * 3.0, 2.25))
    ax = fig.add_subplot(1, 1, 1)
    ax.set_title('%s' % (plot_configs['title']))
    ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)

    # keep track of xticks and labels
    xx = 0.0
    xticks = []
    xtickslabels = []
    # fixed bar graph parameters
    barwidth = 0.5
    # space between big groups of bars
    interspace = 4.0 * barwidth
    # space between bars within groups
    intraspace = 2.5 * barwidth

    # ax.axvspan(-(1.5 * barwidth), (3.5 * barwidth), linewidth = 0.0, facecolor = 'orange', alpha = 0.25)
    # ax.axvspan((3.5 * barwidth), 5.0 * (5.0 * barwidth), linewidth = 0.0, facecolor = 'green', alpha = 0.25)

    label = ['ap handoffs', 'ess handoffs']
    for i, road in enumerate(sorted(roads.keys())):
        for j, hp in enumerate(handoff_plans):

            data = analysis.smc.roads.handoff(road_id = road, input_dir = input_dir, strategy = strategy, plan = hp)
            print(road)
            print(strategy)
            print(hp)
            print(data)

            # nr. of ap handoffs
            ax.bar(xx - barwidth,
                len(data),
                width = barwidth, linewidth = 0.250, alpha = 1.00, 
                color = hp['color'][1], label = label[0])

            # nr. of ess handoffs
            ess_handoffs = 0.0
            if not data.empty:
                data['ess-block'] = (data['ess_id'] != data['ess_id'].shift(1)).astype(int).cumsum()
                ess_handoffs = len(data.drop_duplicates(subset = ['ess-block']))

            ax.bar(xx,
                ess_handoffs,
                width = barwidth, linewidth = 0.250, alpha = 1.00, 
                color = hp['color'][0], label = label[1])

            label = ['', '']

            # # xticks & xticklabel handling
            # xticks.append(xx)
            # xtickslabels.append(('%s' % (roads[road]['label'])))

            if j == ((len(handoff_plans) - 1) / 2):
                xticks.append(xx + barwidth)
                xtickslabels.append('%s' % (roads[road]['label']))

            if j < (len(handoff_plans) - 1):
                xx += intraspace

        if i < (len(roads.keys()) - 1):
            xx += interspace

    # # legend
    # leg = plt.legend(
    #     fontsize = 9, 
    #     ncol = 1, loc = 'upper left',
    #     handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    # ax.add_artist(leg)

    # background legend
    label = ['ap handoffs', 'ess handoffs']
    h = [
        plt.plot([], [], color = 'lightgrey', alpha = 1.00, label = label[0])[0],
        plt.plot([], [], color = 'dimgrey', alpha = 1.00, label = label[1])[0]
    ]
    leg = plt.legend(handles = h,
        fontsize = 9, 
        ncol = 1, loc = 'upper left',
        handletextpad = 0.2, handlelength = 1.5, labelspacing = 0.2, columnspacing = 0.5)

    for legobj in leg.legendHandles:
        legobj.set_linewidth(5.0)

    ax.add_artist(leg)

    # background legend
    h = []
    for j, hp in enumerate(handoff_plans): 
        h.append(plt.plot([], [], color = hp['color'][0], alpha = 1.00, label = hp['label'])[0])
    leg = plt.legend(handles = h,
        fontsize = 9, 
        ncol = 2, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.5, labelspacing = 0.2, columnspacing = 0.5)

    for legobj in leg.legendHandles:
        legobj.set_linewidth(5.0)

    # ax.set_xlabel('road\noperators')
    ax.set_ylabel('# of handoffs')

    ax.set_xlim(-(1.5 * barwidth), xx + (1.5 * barwidth))
    ax.set_xticks(xticks)
    ax.set_xticklabels(xtickslabels, rotation = 0, ha = 'center')

    # ax.set_ylim(0.0, np.ceil(ax.get_ylim()[1] * 1.25))
    ax.set_ylim(0.0, 50) 
    # ax.set_yscale("log", nonposy = 'clip')
    # ax.set_ylim(0.5, 1000.0)
    ax.set_yticks([0, 10, 20, 30, 40, 50])

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, ("roads/handoff/%s/handoffs.pdf" % (strategy))), bbox_inches = 'tight', format = 'pdf')

def coverage(input_dir, output_dir,
    roads = {
        960 : {
            'color' : 'blue',
            'label' : 'road C',
            'length' : 960.0
        },
        # 57 : {
        #     'color' : 'red',
        #     'label' : 'road A',
        #     'length' : 2140.0
        # },
        # 978 : {
        #     'color' : 'green',
        #     'label' : 'road D',
        #     'length' : 3180.0
        # },
        # 67 : {
        #     'color' : 'orange',
        #     'label' : 'road B',
        #     'length' : 3080.0
        # }
    },
    strategy = 'greedy',
    handoff_plans = [
        {'type' : 'any', 'operator' : 'any', 'label' : 'any', 'color' : 'red'},
        # {'type' : 'public', 'operator' : 'any', 'label' : 'any pub.', 'color' : 'blue'},
        # {'type' : 'public', 'operator' : 2, 'label' : 'pub. zon', 'color' : 'orange'},
        # {'type' : 'public', 'operator' : 3, 'label' : 'pub. meo', 'color' : 'green'},
        # {'type' : 'public', 'operator' : 4, 'label' : 'vodaf.'},
        # {'type' : 'public', 'operator' : 5, 'label' : 'plan 5', 'color' : 'pink'}
        ]
    ):

    plt.style.use('classic')

    # 2 types of bar charts: 
    #   - nr. of ap and ess handoffs 
    #   - % of road length covered by handoff plan
    plot_configs = {
        'x-label' : '',
        'title' : ('coverage perc. (%s)' % (strategy)),
        'coef' : 1.0,
        'linewidth' : 0.0,
        'markersize' : 1.25,
        'marker' : 'o',
        'markeredgewidth' : 0.0,
        'label' : '', 
        'color' : '',
        'loc' : 'upper left'
        # 'x-ticks' : [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
        # 'x-lim' : [-80.0, -30.0]
    }

    fig = plt.figure(figsize = (1.25 * 3.0, 2.25))
    ax = fig.add_subplot(1, 1, 1)
    ax.set_title('%s' % (plot_configs['title']))
    ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)

    xx = 0.0
    xticks = []
    xtickslabels = []
    barwidth = 0.5
    interspace = 3 * barwidth
    intraspace = barwidth

    # ax.axvspan(-(1.5 * barwidth), (1.75 * barwidth), linewidth = 0.0, facecolor = 'orange', alpha = 0.25)
    # ax.axvspan((1.75 * barwidth), 5.0 * (5.0 * barwidth), linewidth = 0.0, facecolor = 'green', alpha = 0.25)

    for i, road in enumerate(sorted(roads.keys())):
        for j, hp in enumerate(handoff_plans):

            p = analysis.smc.roads.main.get_handoff_plan(road_id = road, input_dir = input_dir, strategy = strategy, plan = hp)
            coverage_length = analysis.smc.roads.utils.get_coverage_length(p)
            coverage_perc = coverage_length / roads[road]['length']
            print(coverage_perc)
            sys.exit(0)

            # distance %
            ax.bar(xx - barwidth / 2.0,
                int(coverage_perc * 100.0),
                width = barwidth, linewidth = 0.250, alpha = .95, 
                color = hp['color'], label = hp['label'])

            handoff_plans[j]['label'] = ''

            # xticks & xticklabel handling
            # xticks.append(xx)
            # xtickslabels.append(('%s' % (roads[road]['label'])))

            if j == ((len(handoff_plans) - 1) / 2):
                xticks.append(xx + (barwidth / 2.0))
                xtickslabels.append('%s' % (roads[road]['label']))

            if j < (len(handoff_plans) - 1):
                xx += intraspace

        if i < (len(roads.keys()) - 1):
            xx += interspace

    # legend
    leg = plt.legend(
        fontsize = 9, 
        ncol = 2, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)
    ax.add_artist(leg)

    # # background legend
    # h = [plt.plot([], [], color = 'orange', label = 'private or public')[0], plt.plot([], [], color = 'green', label = 'only public', alpha = 0.20)[0]]
    # leg = plt.legend(handles = h,
    #     fontsize = 9, 
    #     ncol = 1, loc = 'upper left',
    #     handletextpad = 0.2, handlelength = 1.5, labelspacing = 0.2, columnspacing = 0.5)

    # for legobj in leg.legendHandles:
    #     legobj.set_linewidth(4.0)

    # ax.set_xlabel('road')
    ax.set_ylabel('coverage %')

    ax.set_xlim(-(1.5 * barwidth), xx + (1.5 * barwidth))
    ax.set_xticks(xticks)
    ax.set_xticklabels(xtickslabels, rotation = 0, ha = 'center')

    # ax.set_ylim(0.0, np.ceil(ax.get_ylim()[1] * 1.5))
    ax.set_ylim(0.0, 125)
    ax.set_yticks([0.0, 20, 40, 60, 80, 100])

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, ("roads/handoff/%s/coverage.pdf" % (strategy))), bbox_inches = 'tight', format = 'pdf')

def coverage_blocks(input_dir, output_dir,
    roads = {
        960 : {
            'color' : 'blue',
            'label' : 'road C',
            'length' : 960.0
        },
        57 : {
            'color' : 'red',
            'label' : 'road A',
            'length' : 2140.0
        },
        978 : {
            'color' : 'green',
            'label' : 'road D',
            'length' : 3180.0
        },
        67 : {
            'color' : 'orange',
            'label' : 'road B',
            'length' : 3080.0
        }        
    },
    strategy = 'greedy',
    handoff_plans = [
        {'type' : 'any', 'operator' : 'any', 'label' : 'any', 'color' : 'red'},
        {'type' : 'public', 'operator' : 'any', 'label' : 'any pub.', 'color' : 'blue'},
        {'type' : 'public', 'operator' : 2, 'label' : 'pub. zon', 'color' : 'orange'},
        {'type' : 'public', 'operator' : 3, 'label' : 'pub. meo', 'color' : 'green'},
        # {'strategy' : 'best-rss', 'type' : 'any', 'operator' : 'any', 'label' : 'any', 'color' : 'red'},
        # {'strategy' : 'best-rss', 'type' : 'public', 'operator' : 'any', 'label' : 'any pub.', 'color' : 'blue'},
        # {'strategy' : 'best-rss', 'type' : 'public', 'operator' : 2, 'label' : 'pub. zon', 'color' : 'orange'},
        # {'strategy' : 'best-rss', 'type' : 'public', 'operator' : 3, 'label' : 'pub. meo', 'color' : 'green'},
        ]
    ):

    database = analysis.smc.utils.get_db(input_dir)

    plt.style.use('classic')

    plot_configs = {
        'range' : {
            'x-label' : 'distance (m)',
            'title' : ('ap coverage (%s)' % (strategy)),
            'coef' : 1.0,
            'linewidth' : 0.0,
            'markersize' : 1.25,
            'marker' : 'o',
            'markeredgewidth' : 0.0,
            'label' : '', 
            'color' : '',
            'loc' : 'lower right'
            # 'x-ticks' : [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
            # 'x-lim' : [-80.0, -30.0]
        },
        'overlap' : {
            'x-label' : 'distance (m)',
            'title' : ('ap overlap (%s)' % (strategy)),
            'coef' : 1.0,
            'linewidth' : 0.0,
            'markersize' : 1.25,
            'marker' : 'o',
            'markeredgewidth' : 0.0,
            'label' : '', 
            'color' : '',
            'loc' : 'upper left'
            # 'x-ticks' : [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
            # 'x-lim' : [-80.0, -30.0]
        },        
    }

    # cdfs
    fig = plt.figure(figsize = (2.0 * 3.0, 3.0))
    
    axs = []
    for i, t in enumerate(['range', 'overlap']):
        axs.append(fig.add_subplot(1, 2, i + 1))
        axs[-1].set_title('%s' % (plot_configs[t]['title']))

    for j, hp in enumerate(handoff_plans):
    
        data = pd.DataFrame()
        for i, road in enumerate(sorted(roads.keys())):

            ol = analysis.smc.roads.overlap(road_id = road, input_dir = input_dir, strategy = strategy, plan = hp)
            if ol.empty:
                continue

            ol = ol[ol['overlap'] > 0.0]
            data = pd.concat([data, ol], ignore_index = True)

        if data.empty:
            continue

        for i, t in enumerate(['range', 'overlap']): 
            plot_configs[t]['color'] = hp['color']
            plot_configs[t]['label'] = hp['label']
            plot.utils.cdf(axs[i], data, metric = t, plot_configs = plot_configs[t])

    # axs[0].set_xscale("log", nonposx = 'clip')
    axs[0].set_xlim([0.0, 750.0])
    axs[0].set_xticks([0, 250, 500, 750])

    # axs[1].set_xlim([0.0, 200.0])
    # axs[1].set_xticks([0, 50, 100, 150, 200])
    axs[1].set_xscale("log", nonposx = 'clip')
    axs[1].set_xlim([1.0, 1000.0])
    axs[1].set_xticks([1, 10, 100, 1000])

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, ("roads/handoff/%s/coverage-blocks.pdf" % (strategy))), bbox_inches = 'tight', format = 'pdf')
