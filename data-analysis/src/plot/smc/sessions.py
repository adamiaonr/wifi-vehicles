# analyze-trace.py : code to analyze custom wifi trace collections
# Copyright (C) 2018  adamiaonr@cmu.edu

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from __future__ import absolute_import

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
import sys
import timeit
import geopandas as gp

# custom imports
#   - mapping
import utils.mapping
#   - hdfs utils
import utils.hdfs
#   - analysis
import analysis.trace
#   - smc analysis
import analysis.smc.sessions
#   - plot
import plot.utils
#   - mapping utils
import utils.mapping.utils
#   - trace analysis
import analysis.trace.utils.gps

# gps coords for a 'central' pin on porto, portugal
LAT  = 41.163158
LON = -8.6127137
# north, south, west, east limits of map, in terms of geo coordinates
LATN = LAT + 0.03
LATS = LAT - 0.03
LONE = LON + 0.06
LONW = LON - 0.06

# wifi net operators
isps = {
    0 : {'name' : 'unknown', 'shortname' : 'n/a'},
    1 : {'name' : 'eduroam', 'shortname' : 'edu'},
    2 : {'name' : 'zon', 'shortname' : 'zon'},
    3 : {'name' : 'meo', 'shortname' : 'meo'},
    4 : {'name' : 'vodafone', 'shortname' : 'vod'},
    5 : {'name' : 'porto digital', 'shortname' : 'pd'}
}

# re-organized auth. types
auth_types = {
    0 : {'name' : 'n/a', 'types' : [0], 'operators' : []},
    1 : {'name' : 'open', 'types' : [1], 'operators' : ['unknown']},
    2 : {'name' : 'comm.', 'types' : [1], 'operators' : ['meo', 'vodafone', 'zon']},
    3 : {'name' : 'WPA-x', 'types' : [2, 3, 4], 'operators' : []},
    4 : {'name' : '802.11x', 'types' : [5], 'operators' : []}}

def device_scans(input_dir, output_dir, db_name = 'smf',
    limits = {'top-devices' : 5, 'min-session-samples' : 5}):

    database = utils.hdfs.get_db(input_dir, ('%s.hdf5' % (db_name)))
    database_keys = utils.hdfs.get_db_keys(input_dir, ('%s.hdf5' % (db_name)))

    plot_configs = {
        'db_name' : ('/devices/scan-times/%d-%d' % (limits['min-session-samples'], limits['top-devices'])),
        'x-label' : 'scan interval (sec)',
        'title' : 'scan interval per\n<device, session>',
        'coef' : 1.0,
        'linewidth' : 0.0,
        'markersize' : 1.25,
        'marker' : 'o',
        'markeredgewidth' : 0.0,
        'label' : '', 
        'color' : '',
        # 'x-ticks' : [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
        'x-lim' : [1, 1000]
    }

    devices = {
        165 : {'label' : 'LG-H650', 'color' : 'blue'},
        132 : {'label' : 'OnePlus A5000', 'color' : 'red'},
        124 : {'label' : 'Moto G Plus', 'color' : 'green'},
        127 : {'label' : 'Google Pixel', 'color' : 'orange'},
        173 : {'label' : 'Sony F8131', 'color' : 'purple'},
        160 : {'label' : 'Xiaomi Mi A1', 'color' : 'grey'},
        177 : {'label' : 'LG-M400', 'color' : 'black'},
        101 : {'label' : 'OnePlus A3003', 'color' : 'lightblue'},
        232 : {'label' : 'Vodafone 710', 'color' : 'pink'},
    }

    if (plot_configs['db_name'] not in database_keys):
        sys.stderr.write("""[ERROR] %s not in database. aborting.\n""" % (plot_configs['db_name']))
        return

    data = database.select(plot_configs['db_name'])

    plt.style.use('classic')

    fig = plt.figure(figsize = (3.5, 3.0))
    ax = fig.add_subplot(1, 1, 1)
    ax.set_title(plot_configs['title'])

    data = data.groupby(['hw_id', 'scan_interval']).size().reset_index(name = 'counts', drop = False)
    for hw_id in set(data['hw_id'].tolist()):
        x = data[data['hw_id'] == hw_id]['scan_interval'].values
        y = data[data['hw_id'] == hw_id]['counts'].cumsum().astype(float).values
        y = y / y[-1]

        ax.plot(x, y, 
                alpha = .75, 
                linewidth = 1.00, 
                color = devices[hw_id]['color'], 
                label = devices[hw_id]['label'], 
                linestyle = '-')

    ax.set_xscale("log", nonposx = 'clip')
    plt.show()
    sys.exit(0)

    for hw_id in set(data['hw_id'].tolist()):
        _data = data[data['hw_id'] == hw_id]

        plot_configs['color'] = devices[hw_id]['color']
        plot_configs['label'] = devices[hw_id]['label']        
        plot.utils.cdf(ax, _data, metric = 'scan_interval', plot_configs = plot_configs)

    ax.set_xscale("log", nonposx = 'clip')

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, ("sessions/device-scan-times.pdf")), bbox_inches = 'tight', format = 'pdf')

# answers:
#   - how good is the signal in road cells?
#       - cdf of avg(rss)
#   - how much does signal vary in road cells?
#       - cdf of stddev(rss)
#   - where do you get which type of signal?
#       - map of rss (?)
def signal_quality(input_dir, output_dir, 
                   cell_size = 20, threshold = -80, draw_map = False,
                   db_name = 'smc'):

#    database = analysis.smc.utils.get_db(input_dir)
    database = utils.hdfs.get_db(input_dir, ('%s.hdf5' % (db_name)))
    database_keys = utils.hdfs.get_db_keys(input_dir, ('%s.hdf5' % (db_name)))

    plt.style.use('classic')

    plot_configs = {
        'rss_mean' : {
                'x-label' : 'RSS (dBm)',
                'title' : 'mean RSS per\n<cell, trip>',
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
        # 'rss_stddev' : {
        #         'x-label' : 'RSS (dBm)',
        #         'title' : '(b) RSS std. dev. per\n<cell, session>',
        #         'coef' : 1.0,
        #         'linewidth' : 0.0,
        #         'markersize' : 1.25,
        #         'marker' : 'o',
        #         'markeredgewidth' : 0.0,
        #         'label' : '', 
        #         'color' : 'red'
        #         # 'x-ticks' : [0.0, 12.5, 25.0, 37.5, 50.0],
        #         # 'x-lim' : [0.0, 50.0]
        # }
    }

    db = ('/signal-quality/rss/%s/%s' % (cell_size, int(abs(threshold))))
    if db not in database_keys:
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (db))
        return

    data = database.select(db)
    # data = data.groupby(['cell_x', 'cell_y']).mean().reset_index(drop = False)

    # cdfs
    fig = plt.figure(figsize = (len(plot_configs.keys()) * 3.0, 3.0))
    axs = []
    for s, stat in enumerate(plot_configs.keys()):
        axs.append(fig.add_subplot(1, len(plot_configs.keys()), s + 1))
        axs[s].set_title('%s' % (plot_configs[stat]['title']))
        plot.utils.cdf(axs[s], data, metric = stat, plot_configs = plot_configs[stat])

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, ("signal-quality-cdfs.pdf")), bbox_inches = 'tight', format = 'pdf')

    # map
    if draw_map:
        bbox = [-8.650, 41.140, -8.575, 41.175]
        dy = utils.mapping.utils.gps_to_dist(bbox[3], 0.0, bbox[1], 0.0)
        dx = utils.mapping.utils.gps_to_dist(bbox[1], bbox[0], bbox[1], bbox[2])
        fig = plt.figure(figsize = ((dx / dy) * 3.75, 3.5))

        ax = fig.add_subplot(111)
        # all cells which overlap w/ roads in Porto
        roadcells_all = gp.GeoDataFrame.from_file(os.path.join(input_dir, "roadcells-raw"))
#        num_roadcells = float(len(roadcells_all['index'].drop_duplicates()))
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

def esses(input_dir, output_dir, cell_size = 20, threshold = -80, draw_map = False,
    bbox = [LONW, LATS, LONE, LATN], 
    tags = ['highway=motorway', 'highway=trunk', 'highway=primary', 'highway=secondary', 'highway=tertiary', 'highway=residential'],
    db_name = 'smc'):

#    database = analysis.smc.utils.get_db(input_dir)
    database = utils.hdfs.get_db(input_dir, ('%s.hdf5' % (db_name)))
    database_keys = utils.hdfs.get_db_keys(input_dir, ('%s.hdf5' % (db_name)))

    plt.style.use('classic')

    plot_configs = {
        'bssid_cnt' : {
                'x-label' : '# of BSSIDs',
                'title' : 'mean # of aps\nper <cell, trip>',
                'coef' : 1.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : 'blue',
                'db' : ('/esses/xssid_cnt/%s/%s' % (cell_size, int(abs(threshold)))),
                # 'x-ticks' : [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
                'x-lim' : [0.0, 50.0]
        },
        'essid_cnt' : {
                'x-label' : '# of ESSIDs',
                'title' : 'mean # of esses\nper cell',
                'coef' : 1.0,
                'linewidth' : 0.0,
                'markersize' : 1.25,
                'marker' : 'o',
                'markeredgewidth' : 0.0,
                'label' : '', 
                'color' : 'blue',
                'db' : ('/esses/xssid_cnt/%s/%s' % (cell_size, int(abs(threshold)))),
                # 'x-ticks' : [0.0, 12.5, 25.0, 37.5, 50.0],
                'x-lim' : [0.0, 50.0]
        },
        # 'essid_bssid_cnt' : {
        #         'x-label' : '# of BSSIDs',
        #         'title' : '(c) # of BSSIDs\nper ESSID',
        #         'coef' : 1.0,
        #         'linewidth' : 0.0,
        #         'markersize' : 1.25,
        #         'marker' : 'o',
        #         'markeredgewidth' : 0.0,
        #         'label' : '', 
        #         'color' : 'blue',
        #         'db' : ('/esses/essid_cnt/%s/%s' % (cell_size, int(abs(threshold)))),
        #         # 'x-ticks' : [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
        #         'x-lim' : [0.0, 10.0]
        # }
    }

    to_plot = ['bssid_cnt']
    fig = plt.figure(figsize = (len(to_plot) * 3.0, 3.0))
    axs = []
    for s, stat in enumerate(to_plot):

        if plot_configs[stat]['db'] not in database_keys:
            sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (plot_configs[stat]['db']))
            return

        data = database.select(plot_configs[stat]['db'])

        axs.append(fig.add_subplot(1, len(to_plot), s + 1))
        axs[s].set_title(plot_configs[stat]['title'])
        axs[s].xaxis.grid(True, ls = 'dotted', lw = 0.05)
        axs[s].yaxis.grid(True, ls = 'dotted', lw = 0.05)

        if stat in ['bssid_cnt', 'essid_cnt']:
            data = data.groupby(['cell_id']).sum().reset_index(drop = False)
            plot.utils.cdf(axs[s], data, metric = stat, plot_configs = plot_configs[stat])
        if stat in ['essid_bssid_cnt']:
            data.rename(index = str, columns = {'bssid_cnt' : 'counts'}, inplace = True)
            plot.utils.cdf(axs[s], data, metric = 'essid_cnt', plot_configs = plot_configs[stat])

    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, ("esses-cdfs.pdf")), bbox_inches = 'tight', format = 'pdf')

    # map (bssids)
    if draw_map:

        # FIXME : smaller bbox to focus on cental Porto
        bbox = [-8.650, 41.140, -8.575, 41.175]
        dy = utils.mapping.utils.gps_to_dist(bbox[3], 0.0, bbox[1], 0.0)
        dx = utils.mapping.utils.gps_to_dist(bbox[1], bbox[0], bbox[1], bbox[2])
        
        fig = plt.figure(figsize = ((dx / dy) * 4.0, 4.0))

        ax = fig.add_subplot(111)
        ax.xaxis.grid(True, ls = 'dotted', lw = 0.75, color = 'white')
        ax.yaxis.grid(True, ls = 'dotted', lw = 0.75, color = 'white')

        # FIXME : hardcoded path ?
        cells_dir = os.path.join('/home/adamiaonr/workbench/wifi-vehicles/data-analysis/data/wifi-scans/traceroutes', 'cells')
#        road_hash = utils.mapping.openstreetmap.get_road_hash(bbox = [LONW, LATS, LONE, LATN], tags = tags)
        road_hash = '77bd2960fd40274230c7e7b77f13ddac'
        cells_dir = os.path.join(cells_dir, road_hash)

        # if db_eng is None:
        #     db_eng = sqlalchemy.create_engine('mysql+mysqlconnector://root:xpto12x1@localhost/smc')

        # cells = pd.read_sql('SELECT * FROM cells', con = db_eng)
        # cells.rename(index = str, columns = {'id' : 'cell_id'}, inplace = True)
        # base cell color : grey
        road_cells = gp.GeoDataFrame.from_file(cells_dir)
        # road_cells = pd.merge(road_cells, cells, on = ['cell_id'])
        # road_cells.plot(ax = ax, facecolor = 'grey', zorder = 5, linewidth = 0.0)
        ap_data = database.select(plot_configs['bssid_cnt']['db'])
        road_cells = pd.merge(road_cells, ap_data, on = ['cell_id'], how = 'left')
        road_cells.fillna(0.0, inplace = True)
        road_cells.loc[road_cells['bssid_cnt'] > 25.0, 'bssid_cnt'] = 25.0

        # draw cells in w/ 0 aps in black
        road_cells[road_cells['bssid_cnt'] < 1.0].plot(ax = ax, facecolor = 'black', zorder = 1, linewidth = 0.0)
        # draw remaining cells w/ 'YlOrRd' color scale according on ap count
        p = road_cells[road_cells['bssid_cnt'] > 0.0].plot(ax = ax, column = 'bssid_cnt', cmap = 'RdYlGn', zorder = 10, legend = True, linewidth = 0.0)
        # background : midnightblue
        p.set_facecolor('midnightblue')

        ax.set_title('mean # of aps per cell')
        ax.set_xlabel('distance (km)')
        ax.set_ylabel('distance (km)')

        x_cell_num, y_cell_num = analysis.trace.utils.gps.get_cell_num(cell_size = cell_size, lat = [bbox[1], bbox[3]], lon = [bbox[0], bbox[2]])
        w = (bbox[2] - bbox[0]) / float(x_cell_num)
        h = (bbox[3] - bbox[1]) / float(y_cell_num)

        # xticks every 1000 meters
        xticks = np.arange(bbox[0], bbox[2], w * (1000.0 / cell_size))
        ax.set_xticks(xticks)
        ax.set_xticklabels(
            np.arange(0, len(xticks) + 1),
            rotation = 0, ha = 'center')

        yticks = np.arange(bbox[1], bbox[3], h * (1000.0 / cell_size))
        ax.set_yticks(yticks)
        ax.set_yticklabels(np.arange(0, len(xticks) + 1))

        ax.set_xlim(bbox[0], bbox[2])
        ax.set_ylim(bbox[1], bbox[3])

        fig.tight_layout()
        plt.savefig(os.path.join(output_dir, "esses-map.pdf"), bbox_inches = 'tight', format = 'pdf')

def auth(input_dir, output_dir, cell_size = 20, threshold = -80):

    database = analysis.smc.utils.get_db(input_dir)

    plot_configs = {
        'ap_cnt': {
            'x-label' : 'auth. method',
            'y-label' : 'mean # of BSSIDs',
            'title' : 'mean # of aps per\n<cell, session, auth.>',
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
    fig = plt.figure(figsize = (3.0, 3.0))
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
                'y-label' : 'mean # of aps',
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
                'y-label' : '',
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
    fig = plt.figure(figsize = (2.0 * 3.0, 3.0))
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
        axs[b].set_title('mean # of aps per\ncell, session, channel\n(%s)' % (plot_configs[band]['title']))
        axs[b].xaxis.grid(True, ls = 'dotted', lw = 0.05)
        axs[b].yaxis.grid(True, ls = 'dotted', lw = 0.05)

        # one band per subplot
        _data = sessions[sessions['band'] == b]
        print(_data)
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

        if band == '5.0':
            axs[b].set_xlim(-(1.0 * barwidth) + xticks[0], xticks[-3] + (1.0 * barwidth))
            axs[b].set_yscale("log", nonposy = 'clip')
            axs[b].set_ylim([0.0001, 1.0])

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
                'title' : '% cells covered\nby operator',
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
                'y-lim' : [0.0, 115.0],
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

    # to_plot = ['bssid_cnt', 'cell_coverage', 'session_cnt']
    to_plot = ['cell_coverage']
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

                data['bssid_freq'] = ((data['bssid_cnt'] / data['bssid_cnt'].sum()) * 100.0).astype(float)

                labels = ['private', 'public']
                for op in [0, 1, 5, 2, 3, 4]:

                    freq = 0.0
                    if not data[(data['operator'] == op) & (data['operator_public'] == 0)].empty:
                        freq = data[(data['operator'] == op) & (data['operator_public'] == 0)]['bssid_freq']

                    axs[s].bar(xx - barwidth,
                        freq,
                        width = barwidth, linewidth = 0.250, alpha = .75, 
                        color = 'red', label = labels[0])

                    freq = 0.0
                    if not data[(data['operator'] == op) & (data['operator_public'] == 1)].empty:
                        freq = data[(data['operator'] == op) & (data['operator_public'] == 1)]['bssid_freq']

                    axs[s].bar(xx + intraspace - barwidth,
                        freq,
                        width = barwidth, linewidth = 0.250, alpha = .75, 
                        color = 'blue', label = labels[1])

                    legend = axs[s].legend(
                        fontsize = 10, 
                        ncol = 1, loc = 'upper right',
                        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)


                    labels = ['', '']
                    # xticks & xticklabel
                    xticks.append(xx)
                    xtickslabels.append(isps[op]['shortname'])
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

                labels = ['closed', 'open'] 
                for op in [0, 5, 2, 3, 4]:

                    freq = 0.0
                    if not data[(data['operator'] == op) & (data['operator_public'] == 0)].empty:
                        freq = data[(data['operator'] == op) & (data['operator_public'] == 0)]['cell_freq']

                    axs[s].bar(xx - barwidth,
                        freq,
                        width = barwidth, linewidth = 0.250, alpha = .75, 
                        color = 'red', label = labels[0])

                    freq = 0.0
                    if not data[(data['operator'] == op) & (data['operator_public'] == 1)].empty:
                        freq = data[(data['operator'] == op) & (data['operator_public'] == 1)]['cell_freq']

                    axs[s].bar(xx + intraspace - barwidth,
                        freq,
                        width = barwidth, linewidth = 0.250, alpha = .75, 
                        color = 'blue', label = labels[1])

                    legend = axs[s].legend(
                        fontsize = 10, 
                        ncol = 2, loc = 'upper right',
                        handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)


                    labels = ['', '']
                    # xticks & xticklabel
                    xticks.append(xx)
                    xtickslabels.append(isps[op]['shortname'])
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

            # for legobj in legend.legendHandles:
            #     legobj.set_linewidth(0.5)

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
