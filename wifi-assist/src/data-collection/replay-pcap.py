import csv
import json
import argparse
import os
import time
import datetime
import subprocess
import sys

from scapy.all import *
from scapy.utils import rdpcap, wrpcap

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

    # read x packets from .pcap file
    pkts = rdpcap(args.capture, 52)

    # replay wlan data frames (type = 0x02, subtype = 0x08)
    for pkt in pkts:
        if pkt.haslayer(Dot11):
            if (pkt.type == 0x02) and (pkt.subtype == 0x08):

                # remove IP payload, so that frames fit sendp() max. allowed length
                pkt[IP].remove_payload()
                # set IP datagram len to 20 byte (header only)
                pkt[IP].len = 20
                # remove IP header checksum to force re-calculation
                del pkt[IP].chksum
                pkt[IP].show2()
                # send the wlan frame away
                sendp(pkt, iface = args.iface)
