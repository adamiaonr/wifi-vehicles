import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import os
import re
import argparse
import sys
import glob
import math
import gmplot
import time
import subprocess
import csv
# for parallel processing of sessions
import multiprocessing as mp 
import hashlib
import datetime
import json

from random import randint
from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple
from matplotlib.gridspec import GridSpec
from prettytable import PrettyTable

def parse_json(input_filename, output_file):

    json_file = open(input_filename)
    json_str = json_file.read()
    # split the .json file in blocks, delimited by '}\n{'
    blocks = json_str.split('}\n{')
    # FIXME: the first block needs a '}' at the end for correct parsing by json.loads()
    blocks[0] = blocks[0] + '}'
    blocks[0] = blocks[0].replace('\n', '').replace('\t', '')
    data = json.loads(blocks[0])
    output_file.writerow( 
        [ 
            data['start']['timestamp']['timesecs'], 
            data['end']['cpu_utilization_percent']['host_total'], 
            data['end']['cpu_utilization_percent']['remote_total'] ] )

    blocks[-1] = '{' + blocks[-1]
    blocks[-1] = blocks[-1].replace('\n', '').replace('\t', '')
    data = json.loads(blocks[-1])
    output_file.writerow( 
        [ 
            data['start']['timestamp']['timesecs'], 
            data['end']['cpu_utilization_percent']['host_total'], 
            data['end']['cpu_utilization_percent']['remote_total'] ] )

    for block in blocks[1:-1]:
        block = '{' + block + '}'
        block = block.replace('\n', '').replace('\t', '')
        data = json.loads(block)
        output_file.writerow( 
            [ 
                data['start']['timestamp']['timesecs'], 
                data['end']['cpu_utilization_percent']['host_total'], 
                data['end']['cpu_utilization_percent']['remote_total'] ] )