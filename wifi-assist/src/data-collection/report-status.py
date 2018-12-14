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

def gps_status(status, logdir, timestamp):
    status['gps'] = 'n/a'
    for filename in glob.glob(os.path.join(logdir, ('gps-log.*.csv'))):
        with open(filename, 'r') as f:
            lines = f.readlines()
            if len(lines) < 2:
                continue
            line = lines[-1]
            if timestamp - int(float(line.split(',')[0])) < 5:
                status['gps'] = 'ok'
            else:
                status['gps'] = 'bad'

def ntp_status(status, logdir, timestamp):
    status['ntp'] = 'n/a'
    for filename in glob.glob(os.path.join(logdir, ('ntpstat.*.csv'))):
        with open(filename, 'r') as f:
            lines = f.readlines()
            line = lines[-1]
            if (timestamp - int(float(line.split(',')[0]))) < 5:
                if int(line.split(',')[3]) > 20:
                    status['ntp'] = 'unsync'
                else:
                    status['ntp'] = 'ok'

def cpu_status(status, logdir, timestamp):
    status['cpu'] = 'n/a'
    for filename in glob.glob(os.path.join(logdir, ('cpu.*.csv'))):
        log = open(filename, 'r')
        line = log.readlines()[-1]
        log.close()
        if timestamp - int(float(line.split(',')[0])) < 5:
            status['cpu'] = 'ok'
        else:
            status['cpu'] = 'bad'

def iperf3_status(status, logdir, timestamp, mode = 'client'):
    status['iperf3'] = 'bad'
    if mode == 'backbone':

        cmd = ['ps', 'aux']
        try:
            output = subprocess.check_output(cmd, stdin = None, stderr = None, shell = False, universal_newlines = False)
        except subprocess.CalledProcessError:
            return

        output = output.splitlines()
        lines = [s.split('-p')[-1].replace(' ', '') for s in output if (('iperf3' in s) and ('grep' not in s))]
        print(lines)
        if all(e in lines for e in ['5203', '5204']):
            status['iperf3'] = 'ok'
        else:
            status['iperf3'] = 'bad'

    else:
        # get iperf3.*.out w/ largest index
        iperf3_logs = glob.glob(os.path.join(logdir, ('iperf3.*.out')))
        m = max([int(l.split('.')[1]) for l in iperf3_logs])

        filename = os.path.join(logdir, ('iperf3.%d.out' % (m)))
        with open(filename, 'r') as f:
            lines = f.readlines()
            if len(lines) > 0:
                line = lines[-1]
                if (timestamp - int(float(os.path.getmtime(filename))) < 5) and ('/sec' in line):
                    status['iperf3'] = 'ok'

def cbt_status(status, logdir, timestamp):
    status['cbt'] = 'n/a'
    trace = logdir.split('/')[-1]
    print(trace)
    print(logdir.rstrip(trace))
    for filename in glob.glob(os.path.join(logdir.rstrip(trace), ('it-unifi-ac-lite-*/%s/cbt.*.csv' % (trace)))):
        print(filename)
        log = open(filename, 'r')
        line = log.readlines()[-1]
        log.close()
        if timestamp - int(float(line.split(',')[0])) < 5:
            status['cbt'] = 'ok'
        else:
            status['cbt'] = 'bad'

def batt_status(status):
    status['batt'] = 'n/a'
    cmd = ['upower', '-i', '/org/freedesktop/UPower/devices/battery_BAT0']
    try:
        output = subprocess.check_output(cmd, stdin = None, stderr = None, shell = False, universal_newlines = False)
    except subprocess.CalledProcessError:
        status['batt'] = 'bad'
        return

    output = output.splitlines()
    status['batt'] = output[output.index([s for s in output if 'percentage' in s][0])].split(' ')[-1]

def signal_handler(signal, frame):
    global stop_loop
    stop_loop = True

def report(ip, port, status):
    cmd = ['curl', '-d', ('%s' % (status)), '-X', 'POST', ('http://%s:%s/status' % (ip, port))]
    print(cmd)
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
        "--mode", 
         help = """either 'backbone' or 'client'""")

    parser.add_argument(
        "--output-dir", 
         help = """dir where .csv files are saved""")

    args = parser.parse_args()

    if not args.ip:
        sys.stderr.write("""%s: [ERROR] please supply an status server ip\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.port:
        sys.stderr.write("""%s: [ERROR] please supply an status server port\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.mode:
        sys.stderr.write("""%s: [ERROR] please supply a mode\n""" % sys.argv[0]) 
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

        # src, time, mode
        status['src'] = platform.uname()[1]
        status['time'] = str(timestamp)
        status['mode'] = args.mode

        if args.mode == 'backbone':

            # check:
            #   - export of unifi aps stats
            #   - ntp synch status
            #   - export of cpu usage stats
            #   - iperf3 servers running
            #   - batt %
            cbt_status(status, args.output_dir, timestamp)
            cpu_status(status, args.output_dir, timestamp)
            ntp_status(status, args.output_dir, timestamp)
            iperf3_status(status, args.output_dir, timestamp, args.mode)
            batt_status(status)

        else:

            # check:
            #   - export of gps stats (if applicable)
            #   - ntp synch status
            #   - export of cpu usage stats
            #   - export of iperf3 stats
            #   - batt %
            gps_status(status, args.output_dir, timestamp)
            cpu_status(status, args.output_dir, timestamp)
            ntp_status(status, args.output_dir, timestamp)
            iperf3_status(status, args.output_dir, timestamp, args.mode)
            batt_status(status)

        print(json.dumps(status))
        report(args.ip, args.port, json.dumps(status))

        time.sleep(5)

    sys.exit(0)

