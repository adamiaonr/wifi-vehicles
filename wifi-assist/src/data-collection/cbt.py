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

def set_channel(iface, channel = 1, bw = 'HT20'):

    # here's the high-level procedure: 
    #   1) bring <iface> down
    #   2) set <iface> in monitor mode
    #   3) bring <iface> up again
    #   4) set channel to channel nr. or freq. value (in MHz)
    cmds = []

    cmds.append(["ifconfig", iface, "down"])
    cmds.append(["iwconfig", iface, "mode", "monitor"])
    cmds.append(["ifconfig", iface, "up"])

    if (int(channel) <= 6080) and (int(channel) >= 2412):
        cmds.append(["iw", "dev", iface, "set", "freq", str(channel)])
    elif (int(channel) <= 216) and ((int(channel) > 0)):
        cmds.append(["iw", "dev", iface, "set", "channel", str(channel)])
    else:
        sys.stderr.write("""%s: [ERROR] invalid channe/freq. argument. aborting.\n""" % sys.argv[0]) 
        return -1
        
    if bw in ['HT20', 'HT40+', 'HT40-']:
        cmds[-1].append(bw) 
    else:
        sys.stderr.write("""%s: [ERROR] invalid channel bw argument. aborting.\n""" % sys.argv[0]) 
        return -1

    for cmd in cmds:
        proc = subprocess.call(cmd)

    return 0

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    #1,6,11,36,40,44,48
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

    parser.add_argument(
        "--set-monitor-mode", 
         help = """set 'iface' to monitor mode to channel x and channel bandwidth y.
syntax is '--set-monitor-mode <x>:<y>'.
for frequency arguments, use MHz units, e.g. 5240 MHz for channel 48.
default value is 1:HT20.
e.g.: '--set-monitor-mode 48:HT40+' or '--set-monitor-mode 5240:HT40+'""")

    args = parser.parse_args()

    if not args.channels:
        args.channels = "1,6,11"

    if not args.duration:
        args.duration = "10"

    if not args.iface:
        sys.stderr.write("""%s: [ERROR] please supply an iface for monitor mode\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if args.set_monitor_mode:

        channel = args.set_monitor_mode.split(':')[0]
        channel_bw = 'HT20'
        if len(args.set_monitor_mode.split(':')) > 1:
            channel_bw = args.set_monitor_mode.split(':')[1]
        
        if (set_channel(args.iface, channel, channel_bw) < 0):
            sys.stderr.write("""%s: [ERROR] error while setting monitor mode. aborting.\n""" % sys.argv[0])
            sys.exit(1)

        sys.exit(0)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    for channel in [int(c) for c in args.channels.split(',')]:
        set_channel(args.iface, channel)
        capture(args.iface, int(args.duration), os.path.join(args.output_dir, ("eeepc-cbt-%02d.pcap" % (channel))))

    sys.exit(0)
