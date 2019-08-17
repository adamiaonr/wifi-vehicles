import argparse
import os
import subprocess
import sys
import time
import signal
import socket

from collections import defaultdict

# FIXME : hardcoded for now
# FIXME : we assume the login username is 'it'
iface_addr_map = {
    'it-eeepc-white-002' : {
        'n'  : [{'login' : 'it@10.10.10.113', 'server-ip' : '10.10.12.3', 'server-port' : '5203', 'route-ip' : '10.10.13.1'}],
        'ac' : [{'login' : 'it@10.10.10.113', 'server-ip' : '10.10.12.4', 'server-port' : '5204', 'route-ip' : '10.10.14.1'}],
    },
    'it-eeepc-white-003' : {
        'n'  : [{'login' : 'it@10.10.10.113', 'server-ip' : '10.10.12.5', 'server-port' : '5205', 'route-ip' : '10.10.13.1'}],
        'ac' : [{'login' : 'it@10.10.10.113', 'server-ip' : '10.10.12.6', 'server-port' : '5206', 'route-ip' : '10.10.14.1'}],
    }
}

def run_client(iface_name, trace_nr, client_info):
    cmd = ["/usr/local/bin/restart-client", iface_name, trace_nr, client_info['login'], client_info['server-port']]
    # FIXME : this starts the process on the background (i.e., equivalent to using '&')
    subprocess.Popen(cmd)

def add_route(iface, params):
    cmd = ['ip', 'route', 'add', ('%s/32' % (params['server-ip'])), 'via', params['route-ip'], 'dev', iface_name]
    proc = subprocess.call(cmd)

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--nr-clients", 
         help = """nr. of background clients, per 802.11 std.
         format : <802.11-type>:<nr>,<802.11-type>:<nr>,... e.g.: --nr-clients 'ac:2,n:1'""")

    # parser.add_argument(
    #     "--proto", 
    #      help = """tcp or udp""")

    parser.add_argument(
        "--trace-nr", 
         help = """trace nr""")

    args = parser.parse_args()

    if not args.nr_clients:
        args.nr_clients = 'ac:1,n:1'

    # # FIXME : if proto is udp, fix (max) bitrate to 10M
    # bitrate = '10'
    # if not args.proto:
    #     args.proto = 'udp'

    if not args.trace_nr:
        sys.stderr.write("""%s: [ERROR] please provide a trace nr\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    hostname = socket.gethostname()
    clients = args.nr_clients.split(',')
    for c in clients:
        client_type = c.split(':')[0]
        if client_type not in ['n', 'ac']:
            continue

        # FIXME : we don't support more than 1 additional ifaces per 802.11 std
        client_nr = min(int(c.split(':')[-1]), 1)

        if client_nr < 1:
            continue

        for i in range(client_nr):
            iface_name = ('wlan-bk-%s%d' % (client_type, i))
            # add_route(iface_name, iface_addr_map[hostname][client_type][i])
            run_client(iface_name, args.trace_nr, iface_addr_map[hostname][client_type][i])
            
    sys.exit(0)
