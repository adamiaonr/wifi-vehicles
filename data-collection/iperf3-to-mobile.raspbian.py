import os
import csv
import json
import argparse
import subprocess
import sys
import glob
import math
import time
import hashlib
import signal

from random import randint
from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple

def signal_handler(signal, frame):
    global stop_loop
    stop_loop = True

def restart_service(service = 'ntp'):
    cmd = ["service", service, "restart"]
    proc = subprocess.call(cmd)

def capture(iface, output_file):
    # tcpdump -i <iface> -y IEEE802_11_RADIO -s0 -w <file>
    cmd = ["tcpdump", "-i", iface, "-s0", "-w", output_file]
    proc = subprocess.Popen(cmd)

def start_iperf3(ip_server, port = 5201, proto = 'udp', bitrate = '54', time = 5):

    output = "N/A"

    # iperf3 -t <time> -c <ip_server> -u (or nothing) -b <bitrate>M
    if proto == 'udp':
        cmd = ["iperf3", "-V", "-J", "-t", str(time), "-c", str(ip_server), "-p", str(port), ("-u" if proto == 'udp' else ''), "-b", str(bitrate) + 'M', "--get-server-output"]
    elif proto == 'tcp':
        time = 10
        cmd = ["iperf3", "-V", "-J", "-t", str(time), "-c", str(ip_server), "-p", str(port)]
    else:
        sys.stderr.write("""%s:::start_iperf3() : [ERROR] unknown protocol : %s\n""" % (sys.argv[0], proto))
        return -1, output

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
        "--ip-server", 
         help = """ip addr of iperf3 server. e.g.: '--ip-server 10.10.10.111'""")

    parser.add_argument(
        "--port", 
         help = """port used by iperf3 server. e.g.: '--port 5204'""")

    # parser.add_argument(
    #     "--rounds", 
    #      help = """number of rounds for each parameter combination. e.g.: '--rounds 5'""")

    parser.add_argument(
        "--iface", 
         help = """wifi iface on which to capture packets. e.g.: '--iface wlx24050f9e2cb1'""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save .csv files""")

    parser.add_argument(
        "--no-log", 
         help = """do not save any .csv files""",
         action = 'store_true')

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

    if not args.ip_server:
        sys.stderr.write("""%s: [ERROR] please supply an iperf3 server ip\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # register CTRL+C catcher
    signal.signal(signal.SIGINT, signal_handler)

    # restart ntp
    if args.restart_ntp:
        restart_service('ntp')

    logging = True
    if args.no_log:
        loggging = False

    timestamp = str(time.time()).split('.')[0]
    if logging:

        reports_file = os.path.join(args.output_dir, ("iperf3-to-mobile.report." + str(args.bitrate) + "." + timestamp + ".csv"))
        results_file = os.path.join(args.output_dir, ("iperf3-to-mobile.results." + str(args.bitrate) + "." + timestamp + ".csv"))

        attrs_reports = None
        attrs_results = None
        if args.protocol == 'udp':

            attrs_reports = ['time', 'proto', 'duration', 'transfer', 'trgt-bw', 'res-bw', 'loss', 'total']
            attrs_results = ['time', 'proto', 'duration', 'transfer', 'trgt-bw', 'res-bw', 'jitter', 'lost', 'total', 'cpu-sndr', 'cpu-rcvr']

        elif args.protocol == 'tcp':

            attrs_reports = ['time', 'proto', 'duration', 'bytes', 'bitrate', 'retransmits', 'cwnd']
            attrs_results = ['time', 'proto', 'duration', 'bytes-sndr', 'bytes-rcvr', 'bitrate-sndr', 'bitrate-rcvr', 'cpu-sndr', 'cpu-rcvr']

        else:
            sys.stderr.write("""%s: [ERROR] unknown protocol : %s\n""" % (sys.argv[0], args.protocol))
            sys.exit(1)

        reports = csv.writer(open(reports_file, 'wb+', 0))
        reports.writerow(attrs_reports)

        results = csv.writer(open(results_file, 'wb+', 0))
        results.writerow(attrs_results)

    # start capturing packets (if specified)
    if args.iface and logging:
        capture_file = os.path.join(args.output_dir, ("iperf3-to-mobile.capture." + str(args.bitrate) + "." + timestamp + ".pcap"))
        capture(args.iface, capture_file)

    # range tuples are used to compare ranges of time
    Range = namedtuple('Range', ['start', 'end'])

    # keep iperfing till a CTRL+C is caught...
    stop_loop = False
    while (stop_loop == False):

        start_timestamp = time.time()
        code, output = start_iperf3(ip_server = args.ip_server, port = args.port, bitrate = args.bitrate, proto = args.protocol)
        
        if code < 0 or (not logging):
            sys.stderr.write("""%s: [ERROR] iperf3 command failed : %s\n""" % (sys.argv[0], output))
            time.sleep(1)
            continue

        output = json.loads(output)

        # # the iperf3 server produces output for each second of the test (if the '--get-server-output' option is used)
        # # it needs to be parsed directly from text, as it is not provided in json format
        # output_server = []
        # if 'server_output_text' in output:
        #     output_server = parse_server_output(output['server_output_text'])

        # k = 0
        # _interval = []
        # for i, interval in enumerate(output['intervals']):

        #     if not output_server:
        #         _interval.append({'loss' : 0.0})
        #     else:

        #         r1 = Range(start = float(interval['sum']['start']), end = float(interval['sum']['end']))
        #         r2 = Range(start = output_server[k]['start'], end = output_server[k]['end'])

        #         while not ((r2.end >= r1.end) or (k == (len(output_server) - 1))):
        #             k += 1
        #             r2 = Range(start = output_server[k]['start'], end = output_server[k]['end'])

        #         loss = 0.0
        #         if output_server[k]['total'] != 0.0:
        #             loss = output_server[k]['lost'] / output_server[k]['total']
        #         _interval.append({'loss' : loss})

        # if output['start']['test_start']['protocol'] == 'UDP':

        #     # 'intervals'
        #     # this assumes 1 sec intervals
        #     for i, interval in enumerate(output['intervals']):

        #         # rely on local output as much as possible (it may happen that server output is lost)
        #         rprts = {
        #             'time'      : start_timestamp + interval['sum']['end'],
        #             'proto'     : output['start']['test_start']['protocol'], 
        #             'duration'  : interval['sum']['seconds'],
        #             'transfer'  : interval['sum']['bytes'], 
        #             'trgt-bw'   : float(args.bitrate) * 1000000.0, 
        #             'res-bw'    : interval['sum']['bits_per_second'],
        #             'loss'      : _interval[i]['loss'],
        #             'total'     : interval['sum']['packets']}

        #         # append line to .csv file
        #         reports.writerow([rprts[attr] for attr in attrs_reports])

        #     rslts = {
        #         'time'      : start_timestamp,
        #         'proto'     : output['start']['test_start']['protocol'], 
        #         'duration'  : output['end']['sum']['seconds'],
        #         'transfer'  : output['end']['sum']['bytes'], 
        #         'trgt-bw'   : float(args.bitrate) * 1000000.0, 
        #         'res-bw'    : output['end']['sum']['bits_per_second'],
        #         'jitter'    : output['end']['sum']['jitter_ms'],
        #         'lost'      : output['end']['sum']['lost_packets'],
        #         'total'     : output['end']['sum']['packets'],
        #         'cpu-sndr'  : output['end']['cpu_utilization_percent']['host_total'],
        #         'cpu-rcvr'  : output['end']['cpu_utilization_percent']['remote_total']}

        # else:

        #     for i, interval in enumerate(output['intervals']):

        #         rprts = {
        #             'time'          : start_timestamp + interval['sum']['end'],
        #             'proto'         : output['start']['test_start']['protocol'], 
        #             'duration'      : interval['sum']['seconds'],
        #             'bytes'         : interval['sum']['bytes'], 
        #             'bitrate'       : interval['sum']['bits_per_second'],
        #             'retransmits'   : interval['sum']['retransmits'],
        #             'cwnd'          : interval['streams'][-1]['snd_cwnd']}

        #         # append line to .csv file
        #         reports.writerow([rprts[attr] for attr in attrs_reports])

        #     rslts = {
        #         'time'          : start_timestamp,
        #         'proto'         : output['start']['test_start']['protocol'], 
        #         'duration'      : output['end']['sum_received']['seconds'],
        #         'bytes-sndr'    : output['end']['sum_sent']['bytes'], 
        #         'bytes-rcvr'    : output['end']['sum_received']['bytes'],
        #         'bitrate-sndr'  : output['end']['sum_sent']['bits_per_second'],
        #         'bitrate-rcvr'  : output['end']['sum_received']['bits_per_second'],
        #         'cpu-sndr'      : output['end']['cpu_utilization_percent']['host_total'],
        #         'cpu-rcvr'      : output['end']['cpu_utilization_percent']['remote_total']}

        # results.writerow([rslts[attr] for attr in attrs_results])

    cmd = ["pkill", "-f", "tcpdump"]
    proc = subprocess.call(cmd)

    sys.exit(0)

