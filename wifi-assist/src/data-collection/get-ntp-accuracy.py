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

def ntpstat():
    output = "N/A"
    # ntpstat
    cmd = ["ntpstat"]

    try:
        output = subprocess.check_output(cmd, stdin = None, stderr = None, shell = False, universal_newlines = False)
    except subprocess.CalledProcessError:
        return -1, output

    return 0, output

def parse_ntpstat(text):

    output = []
    lines = text.splitlines()
    status = lines[0].split(' ')
    if status[0] == 'synchronised':

        server = status[-5].lstrip('(').rstrip(')')
        stratum = status[-2]
        delta = lines[1].split(' ')[-2]
        pollfreq = lines[2].split(' ')[-2]

        output = [server, stratum, delta, pollfreq]

    return output

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output-dir", 
         help = """dir to save .csv files""")

    args = parser.parse_args()

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # register CTRL+C catcher
    signal.signal(signal.SIGINT, signal_handler)

    timestamp = str(time.time()).split('.')[0]
    log_file = os.path.join(args.output_dir, ("ntpstat." + timestamp + ".csv"))
    attrs = ['timestamp', 'server', 'stratum', 'delta', 'poll-freq']
    log = csv.writer(open(log_file, 'wb+', 0))
    log.writerow(attrs)

    # keep iperfing till a CTRL+C is caught...
    stop_loop = False
    while (stop_loop == False):

        code, output = ntpstat()        
        if code < 0:
            continue

        output = parse_ntpstat(output)
        if output:
            log.writerow([time.time()] + output)

        time.sleep(1.0)

    sys.exit(0)

