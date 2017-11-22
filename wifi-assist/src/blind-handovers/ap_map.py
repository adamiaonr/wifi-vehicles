import os
import argparse
import sys
import glob
import math
import time

WPA_SUPPLICANT_CONF_DIR = '/home/pi/workbench/wifi-assist/configs'
wifi_auth_types = {0 : 'open', 1 : 'wep', 2 : 'wpa', 3 : 'wpa2', 4 : 'wpa2-enter'}


class access_point:

    def __init__(self, essid, mac_addr = '38229da24b43', auth_type = 0, channel = 6):

        # for now, we use minimal attributes
        self.mac_addr = mac_addr
        self.essid = essid.strip()
        self.auth_type = auth_type
        self.channel = channel

        self.config_file = os.path.join(WPA_SUPPLICANT_CONF_DIR, ('%s.conf' % (self.essid)))

    def __repr__(self):
        return ("""
[ap id] : %s,
\t[mac_addr] : %s,
\t[essid] : %s""" % (str(hash(self)), self.mac_addr.strip(), self.essid))

    def __hash__(self):
        return hash((self.mac_addr, self.essid))

    def __eq__(self, other):
        try:
            return (self.mac_addr, self.essid) == (other.mac_addr, other.essid)
        except AttributeError:
            return NotImplemented

    def get_conn_attrs(self):
        return {'mac_addr' : self.mac_addr, 'essid' : self.essid, 
                'auth_type' : self.auth_type, 'channel' : self.channel}
