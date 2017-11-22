import os
import argparse
import sys
import glob
import math
import time

from collections import defaultdict

# custom imports
from ap_map import *
from connection_manager import *

if __name__ == "__main__":

    cm = connection_manager()

    ap_list = [access_point(essid = 'ouifi'), access_point(essid = 'linksys'), access_point(essid = 'eduroam')]
    for ap in ap_list: 
        print(ap)
        cm.add_ap(ap)

    cm.manage_connections()

    time.sleep(50)

    # cm.disconnect()