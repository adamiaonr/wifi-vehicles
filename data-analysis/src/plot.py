import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import os
import argparse
import sys
import glob

from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict

# custom imports
import session_analysis
import wifi_connection
import dhcp_capture
import plot_utils

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--data-file", 
         help = """.csv file w/ session data""")
    parser.add_argument(
        "--output-dir", 
         help = """dir on which to print graphs""")
    parser.add_argument(
        "--case", 
         help = """the case you want to output. e.g. 'base'.""")
    # parser.add_argument(
    #     "--subcase", 
    #      help = """the sub-case you want to output. e.g. 'bfs'.""")

    args = parser.parse_args()

    # quit if a dir w/ .tsv files hasn't been provided
    if not args.data_file:
        sys.stderr.write("""%s: [ERROR] please supply a .csv file w/ input data\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # if an output dir is not specified, use data-dir
    if not args.output_dir:
        args.output_dir = ""

    if args.case == 'session-analysis':
        session_analysis.plot(args.data_file, args.output_dir)
    elif args.case == 'wifi-connections':
        wifi_connection.plot(args.data_file, args.output_dir)
    elif args.case == 'dhcp-capture':
        dhcp_capture.plot(args.data_file, args.output_dir)
    else:
        sys.stderr.write("""%s: [ERROR] please supply a valid case\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    sys.exit(0)