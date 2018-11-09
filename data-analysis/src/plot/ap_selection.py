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
    plot_configs,
    time_limits = None):

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))    

    # (1) load groud truth metric data : this determines the ground truth in terms of the best ap to choose
    # usually the perf. metric is 'throughput'
    gt_db_name = ('/%s/%s' % ('best', gt_metric))
    if gt_db_name not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (gt_db_name))
        return

    gt_data = database.select(gt_db_name).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
    # FIXME: why do we end up w/ duplicate 'interval-tmstmp' values?
    gt_data = gt_data.drop_duplicates(subset = ['interval-tmstmp'])
    # some pre-processing
    gt_data.rename(index = str, columns = {'best' : 'gt'}, inplace = True)
    # extract gt metric values of the best ap, for each row
    gt_data['gt-val'] = 0.0
    for mac in gt_data['gt'].unique():
        gt_data.loc[(gt_data['gt'] == mac), 'gt-val'] = gt_data[gt_data['gt'] == mac][mac]

    # (2) load data of ap selection method to evaluate
    base_db_name = ''
    if plot_configs['method'] == 'periodic':
        base_db_name = ('/%s/%s/%d/%d' % ('best-rssi', 'periodic', int(plot_configs['args']['scan-period']), int(plot_configs['args']['scan-time'])))
    elif plot_configs['method'] == 'band-steering':
        base_db_name = ('/%s/%s/%s/%s/%s/%s' % ('best-rssi', plot_configs['method'], plot_configs['args']['scan-period'], plot_configs['args']['scan-time'], plot_configs['args']['cell-size'], plot_configs['args']['aid-metric']))        
    else:
        sys.stderr.write("""[ERROR] method %s not implemented yet. abort.\n""" % (plot_configs['method']))

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
    base_data['ratio'] = np.log10((base_data['best-val']) / base_data['cmp-best-val'])
    base_data['ratio'] = base_data['ratio'].fillna(0.0)

    yy_max = max(abs(np.amin(base_data[np.isfinite(base_data['ratio'])]['ratio'])), abs(np.amax(base_data[np.isfinite(base_data['ratio'])]['ratio'])))
    yy_max = analysis.metrics.custom_round(yy_max, prec = 1, base = 5)
    base_data.replace({'ratio' : {-np.Inf : -(yy_max - 1.5), np.Inf : (yy_max - 1.5)}}, inplace = True)

    # get segments of consecutive intervals in which the client is served by the same selected ap
    segments = base_data.groupby(['best','block'])['interval-tmstmp'].apply(np.array).reset_index(drop = False).sort_values(by = ['block'])

    # *** plot code section ***
    axs[0].set_title(plot_configs['title'])
    axs[1].set_title(plot_configs['sub-title'])

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
        axs[1].bar(
            [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ],
            _data['ratio'],
            label = ('%s loss' % (gt_metric)),
            width = .000015, linewidth = 0.0, alpha = 1.0, color = 'red')

    _data = base_data[base_data['ratio'] > 0.0]
    if not _data.empty:
        axs[1].bar(
            [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ],
            _data['ratio'],
            label = ('%s gain' % (gt_metric)),
            width = .000015, linewidth = 0.0, alpha = 1.0, color = 'green')

    # (2.1) plot 'best-sel' throughput values on secondary axis
    ax2 = axs[1].twinx()
    for i, client in clients.iterrows():

        _data = base_data[base_data['best'] == client['mac']]
        if _data.empty:
            continue

        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ]
        plot.utils.update_time_limits(time_limits, dates)

        # the values of ground truth metric, provided by the selected ap
        ax2.plot(
            dates,
            _data['best-val'] * plot_configs['coef'],
            linewidth = 0.0, 
            linestyle = '-', 
            color = client['color'], 
            label = client['label'], 
            markersize = client['marker-size'], 
            marker = client['marker'], 
            markeredgewidth = 0.0)


    # (3) plot gt metric values provided by selected aps
    y_limits = [None, None]
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

        # plot.utils.update_y_limits(y_limits, (_data['best-val'] * plot_configs['coef']))
        plot.utils.update_y_limits(y_limits, (_data[('%s-orig' % (client['mac']))]))

    axs[0].legend(
        fontsize = 10, 
        ncol = 4, loc = 'lower right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    # # plot a black line w/ throughput for all mac addrs
    # _data = base_data.iloc[::5, :]
    # dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ]
    # axs[0].plot(
    #     dates,
    #     _data['best-val'] * plot_configs['coef'],
    #     alpha = .5,
    #     linewidth = 0.75, 
    #     linestyle = '-', 
    #     color = 'black', 
    #     marker = None)

    axs[1].legend(
        fontsize = 10, 
        ncol = 1, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    axs[0].set_ylabel(plot_configs['y-label'])
    axs[1].set_ylabel('log10(gain)')
    ax2.set_ylabel(plot_configs['y-sec-label'])
    axs[1].set_ylim([-yy_max, yy_max])
    # set ax2 limits so that the plot fits in-between [0, yy_max]

    # x-label
    for ax in axs:
        ax.set_xlabel('time (sec)')
        # x-lims : set w/ time_limits
        ax.set_xlim(time_limits[0], time_limits[1])
        # x-ticks : every scan-period + scan-time seconds, starting from time_limits[0]
        xticks = plot.utils.get_time_xticks(time_limits, duration = plot_configs['args']['scan-period'] + plot_configs['args']['scan-time'])
        ax.set_xticks(xticks)
        xticklabels = [''] * len(xticks)
        for i in list(np.arange(0, len(xticklabels), 5)):
            xticklabels[i] = (((xticks[i].astype('uint64') / 1e6).astype('uint32')) - ((xticks[0].astype('uint64') / 1e6).astype('uint32')))
        ax.set_xticklabels(xticklabels, ha = 'center')

    # # save results for further
    # ap_selection_db = ('/%s/%s/%s/%d/%d' % ('ap-selection', 'best-rssi', 'periodic', int(plot_configs['args']['scan-period']), int(plot_configs['args']['scan-time'])))
    # if ap_selection_db not in database.keys():
    #     parsing.utils.to_hdf5(base_data, ap_selection_db, database)

def cell(axs, input_dir, trace_nr, 
    gt_metric,
    compare_to,
    plot_configs,
    time_limits = None):

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))    

    # (1) load groud truth metric data : this determines the ground truth in terms of the best ap to choose
    # usually the perf. metric is 'throughput'
    gt_db_name = ('/%s/%s' % ('best', gt_metric))
    if gt_db_name not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (gt_db_name))
        return

    gt_data = database.select(gt_db_name).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
    # FIXME: why do we end up w/ duplicate 'interval-tmstmp' values?
    gt_data = gt_data.drop_duplicates(subset = ['interval-tmstmp'])
    # some pre-processing
    gt_data = gt_data.rename(index = str, columns = {'best' : 'gt'})
    # extract gt metric values of the best ap, for each row
    gt_data['gt-val'] = 0.0
    for mac in gt_data['gt'].unique():
        gt_data.loc[(gt_data['gt'] == mac), 'gt-val'] = gt_data[gt_data['gt'] == mac][mac]

    # (2) load data of ap selection to evaluate
    base_db_name = ('/%s/%s/%s/%s' % ('best-cell', plot_configs['args']['cell-size'], 'every-other', 'no-direction'))
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
    base_data['ratio'] = np.log10((base_data['best-val']) / base_data['cmp-best-val'])
    base_data['ratio'] = base_data['ratio'].fillna(0.0)

    yy_max = max(abs(np.amin(base_data[np.isfinite(base_data['ratio'])]['ratio'])), abs(np.amax(base_data[np.isfinite(base_data['ratio'])]['ratio'])))
    yy_max = analysis.metrics.custom_round(yy_max, prec = 1, base = 5)
    base_data.replace({'ratio' : {-np.Inf : -(yy_max - 1.0), np.Inf : (yy_max - 1.0)}}, inplace = True)

    # get segments of consecutive intervals in which the client is served by the same selected ap
    segments = base_data.groupby(['best','block'])['interval-tmstmp'].apply(np.array).reset_index(drop = False).sort_values(by = ['block'])

    # *** plot code section ***
    axs[0].set_title(plot_configs['title'])
    axs[1].set_title(plot_configs['sub-title'])

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
        axs[1].bar(
            [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ],
            _data['ratio'],
            label = ('%s loss' % (gt_metric)),
            width = .000015, linewidth = 0.0, alpha = 1.0, color = 'red')

    _data = base_data[base_data['ratio'] > 0.0]
    if not _data.empty:
        axs[1].bar(
            [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ],
            _data['ratio'],
            label = ('%s gain' % (gt_metric)),
            width = .000015, linewidth = 0.0, alpha = 1.0, color = 'green')

    # (3) plot gt metric values provided by selected aps
    y_limits = [None, None]
    for i, client in clients.iterrows():

        _data = base_data[base_data['best'] == client['mac']]
        if _data.empty:
            continue

        dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ]
        plot.utils.update_time_limits(time_limits, dates)

        # the values of ground truth metric, provided by the selected ap
        axs[0].plot(
            dates,
            _data['best-val'] * plot_configs['coef'],
            linewidth = 0.0, 
            linestyle = '-', 
            color = client['color'], 
            label = client['label'], 
            markersize = client['marker-size'], 
            marker = client['marker'], 
            markeredgewidth = 0.0)

        plot.utils.update_y_limits(y_limits, (_data['best-val'] * plot_configs['coef']))

    axs[0].legend(
        fontsize = 10, 
        ncol = 4, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    # # plot a black line w/ throughput for all mac addrs
    # _data = base_data.iloc[::5, :]
    # dates = [ datetime.datetime.fromtimestamp(float(dt)) for dt in _data['interval-tmstmp'] ]
    # axs[0].plot(
    #     dates,
    #     _data['best-val'] * plot_configs['coef'],
    #     alpha = .5,
    #     linewidth = 0.75, 
    #     linestyle = '-', 
    #     color = 'black', 
    #     marker = None)

    axs[1].legend(
        fontsize = 10, 
        ncol = 1, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

    axs[0].set_ylabel(plot_configs['y-label'])
    axs[1].set_ylabel('log10(gain)')
    axs[1].set_ylim([-yy_max, yy_max])

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

    # ap_selection_db = ('/%s/%s/%s/%s/%s' % ('ap-selection', 'best-cell', plot_configs['args']['cell-size'], 'every-other', 'no-direction'))
    # if ap_selection_db not in database.keys():
    #     parsing.utils.to_hdf5(base_data, ap_selection_db, database)
