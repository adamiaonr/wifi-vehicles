import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import os
import re
import argparse
import sys
import glob
import math
import gmplot
import time
import timeit
import subprocess
import csv
# for parallel processing of sessions
import multiprocessing as mp 
import hashlib
import datetime
import json

import mapping.utils
import mapping.openstreetmap

import geopandas as gp
import plot.utils
import parsing.utils
import analysis.metrics
import shapely.geometry

from random import randint

from collections import defaultdict
from collections import OrderedDict
from collections import namedtuple

from prettytable import PrettyTable

from sklearn import linear_model

import folium
from folium.plugins import HeatMap
from folium.plugins import MarkerCluster
import branca

# gps coords for a 'central' pin on porto, portugal
PORTO_LATITUDE = 41.163158
PORTO_LONGITUDE = -8.6127137

def heatmap(data, output_dir, map_cntr = [PORTO_LATITUDE, PORTO_LONGITUDE], map_types = ['heatmap']):

    # save data on .hdf5 database
    database = pd.HDFStore(os.path.join(output_dir, "all-wf-database.hdf5"))    

    ap_map = folium.Map(location = map_cntr, 
        zoom_start = 14, 
        tiles = "Stamen Toner")

    for mt in map_types:
        if mt == 'heatmap':

            hm_wide = HeatMap( 
                            list(zip(data['lat'].values, data['lon'].values, data['counts'].values)),
                            min_opacity = 0.025,
                            max_val = np.amax(data['counts']),
                            radius = 5, blur = 10, 
                            max_zoom = 1, )

            ap_map.add_child(hm_wide)

        elif mt == 'clustered-marker':

            marker_cluster = MarkerCluster().add_to(ap_map)

            for index, row in data.iterrows():
                folium.Marker(location = [ row['lat'], row['lon'] ]).add_to(marker_cluster)

        ap_map.save(os.path.join(output_dir, ('%s.html' % (mt))))
