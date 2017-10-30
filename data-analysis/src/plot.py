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
import wifi_connection_setup
import dhcp_capture
import wifi_grid
import plot_utils
import channel_switch

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
    parser.add_argument(
        "--gps-limits", 
         help = """limit analysis to box limited by box : --gps-limits '<north lat>,<south lat>,<west lon>,<east lon>'.""")
    parser.add_argument(
        "--cell-size", 
         help = """side of cells which divide the map""")
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
    elif args.case == 'wifi-connection-setup':
        wifi_connection_setup.plot(args.data_file, args.output_dir)
    elif args.case == 'dhcp-capture':
        dhcp_capture.plot(args.data_file, args.output_dir)
    elif args.case == 'wifi-grid':
        wifi_grid.plot(args.data_file, args.output_dir)
    elif args.case == 'channel-switch':

        if not args.cell_size:
            args.cell_size = 10.0

        gps_limits = []
        if not args.gps_limits:
            gps_limits = [41.152844,41.149629,-8.640344,-8.632748]
        else:
            gps_limits = [float(lim) for lim in args.gps_limits.split(",")]

        channel_switch.plot(args.data_file, args.output_dir, args.cell_size, gps_limits)

    else:
        sys.stderr.write("""%s: [ERROR] please supply a valid case\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    sys.exit(0)