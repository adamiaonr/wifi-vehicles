import pandas as pd
import numpy as np
import csv
import json
import argparse
import os
import time
import datetime
import subprocess
import sys

def test(time, ip_server, proto = 'udp', bitrate = '54M'):
    # iperf3 -t <time> -c <ip_server> -u (or nothing) -b <bitrate>M
    cmd = ["iperf3", "-V", "-J", "-t", str(time), "-c", str(ip_server), ("-u" if proto == 'udp' else ''), "-b", str(bitrate) + 'M']
    output = subprocess.check_output(cmd, stdin = None, stderr = None, shell = False, universal_newlines = False)
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

    if not args.ip_server:
        sys.stderr.write("""%s: [ERROR] please supply an iperf3 server ip\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    results = pd.DataFrame(columns = ['proto', 'duration', 'transfer', 'trgt-bw', 'res-bw', 'jitter', 'lost', 'total', 'cpu-sndr', 'cpu-rcvr'])
    for protocol in [p.lower() for p in args.protocols.split(',')]:
        for bitrate in [b for b in args.bitrates.split(',')]:
            for r in xrange(int(args.rounds)):

                output = test(int(args.duration), args.ip_server, protocol, bitrate)
                output = json.loads(output)

                if output['start']['test_start']['protocol'] == 'UDP':

                    results = results.append({
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

                    results = results.append({
                        'proto'     : output['start']['test_start']['protocol'], 
                        'duration'  : output['end']['sum_received']['seconds'],
                        'transfer'  : output['end']['sum_received']['bytes'], 
                        'trgt-bw'   : float(bitrate) * 1000000.0, 
                        'res-bw'    : output['end']['sum_received']['bits_per_second'],
                        'lost'      : output['end']['sum_sent']['retransmits'],
                        'cpu-sndr'  : output['end']['cpu_utilization_percent']['host_total'],
                        'cpu-rcvr'  : output['end']['cpu_utilization_percent']['remote_total']}, ignore_index = True)

    results.to_csv(os.path.join(args.output_dir, ("rpi-wifi.csv")))
    sys.exit(0)
