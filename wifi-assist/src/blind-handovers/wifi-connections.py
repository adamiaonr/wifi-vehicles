import os
import argparse
import sys
import glob
import math
import time
import threading

from collections import defaultdict

# custom imports
from ap_map import *
from network_utils import *

# wpa_supplicant binary and config dirs
WPA_SUPPLICANT = '/sbin/wpa_supplicant'
WPA_SUPPLICANT_CONF_DIR = '/home/pi/workbench/wifi-assist/configs'
WPA_SUPPLICANT_LOG_DIR = '/home/pi/workbench/wifi-assist/data/logs/wifi-connections/wpa-supplicant'
# dhclient logs
DHCLIENT_LOG_DIR = '/home/pi/workbench/wifi-assist/data/logs/wifi-connections/dhclient'
# ping logs
PING_LOG_DIR = '/home/pi/workbench/wifi-assist/data/logs/wifi-connections/ping'

# wireless iface name (usually 'wlan0')
WLAN_IFACE = 'wlan0'

def wpa_supplicant_thread(ap, log_name, stop):

    log_filename = os.path.join(WPA_SUPPLICANT_LOG_DIR, log_name)
    master, slave = pty.openpty()

    try:
        p = sp.Popen(shlex.split(('%s -dd -t -K -i%s -c%s -Dwext' % (WPA_SUPPLICANT, WLAN_IFACE, ap.config_file))), 
            shell = False, stdin = None, stdout = slave, stderr = None)

        log_file = open(log_filename, 'a+')

        while (p.poll() is None) and (not stop.isSet()):

            if select([master], [], [], 0):

                lines = os.read(master, 1024)
                log_file.write(lines)
                log_file.flush()

                lines = lines.split('\n')
                for line in lines:
                    if ('%s: CTRL-EVENT-CONNECTED' % (WLAN_IFACE)) in line[18:]:
                        if (not get_ip_address(WLAN_IFACE)):
                            dhclient(WLAN_IFACE)

        os.close(slave)
        os.close(master)
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)

    except sp.CalledProcessError as e:
        sys.stderr.write(
            "%s::wpa_supplicant() : [ERROR]: output = %s, error code = %s\n"
            % (sys.argv[0], e.output, e.returncode))

    # return the fd of the process started w/ Popen()
    return p

def ping_thread(log_name, stop):

    master, slave = pty.openpty()

    try:
        p = sp.Popen(shlex.split('/bin/ping -D www.fe.up.pt'), 
            shell = False, stdin = None, stdout = slave, stderr = None)

        # save output of wpa_supplicant in log file
        log_file = open(os.path.join(PING_LOG_DIR, log_name), 'a+')
        while (p.poll() is None) and (not stop.isSet()):
            if select([master], [], [], 0):
                lines = os.read(master, 1024)
                log_file.write(lines)
                log_file.flush()

        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        os.close(slave)
        os.close(master)

    except sp.CalledProcessError as e:
        sys.stderr.write(
            "%s::ping_thread() : [ERROR]: output = %s, error code = %s\n"
            % (sys.argv[0], e.output, e.returncode))

    return p

if __name__ == "__main__":

    # create 'fake' access_point() so that wpa_supplicant 
    # reads general.conf file
    ap = access_point(essid = 'general')
    # general log file 
    log_name = ('%s-%s.log' % (ap.essid, str(int(time.time()))))

    stop = threading.Event()

    try:
        # initialize wpa_supplicant thread
        wpa_thread = threading.Thread(target = wpa_supplicant_thread, args = (ap, log_name, stop,))
        wpa_thread.start()

        # initialize ping thread (start only when ip address is obtained)
        ping_thread = threading.Thread(target = ping_thread, args = (log_name, stop, ))

        while not get_ip_address(WLAN_IFACE):
            sys.stderr.write("%s::main() : [ERROR]: still don't have ip address\n" % (sys.argv[0]))
            time.sleep(0.5)

        # start pinging fe.up.pt
        ping_thread.start()

        # ... and let it be like that for now

    except:
        print("%s::main() : [ERROR]" % (sys.argv[0]))
        print(e)

