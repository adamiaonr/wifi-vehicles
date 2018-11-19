import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import os
import re
import argparse
import sys
import glob
import math
import gmplot
import time
import subprocess
import csv
# for parallel processing of sessions
import multiprocessing as mp 
import hashlib
import datetime
import json

import plot.utils
import mapping.utils

import analysis.metrics
import analysis.gps

from random import randint
from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple
from matplotlib.gridspec import GridSpec
from prettytable import PrettyTable

matplotlib.rcParams.update({'font.size': 16})

def rssi(axs, input_dir, trace_nr, 
    gt_metric,
    compare_to,
    configs,
    time_limits = None):

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']
    database = analysis.trace.get_db(input_dir, trace_nr)

    # (1) load groud truth metric data : this determines the ground truth in terms of the best ap to choose
    # usually the perf. metric is 'throughput'
    gt_data = analysis.trace.load_best(database, gt_metric)

    # (2) load data of ap selection method to evaluate
    base_db_name = ''
    if configs['method'] == 'periodic':
        base_db_name = ('/%s/%s/%d/%d' % ('best-rssi', 'periodic', int(configs['args']['scan-period']), int(configs['args']['scan-time'])))

    elif configs['method'] == 'band-steering':
        base_db_name = ('/%s/%s/%s/%s/%s/%s/%s/%s/%s' % (
            'best-rssi', configs['method'], 
            configs['args']['scan-period'], configs['args']['scan-time'], 
            configs['args']['cell-size'], 
            configs['args']['metric'], configs['args']['stat'], ('-'.join([str(v) for v in configs['args']['stat-args'].values()])),
            ('%d-%d' % (configs['args']['use-current-lap'], configs['args']['use-direction']))))

    elif configs['method'] == 'history':
        base_db_name = ('/%s/%s/%s/%s/%s/%s/%s/%s/%s' % (
            'best-rssi', configs['method'], 
            configs['args']['scan-period'], configs['args']['scan-time'], 
            configs['args']['cell-size'], 
            configs['args']['metric'], configs['args']['stat'], ('-'.join([str(v) for v in configs['args']['stat-args'].values()])),
            ('%d-%d' % (configs['args']['use-current-lap'], configs['args']['use-direction']))))

    else:
        sys.stderr.write("""[ERROR] method %s not implemented yet. abort.\n""" % (configs['method']))

    base_data = database.select(base_db_name).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)

    # method-specific pre-processing
    base_data.rename(index = str, columns = {'ap-period' : 'block', 'scan-period' : 'sub-block'}, inplace = True)
    # save 'best' values of original metric
    base_data['best-val-orig'] = 0.0
    base_data.dropna(subset = ['best'], inplace = True)
    for mac in base_data['best'].unique():
        base_data.loc[(base_data['best'] == mac), 'best-val-orig'] = base_data[base_data['best'] == mac][mac]
    base_data['best-val-orig'] = base_data['best-val-orig'].fillna(0.0)
    # re-name the original columns, so that these don't collide w/ the merge w/ gt_data
    orig_cols = []
    for i, client in clients.iterrows():
        if client['mac'] not in base_data:
            continue
        base_data.rename(index = str, columns = {client['mac'] : ('%s-orig' % (client['mac']))}, inplace = True)
        orig_cols.append(('%s-orig' % (client['mac'])))

    # (3) load data of ap selection method for comparison
    cmp_data = None
    if compare_to['method'] == 'best':
        cmp_data = gt_data
        cmp_data['cmp-best'] = gt_data['gt']
        cmp_data['cmp-best-val'] = gt_data['gt-val']

        base_data = pd.merge(base_data[['interval-tmstmp', 'best-val-orig', 'best', 'block', 'sub-block'] + orig_cols], cmp_data, on = ['interval-tmstmp'], how = 'left')

    else:
        if compare_to['db-name'] not in database.keys():
            sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (compare_to['db-name']))
            return
        
        cmp_data = database.select(compare_to['db-name']).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
        cmp_data = pd.merge(cmp_data[['interval-tmstmp', 'best']], gt_data, on = ['interval-tmstmp'], how = 'left')
        cmp_data.rename(index = str, columns = {'best' : 'cmp-best'}, inplace = True)
        cmp_data['cmp-best-val'] = 0.0
        for mac in cmp_data['cmp-best'].unique():
            cmp_data.loc[(cmp_data['cmp-best'] == mac), 'cmp-best-val'] = cmp_data[cmp_data['cmp-best'] == mac][mac]
    
        base_data = pd.merge(base_data[['interval-tmstmp', 'best-val-orig', 'best', 'block', 'sub-block'] + orig_cols], gt_data, on = ['interval-tmstmp'], how = 'left')
        base_data = pd.merge(base_data, cmp_data[['interval-tmstmp', 'cmp-best', 'cmp-best-val']], on = ['interval-tmstmp'], how = 'left')

    base_data['best-val'] = 0.0
    for mac in base_data['best'].unique():
        base_data.loc[(base_data['best'] == mac), 'best-val'] = base_data[base_data['best'] == mac][mac]

    # FIXME: fill any nan values w/ 0.0 (is this bad?)
    base_data['best-val'] = base_data['best-val'].fillna(0.0)

    # ratio between selected metric and gt metric (in log10)
    base_data['ratio'] = 10.0 * (np.log10((base_data['best-val']) / base_data['cmp-best-val']))
    base_data['ratio'] = base_data['ratio'].fillna(0.0)

    yy_max = max(abs(np.amin(base_data[np.isfinite(base_data['ratio'])]['ratio'])), abs(np.amax(base_data[np.isfinite(base_data['ratio'])]['ratio'])))
    yy_max = analysis.metrics.custom_round(yy_max, prec = 1, base = 5)
    base_data.replace({'ratio' : {-np.Inf : -(yy_max - 1.5), np.Inf : (yy_max - 1.5)}}, inplace = True)

    # get segments of consecutive intervals in which the client is served by the same selected ap
    segments = base_data.groupby(['best','block'])['interval-tmstmp'].apply(np.array).reset_index(drop = False).sort_values(by = ['block'])

    # *** plot code section ***
    axs[0].set_title(configs['title'])

    g = 1
    if configs['show'] == 'all':
        axs[g].set_title(configs['sub-title'])
    else:
        g = 0

    for ax in axs:
        ax.xaxis.grid(True)
        ax.yaxis.grid(True)

    if not time_limits:
        time_limits = [None, None]

    # (1) plot segments of selected aps
    for i, client in clients.iterrows():
        for i, segment in segments[segments['best'] == client['mac']].iterrows():

            dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in [ segment['interval-tmstmp'][0], segment['interval-tmstmp'][-1] + 0.5 ] ]
            plot.utils.update_time_limits(time_limits, dates)
    
            for ax in axs:
                ax.axvspan(dates[0], dates[-1], linewidth = 0.0, facecolor = client['color'], alpha = 0.20)


    # (2) bar plots, for gt metric ratios between gt and selected values
    _data = base_data[base_data['ratio'] <= 0.0]
    if not _data.empty:
        axs[g].bar(
            [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ],
            _data['ratio'],
            label = ('%s loss' % (gt_metric)),
            width = .000015, linewidth = 0.0, alpha = 1.0, color = 'red')

    _data = base_data[base_data['ratio'] > 0.0]
    if not _data.empty:
        axs[g].bar(
            [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ],
            _data['ratio'],
            label = ('%s gain' % (gt_metric)),
            width = .000015, linewidth = 0.0, alpha = 1.0, color = 'green')

    # (2.1) plot 'best-sel' throughput values on secondary axis
    ax2 = axs[g].twinx()
    for i, client in clients.iterrows():

        _data = base_data[base_data['best'] == client['mac']]
        if _data.empty:
            continue

        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ]
        plot.utils.update_time_limits(time_limits, dates)

        # the values of ground truth metric, provided by the selected ap
        ax2.plot(
            dates,
            _data['best-val'] * configs['coef'],
            linewidth = 0.0, 
            linestyle = '-', 
            color = client['color'], 
            label = client['label'], 
            markersize = client['marker-size'], 
            marker = client['marker'], 
            markeredgewidth = 0.0)


    # (3) plot gt metric values provided by selected aps
    if configs['show'] == 'all':
        # y_limits = [None, None]
        for i, client in clients.iterrows():

            # _data = base_data[base_data['best'] == client['mac']]
            _data = base_data[['interval-tmstmp', ('%s-orig' % (client['mac']))]]
            if _data.empty:
                continue

            dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ]
            plot.utils.update_time_limits(time_limits, dates)

            # the values of ground truth metric, provided by the selected ap
            axs[0].plot(
                dates,
                _data[('%s-orig' % (client['mac']))],
                linewidth = 0.0, 
                linestyle = '-', 
                color = client['color'], 
                label = client['label'], 
                markersize = client['marker-size'], 
                marker = client['marker'], 
                markeredgewidth = 0.0)

            # plot.utils.update_y_limits(y_limits, (_data['best-val'] * configs['coef']))
            # plot.utils.update_y_limits(y_limits, (_data[('%s-orig' % (client['mac']))]))

        axs[0].legend(
            fontsize = 10, 
            ncol = 4, loc = 'lower right',
            handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

        axs[0].set_ylabel(configs['y-label'])

    axs[g].legend(
        fontsize = 10, 
        ncol = 1, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    axs[g].set_ylabel('10.log10(gain)')
    ax2.set_ylabel(configs['y-sec-label'])
    axs[g].set_ylim([-yy_max, yy_max])
    # set ax2 limits so that the plot fits in-between [0, yy_max]

    # x-label
    for ax in axs:
        ax.set_xlabel('time (sec)')
        # x-lims : set w/ time_limits
        ax.set_xlim(time_limits[0], time_limits[1])
        # x-ticks : every scan-period + scan-time seconds, starting from time_limits[0]
        xticks = plot.utils.get_time_xticks(time_limits, duration = configs['args']['scan-period'] + configs['args']['scan-time'])
        ax.set_xticks(xticks)
        xticklabels = [''] * len(xticks)
        for i in list(np.arange(0, len(xticklabels), 5)):
            xticklabels[i] = (((xticks[i].astype('uint64') / 1e6).astype('uint32')) - ((xticks[0].astype('uint64') / 1e6).astype('uint32')))
        ax.set_xticklabels(xticklabels, ha = 'center')

def cell(axs, input_dir, trace_nr, 
    gt_metric,
    compare_to,
    configs,
    time_limits = None):

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']

    database = analysis.trace.get_db(input_dir, trace_nr)

    # (1) load groud truth metric data : this determines the ground truth in terms of the best ap to choose
    # usually the perf. metric is 'throughput'
    gt_data = analysis.trace.load_best(database, gt_metric)

    # (2) load data of ap selection to evaluate
    # base_db_name = ('/%s/%s/%s/%s/%s' % ('best-cell', configs['args']['cell-size'], 'every-other', 'no-direction', configs['args']['metric']))
    base_db_name = ('/%s/%s/%s/%s/%s/%s' % (
        'best-cell',
        configs['args']['cell-size'],
        configs['args']['metric'], configs['args']['stat'], ('-'.join([str(v) for v in configs['args']['stat-args'].values()])),
        ('%d-%d' % (int(configs['args']['use-current-lap']), int(configs['args']['use-direction'])))))

    if base_db_name not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (base_db_name))
        return
    
    base_data = database.select(base_db_name).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)

    # (3) load data of ap selection method for comparison
    cmp_data = None
    if compare_to['method'] == 'best':
        cmp_data = gt_data
        cmp_data['cmp-best'] = gt_data['gt']
        cmp_data['cmp-best-val'] = gt_data['gt-val']

        base_data = pd.merge(base_data[['interval-tmstmp', 'best', 'block', 'cell-x', 'cell-y', 'lat', 'lon', 'lap-number', 'direction']], cmp_data, on = ['interval-tmstmp'], how = 'left')

    else:
        if compare_to['db-name'] not in database.keys():
            sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (compare_to['db-name']))
            return
        
        cmp_data = database.select(compare_to['db-name']).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
        cmp_data = pd.merge(cmp_data[['interval-tmstmp', 'best']], gt_data, on = ['interval-tmstmp'], how = 'left')
        cmp_data.rename(index = str, columns = {'best' : 'cmp-best'}, inplace = True)
        cmp_data['cmp-best-val'] = 0.0
        for mac in cmp_data['cmp-best'].unique():
            cmp_data.loc[(cmp_data['cmp-best'] == mac), 'cmp-best-val'] = cmp_data[cmp_data['cmp-best'] == mac][mac]
    
        base_data = pd.merge(base_data[['interval-tmstmp', 'best', 'block', 'cell-x', 'cell-y', 'lat', 'lon', 'lap-number', 'direction']], gt_data, on = ['interval-tmstmp'], how = 'left')
        base_data = pd.merge(base_data, cmp_data[['interval-tmstmp', 'cmp-best', 'cmp-best-val']], on = ['interval-tmstmp'], how = 'left')

    base_data['best-val'] = 0.0
    for mac in base_data['best'].unique():
        base_data.loc[(base_data['best'] == mac), 'best-val'] = base_data[base_data['best'] == mac][mac]
    # FIXME: fill any nan values w/ 0.0 (is this bad?)
    base_data['best-val'] = base_data['best-val'].fillna(0.0)
    
    # ratio between selected metric and gt metric (in log10)
    base_data['ratio'] = 10.0 * (np.log10((base_data['best-val']) / base_data['cmp-best-val']))
    base_data['ratio'] = base_data['ratio'].fillna(0.0)

    yy_max = max(abs(np.amin(base_data[np.isfinite(base_data['ratio'])]['ratio'])), abs(np.amax(base_data[np.isfinite(base_data['ratio'])]['ratio'])))
    yy_max = analysis.metrics.custom_round(yy_max, prec = 1, base = 5)
    base_data.replace({'ratio' : {-np.Inf : -(yy_max - 1.0), np.Inf : (yy_max - 1.0)}}, inplace = True)

    # get segments of consecutive intervals in which the client is served by the same selected ap
    segments = base_data.groupby(['best','block'])['interval-tmstmp'].apply(np.array).reset_index(drop = False).sort_values(by = ['block'])

    # *** plot code section ***
    axs[0].set_title(configs['title'])

    g = 1
    if configs['show'] == 'all':
        axs[g].set_title(configs['sub-title'])
    else:
        g = 0

    for ax in axs:
        ax.xaxis.grid(True, linestyle = '-')
        ax.xaxis.grid(True, which = 'minor', linestyle = ':')
        ax.yaxis.grid(True)

    if not time_limits:
        time_limits = [None, None]

    # (1) plot segments of selected aps
    for i, client in clients.iterrows():
        for i, segment in segments[segments['best'] == client['mac']].iterrows():

            dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in [ segment['interval-tmstmp'][0], segment['interval-tmstmp'][-1] + 0.5 ] ]
            plot.utils.update_time_limits(time_limits, dates)
    
            for ax in axs:
                ax.axvspan(dates[0], dates[-1], linewidth = 0.0, facecolor = client['color'], alpha = 0.20)


    # (2) bar plots, for gt metric ratios between gt and selected values
    _data = base_data[base_data['ratio'] <= 0.0]
    if not _data.empty:
        axs[g].bar(
            [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ],
            _data['ratio'],
            label = ('%s loss' % (gt_metric)),
            width = .000015, linewidth = 0.0, alpha = 1.0, color = 'red')

    _data = base_data[base_data['ratio'] > 0.0]
    if not _data.empty:
        axs[g].bar(
            [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ],
            _data['ratio'],
            label = ('%s gain' % (gt_metric)),
            width = .000015, linewidth = 0.0, alpha = 1.0, color = 'green')

    # (2.1) plot 'best-sel' throughput values on secondary axis
    ax2 = axs[g].twinx()
    for i, client in clients.iterrows():

        _data = base_data[base_data['best'] == client['mac']]
        if _data.empty:
            continue

        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ]
        plot.utils.update_time_limits(time_limits, dates)

        # the values of ground truth metric, provided by the selected ap
        ax2.plot(
            dates,
            _data['best-val'] * configs['coef'],
            linewidth = 0.0, 
            linestyle = '-', 
            color = client['color'], 
            label = client['label'], 
            markersize = client['marker-size'], 
            marker = client['marker'], 
            markeredgewidth = 0.0)

    # (3) plot gt metric values provided by selected aps
    # y_limits = [None, None]
    if configs['show'] == 'all':
        for i, client in clients.iterrows():

            _data = base_data[base_data['best'] == client['mac']]
            if _data.empty:
                continue

            dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ]
            plot.utils.update_time_limits(time_limits, dates)

            # the values of ground truth metric, provided by the selected ap
            axs[0].plot(
                dates,
                _data['best-val'] * configs['coef'],
                linewidth = 0.0, 
                linestyle = '-', 
                color = client['color'], 
                label = client['label'], 
                markersize = client['marker-size'], 
                marker = client['marker'], 
                markeredgewidth = 0.0)

            # plot.utils.update_y_limits(y_limits, (_data['best-val'] * configs['coef']))

        axs[0].legend(
            fontsize = 10, 
            ncol = 4, loc = 'upper right',
            handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

        axs[0].set_ylabel(configs['y-label'])

    axs[g].legend(
        fontsize = 10, 
        ncol = 1, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    axs[g].set_ylabel('10.log10(gain)')
    ax2.set_ylabel(configs['y-sec-label'])
    axs[g].set_ylim([-yy_max, yy_max])

    # x-label
    te = datetime.datetime(1970, 1, 1)
    for ax in axs:
        ax.set_xlabel('time (sec)')
        # x-lims : set w/ time_limits
        ax.set_xlim(time_limits[0], time_limits[1])
        # minor x-ticks : every cell entry
        minor_xticks = analysis.gps.get_cell_datetimes(base_data)
        # ax.set_xticks(minor_xticks, minor = True)
        # major x-ticks : every new lap
        major_xticks = analysis.gps.get_lap_datetimes(base_data)
        ax.set_xticks(sorted(major_xticks.values()), minor = False)
        ax.set_xticklabels([int((dt - te).total_seconds() - (time_limits[0] - te).total_seconds()) for dt in sorted(major_xticks.values())], ha = 'center')
