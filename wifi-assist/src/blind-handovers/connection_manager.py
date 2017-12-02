import os
import sys
import glob
import math
import time
import pwd

# required for external commands (e.g. wpa_supplicant, iwconfig, ifconfig)
import signal
import subprocess as sp
import shlex
import tempfile as tf
import pty

# required by dhcp
import socket
import fcntl
import struct

from collections import defaultdict

# custom imports
from ap_map import *
from connection_manager import *
from network_utils import *

# wpa_supplicant binary and config dirs
WPA_SUPPLICANT = '/sbin/wpa_supplicant'
WPA_SUPPLICANT_CONF_DIR = '/home/pi/workbench/wifi-assist/configs'
WPA_SUPPLICANT_LOG_DIR = '/home/pi/workbench/wifi-assist/data/logs/wifi-connections/wpa-supplicant'

# wireless iface name (usually 'wlan0')
WLAN_IFACE = 'wlan0'

# dhclient logs
DHCLIENT_LOG_DIR = '/home/pi/workbench/wifi-assist/data/logs/wifi-connections/dhclient'

def run_cmd(cmd, wait = False):

    try:
        if (wait):
            p = sp.Popen(
                [cmd], 
                stdout = sp.PIPE,
                shell = True)
            p.wait()

        else:
            p = sp.Popen(
                [cmd], 
                shell = True, 
                stdin = None, stdout = None, stderr = None, close_fds = True)

        (result, error) = p.communicate()
        
    except sp.CalledProcessError as e:
        sys.stderr.write(
            "%s::run_cmd() : [ERROR]: output = %s, error code = %s\n"
            % (sys.argv[0], e.output, e.returncode))

    return result

# manages current list of connections, given an ap map
class connection_manager:

    def __init__(self, ap_map = None):
        
        # list of currently connected aps, indexed by ap id
        self.conn_list = defaultdict()
        self.current_conn = None

        # if no ap map is passed, we create a new one
        # now from a default file
        if ap_map is None:
            self.ap_map = defaultdict(list)

    # for now, we simply try to connect to an ap in the 
    # cell (if not already connected)
    def manage_connections(self, cell = (-1, -1)):
        if self.current_conn in self.ap_map[cell]:
            return 1
        else:

            for i, ap in enumerate(self.ap_map[cell]):

                # call wpa_supplicant to connect to ap

                # FIXME : not sure if this means no scanning will occur. you need 
                # to measure exactly what's going on. as such, it would be important 
                # to set another rpi in monitor mode capture the frames exchanged during 
                # this step.
                p = self.connect(ap)

                # kill the wpa_supplicant after 5 secs
                time.sleep(5)
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)

        return -1

    # add ap to ap map
    def add_ap(self, ap, cell = (-1, -1)):
        self.ap_map[cell].append(ap)

    # 
    def connect(self, ap):

        # log name used for this ap connection
        log_name = ('%s-%s.log' % (ap.essid, str(int(time.time()))))

        # start wifi connection w/ wpa_supplicant, save return value as 
        # fd of the running wpa_supplicant process
        p = wpa_supplicant(ap, WLAN_IFACE, os.path.join(WPA_SUPPLICANT_LOG_DIR, log_name))
        # force dhcp request ip address (optional)
        dhclient(WLAN_IFACE, os.path.join(DHCLIENT_LOG_DIR, log_name))

        return p

    # forces termination of current wifi connection by shutting down
    # the wlan0 interface
    def disconnect(self):
        result = run_cmd("ifconfig %s down" % (WLAN_IFACE))
        
