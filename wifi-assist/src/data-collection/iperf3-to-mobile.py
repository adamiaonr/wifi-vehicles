import pandas as pd
import numpy as np
import os
import csv
import json
import argparse
import subprocess
import sys
import glob
import math
import time
# for parallel processing of sessions
import multiprocessing as mp 
import hashlib
import signal

from random import randint
from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple

from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict

def signal_handler(signal, frame):
    global stop_loop
    stop_loop = True

def test(time, ip_server, port = 5201, proto = 'udp', bitrate = '54'):

    output = "N/A"
    # iperf3 -t <time> -c <ip_server> -u (or nothing) -b <bitrate>M
    cmd = ["iperf3", "-V", "-J", "-O", "1", "-i", "0.5", "-t", str(time), "-c", str(ip_server), "-p", str(port), ("-u" if proto == 'udp' else ''), "-b", str(bitrate) + 'M', "--get-server-output"]

    try:
        output = subprocess.check_output(cmd, stdin = None, stderr = None, shell = False, universal_newlines = False)
    except subprocess.CalledProcessError:
        return -1, output

    return 0, output

def parse_server_output(server_output_text):

    # collect iperf3 server output as a list of dictionaries
    output = []
    # split into lines
    lines = server_output_text.splitlines()

    # lines of interest are from line 8 on
    for line in lines[8:]:
        
        line = line.split(' ')

        to_append = OrderedDict()
        to_append['start'] = float(line[5].split('-')[0])
        to_append['end'] = float(line[5].split('-')[1])
        
        # find index i of line element w/ '/sec' in it, the bw value is i - 1 
        to_append['bw'] = float(line[line.index([s for s in line if '/sec' in s][0]) - 1])
        # find index i of second line element w/ '/' in it. split it by the '/'. 
        to_append['lost'] = float(line[line.index([s for s in line if '/' in s][1])].split('/')[0])
        to_append['total'] = float(line[line.index([s for s in line if '/' in s][1])].split('/')[1])

        output.append(to_append)

    return output


if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--bitrates", 
         help = """list of iperf3 bitrates (in Mbps) to try out, separated by ','. e.g.: '--bitrates 11,54,72'""")

    parser.add_argument(
        "--protocols", 
         help = """list of protocols (UDP or TCP), separated by ','. e.g.: '--protocols UDP,TCP'""")

    parser.add_argument(
        "--duration", 
         help = """duration of the test (in seconds). e.g.: '--duration 120'""")

    parser.add_argument(
        "--ip-server", 
         help = """ip addr of iperf3 server. e.g.: '--ip-server 10.10.10.111'""")

    parser.add_argument(
        "--port", 
         help = """port used by iperf3 server. e.g.: '--port 5204'""")

    parser.add_argument(
        "--rounds", 
         help = """number of rounds for each parameter combination. e.g.: '--rounds 5'""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save .csv files""")

    args = parser.parse_args()

    if not args.bitrates:
        args.bitrates = "54"

    if not args.duration:
        args.duration = "5"

    if not args.rounds:
        args.rounds = "5"

    if not args.protocols:
        args.protocols = "udp"

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    reports_file = os.path.join(args.output_dir, ("iperf3-to-mobile.report." + str(args.bitrates) + ".csv"))
    results_file = os.path.join(args.output_dir, ("iperf3-to-mobile.results." + str(args.bitrates) + ".csv"))

    if not args.ip_server:
        sys.stderr.write("""%s: [ERROR] please supply an iperf3 server ip\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # register CTRL+C catcher
    signal.signal(signal.SIGINT, signal_handler)
    # columns of data frames
    reports = pd.DataFrame(columns = ['time', 'proto', 'duration', 'transfer', 'trgt-bw', 'res-bw', 'loss', 'total'])
    results = pd.DataFrame(columns = ['time', 'proto', 'duration', 'transfer', 'trgt-bw', 'res-bw', 'jitter', 'lost', 'total', 'cpu-sndr', 'cpu-rcvr'])
    # write the column names to the file
    reports.to_csv(reports_file, index = False, index_label = False)
    results.to_csv(results_file, index = False, index_label = False)
    # range tuples are used to compare ranges of time
    Range = namedtuple('Range', ['start', 'end'])

    # keep iperfing till a CTRL+C is caught...
    stop_loop = False
    while (stop_loop == False):
        for protocol in [p.lower() for p in args.protocols.split(',')]:
            for bitrate in [b for b in args.bitrates.split(',')]:

                start_timestamp = time.time()
                code, output = test(int(args.duration), args.ip_server, args.port, protocol, bitrate)
                
                if code < 0:
                    continue

                output = json.loads(output)
                # the iperf3 server produces output every second (if the '--get-server-ouput' option is used)
                # it needs to be parsed directly from text, as it is not provided in json format
                output_server = []
                if 'server_output_text' in output:
                    output_server = parse_server_output(output['server_output_text'])

                k = 0
                _interval = []
                for i, interval in enumerate(output['intervals']):

                    if not output_server:
                        _interval.append({'loss' : 0.0})
                    else:

                        r1 = Range(start = float(interval['sum']['start']), end = float(interval['sum']['end']))
                        r2 = Range(start = output_server[k]['start'], end = output_server[k]['end'])

                        while not ((r2.end >= r1.end) or (k == (len(output_server) - 1))):
                            k += 1
                            r2 = Range(start = output_server[k]['start'], end = output_server[k]['end'])

                        loss = 0.0
                        if output_server[k]['total'] != 0.0:
                            loss = output_server[k]['lost'] / output_server[k]['total']
                        _interval.append({'loss' : loss})

                if output['start']['test_start']['protocol'] == 'UDP':

                    # 'intervals'
                    # this assumes 1 sec intervals
                    for i, interval in enumerate(output['intervals']):

                        # rely on local output as much as possible (it may happen that server output is lost)
                        reports = reports.append({
                            'time'      : start_timestamp + interval['sum']['end'],
                            'proto'     : output['start']['test_start']['protocol'], 
                            'duration'  : interval['sum']['seconds'],
                            'transfer'  : interval['sum']['bytes'], 
                            'trgt-bw'   : float(bitrate) * 1000000.0, 
                            'res-bw'    : interval['sum']['bits_per_second'],
                            'loss'      : _interval[i]['loss'],
                            'total'     : interval['sum']['packets']}, ignore_index = True)

                    results = results.append({
                        'time'      : start_timestamp,
                        'proto'     : output['start']['test_start']['protocol'], 
                        'duration'  : output['end']['sum']['seconds'],
                        'transfer'  : output['end']['sum']['bytes'], 
                        'trgt-bw'   : float(bitrate) * 1000000.0, 
                        'res-bw'    : output['end']['sum']['bits_per_second'],
                        'jitter'    : output['end']['sum']['jitter_ms'],
                        'lost'      : output['end']['sum']['lost_packets'],
                        'total'     : output['end']['sum']['packets'],
                        'cpu-sndr'  : output['end']['cpu_utilization_percent']['host_total'],
                        'cpu-rcvr'  : output['end']['cpu_utilization_percent']['remote_total']}, ignore_index = True)

                else:
                    sys.stderr.write("""%s: [ERROR] TCP is not supported (yet)\n""" % sys.argv[0]) 
                    sys.exit(1)

                # append lines to .csv files
                reports.to_csv(reports_file, mode = 'a', header = False, index = False, index_label = False)
                results.to_csv(results_file, mode = 'a', header = False, index = False, index_label = False)
                # clear the results dataframe
                reports = reports.iloc[0:0]
                results = results.iloc[0:0]

    sys.exit(0)

