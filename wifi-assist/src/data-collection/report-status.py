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
import platform

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

def report(ip, port, status):
    cmd = ['curl', '-d', ('"%s"' % (status)), '-X', 'POST', ('http://%s:%s/status' % (ip, port))]
    proc = subprocess.Popen(cmd)

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--ip", 
         help = """ip addr of status server""")

    parser.add_argument(
        "--port", 
         help = """port used by status server""")

    parser.add_argument(
        "--output-dir", 
         help = """dir where .csv files are saved""")

    args = parser.parse_args()

    if not args.server_ip:
        sys.stderr.write("""%s: [ERROR] please supply an status server ip\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.server_port:
        sys.stderr.write("""%s: [ERROR] please supply an status server port\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # register CTRL+C catcher
    signal.signal(signal.SIGINT, signal_handler)

    # keep iperfing till a CTRL+C is caught...
    stop_loop = False
    while (stop_loop == False):

        timestamp = int(time.time())
        status = defaultdict(str)

        status['src'] = platform.uname()[1]
        status['time'] = str(timestamp)

        # check status of multiple parameters

        # gps
        status['gps'] = 'bad'
        for filename in glob.glob(os.path.join(args.output_dir, ('gps-log.*.csv'))):
            gps_log = open(filename, 'r')
            line = gps_log.readlines()[-1]
            gps_log.close()

            if timestamp - int(float(line.split(',')[0])) < 5:
                status['gps'] = 'ok'

        # ntpstat
        status['ntp'] = 'bad'
        for filename in glob.glob(os.path.join(args.output_dir, ('ntpstat.*.csv'))):
            log = open(filename, 'r')
            line = log.readlines()[-1]
            log.close()

            if timestamp - int(float(line.split(',')[0])) < 5:

                if int(line.split(',')[3]) > 20:
                    status['ntp'] = 'unsync'
                else:
                    status['ntp'] = 'ok'

        # cpu
        status['cpu'] = 'bad'
        for filename in glob.glob(os.path.join(args.output_dir, ('cpu.*.csv'))):
            log = open(filename, 'r')
            line = log.readlines()[-1]
            log.close()

            if timestamp - int(float(line.split(',')[0])) < 5:
                status['cpu'] = 'ok'

        # iperf3
        status['iperf3'] = 'bad'

        iperf3_logs = glob.glob(os.path.join(args.output_dir, ('iperf3.*.out')))
        to_read = max([int(l.split('.')[1]) for l in iperf3_logs])

        filename = os.path.join(args.output_dir, ('iperf3.%d.out' % (to_read)))
        iperf3_log = open(filename, 'r')
        line = iperf3_log.readlines()[-1]
        iperf3_log.close()

        if (timestamp - int(float(os.path.getmtime(filename))) < 5) and ('/sec' in line):
            status['iperf3'] = 'ok'


        print(json.dumps(status))
        report(args.ip, args.port, json.dumps(status))

        time.sleep(5)

    sys.exit(0)

