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

import mapping.utils

import shapely.geometry

from random import randint

from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple

from prettytable import PrettyTable

from sklearn import linear_model

# wifi net operators
isps = {
    0 : {'name' : 'unknown'},
    1 : {'name' : 'eduroam'},
    2 : {'name' : 'zon'},
    3 : {'name' : 'meo'},
    4 : {'name' : 'vodafone'},
    5 : {'name' : 'porto digital'}
}

# re-organized auth. types
auth_types = {
    0 : {'name' : 'n/a', 'types' : [0], 'operators' : []},
    1 : {'name' : 'open', 'types' : [1], 'operators' : ['unknown']},
    2 : {'name' : 'comm.', 'types' : [1], 'operators' : ['meo', 'vodafone', 'zon']},
    3 : {'name' : 'WPA-x', 'types' : [2, 3, 4], 'operators' : []},
    4 : {'name' : '802.11x', 'types' : [5], 'operators' : []}}

# answers:
#   - how good is the signal in road cells?
#       - cdf of avg(rss)
#   - how much does signal vary in road cells?
#       - cdf of stddev(rss)
#   - where do you get which type of signal?
#       - map of rss (?)
def signal_quality(input_dir, output_dir, cell_size = 20, threshold = -80, draw_map = False):

    database = analysis.smc.utils.get_db(input_dir)

    plt.style.use('classic')

    plot_configs = {
        'rss_mean' : {
                'x-label' : 'RSS (dBm)',
                'title' : '(a) mean RSS per\n<cell, session>',
                'coef' : 1.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : 'blue',
                # 'x-ticks' : [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
                'x-lim' : [-80.0, -30.0]
        },
        'rss_stddev' : {
                'x-label' : 'RSS (dBm)',
                'title' : '(b) RSS std. dev. per\n<cell, session>',
                'coef' : 1.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : 'red'
                # 'x-ticks' : [0.0, 12.5, 25.0, 37.5, 50.0],
                # 'x-lim' : [0.0, 50.0]
        }
    }

    db = ('/signal-quality/rss/%s/%s' % (cell_size, int(abs(threshold))))
    if db not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (db))
        return

    data = database.select(db)
    # data = data.groupby(['cell_x', 'cell_y']).mean().reset_index(drop = False)

    # cdfs
    fig = plt.figure(figsize = (2.0 * 3.0, 3.0))
    axs = []
    for s, stat in enumerate(plot_configs.keys()):
        axs.append(fig.add_subplot(1, 2, s + 1))
        axs[s].set_title('%s' % (plot_configs[stat]['title']))
        plot.utils.cdf(axs[s], data, metric = stat, plot_configs = plot_configs[stat])

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, ("signal-quality-cdfs.pdf")), bbox_inches = 'tight', format = 'pdf')

    # map
    if draw_map:
        bbox = [-8.650, 41.140, -8.575, 41.175]
        dy = mapping.utils.gps_to_dist(bbox[3], 0.0, bbox[1], 0.0)
        dx = mapping.utils.gps_to_dist(bbox[1], bbox[0], bbox[1], bbox[2])
        fig = plt.figure(figsize = ((dx / dy) * 3.75, 3.5))

        ax = fig.add_subplot(111)
        # all cells which overlap w/ roads in Porto
        roadcells_all = gp.GeoDataFrame.from_file(os.path.join(input_dir, "roadcells-raw"))
        num_roadcells = float(len(roadcells_all['index'].drop_duplicates()))
        # all cells which overlap w/ roads in Porto, captured in SMC dataset
        roadcells_smc = gp.GeoDataFrame.from_file(os.path.join(input_dir, "roadcells-smc"))
        road_coverage = gp.GeoDataFrame.from_file(os.path.join(input_dir, ("processed/signal-quality/%s-%s" % (cell_size, int(abs(threshold))))))
        road_coverage = road_coverage[road_coverage['rss_mean'] < -60]
        # plot base : road cells in black, smc cells in gray
        roadcells_all.plot(ax = ax, facecolor = 'black', zorder = 1, linewidth = 0.0)
        roadcells_smc.plot(ax = ax, facecolor = 'grey', zorder = 5, linewidth = 0.0)
        # road coverage 'YlOrRd' color scale
        p = road_coverage.plot(ax = ax, column = 'rss_mean', cmap = 'YlOrRd', zorder = 10, legend = True, linewidth = 0.0)
        # background : midnightblue
        p.set_axis_bgcolor('midnightblue')

        ax.set_title('mean RSS (dBm) per\n<cell, session>')
        ax.set_xlabel('<- %.2f km ->' % (float(dx) / 1000.0))
        ax.set_ylabel('<- %.2f km ->' % (float(dy) / 1000.0))

        ax.set_xticks([])
        ax.set_yticks([])

        ax.set_xlim(bbox[0], bbox[2])
        ax.set_ylim(bbox[1], bbox[3])

        fig.tight_layout()
        plt.savefig(os.path.join(output_dir, "signal-quality-map.pdf"), bbox_inches = 'tight', format = 'pdf')

def esses(input_dir, output_dir, cell_size = 20, threshold = -80, draw_map = False):

    database = analysis.smc.utils.get_db(input_dir)

    plt.style.use('classic')

    plot_configs = {
        'bssid_cnt' : {
                'x-label' : '# of BSSIDs',
                'title' : '(a) mean # of BSSIDs\nper <session, cell>',
                'coef' : 1.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : 'blue',
                'db' : ('/esses/bssid_cnt/%s/%s' % (cell_size, int(abs(threshold)))),
                # 'x-ticks' : [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
                'x-lim' : [0.0, 50.0]
        },
        'essid_cnt' : {
                'x-label' : '# of ESSIDs',
                'title' : '(b) mean # of ESSIDs\nper <session, cell>',
                'coef' : 1.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : 'blue',
                'db' : ('/esses/bssid_cnt/%s/%s' % (cell_size, int(abs(threshold)))),
                # 'x-ticks' : [0.0, 12.5, 25.0, 37.5, 50.0],
                'x-lim' : [0.0, 50.0]
        },
        'essid_bssid_cnt' : {
                'x-label' : '# of BSSIDs',
                'title' : '(c) # of BSSIDs\nper ESSID',
                'coef' : 1.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : 'blue',
                'db' : ('/esses/essid_cnt/%s/%s' % (cell_size, int(abs(threshold)))),
                # 'x-ticks' : [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
                'x-lim' : [0.0, 10.0]
        }        
    }

    to_plot = ['bssid_cnt', 'essid_cnt', 'essid_bssid_cnt']
    fig = plt.figure(figsize = (len(to_plot) * 3.0, 3.0))
    axs = []
    for s, stat in enumerate(to_plot):

        if plot_configs[stat]['db'] not in database.keys():
            sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (plot_configs[stat]['db']))
            return

        data = database.select(plot_configs[stat]['db'])

        axs.append(fig.add_subplot(1, len(to_plot), s + 1))
        axs[s].set_title(plot_configs[stat]['title'])
        axs[s].xaxis.grid(True, ls = 'dotted', lw = 0.05)
        axs[s].yaxis.grid(True, ls = 'dotted', lw = 0.05)

        if stat in ['bssid_cnt', 'essid_cnt']:
            data = data.groupby(['cell_x', 'cell_y']).sum().reset_index(drop = False)
            plot.utils.cdf(axs[s], data, metric = stat, plot_configs = plot_configs[stat])
        if stat in ['essid_bssid_cnt']:
            data.rename(index = str, columns = {'bssid_cnt' : 'counts'}, inplace = True)
            plot.utils.cdf(axs[s], data, metric = 'essid_cnt', plot_configs = plot_configs[stat])

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, ("esses-cdfs.pdf")), bbox_inches = 'tight', format = 'pdf')

    # map (bssids)
    if draw_map:
        bbox = [-8.650, 41.140, -8.575, 41.175]
        dy = mapping.utils.gps_to_dist(bbox[3], 0.0, bbox[1], 0.0)
        dx = mapping.utils.gps_to_dist(bbox[1], bbox[0], bbox[1], bbox[2])
        fig = plt.figure(figsize = ((dx / dy) * 3.75, 3.5))

        ax = fig.add_subplot(111)
        # all cells which overlap w/ roads in Porto
        roadcells_all = gp.GeoDataFrame.from_file(os.path.join(input_dir, "roadcells-raw"))
        # all cells which overlap w/ roads in Porto, captured in SMC dataset
        roadcells_smc = gp.GeoDataFrame.from_file(os.path.join(input_dir, "roadcells-smc"))
        road_coverage = gp.GeoDataFrame.from_file(os.path.join(input_dir, ("processed/ess-cnt/%s-%s" % (cell_size, int(abs(threshold))))))
        road_coverage = road_coverage[road_coverage['bssid_cnt'] < 25]

        # plot base : road cells in black, smc cells in gray
        roadcells_all.plot(ax = ax, facecolor = 'black', zorder = 1, linewidth = 0.0)
        roadcells_smc.plot(ax = ax, facecolor = 'grey', zorder = 5, linewidth = 0.0)
        # road coverage 'YlOrRd' color scale
        p = road_coverage.plot(ax = ax, column = 'bssid_cnt', cmap = 'YlOrRd', zorder = 10, legend = True, linewidth = 0.0)
        # background : midnightblue
        p.set_axis_bgcolor('midnightblue')

        ax.set_title('mean # of BSSIDs per\n<cell, session>')
        ax.set_xlabel('<- %.2f km ->' % (float(dx) / 1000.0))
        ax.set_ylabel('<- %.2f km ->' % (float(dy) / 1000.0))

        ax.set_xticks([])
        ax.set_yticks([])

        ax.set_xlim(bbox[0], bbox[2])
        ax.set_ylim(bbox[1], bbox[3])

        fig.tight_layout()
        # fig.subplots_adjust(wspace = 0.3)
        plt.savefig(os.path.join(output_dir, "esses-map.pdf"), bbox_inches = 'tight', format = 'pdf')

def auth(input_dir, output_dir, cell_size = 20, threshold = -80):

    database = analysis.smc.utils.get_db(input_dir)

    plot_configs = {
        'ap_cnt': {
            'x-label' : 'auth. method',
            'y-label' : 'mean # of BSSIDs',
            'title' : 'mean # of BSSIDs observed per\n<cell, session, auth. method>',
            'coef' : 1.0,
            'linewidth' : 0.0,
            'markersize' : 1.25,
            'marker' : 'o',
            'markeredgewidth' : 0.0,
            'label' : '', 
            'color' : 'blue',
            'db' : ('/auth/ap_cnt/%s/%s' % (cell_size, int(abs(threshold)))),
            # 'x-ticks' : [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
            # 'x-lim' : [0.0, 50.0]
        }
    }

    # pre-processing
    db = plot_configs['ap_cnt']['db']
    if db not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (db))
        return

    data = database.select(db)

    #   - total nr. of sessions per <frequency, ap_cnt> tuple
    sessions = data[['auth', 'ap_cnt', 'session_cnt']].groupby(['auth', 'ap_cnt']).sum().reset_index(drop = False)
    print(sessions['auth'].unique())
    sessions.rename(index = str, columns = {'session_cnt' : 'auth_cnt'}, inplace = True)
    #   - total nr. of sessions
    db = ('/sessions/session_cnt/%s/%s' % (cell_size, int(abs(threshold))))
    if db not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (db))
        return

    nr_sessions = database.select(db)['session_cnt'].sum()
    sessions['total'] = nr_sessions
    sessions['prob_auth'] = sessions['auth_cnt'] / sessions['total']
    # print(sessions.sort_values(by = ['auth', 'ap_cnt']))
    # print(sessions[['auth', 'prob_auth']].groupby(['auth']).sum().reset_index(drop = False))

    plt.style.use('classic')
    fig = plt.figure(figsize = (1.0 * 4.0, 3.0))
    axs = []

    # fixed bar graph parameters:
    #   - bar width
    barwidth = 0.5
    #   - space between bars
    intraspace = 1.5 * barwidth

    xx = 0.0
    xticks = []
    xtickslabels = []

    axs.append(fig.add_subplot(1, 1, 1))
    axs[-1].set_title('%s' % (plot_configs['ap_cnt']['title']))

    axs[-1].xaxis.grid(True, ls = 'dotted', lw = 0.05)
    axs[-1].yaxis.grid(True, ls = 'dotted', lw = 0.05)

    sessions['expected_nr'] = sessions['ap_cnt'] * sessions['prob_auth']
    sessions = sessions[['auth', 'expected_nr']].groupby(['auth']).sum().reset_index(drop = False)

    # one bar per frequency
    for a in sorted(list(sessions['auth'].unique())):

        axs[-1].bar(xx - barwidth,
            sessions[sessions['auth'] == a]['expected_nr'],
            width = barwidth, linewidth = 0.250, alpha = .75, 
            color = plot_configs['ap_cnt']['color'])

        # xticks & xticklabel
        xticks.append(xx - (0.5 * barwidth))
        xtickslabels.append(auth_types[a]['name'])
        xx += intraspace

    # x-axis
    axs[-1].set_xlim(-(1.0 * barwidth) + xticks[0], xticks[-1] + (1.0 * barwidth))
    axs[-1].set_xticks(xticks)
    axs[-1].set_xticklabels(xtickslabels, rotation = 45, ha = 'right')
    axs[-1].set_xlabel(plot_configs['ap_cnt']['x-label'])
    # y-axis
    axs[-1].set_ylabel(plot_configs['ap_cnt']['y-label'])

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, ("auth.pdf")), bbox_inches = 'tight', format = 'pdf')

def get_channel(freq, band):
    if band == 0:
        return int((freq - 2412) / 5) + 1
    elif band == 1:
        return int((freq - 5180) / 10) + 36

def channels(input_dir, output_dir, cell_size = 20, threshold = -80):

    database = analysis.smc.utils.get_db(input_dir)

    plot_configs = {
        '2.4' : {
                'x-label' : 'channels',
                'y-label' : 'mean # of BSSIDs',
                'title' : '2.4 GHz',
                'coef' : 1.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : 'blue',
                # 'x-ticks' : [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
                # 'x-lim' : [0.0, 50.0]
        },

        '5.0' : {
                'x-label' : 'channels',
                'y-label' : 'mean # of BSSIDs',
                'title' : '5 GHz',
                'coef' : 1.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : 'red',
                # 'x-ticks' : [0.0, 12.5, 25.0, 37.5, 50.0],
                # 'x-lim' : [0.0, 50.0]
        }
    }

    # pre-processing
    #   - nr. of sessions w/ <ap_cnt, frequency> tuple, per cell
    print(database.keys())
    db = ('/channels/ap_cnt/%s/%s' % (cell_size, int(abs(threshold))))
    if db not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (db))
        return
    data = database.select(db)
    
    #   - total nr. of sessions per <frequency, ap_cnt> tuple
    sessions = data[['frequency', 'ap_cnt', 'session_cnt']].groupby(['frequency', 'ap_cnt']).sum().reset_index(drop = False)
    sessions.rename(index = str, columns = {'session_cnt' : 'freq_cnt'}, inplace = True)
    #   - total nr. of sessions
    db = ('/sessions/session_cnt/%s/%s' % (cell_size, int(abs(threshold))))
    if db not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (db))
        return

    nr_sessions = database.select(db)['session_cnt'].sum()
    sessions['total'] = nr_sessions
    sessions['prob_freq'] = sessions['freq_cnt'] / sessions['total']
    # print(sessions.sort_values(by = ['frequency', 'ap_cnt']))
    # print(sessions[['frequency', 'prob_freq']].groupby(['frequency']).sum().reset_index(drop = False))

    # add band
    # FIXME: again?!? this is inefficient
    analysis.smc.utils.add_band(sessions)

    plt.style.use('classic')
    fig = plt.figure(figsize = (2.0 * 4.0, 3.0))
    axs = []
    # fixed bar graph parameters:
    #   - bar width
    barwidth = 0.5
    #   - space between bars
    intraspace = 1.5 * barwidth

    for b, band in enumerate(sorted(plot_configs.keys())):

        xx = 0.0
        xticks = []
        xtickslabels = []

        axs.append(fig.add_subplot(1, 2, b + 1))
        axs[b].set_title('mean # of BSSIDs observed per\n<cell, session, channel>\n(%s)' % (plot_configs[band]['title']))
        axs[b].xaxis.grid(True, ls = 'dotted', lw = 0.05)
        axs[b].yaxis.grid(True, ls = 'dotted', lw = 0.05)

        # one band per subplot
        _data = sessions[sessions['band'] == b]
        _data['expected_nr'] = _data['ap_cnt'] * _data['prob_freq']
        _data = _data[['frequency', 'expected_nr']].groupby(['frequency']).sum().reset_index(drop = False)

        # one bar per frequency
        for f in sorted(list(_data['frequency'].unique())):

            axs[b].bar(xx - barwidth,
                _data[_data['frequency'] == f]['expected_nr'],
                width = barwidth, linewidth = 0.250, alpha = .75, 
                color = plot_configs[band]['color'])

            # xticks & xticklabel
            xticks.append(xx - (0.5 * barwidth))
            xtickslabels.append(get_channel(int(f), b))
            xx += intraspace

        # x-axis
        axs[b].set_xlim(-(1.0 * barwidth) + xticks[0], xticks[-1] + (1.0 * barwidth))
        axs[b].set_xticks(xticks)
        axs[b].set_xticklabels(xtickslabels, rotation = 45, ha = 'center')
        axs[b].set_xlabel(plot_configs[band]['x-label'])
        # y-axis
        axs[b].set_ylabel(plot_configs[band]['y-label'])

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, ("channels.pdf")), bbox_inches = 'tight', format = 'pdf')

def operators(input_dir, output_dir, cell_size = 20, threshold = -80):

    database = analysis.smc.utils.get_db(input_dir)

    plt.style.use('classic')

    plot_configs = {
        'bssid_cnt' : {
                'x-label' : 'operator',
                'y-label' : '% of BSSIDs',
                'title' : '(a) % of BSSIDs per\noperator',
                'coef' : 1.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : 'blue',
                'db' : ('/operators/bssid_cnt/%s/%s' % (cell_size, int(abs(threshold)))), 
                # 'x-ticks' : [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
                # 'x-lim' : [0.0, 50.0],
                'y-lim' : [0.0, 50.0],
                # 'y-scale' : 'log',
        },
        'cell_coverage' : {
                'x-label' : 'operator',
                'y-label' : '% of cells ',                
                'title' : '(b) % cells covered\nby operator',
                'coef' : 1.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : 'blue',
                'db' : ('/operators/cell_coverage/%s/%s' % (cell_size, int(abs(threshold)))), 
                # 'x-ticks' : [0.0, 12.5, 25.0, 37.5, 50.0],
                # 'x-lim' : [0.0, 50.0],
                'y-lim' : [0.0, 100.0],
        },
        'session_cnt' : {
                'x-label' : '# of operators',
                'title' : '(c) # of operators\nper <session, cell>',
                'coef' : 1.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : 'blue',
                'db' : ('/operators/session_cnt/%s/%s' % (cell_size, int(abs(threshold)))), 
                'x-ticks' : [1, 2, 3, 4, 5],
                'x-lim' : [0, 6]
        }
    }

    # fixed bar graph parameters
    barwidth = 0.5
    # space between big groups of bars
    interspace = 3.0 * barwidth
    # space between bars withing groups
    intraspace = 1.0 * barwidth

    to_plot = ['bssid_cnt', 'cell_coverage', 'session_cnt']
    fig = plt.figure(figsize = (len(to_plot) * 3.0, 3.0))
    axs = []
    for s, stat in enumerate(to_plot):

        if plot_configs[stat]['db'] not in database.keys():
            sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (plot_configs[stat]['db']))
            return

        data = database.select(plot_configs[stat]['db'])

        axs.append(fig.add_subplot(1, len(to_plot), s + 1))
        axs[s].set_title(plot_configs[stat]['title'])
        axs[s].xaxis.grid(True, ls = 'dotted', lw = 0.05)
        axs[s].yaxis.grid(True, ls = 'dotted', lw = 0.05)

        if stat in ['bssid_cnt', 'cell_coverage']:

            # keep track of xticks and labels
            xx = 0.0
            xticks = []
            xtickslabels = []

            if stat == 'bssid_cnt':

                print(data)
                data['bssid_freq'] = ((data['bssid_cnt'] / data['bssid_cnt'].sum()) * 100.0).astype(float)

                labels = ['private', 'public']
                for op in [0, 1, 5, 2, 3, 4]:

                    axs[s].bar(xx - barwidth,
                        data[(data['operator'] == op) & (data['operator_public'] == 0)]['bssid_freq'],
                        width = barwidth, linewidth = 0.250, alpha = .75, 
                        color = 'red', label = labels[0])

                    axs[s].bar(xx + intraspace - barwidth,
                        data[(data['operator'] == op) & (data['operator_public'] == 1)]['bssid_freq'],
                        width = barwidth, linewidth = 0.250, alpha = .75, 
                        color = 'blue', label = labels[1])

                    labels = ['', '']
                    # xticks & xticklabel
                    xticks.append(xx)
                    xtickslabels.append(isps[op]['name'])
                    xx += interspace

            if stat == 'cell_coverage':

                # load nr. of road cells
                start_time = timeit.default_timer()
                road_data = gp.GeoDataFrame.from_file(os.path.join(input_dir, "roadcells-smc"))
                print("%s::to_sql() : [INFO] read road-cells file in %.3f sec" % (sys.argv[0], timeit.default_timer() - start_time))
                road_data_size = float(len(road_data))

                data['cell_freq'] = ((data['cell_cnt'] / road_data_size) * 100.0).astype(int)
                # load combined data of all operators
                _data = database.select(plot_configs[stat]['db'].replace('cell_coverage', 'cell_coverage_all'))
                _data['cell_freq'] = ((_data['cell_cnt'] / road_data_size) * 100.0).astype(int)

                labels = ['private', 'public'] 
                for op in [0, 1, 5, 2, 3, 4]:

                    axs[s].bar(xx - barwidth,
                        data[(data['operator'] == op) & (data['operator_public'] == 0)]['cell_freq'],
                        width = barwidth, linewidth = 0.250, alpha = .75, 
                        color = 'red', label = labels[0])

                    axs[s].bar(xx + intraspace - barwidth,
                        data[(data['operator'] == op) & (data['operator_public'] == 1)]['cell_freq'],
                        width = barwidth, linewidth = 0.250, alpha = .75, 
                        color = 'blue', label = labels[1])

                    labels = ['', '']
                    # xticks & xticklabel
                    xticks.append(xx)
                    xtickslabels.append(isps[op]['name'])
                    xx += interspace

                # add final bar w/ all operators
                axs[s].bar(xx - barwidth,
                    _data[_data['operator_public'] == 0]['cell_freq'],
                    width = barwidth, linewidth = 0.250, alpha = .75, 
                    color = 'red', label = labels[0])

                axs[s].bar(xx + intraspace - barwidth,
                    _data[_data['operator_public'] == 1]['cell_freq'],
                    width = barwidth, linewidth = 0.250, alpha = .75, 
                    color = 'blue', label = labels[1])

                # xticks & xticklabel
                xticks.append(xx)
                xtickslabels.append('all')
                xx += interspace                

            # x-axis
            axs[s].set_xlim(-(1.5 * barwidth) + xticks[0], xticks[-1] + (1.5 * barwidth))
            axs[s].set_xticks(xticks)
            axs[s].set_xticklabels(xtickslabels, rotation = 45, ha = 'right')
            axs[s].set_xlabel(plot_configs[stat]['x-label'])
            # y-axis
            axs[s].set_ylim(plot_configs[stat]['y-lim'])
            axs[s].set_ylabel(plot_configs[stat]['y-label'])

            if 'y-scale' in plot_configs[stat]:
                axs[s].set_yscale(plot_configs[stat]['y-scale'])

        if stat == 'session_cnt':
            data.rename(index = str, columns = {'session_cnt' : 'counts'}, inplace = True)
            plot.utils.cdf(axs[s], data, metric = 'operator_cnt', plot_configs = plot_configs[stat])

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, ("operators.pdf")), bbox_inches = 'tight', format = 'pdf')

def contact(database, output_dir):

    plt.style.use('classic')

    plot_configs = {
        'time' : {
                'x-label' : 'time (sec)',
                'coef' : 1.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : 'blue',
                'x-ticks' : [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
                'x-lim' : [0.0, 30.0]
        },
        'speed' : {
                'x-label' : 'speed (m/s)',
                'coef' : 1.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : 'red',
                'x-ticks' : [0.0, 12.5, 25.0, 37.5, 50.0],
                'x-lim' : [0.0, 50.0]
        }
    }

    fig = plt.figure(figsize = (2.0 * 3.0, 3.0))
    axs = []
    for s, stat in enumerate(plot_configs.keys()):
        # add ax objs to figure
        axs.append(fig.add_subplot(1, 2, s + 1))
        # add titles to ax objs
        axs[s].set_title('contact %s' % (stat))

    for s, stat in enumerate(plot_configs.keys()):

        db = ('/%s/%s' % ('coverage', stat))
        if db not in database.keys():
            sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (db))
            return

        # mix bands
        data = database.select(db).groupby([stat]).sum().reset_index(drop = False)
        data.rename(index = str, columns = {'count' : 'counts'}, inplace = True)

        plot.utils.cdf(axs[s], data, metric = stat, plot_configs = plot_configs[stat])

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, ("coverage-cdfs.pdf")), bbox_inches = 'tight', format = 'pdf')

def bands(database, output_dir):

    plt.style.use('classic')

    db = ('/%s/%s' % ('bands', 'raw'))
    if db not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (db))
        return

    # group raw data by session, ap, cell and band
    data = database.select(db).groupby(['session_id', 'cell-x', 'cell-y', 'band'])['snr'].apply(np.array).reset_index(drop = False).sort_values(by = ['cell-x', 'cell-y', 'session_id']).reset_index(drop = False)
    data['id'] = data['session_id'].astype(str) + '.' + data['cell-x'].astype(str) + '.' + data['cell-y'].astype(str)
    data['xx'] = (data['id'] != data['id'].shift(1)).astype(int).cumsum()
    data['xx'] -= 1

    bands = {0 : {'title' : 'RSS per session & cell\n(2.4 GHz)', 'color' : 'red'}, 1 : {'title' : '5 GHz', 'color' : 'blue'}}

    fig = plt.figure(figsize = (2.0 * 3.0, 2.5))
    axs = []
    for b, band in enumerate(bands.keys()):
        # add ax objs to figure
        axs.append(fig.add_subplot(1, 2, b + 1))
        # add titles to ax objs
        axs[b].set_title('%s' % (bands[band]['title']))

        axs[b].xaxis.grid(True, ls = 'dotted', lw = 0.25)
        axs[b].yaxis.grid(True, ls = 'dotted', lw = 0.25)

        _data = data[data['band'] == band]

        # max & min
        yy_max = _data['snr'].apply(np.amax)
        yy_min = _data['snr'].apply(np.amin)

        # axs[b].plot(_data.index, yy_max, color = 'black', linewidth = .5, linestyle = ':', label = 'max')
        # axs[b].plot(_data.index, yy_min, color = 'black', linewidth = .5, linestyle = '-.', label = 'min')
        # fill area in-between max and min
        axs[b].fill_between(_data['xx'], yy_min, yy_max, 
            facecolor = bands[band]['color'], alpha = .50, interpolate = True, linewidth = 0.0,
            label = '[min, max]')

        # median
        axs[b].plot(_data['xx'], _data['snr'].apply(np.median), color = 'black', linewidth = .25, linestyle = '-', label = 'median')

        axs[b].set_xlabel('session & cell pairs')
        axs[b].set_ylabel("RSS (dBm)")

        # no x-ticks
        axs[b].set_xticks(np.arange(0, analysis.metrics.custom_round(np.amax(data['xx']), base = 10) + 10, 10))

        legend = axs[b].legend(
            fontsize = 10, 
            ncol = 1, loc = 'upper right',
            handletextpad = 0.2, handlelength = 1.5, labelspacing = 0.2, columnspacing = 0.5)

        for legobj in legend.legendHandles:
            legobj.set_linewidth(0.5)


    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, ("bands-rss-distribution.pdf")), bbox_inches = 'tight', format = 'pdf')
