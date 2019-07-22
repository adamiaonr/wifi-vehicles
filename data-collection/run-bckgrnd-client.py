import argparse
import os
import subprocess
import sys
import time
import signal

from collections import defaultdict

# FIXME : hardcoded for now
iface_addr_map = {
    'wlan-bk-n0'  : {'server-ip' : '10.10.12.3', 'port' : '5203'},
    'wlan-bk-n1'  : {'server-ip' : '10.10.12.4', 'port' : '5204'},
    'wlan-bk-ac0' : {'server-ip' : '10.10.12.5', 'port' : '5205'},
    'wlan-bk-ac1' : {'server-ip' : '10.10.12.6', 'port' : '5206'},
}

def run_client(trace_nr, proto, bitrate, iperf3_info):
    # FIXME : we assume the login username is 'it'
    cmd = ["/usr/local/bin/restart-client", trace_nr, ('it@%s' % (iperf3_info['server-ip'])), iperf3_info['server-ip'], iperf3_info['server-port'], proto, '10M']
    # FIXME : this starts the process on the background (i.e., equivalent to using '&')
    subprocess.Popen(cmd)

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
        "--trace_nr", 
         help = """trace nr""")

    args = parser.parse_args()

    if not args.nr_clients:
        args.nr_clients = 'ac:1,n:1'

    # FIXME : if proto is udp, fix (max) bitrate to 10M
    bitrate = '10'
    if not args.proto:
        args.proto = 'udp'

    if not args.trace_nr:
        sys.stderr.write("""%s: [ERROR] please provide a trace nr\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    clients = args.nr_clients.split(',')
    for c in clients:
        client_type = c.split(':')[0]
        # FIXME : we don't support more than 2 additional ifaces per 802.11 std
        client_nr = max(int(c.split(':')[-1]), 2)
        for i in range(client_nr):
            iface_name = ('wlan-bk-%s%d' % (client_type, i))
            run_client(args.trace_nr, args.proto, bitrate, iface_addr_map[iface_name])
            
    sys.exit(0)