#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Apr  8 13:34:27 2019

@author: adamiaonr
"""

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

import os
import argparse
import sys
import glob
import numpy as np
# import hashlib
import pandas as pd
import matplotlib.pyplot as plt
import folium

from folium.plugins import HeatMap
from folium.plugins import MarkerCluster

BBOX = [41.197033, -8.691692, 41.129342, -8.558394]

LAT = 41.163158
LON = -8.6127137

phases = {
        '802.11' : {'column' : 'wlan type-subtype', 'values' : ['Authentication', 'Association Request', 'Association Response']}, 
        'dhcp' : {'column' : 'dhcp type', 'values' : ['Discover', 'Offer', 'Request', 'ACK']}, 
        'tls' : {'valid-ips' : ['212.113.163.165', '31.25.212.248', '79.125.118.177', '54.77.293.1', '54.77.70.103']}, 
        'first-ping' : {'exclude-ips' : ['212.113.163.165', '31.25.212.248', '79.125.118.177', '54.77.293.1', '54.77.70.103']}
        }

locs = [
        {'timestamp' : '1554736368', 'lat' : 41.174768, 'lon' : -8.588690},
        {'timestamp' : '1554736262', 'lat' : 41.175886, 'lon' : -8.588248},
        {'timestamp' : '1554665772', 'lat' : 41.155168, 'lon' : -8.628393},
        {'timestamp' : '1554667049', 'lat' : 41.155168, 'lon' : -8.628393},
        {'timestamp' : '1554667178', 'lat' : 41.155168, 'lon' : -8.628393},
        {'timestamp' : '1554668908', 'lat' : 41.155168, 'lon' : -8.628393},
        {'timestamp' : '1554670099', 'lat' : 41.155168, 'lon' : -8.628393},
        {'timestamp' : '1554670211', 'lat' : 41.155168, 'lon' : -8.628393},
        {'timestamp' : '1554668352', 'lat' : 41.154828, 'lon' : -8.629458},
        {'timestamp' : '1554675584', 'lat' : 41.158611, 'lon' : -8.630963}]

def draw_map(data, output_dir, map_cntr = [LAT, LON], map_types = ['heatmap']):
    
    ap_map = folium.Map(location = map_cntr, 
        zoom_start = 14, 
        tiles = "Stamen Toner")

    for mt in map_types:
        if mt == 'heatmap':

            hm_wide = HeatMap( 
                            list(zip(data['lat'].values, data['lon'].values, data['counts'].values)),
                            min_opacity = 0.025,
                            max_val = np.amax(data['counts']),
                            radius = 5, blur = 10, 
                            max_zoom = 1, )

            ap_map.add_child(hm_wide)

        elif mt == 'clustered-marker':

            marker_cluster = MarkerCluster().add_to(ap_map)
            for index, row in data.iterrows():
                folium.Marker(location = [ row['lat'], row['lon'] ]).add_to(marker_cluster)

        ap_map.save(os.path.join(output_dir, ('%s.html' % (mt))))

def draw_tls_conn(input_dir, output_dir, 
   restrict_timestamps = {'exclude' : [], 'include' : [1554736262, 1554736368]}):
    
    tls_data = pd.read_csv(os.path.join(input_dir, ('tls.csv')))
    
    ips = {'212.113.163.165' : {'color' : 'red', 'label' : 'endpoint 1'}, 
           '31.25.212.248' : {'color' : 'green', 'label' : 'endpoint 2'}, 
           '79.125.118.177' : {'color' : 'blue', 'label' : 'endpoint 3'}}
    
    # find which timestamps to use
    if not restrict_timestamps['exclude']:
        tmstmps = restrict_timestamps['include']
    else:
        tmstmps = list(set(tls_data['timestamp'].tolist()) - set(restrict_timestamps['exclude']))
        
    for ts in tmstmps:

        plt.style.use('classic')
        fig = plt.figure(figsize = (3.0, 3.0))
        
        ax = fig.add_subplot(1, 1, 1)
        ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
        ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)

        xx = 0.0
        xticks = []
        xtickslabels = []
        
        for ip in ips:
            data = tls_data[(tls_data['timestamp'] == ts) & (tls_data['ip server'] == ip)].reset_index(drop = True)

            n_conns = 0
            if not data.empty:
                n_conns = len(data.drop_duplicates(subset = ['conn-id']))
                
            ax.bar(xx, n_conns,
               width = 0.5, linewidth = 0.250, alpha = .75, 
               color = ips[ip]['color'], label = ips[ip]['label'])

            xticks.append(xx)
            xtickslabels.append('')
            xx += 2.0 * 0.5            
            
        ax.legend(
            fontsize = 10, 
            ncol = 1, loc = 'upper right',
            handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

        ax.set_ylabel('# connections')
#        ax.set_ylim(0.0, np.ceil(ax.get_ylim()[1] * 1.50))
        ax.set_ylim(0.0, 35.0)        
#        ax.set_yscale('log')
#        ax.set_ylim([0.001, 10000])
        ax.set_xticks(xticks)
        ax.set_xticklabels(xtickslabels)
                        
        fig.tight_layout()
        fig.savefig(os.path.join(output_dir, ("%s-tls-conns.pdf" % (ts))), bbox_inches = 'tight', format = 'pdf')    

def draw_times(input_dir, output_dir, 
   restrict_timestamps = {'exclude' : [], 'include' : [1554736262, 1554736368]}):
        
    pre_auth_data = pd.read_csv(os.path.join(input_dir, ('pre-auth.csv')))
    tls_data = pd.read_csv(os.path.join(input_dir, ('tls.csv')))

    # find which timestamps to use
    if not restrict_timestamps['exclude']:
        tmstmps = restrict_timestamps['include']
    else:
        tmstmps = list(set(pre_auth_data['timestamp'].tolist()) - set(restrict_timestamps['exclude']))
        
    for ts in tmstmps:

        plt.style.use('classic')        
        fig = plt.figure(figsize = (3.0, 3.0))
        ax = fig.add_subplot(1, 1, 1)
        ax.xaxis.grid(True, ls = 'dotted', lw = 0.05)
        ax.yaxis.grid(True, ls = 'dotted', lw = 0.05)

        xx = 0.0
        xticks = []
        xtickslabels = []
        
        # total time
        total_time = 0.0        
        # 802.11 auth/assoc + dhcp times
        data = pre_auth_data[pre_auth_data['timestamp'] == ts]
        phases = {0 : {'name' : '802.11 auth/assoc', 'color' : 'red'}, 1 : {'name' : 'dhcp', 'color' : 'blue'}}
        for phase in phases:
            
            phz_name = phases[phase]['name']
            time = round(data[data['phase'] == phz_name]['time-end'] - data[data['phase'] == phz_name]['time-start'], 3)
            total_time += float(time)
            
            ax.bar(xx, time,
               width = 0.5, linewidth = 0.250, alpha = .75, 
               color = phases[phase]['color'], label = phz_name)
            
            xticks.append(xx)
            xtickslabels.append('')
            
            xx += 2.0 * 0.5

        # tls times
        data = tls_data[tls_data['timestamp'] == ts]                        
        phases = {0 : {'name' : 'app. layer auth.', 'color' : 'green'}}
        for phase in phases:
            
            phz_name = phases[phase]['name']

            if data.empty:
                time = 0.0
            else:
                time = round(data.iloc[-1]['time-end'] - data.iloc[0]['time-start'], 3)

            total_time += float(time)
                
            ax.bar(xx, time,
               width = 0.5, linewidth = 0.250, alpha = .75, 
               color = phases[phase]['color'], label = phz_name)
            
            xticks.append(xx)
            xtickslabels.append('')
            
            xx += 2.0 * 0.5
            
        ax.bar(xx, total_time, 
           width = 0.5, linewidth = 0.250, alpha = .75, 
           color = 'orange', label = 'total')
        
        xticks.append(xx)
        xtickslabels.append('')

        ax.legend(
            fontsize = 10, 
            ncol = 1, loc = 'upper right',
            handletextpad = 0.2, handlelength = 1.0, labelspacing = 0.2, columnspacing = 0.5)

        ax.set_ylabel('time (sec)')
#        ax.set_ylim(0.0, np.ceil(ax.get_ylim()[1] * 1.25))
        ax.set_yscale('log')

        ax.set_ylim([0.001, 1000])
        ax.set_yticks([0.001, 0.01, 0.1, 1, 10, 100, 1000])

#        ax.set_ylim([0.001, 1000])
#        ax.set_yticks([0.001, 0.01, 0.1, 1, 10, 100, 1000])

        ax.set_xticks(xticks)
        ax.set_xticklabels(xtickslabels)
                        
        fig.tight_layout()
        fig.savefig(os.path.join(output_dir, ("%s-times.pdf" % (ts))), bbox_inches = 'tight', format = 'pdf')

def analyze_tls(tls_data):

    # add a connection id column, identified by the tuple <ip.src, ip.dst, tcp.src, tcp.dst>
    tls_data['conn-id'] = tls_data['tcp src'].astype(str) + ',' + tls_data['tcp dst'].astype(str) + ',' + tls_data['ip src'].astype(str) + ',' + tls_data['ip dst'].astype(str) 
    tls_data['conn-id'] = tls_data['conn-id'].apply(lambda x : str(','.join(sorted(x.split(',')))))
#    tls_data['connection-id'] = tls_data['connection-id'].apply(lambda x : hashlib.md5(str(sorted(x.split(','))).encode()).hexdigest())
    # direction : client > server or client < server
    tls_data['direction'] = tls_data['tcp dst'].apply(lambda x : '>' if x == 443 else '<')
    # FIXME: only include FON endpoints
    tls_data = tls_data[(tls_data['ip src'].isin(phases['tls']['valid-ips'])) | (tls_data['ip dst'].isin(phases['tls']['valid-ips']))]
    # FIXME : is it always 'Application Data' though?
    tls_data['tls content type'] = tls_data['tls content type'].fillna('Application Data')

    # order connection ids per min epoch time
    conn_ids = tls_data[['epoch time', 'conn-id']].groupby(['conn-id'])['epoch time'].min().reset_index(drop = False, name = 'time').sort_values(by = ['time'])['conn-id']
    tls_stats = pd.DataFrame()
    for conn_id in conn_ids:
        
        conn_data = tls_data[tls_data['conn-id'] == conn_id].reset_index(drop = True)

        rows = []
        for phase in ['Handshake', 'Application Data']:            
            _data = conn_data[conn_data['tls content type'].str.contains(phase)].reset_index(drop = True)
            if not _data.empty:
                
                stats = {
                    'phase' : phase,
                    'time-start' : _data['epoch time'].min(),
                    'time-end' : _data['epoch time'].max(),
                    'pkts >' : str(len(_data[_data['direction'] == '>'])),
                    'pkts <' : str(len(_data[_data['direction'] == '>']))}
                
                rows.append(stats)
        
        data = pd.DataFrame(rows)
        data['conn-id'] = conn_id
        data['ip client'] = conn_data[conn_data['tcp dst'] == 443].iloc[0]['ip src']
        data['ip server'] = conn_data[conn_data['tcp dst'] == 443].iloc[0]['ip dst']
        
        tls_stats = pd.concat([tls_stats, data], ignore_index = True)
    
    return tls_stats

def analyze_pre_auth(net_cap):

    rows = []
    
    # 802.11 auth/assoc.
    data = net_cap[net_cap[phases['802.11']['column']].isin(phases['802.11']['values'])]
    rows.append({
            'phase' : '802.11 auth/assoc',
            'src' : data[data[phases['802.11']['column']].isin(['Association Request'])].iloc[0]['wlan src addr'],
            'dst' : data[data[phases['802.11']['column']].isin(['Association Request'])].iloc[0]['wlan dst addr'],
            'time-start' : data['epoch time'].min(),
            'time-end' : data['epoch time'].max(),
            'pkts >' : len(data[data['wlan src addr'].isin(['cc:fa:00:a7:95:0c', '88:07:4b:b3:f9:7e'])]),
            'pkts <' : len(data[data['wlan dst addr'].isin(['cc:fa:00:a7:95:0c', '88:07:4b:b3:f9:7e'])]),
            'msgs' : ','.join(list(set(data['wlan type-subtype'].tolist())))
            })

    # dhcp
    data = net_cap[net_cap[phases['dhcp']['column']].isin(phases['dhcp']['values'])]
    rows.append({
            'phase' : 'dhcp',
            'src' : data[data[phases['dhcp']['column']].isin(['Request'])].iloc[0]['dhcp req ip addr'],
            'dst' : data[data[phases['dhcp']['column']].isin(['Request'])].iloc[0]['ip dst'],
            'time-start' : data['epoch time'].min(),
            'time-end' : data['epoch time'].max(),
            'pkts >' : len(data[data['wlan src addr'].isin(['cc:fa:00:a7:95:0c', '88:07:4b:b3:f9:7e'])]),
            'pkts <' : len(data[data['wlan dst addr'].isin(['cc:fa:00:a7:95:0c', '88:07:4b:b3:f9:7e'])]),
            'msgs' : ','.join(list(set(data['dhcp type'].tolist())))
            })
    
    return pd.DataFrame(rows)

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input-dir", 
         help = """dir w/ smc data""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save processed data""")

    parser.add_argument(
        "--graph-dir", 
         help = """dir to save graphs""")

    args = parser.parse_args()
    
    if not args.input_dir:
        sys.stderr.write("""%s: [ERROR] must provide a dir w/ input files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] must provide an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.graph_dir:
        sys.stderr.write("""%s: [ERROR] must provide a graph dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

        
    if ((not os.path.isfile(os.path.join(args.output_dir, ('pre-auth.csv')))) 
        and (not os.path.isfile(os.path.join(args.output_dir, ('tls.csv'))))):
        
        # read all .csv files in input dir
        for filename in sorted(glob.glob(os.path.join(args.input_dir, ('*.csv')))):
            
            print(filename) 
    
            essid = filename.split('/')[-1].split('.')[1]      
            channel = filename.split('/')[-1].split('.')[2]
            timestamp = filename.split('/')[-1].split('.')[4]
            
            net_cap = pd.read_csv(filename)
            
            if 'ssl' in filename:
                
                tls_stats = analyze_tls(net_cap)
                tls_stats['essid'] = essid
                tls_stats['timestamp'] = timestamp
                tls_stats['channel'] = channel
                
                outfile = os.path.join(args.output_dir, ('tls.csv'))
                if (not os.path.isfile(outfile)) and (not tls_stats.empty):
                    tls_stats.to_csv(outfile)
                elif (not tls_stats.empty):
                    tls_stats.to_csv(outfile, header = False, mode = 'a')
                
            else:
    
                pre_auth_stats = analyze_pre_auth(net_cap)
                pre_auth_stats['essid'] = essid
                pre_auth_stats['timestamp'] = timestamp
                pre_auth_stats['channel'] = channel
                
                outfile = os.path.join(args.output_dir, ('pre-auth.csv'))
                if (not os.path.isfile(outfile)) and (not pre_auth_stats.empty):
                    pre_auth_stats.to_csv(outfile)
                elif (not pre_auth_stats.empty):
                    pre_auth_stats.to_csv(outfile, header = False, mode = 'a')            
            
    draw_times(args.output_dir, args.graph_dir)
    draw_tls_conn(args.output_dir, args.graph_dir)
    draw_map(pd.DataFrame(locs), args.graph_dir, map_cntr = [LAT, LON], map_types = ['clustered-marker'])






































    