import csv
import json
import argparse
import os
import time
import datetime
import subprocess
import sys
import signal

def signal_handler(signal, frame):
    global stop_loop
    stop_loop = True

def capture(iface, output_file, mode = 'ap'):
    # tcpdump -i <iface> -y IEEE802_11_RADIO -s0 -w <file>
    cmd = ''
    if mode == 'ap':
        cmd = ["tcpdump", "-i", iface, "-s0", "-w", output_file]
    elif mode == 'monitor':
        cmd = ["tcpdump", "-i", iface, "-y", "IEEE802_11_RADIO", "-s0", "-w", output_file]

    proc = subprocess.Popen(cmd)

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

    # parser.add_argument(
    #     "--duration", 
    #      help = """duration of scan (in seconds). e.g.: '--scan-duration 120'""")

    parser.add_argument(
        "--iface", 
         help = """wifi iface to use for monitor mode. e.g.: '--iface wlx24050f9e2cb1'""")

    parser.add_argument(
        "--channel", 
         help = """channel x and channel bandwidth y to scan.
this sets the iface specified in the '--iface' option to monitor mode, on the specified channel and bandwidth.
syntax is '--channel <x>:<y>'. the bandwidth y is specified in 'HT capability' format, i.e. 'HT20', 'HT40-' and 'HT40+'. 
e.g.: '--channel 36:HT40+' sets iface to channel 36, 40 MHz bandwidth, center frequency in 5190 MHz.
default value is 1:HT20 for channel 1, 20 MHz bandwidth.""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save .pcap files""")

    parser.add_argument(
        "--set-monitor-mode", 
         help = """set 'iface' to monitor mode to channel x and channel bandwidth y.
this sets the iface specified in the '--iface' option to monitor mode, on the specified channel and bandwidth.
syntax is '--channel <x>:<y>'. the bandwidth y is specified in 'HT capability' format, i.e. 'HT20', 'HT40-' and 'HT40+'. 
e.g.: '--channel 36:HT40+' sets iface to channel 36, 40 MHz bandwidth, center frequency in 5190 MHz.
default value is 1:HT20 for channel 1, 20 MHz bandwidth.""")

    parser.add_argument(
        "--capture-only", 
         help = """only starts tcpdump capture without setting iface to monitor mode""",
         action = 'store_true')

    args = parser.parse_args()

    if not args.channel:
        args.channel = "1:HT20"

    # if not args.duration:
    #     args.duration = "10"

    capture_only = False
    if args.capture_only:
        capture_only = True

    if not args.iface:
        sys.stderr.write("""%s: [ERROR] please supply an iface for monitor mode\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if args.set_monitor_mode:

        # FIXME: this is redundant, but here for retro-compatibility purposes
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

    # register CTRL+C catcher
    signal.signal(signal.SIGINT, signal_handler)

    channel = args.channel.split(':')[0]
    channel_bw = 'HT20'

    if len(args.channel.split(':')) > 1:
        channel_bw = args.channel.split(':')[1]

    if not capture_only:
        set_channel(args.iface, channel)

    timestamp = str(time.time()).split('.')[0]
    capture(args.iface, os.path.join(args.output_dir, ("monitor." + str(channel) + "." + str(channel_bw).rstrip('+').rstrip('-') + "." + timestamp + ".pcap")))

    # keep sleeping till a CTRL+C is caught...
    stop_loop = False
    while (stop_loop == False):
        time.sleep(1.0)

    cmd = ["pkill", "-f", "tcpdump"]
    proc = subprocess.call(cmd)

    sys.exit(0)
