import argparse
import os
import subprocess
import sys
import time
import signal

from collections import defaultdict

def capture(iface, output_file, time = 5):
    cmd = ["timeout", str(time), "tcpdump", "-i", iface, "-y", "IEEE802_11_RADIO", "-s0", "-w", output_file]
    # print(' '.join(cmd))
    proc = subprocess.Popen(cmd).communicate()
    # stdout, stderr = proc.communicate()
    # print(stdout)
    # print(stderr)

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
        # print(' '.join(cmd))
        proc = subprocess.call(cmd)

    return 0

def signal_handler(signal, frame):
    global stop_loop
    stop_loop = True

def is_bonding_valid(channel, bandwidth):

    # starting channel nrs for each possible bw
    base_ch = {40 : 36, 80 : 38, 160 : 42}

    ch = int(channel)
    bw = int(bandwidth.rstrip('+').rstrip('-'))
    if bw not in base_ch:
        return False

    a = (bw / 10)
    if ((ch - base_ch[bw]) % a):
        return False

    # FIXME: this only works for channels in between 36 and 64
    # do not allow upper secondary channel on upper limit
    if (not (ch - base_ch[bw])) and (bandwidth[-1] == '-'):
        return False
    # do not allow upper secondary channel on upper limit
    if (not (ch - (base_ch[bw] + (16 * 2 - a)))) and (bandwidth[-1] == '+'):
        return False

    return True

def fix_channel_bonding(channel_list):

    for cb in channel_list:
        
        ch = cb.split(':')[0]
        bw = cb.split(':')[1]

        if int(bw.rstrip('+').rstrip('-')) > 20:
            if not is_bonding_valid(ch, bw):
                channel_list.remove(cb)

if __name__ == "__main__":

    # $ sudo python run-wardrive.py --iface wlan0 --channel-list '1:20,6:20,36:40+' --scan-time 20 --output-dir ~/wardrive &
    # In this example, the `wlan0` interface will start an iterative scan, 
    # scanning channel i (i &isin; `channel-list`) for `scan-time` seconds.
    # At every iteration, the script starts WLAN frame captures with `tcpdump`, 
    # also saving values of GPS position, channel utilization 
    # (if such capability is made available by the WiFi driver), CPU usage, etc. 
    # The results are saved as `.pcap` or `.csv` files in the directory specified as `output-dir`.

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--monitor-iface", 
         help = """wifi iface on which to capture wlan frames. e.g.: '--monitor-iface wlan0'""")

    parser.add_argument(
        "--scan-time", 
         help = """duration of a scan iteration (in seconds). e.g.: '--scan-time 3 (default)'""")

    # FIXME: for bw > 20 MHz, we need to specify the secondary channel w/ a '+' or '-'
    # e.g., the tuple 52:40+ results in the bonding of 20 MHz channels 52 and 56,
    # and it the setting of channel 52 (i.e., the 'upper' channel of the pair) as the secondary channel
    parser.add_argument(
        "--channel-list", 
         help = """list of <channel>:<bandwidth> tuples to scan, separated by ','. 
         bandwidth in MHz. 
         if bandwidth > 20 MHz, the secondary channel must be specified w/ '+' or '-'.
         e.g.: '--channel-list '1:20,6:20,36:40+''""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to save output files""")

    args = parser.parse_args()

    if not args.monitor_iface:
        sys.stderr.write("""%s: [ERROR] please supply a monitor iface\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # mkdir output dir if it does not exist
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)

    # default scan time : 3 sec
    scan_time = 3
    if args.scan_time:
        scan_time = int(args.scan_time)

    # default channel:bw tuples : ['1:20', '6:20']
    channel_list = ['1:20', '6:20', '36:40+']
    if args.channel_list:
        channel_list = args.channel_list.split(',')

    # only some channel pairs are allowed, so we remove invalid bondings here
    fix_channel_bonding(channel_list)
    print(channel_list)

    # register CTRL+C catcher
    signal.signal(signal.SIGINT, signal_handler)
    stop_loop = False
    while (stop_loop == False):

        for cb in channel_list:

            # set iface on monitor mode, w/ specified channel & bw
            ch = cb.split(':')[0]
            bw = cb.split(':')[1]
            set_channel(args.monitor_iface, channel = ch, bw = ('HT%s' % (bw)))
            # start tcpdump capture for {ch, bw}
            timestamp = str(time.time()).split('.')[0]
            pcap_filename = os.path.join(args.output_dir, ("monitor." + str(ch) + "." + str(bw).rstrip('+').rstrip('-') + "." + timestamp + ".pcap"))
            capture(args.monitor_iface, pcap_filename, time = scan_time)

            # end tcpdump capture
            cmd = ["pkill", "-f", "tcpdump"]
            proc = subprocess.Popen(cmd)

    sys.exit(0)