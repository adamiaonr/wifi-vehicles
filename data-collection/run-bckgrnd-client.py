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

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--nr-clients", 
         help = """nr. of background clients, per type.
         format : <802.11-type>:<nr>,<802.11-type>:<nr>,... e.g.: --nr-clients 'ac:2,n:1'""")

    parser.add_argument(
        "--proto", 
         help = """tcp or udp""")

    parser.add_argument(
        "--ip-srvr", 
         help = """ip addr of iperf3 server""")

    args = parser.parse_args()

    if not args.nr_clients:
        args.nr_clients = 'ac:1,n:1'

    if not args.proto:
        args.proto = 'udp'

    if not args.ip_srvr:
        sys.stderr.write("""%s: [ERROR] please provide an iperf3 server ip addr\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    clients = args.nr_clients.split(',')
    for c in clients:
        client_type = c.split(':')[0]
        # FIXME : we don't support more than 2 additional ifaces per 802.11 std
        client_nr = max(int(c.split(':')[-1]), 2)

        for i in range(client_nr):
            iface_name = ('wlan-bck-%s%d' % (client_type, i))
            


    sys.exit(0)