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

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--output-dir", 
         help = """dir to save .csv files""")

    args = parser.parse_args()

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    report = csv.writer(open(os.path.join(args.output_dir, 'protocol-profile.csv'), 'wb+', 0))
    report.writerow(['protocol', 'key', 'value'])

    for proto in ['tcp', 'udp']:
        for filename in glob.glob(os.path.join('/proc/sys/net/ipv4', ('%s_*' % (proto)))):
            parameter = filename.split('/')[-1]
            with open(filename, 'r') as f:
                report.writerow([proto, parameter, f.read().replace('\n', '')])

    sys.exit(0)
