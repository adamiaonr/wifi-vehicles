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

def signal_handler(signal, frame):
    global stop_loop
    stop_loop = True

def test(time, ip_server, port = 5201, proto = 'udp', bitrate = '54'):

    output = "N/A"
    # iperf3 -t <time> -c <ip_server> -u (or nothing) -b <bitrate>M
    cmd = ["iperf3", "-V", "-J", "-t", str(time), "-c", str(ip_server), "-p", str(port), ("-u" if proto == 'udp' else ''), "-b", str(bitrate) + 'M']

    try:
        output = subprocess.check_output(cmd, stdin = None, stderr = None, shell = False, universal_newlines = False)
    except subprocess.CalledProcessError:
        return -1, output

    return 0, output

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

    results_file = os.path.join(args.output_dir, ("iperf3-to-mobile." + str(time.time()).split('.')[0] + ".csv"))

    if not args.ip_server:
        sys.stderr.write("""%s: [ERROR] please supply an iperf3 server ip\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # register CTRL+C catcher
    signal.signal(signal.SIGINT, signal_handler)

    attrs = ['time', 'proto', 'duration', 'transfer', 'trgt-bw', 'res-bw', 'jitter', 'lost', 'total', 'cpu-sndr', 'cpu-rcvr']
    iperf_log = csv.writer(open(results_file, 'wb+', 0))
    iperf_log.writerow(attrs)

    # keep iperfing till a CTRL+C is caught...
    stop_loop = False
    while (stop_loop == False):
        for protocol in [p.lower() for p in args.protocols.split(',')]:
            for bitrate in [b for b in args.bitrates.split(',')]:

                code, output = test(int(args.duration), args.ip_server, args.port, protocol, bitrate)
                
                if code < 0:
                    continue

                output = json.loads(output)

                if output['start']['test_start']['protocol'] == 'UDP':

                    results = {
                        'time'      : time.time(),
                        'proto'     : output['start']['test_start']['protocol'], 
                        'duration'  : output['end']['sum']['seconds'],
                        'transfer'  : output['end']['sum']['bytes'], 
                        'trgt-bw'   : float(bitrate) * 1000000.0, 
                        'res-bw'    : output['end']['sum']['bits_per_second'],
                        'jitter'    : output['end']['sum']['jitter_ms'],
                        'lost'      : output['end']['sum']['lost_packets'],
                        'total'     : output['end']['sum']['packets'],
                        'cpu-sndr'  : output['end']['cpu_utilization_percent']['host_total'],
                        'cpu-rcvr'  : output['end']['cpu_utilization_percent']['remote_total']}

                else:
                    sys.stderr.write("""%s: [ERROR] TCP is not supported (yet)\n""" % sys.argv[0]) 
                    sys.exit(1)

                # append line to .csv file
                iperf_log.writerow([results[attr] for attr in attrs])

    sys.exit(0)

