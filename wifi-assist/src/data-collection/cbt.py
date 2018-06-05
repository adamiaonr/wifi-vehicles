import iwlist
import csv
import json
import argparse
import os
import time
import datetime
import subprocess
import sys

def capture(iface, time, output_file):
    # tcpdump -i <iface> -y IEEE802_11_RADIO -s0 -w <file>
    cmd = ["timeout", str(time), "tcpdump", "-i", iface, "-y", "IEEE802_11_RADIO", "-s0", "-w", output_file]
    proc = subprocess.call(cmd)

def set_channel(iface, channel):
    # ifconfig <iface> down
    cmd = ["ifconfig", iface, "down"]
    proc = subprocess.call(cmd)

    # iwconfig <iface> mode monitor
    cmd = ["iwconfig", iface, "mode", "monitor"]
    proc = subprocess.call(cmd)

    # iwconfig <iface> up
    cmd = ["ifconfig", iface, "up"]
    proc = subprocess.call(cmd)

    # iwconfig <iface> channel <channel>
    cmd = ["iwconfig", iface, "channel", str(channel)]
    proc = subprocess.call(cmd)

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    #1,2,3,4,5,6,7,8,9,10,11,12,13,14,36,28,40,42,44,46,48
    parser.add_argument(
        "--channels", 
         help = """list of channels to scan, separated by ','. e.g.: '--channels 1,6,11'""")

    parser.add_argument(
        "--duration", 
         help = """duration of scan (in seconds). e.g.: '--scan-duration 120'""")

    parser.add_argument(
        "--iface", 
         help = """wifi iface to use for monitor mode. e.g.: '--iface wlx24050f9e2cb1'""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save .pcap files""")

    args = parser.parse_args()

    if not args.channels:
        args.channels = "1,6,11"

    if not args.duration:
        args.duration = "10"

    if not args.iface:
        sys.stderr.write("""%s: [ERROR] please supply an iface for monitor mode\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    for channel in [int(c) for c in args.channels.split(',')]:
        set_channel(args.iface, channel)
        capture(args.iface, int(args.duration), os.path.join(args.output_dir, ("eeepc-cbt-%02d.pcap" % (channel))))

    exit(0)
