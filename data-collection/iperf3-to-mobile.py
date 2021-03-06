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

def restart_service(service = 'ntp'):
    cmd = ["service", service, "restart"]
    proc = subprocess.call(cmd)

def get_iface_mode(iface):

    output = 'managed'
    cmd = ['iw', 'dev', str(iface), 'info']

    try:
        output = subprocess.check_output(cmd, stdin = None, stderr = None, shell = False, universal_newlines = False)
    except subprocess.CalledProcessError:
        return -1, output

    output = output.splitlines()
    return 0, output[output.index([s for s in output if 'type' in s][0])].split(' ')[-1]

def restart_iperf3_server(remote_login, port):
    # remotely execute 2 tasks:
    # - kill iperf3 server w/ specific port
    # - start iperf3 server
    cmd = ['restart-iperf3-server', remote_login, port]

    output = ''
    try:
        output = subprocess.check_output(cmd, stdin = None, stderr = None, shell = False, universal_newlines = False)
    except subprocess.CalledProcessError:
        return -1, output

    return 0, output

def capture(iface, output_file, mode = 'managed'):

    cmd = ''
    if mode == 'managed':
        cmd = ["tcpdump", "-i", iface, "-s0", "-w", output_file]
    elif mode == 'monitor':
        cmd = ["tcpdump", "-i", iface, "-y", "IEEE802_11_RADIO", "-s0", "-w", output_file]

    proc = subprocess.Popen(cmd)
    
def start_iperf3(ip_server, port = 5201, proto = 'udp', bitrate = '54', time = 180, reverse = False):

    output = "N/A"

    # iperf3 -t <time> -c <ip_server> -u (or nothing) -b <bitrate>M
    if proto == 'udp':
        cmd = ["iperf3", "-V", "-J", "-t", str(time), "-c", str(ip_server), "-p", str(port), ("-u" if proto == 'udp' else ''), "-b", str(bitrate) + 'M', "--get-server-output"]
    elif proto == 'tcp':
        cmd = ["iperf3", "-V", "-J", "-t", str(time), "-c", str(ip_server), "-p", str(port)]
    else:
        sys.stderr.write("""%s:::start_iperf3() : [ERROR] unknown protocol : %s\n""" % (sys.argv[0], proto))
        return -1, output

    # if reverse mode is used, don't gather server stats (we're the server already)
    if reverse:
        cmd.append('-R')
        cmd.remove('--get-server-output')

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

        to_append['start'] = float(line[line.index([s for s in line if '-' in s][0])].split('-')[0])
        to_append['end'] = float(line[line.index([s for s in line if '-' in s][0])].split('-')[1])
        
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
        "--bitrate", 
         help = """iperf3 bitrate (in Mbps) to use in test. e.g.: '--bitrate 11'""")

    parser.add_argument(
        "--protocol", 
         help = """protocol to use ('udp' or 'tcp')""")

    # parser.add_argument(
    #     "--duration", 
    #      help = """duration of the test (in seconds). e.g.: '--duration 120'""")

    parser.add_argument(
        "--control-login", 
         help = """used for remote command execution. e.g., --control-login it@10.10.13.175""")

    parser.add_argument(
        "--ip-server", 
         help = """ip addr of iperf3 server. e.g.: '--ip-server 10.10.10.111'""")

    parser.add_argument(
        "--port", 
         help = """port used by iperf3 server. e.g.: '--port 5204'""")

    parser.add_argument(
        "--reverse", 
         help = """reverse client & server roles in iperf3""",
         action = 'store_true')

    # parser.add_argument(
    #     "--rounds", 
    #      help = """number of rounds for each parameter combination. e.g.: '--rounds 5'""")

    parser.add_argument(
        "--monitor-iface", 
         help = """wifi iface on which to capture packets. e.g.: '--iface wlx24050f615114'""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save .csv files""")

    parser.add_argument(
        "--restart-ntp", 
         help = """restart ntp daemon""",
         action = 'store_true')

    args = parser.parse_args()

    if not args.bitrate:
        args.bitrate = "54"

    # if not args.duration:
    #     args.duration = "5"

    # if not args.rounds:
    #     args.rounds = "5"

    if not args.protocol:
        args.protocol = "udp"
    else:
        args.protocol = args.protocol.lower()

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # restart ntp
    if args.restart_ntp:
        restart_service('ntp')

    timestamp = str(time.time()).split('.')[0]
    reports_file = os.path.join(args.output_dir, ("iperf3-to-mobile.report." + str(args.bitrate) + "." + timestamp + ".csv"))
    results_file = os.path.join(args.output_dir, ("iperf3-to-mobile.results." + str(args.bitrate) + "." + timestamp + ".csv"))

    if not args.ip_server:
        sys.stderr.write("""%s: [ERROR] please supply an iperf3 server ip\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # register CTRL+C catcher
    signal.signal(signal.SIGINT, signal_handler)
    # columns of data frames
    reports = None
    results = None

    if args.protocol == 'udp':

        reports = pd.DataFrame(columns = ['time', 'proto', 'duration', 'transfer', 'trgt-bw', 'res-bw', 'loss', 'total'])
        results = pd.DataFrame(columns = ['time', 'proto', 'duration', 'transfer', 'trgt-bw', 'res-bw', 'jitter', 'lost', 'total', 'cpu-sndr', 'cpu-rcvr'])

    elif args.protocol == 'tcp':

        reports = pd.DataFrame(columns = ['time', 'proto', 'duration', 'bytes', 'bitrate', 'retransmits', 'cwnd'])
        results = pd.DataFrame(columns = ['time', 'proto', 'duration', 'bytes-sndr', 'bytes-rcvr', 'bitrate-sndr', 'bitrate-rcvr', 'cpu-sndr', 'cpu-rcvr'])

    else:
        sys.stderr.write("""%s: [ERROR] unknown protocol : %s\n""" % (sys.argv[0], args.protocol))
        sys.exit(1)

    # write the column names to the file
    reports.to_csv(reports_file, index = False, index_label = False)
    results.to_csv(results_file, index = False, index_label = False)
    # range tuples are used to compare ranges of time
    Range = namedtuple('Range', ['start', 'end'])

    # start capturing packets (if specified)
    if args.monitor_iface:

        # if iface is in monitor mode, capture in 'monitor mode', otherwise in 'managed' mode (no IEEE802_11_RADIO flags)
        rc, capture_mode = get_iface_mode(args.monitor_iface)
        if rc == 0:
            capture_file = os.path.join(args.output_dir, ("%s.capture.%s.pcap" % (capture_mode, str(timestamp))))
            capture(args.monitor_iface, capture_file)

    reverse = False
    if args.reverse:
        reverse = True

    # keep iperfing till a CTRL+C is caught...
    stop_loop = False
    while (stop_loop == False):

        # # wait a random interval (0 to 1 sec) before (re-)starting
        # if args.protocol == 'udp':
        #     time.sleep(randint(0,1))

        start_timestamp = time.time()

        # restart iperf3 server on remote side
        restart_iperf3_server(args.control_login, args.port)
        # start client run
        code, output = start_iperf3(
            ip_server = args.ip_server, port = args.port, 
            proto = args.protocol, bitrate = args.bitrate, 
            reverse = reverse)
        
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
                    'trgt-bw'   : float(args.bitrate) * 1000000.0, 
                    'res-bw'    : interval['sum']['bits_per_second'],
                    'loss'      : _interval[i]['loss'],
                    'total'     : interval['sum']['packets']}, ignore_index = True)

            results = results.append({
                'time'      : start_timestamp,
                'proto'     : output['start']['test_start']['protocol'], 
                'duration'  : output['end']['sum']['seconds'],
                'transfer'  : output['end']['sum']['bytes'], 
                'trgt-bw'   : float(args.bitrate) * 1000000.0, 
                'res-bw'    : output['end']['sum']['bits_per_second'],
                'jitter'    : output['end']['sum']['jitter_ms'],
                'lost'      : output['end']['sum']['lost_packets'],
                'total'     : output['end']['sum']['packets'],
                'cpu-sndr'  : output['end']['cpu_utilization_percent']['host_total'],
                'cpu-rcvr'  : output['end']['cpu_utilization_percent']['remote_total']}, ignore_index = True)

        else:

            for i, interval in enumerate(output['intervals']):

                reports = reports.append({
                    'time'          : start_timestamp + interval['sum']['end'],
                    'proto'         : output['start']['test_start']['protocol'], 
                    'duration'      : interval['sum']['seconds'],
                    'bytes'         : interval['sum']['bytes'], 
                    'bitrate'       : interval['sum']['bits_per_second'],
                    'retransmits'   : interval['sum']['retransmits'],
                    'cwnd'          : interval['streams'][-1]['snd_cwnd']}, ignore_index = True)

            results = results.append({
                'time'          : start_timestamp,
                'proto'         : output['start']['test_start']['protocol'], 
                'duration'      : output['end']['sum_received']['seconds'],
                'bytes-sndr'    : output['end']['sum_sent']['bytes'], 
                'bytes-rcvr'    : output['end']['sum_received']['bytes'],
                'bitrate-sndr'  : output['end']['sum_sent']['bits_per_second'],
                'bitrate-rcvr'  : output['end']['sum_received']['bits_per_second'],
                'cpu-sndr'      : output['end']['cpu_utilization_percent']['host_total'],
                'cpu-rcvr'      : output['end']['cpu_utilization_percent']['remote_total']}, ignore_index = True)

        # append lines to .csv files
        reports.to_csv(reports_file, mode = 'a', header = False, index = False, index_label = False)
        results.to_csv(results_file, mode = 'a', header = False, index = False, index_label = False)
        # clear the results dataframe
        reports = reports.iloc[0:0]
        results = results.iloc[0:0]

    cmd = ["pkill", "-f", "tcpdump"]
    proc = subprocess.call(cmd)

    sys.exit(0)

