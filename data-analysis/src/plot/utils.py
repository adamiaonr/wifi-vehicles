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

from random import randint
from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple
from matplotlib.gridspec import GridSpec
from prettytable import PrettyTable

def update_time_limits(time_limits, array):
    if ((time_limits[0] is None) or (min(array) < time_limits[0])):
        time_limits[0] = np.amin(array)

    if ((time_limits[1] is None) or (max(array) > time_limits[1])):
        time_limits[1] = np.amax(array)

def update_y_limits(y_limits, data):
    if ((y_limits[0] is None) or (np.amin(data) < y_limits[0])):
        y_limits[0] = np.amin(data)

    if ((y_limits[1] is None) or (np.amax(data) > y_limits[1])):
        y_limits[1] = np.amax(data)

def get_time_xticks(time_limits, num = 10.0, duration = None):
    
    if duration is None:
        delta = datetime.timedelta(seconds = ((time_limits[1] - time_limits[0]).total_seconds() / num))
    else:
        delta = datetime.timedelta(seconds = duration)

    xticks = np.arange(time_limits[0], time_limits[1] + delta, delta)
    return xticks

def cdf(
    ax,
    data,
    metric,
    plot_configs):

    ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)

    data = data.sort_values(by = [metric])
    if 'counts' not in data:
        cdf = data.groupby([metric]).size().reset_index(name = 'counts')
    else:
        cdf = data
        
    fontsize = 10
    if 'fontsize' in plot_configs:
        fontsize = plot_configs['fontsize']

    cdf['counts'] = np.array(cdf['counts'].cumsum(), dtype = float)
    cdf['counts'] = cdf['counts'] / cdf['counts'].values[-1]

    linestyle = '-'
    if 'linestyle' in plot_configs:
        linestyle = plot_configs['linestyle']

    ax.plot(cdf[metric] * plot_configs['coef'], cdf['counts'], 
        alpha = .75, 
        linewidth = 1.00, 
        color = plot_configs['color'], 
        label = plot_configs['label'], 
        linestyle = linestyle)

    ax.set_xlabel(plot_configs['x-label'], fontsize = fontsize)
    ax.set_ylabel("CDF", fontsize = fontsize)

    ax.tick_params(axis = 'both', which = 'major', labelsize = fontsize)
    ax.tick_params(axis = 'both', which = 'minor', labelsize = fontsize)

    if 'x-ticks' in plot_configs:
        ax.set_xticks(plot_configs['x-ticks'])
    if 'x-ticklabels' in plot_configs:
        ax.set_xticklabels(plot_configs['x-ticklabels'], fontsize = fontsize)
    if 'x-lim' in plot_configs:
        ax.set_xlim(plot_configs['x-lim'])

    ax.set_yticks(np.arange(0.0, 1.1, 0.25))
    if 'loc' not in plot_configs:
        plot_configs['loc'] = 'lower right'

    if plot_configs['label'] != '':
        legend = ax.legend(
            fontsize = 7, 
            ncol = 1, loc = plot_configs['loc'],
            handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

        for legobj in legend.legendHandles:
            legobj.set_linewidth(2.0)

def vs(
    ax,
    data,
    metrics,
    plot_configs):

    ax.xaxis.grid(True, ls = 'dotted', lw = 0.75)
    ax.yaxis.grid(True, ls = 'dotted', lw = 0.75)

    ax.plot(data[metrics[0]], data[metrics[1]] * plot_configs['coef'], 
        alpha = .5, 
        linewidth = plot_configs['linewidth'], 
        color = plot_configs['color'], 
        label = plot_configs['label'], 
        linestyle = '-',
        markersize = plot_configs['markersize'], 
        marker = plot_configs['marker'], 
        markeredgewidth = plot_configs['markeredgewidth'])

    ax.set_xlabel(plot_configs['x-label'])
    ax.set_ylabel(plot_configs['y-label'])

    legend = ax.legend(
        fontsize = 10, 
        ncol = 1, loc = 'upper right',
        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5, 
        markerscale = (plot_configs['markersize'] if plot_configs['markersize'] > 3.0 else 3.0))

def save_hash(output_dir, plot_hash, methods, configs):

    filename = os.path.join(output_dir, 'plot-info.csv')

    plot_list = pd.DataFrame(columns = ['hash', 'method', 'params'])
    if not os.path.isfile(filename):
        plot_list.to_csv(filename, index = False, sep = ',')

    if plot_hash not in pd.read_csv(filename)['hash'].tolist():

        plot_list = plot_list.append({
            'hash' : plot_hash,
            'method' : str(methods),
            'params' : str(json.dumps(configs, sort_keys = True))}, ignore_index = True)

        plot_list.to_csv(filename, mode = 'a', header = False, index = False, sep = ',')
