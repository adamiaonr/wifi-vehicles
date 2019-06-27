# data.py : manipulate wifi trace data
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
import os
import sys
import glob
import datetime

# custom imports
#   - hdfs utils
import utils.hdfs
#   - mapping utils
import utils.mapping.utils
#   - analysis
import analysis.trace

# north, south, west, east limits of map, in terms of geo coordinates
LATN = 41.176796
LATS = 41.179283
LONE = -8.593912
LONW = -8.598336
# gps coords for a 'central' pin on FEUP, Porto, Portugal
LAT  = (41.176796 + 41.179283) / 2.0
LON = (-8.598336 + -8.593912) / 2.0

# CELL_SIZE = 20.0
CELL_SIZE = 500.0

# number of cells in grid, in x and y directions
X_CELL_NUM = int(np.ceil((utils.mapping.utils.gps_to_dist(LATN, 0.0, LATS, 0.0) / CELL_SIZE)))
Y_CELL_NUM = int(np.ceil((utils.mapping.utils.gps_to_dist(LAT, LONW, LAT, LONE) / CELL_SIZE)))

ref = {'lat' : 41.178685, 'lon' : -8.597872}

def merge_traces(input_dir, traces_nrs = [], nodes = [], new_trace_nr = 0):

    output_dir = os.path.join(input_dir, ("trace-%03d" % (int(new_trace_nr))))
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # beacon files
    for node in nodes:

        output_file = os.path.join(output_dir, ("%s/beacons.csv" % (node)))
        if os.path.isfile(output_file):
            sys.stderr.write("""%s: [INFO] %s exists. skipping merge.\n""" % (sys.argv[0], output_file))
            continue

        if not os.path.exists(os.path.join(output_dir, ("%s" % (node)))):
            os.makedirs(os.path.join(output_dir, ("%s" % (node))))

        for trace_nr in traces_nrs:

            trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
            for filename in sorted(glob.glob(os.path.join(trace_dir, ('%s/beacons*.csv' % (node))))):
                chunksize = 10 ** 5

                for chunk in pd.read_csv(filename, chunksize = chunksize):

                    chunk['trace-nr'] = int(trace_nr)
                    if not os.path.isfile(output_file):
                        chunk.to_csv(output_file, sep = ',')
                    else:
                        chunk.to_csv(output_file, sep = ',', mode = 'a', header = False)

    # monitor files
    for node in nodes:

        output_file = os.path.join(output_dir, ("%s/monitor.csv" % (node)))
        if os.path.isfile(output_file):
            sys.stderr.write("""%s: [INFO] %s exists. skipping merge.\n""" % (sys.argv[0], output_file))            
            continue

        if not os.path.exists(os.path.join(output_dir, ("%s" % (node)))):
            os.makedirs(os.path.join(output_dir, ("%s" % (node))))

        for trace_nr in traces_nrs:

            trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
            for filename in sorted(glob.glob(os.path.join(trace_dir, ('%s/monitor*.csv' % (node))))):
                chunksize = 10 ** 5

                for chunk in pd.read_csv(filename, chunksize = chunksize):

                    chunk['trace-nr'] = int(trace_nr)
                    if not os.path.isfile(output_file):
                        chunk.to_csv(output_file, sep = ',')
                    else:
                        chunk.to_csv(output_file, sep = ',', mode = 'a', header = False)

    # all other filename patterns
    for pattern in ['cbt.csv', 'cpu.csv', 'gps-log*.csv', 'iperf3.csv', 'laps.csv', 'ntpstat.csv']:

        output_file = os.path.join(output_dir, pattern.replace('*', ''))
        if os.path.isfile(output_file):
            sys.stderr.write("""%s: [INFO] %s exists. skipping merge.\n""" % (sys.argv[0], output_file))
            continue

        for trace_nr in traces_nrs:
            trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))

            for filename in sorted(glob.glob(os.path.join(trace_dir, (pattern)))):
                chunksize = 10 ** 5

                for chunk in pd.read_csv(filename, chunksize = chunksize):

                    chunk['trace-nr'] = int(trace_nr)
                    if not os.path.isfile(output_file):
                        chunk.to_csv(output_file, sep = ',')
                    else:
                        chunk.to_csv(output_file, sep = ',', mode = 'a', header = False)

def iperf3_to_csv(input_dir, trace_nr, nodes = ['w3', 'w2', 'w1', 'm1']):

    multiplier = {
        'Bytes' : 1.0,
        'KBytes' : 1000.0,
        'MBytes' : 1000000.0,
        'GBytes' : 1000000000.0,
        'bits/sec' : 1.0,
        'Kbits/sec' : 1000.0,
        'Mbits/sec' : 1000000.0,
        'Gbits/sec' : 1000000000.0
    }

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))

    iperf3_data = pd.DataFrame()
    for node in nodes:
        iperf3_dir = os.path.join(trace_dir, ("%s" % (node)))
        for filename in sorted(glob.glob(os.path.join(iperf3_dir, ('iperf3.*.out')))):

            data = []
            reverse = False
            measurement_section = False
            with open(filename, 'r') as f:
                lines = f.readlines()

            for line in lines:

                if 'Time:' in line:
                    # format e.g.: Tue, 29 Jan 2019 16:42:22 GMT
                    date_str = line.split('Time:')[-1].strip()
                    base_timestamp = float(datetime.datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z").timestamp())

                if 'Reverse mode' in line:
                    reverse = True

                if 'connected to' in line:
                    local_ip    = line.split('local ')[-1].split()[0]
                    local_port  = line.split('local ')[-1].split()[2]
                    remote_ip   = line.split('connected to ')[-1].split()[0]
                    remote_port = line.split('connected to ')[-1].split()[2]

                if 'Starting Test:' in line:
                    protocol = line.split('protocol:')[-1].split()[0].rstrip(',')
                    measurement_section = True

                if ('sec ' in line) and (measurement_section):
                    line = line.split(']')[-1].lstrip()
                    values = line.split()

                    data.append({
                        'protocol' : protocol.lower(),
                        'src-addr' : remote_ip if reverse else local_ip,
                        'src-port' : remote_port if reverse else local_port,
                        'dst-addr' : local_ip if reverse else remote_ip,
                        'dst-port' : local_port if reverse else remote_port,
                        'interval-start' : base_timestamp + float(values[0].split('-')[0]),
                        'interval-end' : base_timestamp + float(values[0].split('-')[1]), 
                        'data-volume' : float(values[2]) * multiplier[values[3]],
                        'data-rate' : float(values[4]) * multiplier[values[5]],
                        'jitter' : float(values[6]),
                        'pckt-lost' : int(values[8].split('/')[0]),
                        'pckt-total' : int(values[8].split('/')[1])
                        })

                if 'Test Complete' in line:
                    measurement_section = False

            data = pd.DataFrame(data)
            data['client-id'] = node

            iperf3_data = pd.concat([iperf3_data, data], ignore_index = True)

    iperf3_data.to_csv(os.path.join(trace_dir, ("%s.csv" % ('iperf3'))), sep = ',')

def aggregate_csv(input_dir, trace_nr, prefix = 'cbt', nodes = ['ap1', 'ap2', 'ap3', 'ap4']):
    
    node_info = get_node_info(input_dir, trace_nr)
    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))

    data = pd.DataFrame()
    for node in nodes:
        # dir w/ multiple .csv files named w/ pattern <node>.*.csv
        csv_dir = os.path.join(trace_dir, ("%s" % (node)))
        for filename in sorted(glob.glob(os.path.join(csv_dir, ('%s.*.csv' % (prefix))))):
            
            # read .csv file
            _data = pd.read_csv(filename)
            # if prefix is 'cbt', pre-processing required
            if prefix == 'cbt':
                laps = extract_laps(input_dir, trace_nr)
                _data = analysis.trace.utils.metrics.get_channel_util(_data, timestamps = [laps.iloc[0]['start-time'], laps.iloc[-1]['end-time']])
            
            # add node id and mac addr columns
            _data['id'] = node
            _data['mac-addr'] = ''
            if node in node_info['id'].tolist():
                _data['mac-addr'] = node_info[node_info['id'].str.contains(node)].iloc[0]['mac-addr']
                
            # append to aggregated .csv file
            data = pd.concat([_data, data], ignore_index = True)
            
    # save aggrgated .csv file
    data.to_csv(os.path.join(trace_dir, ("%s.csv" % (prefix))), sep = ',')
    
def load_best(database, metric):

    # 1) db key
    gt_db = ('/%s/%s' % ('best', metric))
    if gt_db not in database.keys():
        sys.stderr.write("""[ERROR] database not available (%s). abort.\n""" % (gt_db))
        return

    # 2) load
    gt_data = database.select(gt_db).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
    # 3) some data cleaning...
    # FIXME: why do we end up w/ duplicate 'interval-tmstmp' values?
    gt_data = gt_data.drop_duplicates(subset = ['interval-tmstmp'])
    # rename 'best' to 'get'
    # FIXME : this shouldn't be necessary but...
    gt_data.rename(index = str, columns = {'best' : 'gt'}, inplace = True)
    # 3) fill column with best values
    gt_data['gt-val'] = 0.0
    for mac in gt_data['gt'].unique():
        gt_data.loc[(gt_data['gt'] == mac), 'gt-val'] = gt_data[gt_data['gt'] == mac][mac]

    return gt_data

def load_and_merge(database, key, to_merge):

    # 1) load
    data = database.select(key).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
    # 2) merge w/ to_merge
    data = pd.merge(data[['interval-tmstmp', 'best']], to_merge, on = ['interval-tmstmp'], how = 'left')
    # get rid of 'nans'
    data.dropna(subset = ['best'], inplace = True)
    # 3) fill column with best values
    data['best-val'] = 0.0
    for mac in data['best'].unique():
        data.loc[(data['best'] == mac), 'best-val'] = data[data['best'] == mac][mac]
    # FIXME: fill any nan values w/ 0.0 (is this necessary?)
    data['best-val'] = data['best-val'].fillna(0.0)

    return data

def get_list(input_dir):

    filename = os.path.join(input_dir, ("trace-info.csv"))
    if not os.path.isfile(filename):
        sys.stderr.write("""%s: [ERROR] no 'trace-info.csv' at %s\n""" % (sys.argv[0], input_dir))
        # return empty dataframe
        return pd.DataFrame()

    trace_list = pd.read_csv(filename)
    return trace_list

def get_info(input_dir, trace_nr, mode = 'rx'):

    trace_info = pd.DataFrame()

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database_file = os.path.join(trace_dir, "processed/database.hdf5")
    if not os.path.isfile(database_file):
        sys.stderr.write("""%s: [ERROR] no .hdf5 available at %s\n""" % (sys.argv[0], trace_dir))
        # return empty dataframe
        return trace_info

    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    database_name = ('/%s/%s' % ('dataset-stats', mode))
    if database_name not in database.keys():
        sys.stderr.write("""%s: [ERROR] no dataset stats available yet\n""" % (sys.argv[0]))
        # return empty dataframe
        return trace_info

    # load trace data into dataframe and return
    trace_info = database.select(database_name)
    return trace_info

def get_node_info(input_dir, trace_nr):
    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    return pd.read_csv(os.path.join(trace_dir, ("node-info.csv")))
    
def merge_gps(input_dir, trace_nr, metric, cell_size = 20.0):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    #   - get /best/<metric>
    base_db = analysis.trace.utils.data.extract_best(input_dir, trace_nr, metric)
    nodes = ['m1', 'w1', 'w2', 'w3']
    data = database.select(base_db)[['timed-tmstmp'] + nodes].sort_values(by = ['timed-tmstmp']).reset_index(drop = True)
    #   - get gps data
    gps_data = analysis.gps.get_data(input_dir, trace_dir)
    gps_data['timed-tmstmp'] = gps_data['timestamp'].astype(float)
    # merge /best/<metric> & gps data
    data = pd.merge(data, gps_data[['timed-tmstmp', 'lat', 'lon']], on = ['timed-tmstmp'], how = 'left')
    # fix <lat, lon> gaps via interpolation
    analysis.trace.utils.data.fix_gaps(data, subset = ['lat', 'lon'])
    data = data.dropna(subset = ['lat', 'lon']).reset_index(drop = True)
    # add cell info
    analysis.gps.add_cells(data, cell_size = cell_size, bbox = [LONW, LATS, LONE, LATN])

    return data

def extract_bitrates(input_dir, trace_nr, protocol = 'udp', time_delta = 0.5, force_calc = False):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))
    # FIXME : this should be loaded from a file
    nodes = ['m1', 'w1', 'w2', 'w3']
    for node in nodes:
        for sub_type in ['beacons', 'bitrates']:
            db = ('/%s/%s/%s' % (node, 'basic', sub_type))
            if db in database.keys():
                if force_calc:
                    database.remove(db)
                else:
                    sys.stderr.write("""[WARNING] %s already in database. skipping data extraction for node %s.\n""" % (db, node))
                    if node in nodes:
                        nodes.remove(node)

    for node in nodes:
        for filename in sorted(glob.glob(os.path.join(trace_dir, ('%s/monitor*.csv' % (node))))):

            chunksize = 10 ** 5
            for chunk in pd.read_csv(filename, chunksize = chunksize):

                # # extract beacon frames & store them directly in database
                # beacon_data = chunk[ (chunk['wlan type-subtype'] == 'Beacon frame') ][['epoch time', 'wlan tsf time', 'wlan rssi', 'wlan data rate', 'wlan seq number']].reset_index(drop = True)
                # beacon_data['wlan data rate'] = beacon_data['wlan data rate'].astype(float)
                # utils.hdfs.to_hdfs(beacon_data, ('/%s/%s/%s' % (node, 'basic', 'beacons')), database)

                # extract wlan data frame data
                qos_data = chunk[ (chunk['ip proto'] == protocol.upper()) ].reset_index(drop = True)
                # analyze for intervals of .5 seconds
                qos_data['timed-tmstmp'] = qos_data['epoch time'].apply(analysis.trace.utils.metrics.custom_round)
                # get interval timestamps for later merge
                proc_qos_data = qos_data[['timed-tmstmp']].drop_duplicates().reset_index(drop = True)
                # calculate each metric, and merge according to timed-tmstmp 
                for metric in ['throughput', 'wlan data rate']:
                    res = analysis.trace.utils.metrics.process_metric(qos_data, metric, time_delta = time_delta)
                    proc_qos_data = pd.merge(proc_qos_data, res, on = ['timed-tmstmp'], how = 'left')

                # save bitrates in database
                utils.hdfs.to_hdfs(proc_qos_data, ('/%s/%s/%s' % (node, 'basic', 'bitrates')), database)

def extract_distances(input_dir, trace_nr, time_delta = 0.5, force_calc = False):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    db_name = ('/%s/%s' % ('gps', 'distances'))
    if db_name in database.keys():
        
        if force_calc:
            database.remove(db_name)
        else:
            return

    # extract gps data
    gps_data = analysis.trace.utils.gps.get_data(input_dir, trace_dir, tag_laps = True)
    # oversample to .5 time_delta
    gps_data['timed-tmstmp'] = gps_data['timestamp'].astype(float)
    # calculate distances to fixed positions
    # FIXME : this should be loaded from a file
    ap_pos = {
        'p1' : {'lat' : 41.178563, 'lon' : -8.596012}, 
        'p2' : {'lat' : 41.178518, 'lon' : -8.595366}, 
        'ref' : ref
    }
    pos = [ [ row['lat'], row['lon'] ] for index, row in gps_data[['lat', 'lon']].iterrows() ]
    for ap in ap_pos:
        gps_data[ap] = [ utils.mapping.utils.gps_to_dist(ap_pos[ap]['lat'], ap_pos[ap]['lon'], p[0], p[1]) for p in pos ]

    gps_data = gps_data.sort_values(by = ['timestamp']).reset_index(drop = True)
    utils.hdfs.to_hdfs(gps_data[['timestamp', 'lat', 'lon', 'lap', 'direction'] + list(ap_pos.keys())], db_name, database)

def extract_channel_util(input_dir, trace_nr, time_delta = 0.5):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    aps = ['ap1', 'ap2', 'ap3', 'ap4']
    cutil = pd.DataFrame()
    for ap in aps:

        db_name = ('/%s/%s/%s' % (ap, 'basic', 'channel-util'))
        if db_name in database.keys():
            continue

        cbt = pd.DataFrame()
        for filename in sorted(glob.glob(os.path.join(trace_dir, ('cbt*.csv' % (ap))))):
            cbt = pd.concat([cbt, pd.read_csv(filename)], ignore_index = True)

        print(cbt)

        cbt = cbt.sort_values(by = ['timestamp']).reset_index(drop = True)
        cutil = analysis.trace.utils.metrics.get_channel_util(cbt)
        cutil = cutil.sort_values(by = ['timestamp']).reset_index(drop = True)
        utils.hdfs.to_hdfs(cutil[['timestamp', 'freq', 'cutil']], db_name, database)

def get_data(node, metric, database):

    data = pd.DataFrame()
    if metric in ['throughput', 'wlan data rate']:
        db_name = ('/%s/%s/%s' % (node, 'basic', 'bitrates'))
        if db_name not in database.keys():
            return None
        data = database.select(db_name)[['timed-tmstmp', metric]].sort_values(by = ['timed-tmstmp']).reset_index(drop = True)

    elif metric == 'rss':
        db_name = ('/%s/%s/%s' % (node, 'basic', 'beacons'))
        if db_name not in database.keys():
            return None

        data = database.select(db_name)[['epoch time', 'wlan rssi']].sort_values(by = ['epoch time']).reset_index(drop = True)
        data.rename(index = str, columns = {'wlan rssi' : metric}, inplace = True)
        data['timed-tmstmp'] = data['epoch time'].apply(analysis.metrics.custom_round)
        data = data[['timed-tmstmp', 'rss']].groupby(['timed-tmstmp']).max().reset_index().sort_values(by = ['timed-tmstmp'])

    elif metric == 'distances':
        db_name = ('/%s/%s' % ('gps', 'distances'))
        if db_name not in database.keys():
            return None

        data = database.select(db_name).sort_values(by = ['timestamp']).reset_index(drop = True)
        if node in ['m1', 'w2']:
            data = data[['timestamp', 'p2']]
            data.rename(index = str, columns = {'timestamp' : 'timed-tmstmp', 'p2' : metric}, inplace = True)
        else:
            data = data[['timestamp', 'p1']]
            data.rename(index = str, columns = {'timestamp' : 'timed-tmstmp', 'p1' : metric}, inplace = True)

    return data

def extract_best(input_dir, trace_nr, metric = 'throughput', smoothen = False, force_calc = False):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))
    db_name = ('/%s/%s' % ('best', metric))
    if db_name in database.keys():
        if force_calc:
            database.remove(db_name)
        else:
            sys.stderr.write("""[INFO] %s already in database. skipping data extraction.\n""" % (db_name))
            return db_name

    nodes = ['m1', 'w1', 'w2', 'w3']
    best = pd.DataFrame(columns = ['timed-tmstmp'])
    for node in nodes:

        data = get_data(node, metric, database)
        if data.empty:
            continue

        # update best w/ mac info
        # FIXME: is the use of 'outer' merge correct here?
        data[node] = data[metric]
        best = pd.merge(best, data[ ['timed-tmstmp', node] ], on = ['timed-tmstmp'], how = 'outer')

    # drop duplicate timestamps (if we merged, why should there be duplicates?)
    best.drop_duplicates(subset = ['timed-tmstmp'], inplace = True)
    # sort by time
    best = best.sort_values(by = ['timed-tmstmp']).reset_index(drop = True)
    best[nodes] = best[nodes].fillna(0.0)
    
    # smoothen curves for all
    if smoothen:
        for node in nodes:
            analysis.metrics.smoothen(best, column = node, span = 2)

    # calculate the node w/ max. value at each row
    if metric == 'dist':
        best['best'] = best[nodes].idxmin(axis = 1)
        best['best-val'] = best[nodes].min(axis = 1)
    else:
        best['best'] = best[nodes].idxmax(axis = 1)
        best['best-val'] = best[nodes].max(axis = 1)

    parsing.utils.to_hdf5(best, ('/%s/%s' % ('best', metric)), database)
    return ('/%s/%s' % ('best', metric))

def get_distances(input_dir, trace_nr):

    # get mac addr, info
    mac_addrs = pd.read_csv(os.path.join(input_dir, ("mac-info.csv")))
    # for quick access to aps and clients
    clients = mac_addrs[mac_addrs['type'] == 'client']

    # save data on .hdf5 database
    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))

    dist_db = ('/%s' % ('dist-data'))
    if dist_db not in database.keys():
        sys.stderr.write("""[INFO] %s not in database. aborting.\n""" % (dist_db))
        return

    return database.select(dist_db).sort_values(by = ['interval-tmstmp']).reset_index(drop = True)

def fix_gaps(data, subset, column = 'timed-tmstmp'):
    # FIXME : still don't know how to do this without copying, hence the variable '_data'
    _data = data[[column] + subset]
    # use pandas native time-based interpolation, which requires a datetime index
    # FIXME : the type of interpolation should be defined as a parameter later on
    _data['datetime'] = pd.to_datetime(_data[column], unit = 's')
    _data.set_index(['datetime'], inplace = True)
    _data.interpolate(method = 'time', inplace = True)
    # update subset columns w/ the interpolated values
    data.update(_data[subset].reset_index(drop = True))

def extract_moving_data(gps_data, method = 'dropna'):

    if method == 'dropna':
        # find the interval-tmstmps of the first and last rows w/ gps positions
        ix = gps_data.dropna(subset = ['lat', 'lon'], how = 'all').iloc[[0,-1]].index.tolist()
        return gps_data.iloc[ix[0]:ix[-1]].sort_values(by = ['interval-tmstmp']).reset_index(drop = True)

    elif method == 'lap-number':
        return gps_data[(gps_data['lap-number'] >= 1) & (gps_data['lap-number'] <= 5)].sort_values(by = ['interval-tmstmp']).reset_index(drop = True)
