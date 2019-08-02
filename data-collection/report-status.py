import os
import csv
import json
import argparse
import subprocess
import sys
import glob
import math
import time
# for parallel processing of sessions
import multiprocessing as mp 
import hashlib
import signal
import platform

from random import randint
from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple

from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict

# FIXME: hardcoded instructions to build status lines to POST to server
report_profiles = {
    'it-eeepc-maroon-001' : {
        'm1' : {
            'section' : 'client-main',
            'fields' : {
                'iperf' : {'type' : 'ps', 'args' : '10.10.12.1:5201'},
                'tcpdump' : 'monitor.*.pcap',
                'cbt' : 'cbt.wlan-monitor.*.csv',
                'ntp' : 'ntpstat.*.csv',
                'battery' : '',
                'gps' : 'gps-log.*.log',
                'cpu' : 'cpu.*.csv'
            }}},
    'it-eeepc-black-001' : {
        'b1' : {
            'section' : 'server',
            'fields' : {
                'iperf' : '',
                'ntp' : 'ntpstat.*.csv',
                'battery' : '',
                'cpu' : 'cpu.*.csv'
            },
        },
        'unifi-1 (n)' : {
            'section' : 'ap',
            'fields' : {
                'cbt' : 'it-unifi-ac-lite-001//cbt.wlan1.*.csv',
                'cpu' : 'cpu.*.csv'
            },
        },
        'unifi-1 (ac)' : {
            'section' : 'ap',
            'fields' : {
                'cbt' : 'it-unifi-ac-lite-001//cbt.wlan0.*.csv',
                'cpu' : 'cpu.*.csv'
            }}},
    'it-asus-black-002' : {
        'b2' : {
            'section' : 'main-client',
            'fields' : {
                'iperf' : {'type' : 'ps', 'args' : '10.10.12.2:5202'},
                'tcpdump' : 'monitor.*.pcap',
                'cbt' : 'cbt.wlan-monitor.*.csv',
                'ntp' : 'ntpstat.*.csv',
                'battery' : '',
                'cpu' : 'cpu.*.csv',
                'gps' : '',
            }
        },
        'tp3 (ac)' : {
            'section' : 'main-client',
            'fields' : {
                'iperf' : {'type' : 'file', 'args' : 'tp-03//iperf3.5201.*.out'},
                'tcpdump' : 'tp-02//monitor.ac.*.pcap',
                'cbt' : 'tp-03//cbt.wlan0.*.csv',
                'ntp' : 'ntpstat.*.csv',
                'battery' : '',
                'cpu' : 'tp-03//cpu.*.csv',
                'gps' : '',
            }
        },
        'tp3 (ad)' : {
            'section' : 'main-client',
            'fields' : {
                'iperf' : {'type' : 'file', 'args' : 'tp-03//iperf3.5202.*.out'},
                'tcpdump' : 'tp-02//monitor.ad.*.pcap',
                'cbt' : '',
                'ntp' : 'ntpstat.*.csv',
                'battery' : '',
                'cpu' : 'tp-02//cpu.*.csv',
                'gps' : '',
            }}},
    'it-eeepc-white-002' : {
        'w2 (n)' : {
            'section' : 'bck-client',
            'fields' : {
                'iperf' : {'type' : 'ps', 'args' : '10.10.12.3:5203'},
                'cbt' : '',
                'ntp' : 'ntpstat.*.csv',
                'battery' : '',
                'cpu' : 'cpu.*.csv',
            }
        },
        'w2 (ac)' : {
            'section' : 'bck-client',
            'fields' : {
                'iperf' : {'type' : 'ps', 'args' : '10.10.12.4:5204'},
                'cbt' : 'cbt.wlan-bk-ac0.*.csv',
                'ntp' : 'ntpstat.*.csv',
                'battery' : '',
                'cpu' : 'cpu.*.csv',
            }
        }},
    'it-eeepc-white-003' : {
        'w3 (n)' : {
            'section' : 'bck-client',
            'fields' : {
                'iperf' : {'type' : 'ps', 'args' : '10.10.12.5:5205'},
                'cbt' : '',
                'ntp' : 'ntpstat.*.csv',
                'battery' : '',
                'cpu' : 'cpu.*.csv',
            }
        },
        'w3 (ac)' : {
            'section' : 'bck-client',
            'fields' : {
                'iperf' : {'type' : 'ps', 'args' : '10.10.12.6:5206'},
                'cbt' : 'cbt.wlan-bk-ac0.*.csv',
                'ntp' : 'ntpstat.*.csv',
                'battery' : '',
                'cpu' : 'cpu.*.csv',
            }
        }},
}

status_funcs = {
    'iperf' : iperf3_status,
    'cbt' : cbt_status,
    'gps' : gps_status,
    'ntp' : ntp_status,
    'battery' : batt_status,
    'cpu' : cpu_status,
    'tcpdump' : monitor_status
}

def get_latest_file(logdir, filename):

    # extract prefix and extension from filename
    prefix = filename.split('.')[0]
    ext = filename.split('.')[-1]

    # get <prefix>.*.<ext> file w/ largest index
    logs = glob.glob(os.path.join(logdir, ('%s.*.%s' % (prefix, ext))))
    if not logs:
        return

    m = max([int(l.split('.')[1]) for l in logs])
    return os.path.join(logdir, ('%s.%d.%s' % (prefix, m, ext)))

def gps_status(status, logdir, timestamp):
    status['gps'] = 'n/a'
    filename = get_latest_file(logdir, 'gps-log.*.csv')

    try:
        with open(filename, 'r') as f:
            lines = f.readlines()
            if len(lines) < 2:
                return

            line = lines[-1]
            if timestamp - int(float(line.split(',')[0])) < 5:
                status['gps'] = 'ok'
            else:
                status['gps'] = 'bad'
    except Exception:
        sys.stderr.write("""%s::gps_status() : [ERROR] exception found\n""" % sys.argv[0])

def ntp_status(status, logdir, timestamp):
    status['ntp'] = 'n/a'
    filename = get_latest_file(logdir, 'ntpstat.*.csv')

    try:
        with open(filename, 'r') as f:
            line = f.readlines()[-1]
            if (timestamp - int(float(line.split(',')[0]))) < 15:
                if int(line.split(',')[3]) > 20:
                    status['ntp'] = 'unsync'
                else:
                    status['ntp'] = 'ok'
    except Exception:
        sys.stderr.write("""%s::ntp_status() : [ERROR] exception found\n""" % sys.argv[0])

def cpu_status(status, logdir, timestamp):
    status['cpu'] = 'n/a'
    filename = get_latest_file(logdir, 'cpu.*.csv')

    try:
        with open(filename, 'r') as f:
            line = f.readlines()[-1]
            if timestamp - int(float(line.split(',')[0])) < 15:
                status['cpu'] = 'ok'
            else:
                status['cpu'] = 'bad'

    except Exception:
        sys.stderr.write("""%s::cpu_status() : [ERROR] exception found\n""" % sys.argv[0])

def cbt_status(status, logdir, timestamp):
    status['cbt'] = 'n/a'
    trace = logdir.split('/')[-1]
    for _logdir in glob.glob(os.path.join(logdir.rstrip(trace), ('it-unifi-ac-lite-*/%s' % (trace)))):
        filename = get_latest_file(_logdir, 'cbt.*.csv')

        try:
            with open(filename, 'r') as f:
                line = f.readlines()[-1]
                if timestamp - int(float(line.split(',')[0])) < 5:
                    status['cbt'] = 'ok'
                else:
                    status['cbt'] = 'bad'

        except Exception:
            sys.stderr.write("""%s::cbt_status() : [ERROR] exception found\n""" % sys.argv[0])

def batt_status(status):
    status['batt'] = 'n/a'
    cmd = ['upower', '-i', '/org/freedesktop/UPower/devices/battery_BAT0']
    try:
        output = subprocess.check_output(cmd, stdin = None, stderr = None, shell = False, universal_newlines = False)
    except subprocess.CalledProcessError:
        status['batt'] = 'bad'
        return

    output = output.splitlines()
    status['batt'] = output[output.index([s for s in output if 'percentage' in s][0])].split(' ')[-1]

def monitor_status(status, logdir, timestamp):
    status['monitor'] = 'bad'
    filename = get_latest_file(logdir, 'monitor.*.pcap')
    try:
        # FIXME: the threshold size is arbitrary at 100 byte
        if (int(os.stat(filename).st_size) > 100) and (timestamp - int(float(os.path.getmtime(filename))) < 5):
            status['monitor'] = 'ok'
    except Exception:
        sys.stderr.write("""%s::monitor_status() : [ERROR] exception found\n""" % sys.argv[0])

def signal_handler(signal, frame):
    global stop_loop
    stop_loop = True

def report(ip, port, status):
    cmd = ['curl', '-d', ('%s' % (status)), '-X', 'POST', ('http://%s:%s/status' % (ip, port))]
    proc = subprocess.Popen(cmd)

def iperf_status(status, logdir, timestamp, args):

    status['iperf'] = 0

    check_type = args['type']
    check_args = args['args']

    if check_type == 'ps':

        server_ip = check_args.split(':')[0]
        server_port = check_args.split(':')[-1]

        cmd = ['ps', 'aux']
        try:
            output = subprocess.check_output(cmd, stdin = None, stderr = None, shell = False, universal_newlines = False)
        except subprocess.CalledProcessError:
            return

        output = output.splitlines()
        lines = [s.split('-p')[-1].replace(' ', '') for s in output if (('iperf' in s) and ('grep' not in s))]
        if all(e in lines for e in [server_port]):
            status['iperf'] = 'ok'
        else:
            status['iperf'] = 'bad'

    elif check_type == 'file':

        filename = check_args.split('/')
        filename[1] = logdir.split('/')[-1]
        trace_nr = logdir.split('/')[-1]
        filename = '/'.join(filename)
        filename = get_latest_file(logdir[:-1], 'iperf.*.out')

        try:

            # FIXME: the threshold size is arbitrary at 100 byte
            if (int(os.stat(filename).st_size) < 100):
                return

            with open(filename, 'r') as f:
                line = f.readlines()[-1]
                if (timestamp - int(float(os.path.getmtime(filename))) < 5) and ('/sec' in line):
                    status['iperf'] = 'ok'

    else:
        sys.stderr.write("""%s::iperf_status() : [ERROR] unknown check type\n""" % sys.argv[0])

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--ip", 
         help = """ip addr of status server""")

    parser.add_argument(
        "--port", 
         help = """port used by status server""")

    parser.add_argument(
        "--mode", 
         help = """either 'backbone' or 'client'""")

    # FIXME : if the report status daemon is to be kept running at all times,
    # the output dir must be read from a static location now.
    parser.add_argument(
        "--output-dir", 
         help = """dir where .csv files are saved""")

    args = parser.parse_args()

    if not args.ip:
        sys.stderr.write("""%s: [ERROR] please supply an status server ip\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.port:
        sys.stderr.write("""%s: [ERROR] please supply an status server port\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.mode:
        sys.stderr.write("""%s: [ERROR] please supply a mode\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] please supply an output dir\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    # register CTRL+C catcher
    signal.signal(signal.SIGINT, signal_handler)

    # keep iperfing till a CTRL+C is caught...
    stop_loop = False
    while (stop_loop == False):

        output_dir = ''
        with open(os.path.join(args.output_dir, 'output-dir.txt'), 'r') as f:
            output_dir = f.readlines()[-1].strip()

        if output_dir == '':
            time.sleep(10)
            continue

        timestamp = int(time.time())

        hostname = platform.uname()[1]
        profile = report_profiles[hostname]

        for node in profile:
            
            status = defaultdict(str)
            
            status['node'] = node
            status['section'] = node['section']
            status['time'] = time(str(timestamp))

            for f in node['fields']:
                status_funcs[f](status, output_dir, timestamp, args = node['fields'][f])

        if args.mode == 'server':

            # check:
            #   - export of unifi aps stats
            #   - ntp synch status
            #   - export of cpu usage stats
            #   - iperf3 servers running
            #   - batt %
            cbt_status(status, output_dir, timestamp)
            cpu_status(status, output_dir, timestamp)
            ntp_status(status, output_dir, timestamp)
            iperf3_status(status, output_dir, timestamp, args.mode)
            batt_status(status)

        else:

            # check:
            #   - export of gps stats (if applicable)
            #   - ntp synch status
            #   - export of cpu usage stats
            #   - export of iperf3 stats
            #   - batt %
            gps_status(status, output_dir, timestamp)
            cpu_status(status, output_dir, timestamp)
            ntp_status(status, output_dir, timestamp)
            cbt_status(status, output_dir, timestamp)
            monitor_status(status, output_dir, timestamp)
            iperf3_status(status, output_dir, timestamp, args.mode)
            batt_status(status)

        # print(json.dumps(status))
        report(args.ip, args.port, json.dumps(status))

        time.sleep(10)

    sys.exit(0)

