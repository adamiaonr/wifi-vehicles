import csv
import json
import argparse
import os
import time
import datetime
import subprocess
import sys

from scapy.all import *
from scapy.utils import rdpcap

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--capture", 
         help = """.pcap file w/ packet capture""")

    parser.add_argument(
        "--iface", 
         help = """wifi iface to use for monitor mode. e.g.: '--iface wlx24050f9e2cb1'""")

    args = parser.parse_args()

    if not args.iface:
        sys.stderr.write("""%s: [ERROR] please provide iface on which to tx packets\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.capture:
        sys.stderr.write("""%s: [ERROR] please provide .pcap file\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    pkts = rdpcap(args.capture, 50)
    for pkt in pkts:
        if pkt.haslayer(Dot11):
            if (pkt.type == 0x02) and (pkt.subtype == 0x08):
                pkt[Dot11].addr1 = 'ff:ff:ff:ff:ff'
                pkt[Dot11].addr3 = 'ff:ff:ff:ff:ff'
                # sendp(pkt, iface = args.iface, inter = 0.1, loop = 1)