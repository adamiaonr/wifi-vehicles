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
                'iperf' : {'type' : 'ps', 'args' : '10.10.12.1:5201,10.10.12.2:5202,10.10.12.3:5203,10.10.12.4:5204,10.10.12.5:5205,10.10.12.6:5206'},
                'ntp' : {'type' : 'file', 'args' : 'ntpstat.*.csv'},
                'battery' : '',
                'cpu' : {'type' : 'file', 'args' : 'cpu.*.csv'},
            },
        },
        'unifi-1 (n)' : {
            'section' : 'ap',
            'fields' : {
                'cbt' : {'type' : 'file', 'subdir' : 'it-unifi-ac-lite-001', 'args' : 'cbt.wlan1.*.csv'},
                'cbt' : {'type' : 'file', 'subdir' : 'it-unifi-ac-lite-001', 'args' : 'cpu.*.csv'},
            },
        },
        'unifi-1 (ac)' : {
            'section' : 'ap',
            'fields' : {
                'cbt' : {'type' : 'file', 'subdir' : 'it-unifi-ac-lite-001', 'args' : 'cbt.wlan0.*.csv'},
                'cbt' : {'type' : 'file', 'subdir' : 'it-unifi-ac-lite-001', 'args' : 'cpu.*.csv'},
            }}},
    'it-asus-black-002' : {
        'b2' : {
            'section' : 'main-client',
            'fields' : {
                'iperf' : {'type' : 'ps', 'args' : '10.10.12.2:5202'},
                'tcpdump' : {'type' : 'file', 'args' : 'monitor.*.pcap'},
                'cbt' : {'type' : 'file', 'args' : 'cbt.wlan-monitor.*.csv'},
                'ntp' : {'type' : 'file', 'args' : 'ntpstat.*.csv'},
                'battery' : '',
                'cpu' : {'type' : 'file', 'args' : 'cpu.*.csv'},
                'gps' : '',
            }
        },
        'tp3 (ac)' : {
            'section' : 'main-client',
            'fields' : {
                'iperf' : {'type' : 'file', 'subdir' : 'tp-03', 'args' : 'iperf3.5201.*.out'},
                'tcpdump' : {'type' : 'file', 'subdir' : 'tp-02', 'args' : 'monitor.ac.*.pcap'},
                'cbt' : {'type' : 'file', 'subdir' : 'tp-03', 'args' : 'cbt.wlan0.*.csv'},
                'ntp' : {'type' : 'file', 'args' : 'ntpstat.*.csv'},
                'battery' : '',
                'cpu' : {'type' : 'file', 'subdir' : 'tp-03', 'args' : 'cpu.*.csv'},
                'gps' : '',
            }
        },
        'tp3 (ad)' : {
            'section' : 'main-client',
            'fields' : {
                'iperf' : {'type' : 'file', 'subdir' : 'tp-03', 'args' : 'iperf3.5202.*.out'},
                'tcpdump' : {'type' : 'file', 'subdir' : 'tp-02', 'args' : 'monitor.ad.*.pcap'},
                'cbt' : '',
                'ntp' : {'type' : 'file', 'args' : 'ntpstat.*.csv'},
                'battery' : '',
                'cpu' : {'type' : 'file', 'subdir' : 'tp-02', 'args' : 'cpu.*.csv'},
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
        return ''

    m = max([int(l.split('.')[1]) for l in logs])
    return os.path.join(logdir, ('%s.%d.%s' % (prefix, m, ext)))

def signal_handler(signal, frame):
    global stop_loop
    stop_loop = True

def report(ip, port, status):
    cmd = ['curl', '-d', ('%s' % (status)), '-X', 'POST', ('http://%s:%s/status' % (ip, port))]
    proc = subprocess.Popen(cmd)

def iperf_status(status, logdir, timestamp, args):

    status['iperf'] = 'bad'

    if args['type'] == 'ps':

        iperf_tuples = args['args'].split(',')
        ips = []
        ports = []
        for it in iperf_tuples:
            ips.append(it.split(':'))[0]
            ports.append(it.split(':'))[-1]

        cmd = ['ps', 'aux']
        try:
            output = subprocess.check_output(cmd, stdin = None, stderr = None, shell = False, universal_newlines = False)
        except subprocess.CalledProcessError:
            return

        output = output.splitlines()
        lines = [s.split('-p')[-1].replace(' ', '') for s in output if (('iperf' in s) and ('grep' not in s))]
        if all(e in lines for e in ports):
            status['iperf'] = 'ok'
        else:
            status['iperf'] = 'bad'

    elif args['type'] == 'file':

        # FIXME : workaround for subdir argument (nfs mounting)
        base_dir = logdir
        if 'subdir' in args:
            base_dir = logdir.split('/')
            base_dir = base_dir[:-1] + [args['subdir'], base_dir[-1]]
            base_dir = '/'.join(base_dir)

        filename = get_latest_file(base_dir, args['args'])
        if not filename:
            status['iperf'] = 'bad'
            return

        try:
            # FIXME: the threshold size is arbitrary at 100 byte
            if (int(os.stat(filename).st_size) < 100):
                status['iperf'] = 'bad'
                return

            with open(filename, 'r') as f:
                line = f.readlines()[-1]
                if (timestamp - int(float(os.path.getmtime(filename))) < 10) and ('/sec' in line):
                    status['iperf'] = 'ok'

    else:
        sys.stderr.write("""%s::iperf_status() : [ERROR] unknown arg type\n""" % sys.argv[0])

def cbt_status(status, logdir, timestamp, args):
    
    # by default cbt is 'n/a'
    status['cbt'] = 'n/a'

    if not args:
        return

    if args['type'] == 'file':

        # FIXME : workaround for subdir argument (nfs mounting)
        base_dir = logdir
        if 'subdir' in args:
            base_dir = logdir.split('/')
            base_dir = base_dir[:-1] + [args['subdir'], base_dir[-1]]
            base_dir = '/'.join(base_dir)

        filename = get_latest_file(base_dir, args['args'])
        if not filename:
            status['cbt'] = 'bad'
            return

        try:
            with open(filename, 'r') as f:
                line = f.readlines()[-1]
                if timestamp - int(float(line.split(',')[0])) < 5:
                    status['cbt'] = 'ok'
                else:
                    status['cbt'] = 'bad'

        except Exception:
            sys.stderr.write("""%s::cbt_status() : [ERROR] exception found\n""" % sys.argv[0])

    else:
        sys.stderr.write("""%s::cbt_status() : [ERROR] unknown arg type\n""" % sys.argv[0])

def gps_status(status, logdir, timestamp, args):

    status['gps'] = 'n/a'

    if not args:
        return

    if args['type'] == 'file':

        base_dir = logdir
        if 'subdir' in args:
            base_dir = logdir.split('/')
            base_dir = base_dir[:-1] + [args['subdir'], base_dir[-1]]
            base_dir = '/'.join(base_dir)

        filename = get_latest_file(base_dir, args['args'])
        if not filename:
            status['gps'] = 'bad'
            return

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

    else:
        sys.stderr.write("""%s::gps_status() : [ERROR] unknown arg type\n""" % sys.argv[0])

def ntp_status(status, logdir, timestamp, args):

    status['ntp'] = 'n/a'
    if not args:
        return

    if args['type'] == 'file':

        base_dir = logdir
        if 'subdir' in args:
            base_dir = logdir.split('/')
            base_dir = base_dir[:-1] + [args['subdir'], base_dir[-1]]
            base_dir = '/'.join(base_dir)

        filename = get_latest_file(base_dir, args['args'])
        if not filename:
            status['ntp'] = 'bad'
            return

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

    else:
        sys.stderr.write("""%s::ntp_status() : [ERROR] unknown arg type\n""" % sys.argv[0])

def cpu_status(status, logdir, timestamp, args):
    
    status['cpu'] = 'n/a'
    if not args:
        return

    if args['type'] == 'file':

        base_dir = logdir
        if 'subdir' in args:
            base_dir = logdir.split('/')
            base_dir = base_dir[:-1] + [args['subdir'], base_dir[-1]]
            base_dir = '/'.join(base_dir)

        filename = get_latest_file(base_dir, args['args'])
        if not filename:
            status['cpu'] = 'bad'
            return

        try:
            with open(filename, 'r') as f:
                line = f.readlines()[-1]
                if timestamp - int(float(line.split(',')[0])) < 15:
                    status['cpu'] = 'ok'
                else:
                    status['cpu'] = 'bad'

        except Exception:
            sys.stderr.write("""%s::cpu_status() : [ERROR] exception found\n""" % sys.argv[0])

    else:
        sys.stderr.write("""%s::cpu_status() : [ERROR] unknown arg type\n""" % sys.argv[0])

def batt_status(status, logdir, timestamp, args):
    status['batt'] = 'n/a'
    cmd = ['upower', '-i', '/org/freedesktop/UPower/devices/battery_BAT0']
    try:
        output = subprocess.check_output(cmd, stdin = None, stderr = None, shell = False, universal_newlines = False)
    except subprocess.CalledProcessError:
        status['batt'] = 'bad'
        return

    output = output.splitlines()
    status['batt'] = output[output.index([s for s in output if 'percentage' in s][0])].split(' ')[-1]

def monitor_status(status, logdir, timestamp, args):

    status['tcpdump'] = 'n/a'

    if not args:
        return

    if args['type'] == 'file':

        base_dir = logdir
        if 'subdir' in args:
            base_dir = logdir.split('/')
            base_dir = base_dir[:-1] + [args['subdir'], base_dir[-1]]
            base_dir = '/'.join(base_dir)

        filename = get_latest_file(base_dir, args['args'])
        if not filename:
            status['tcpdump'] = 'bad'
            return

        try:
            # FIXME: the threshold size is arbitrary at 100 byte
            if (int(os.stat(filename).st_size) > 100) and (timestamp - int(float(os.path.getmtime(filename))) < 5):
                status['tcpdump'] = 'ok'
            else:
                status['tcpdump'] = 'bad'

        except Exception:
            sys.stderr.write("""%s::monitor_status() : [ERROR] exception found\n""" % sys.argv[0])

    else:
        sys.stderr.write("""%s::monitor_status() : [ERROR] unknown arg type\n""" % sys.argv[0])

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

        statuses = []
        for node in profile:
            
            status = defaultdict(str)
            
            status['node'] = node
            status['section'] = node['section']
            status['time'] = time(str(timestamp))

            for f in node['fields']:
                status_funcs[f](status, output_dir, timestamp, args = node['fields'][f])

            statuses.append(status)

        print(json.dumps(statuses))
        report(args.ip, args.port, json.dumps(statuses))

        time.sleep(10)

    sys.exit(0)

