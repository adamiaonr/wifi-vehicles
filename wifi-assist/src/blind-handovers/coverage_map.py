import os
import argparse
import sys
import glob
import math
import time
import timeit
import numpy as np
import pandas as pd
import shapely.geometry

from collections import defaultdict

WPA_SUPPLICANT_CONF_DIR = '/home/pi/workbench/wifi-assist/configs'
wifi_auth_types = {0 : 'open', 1 : 'wep', 2 : 'wpa', 3 : 'wpa2', 4 : 'wpa2-enter'}

def to_radians(degrees):
    return (degrees * math.pi / 180.0)

def to_degrees(radians):
    return (radians / (math.pi / 180.0))

def gps_to_dist(lat_start, lon_start, lat_end, lon_end):

    # we use the haversine formula to calculate the great-circle distance between two points. 
    # in other words, this calculates the lenght of the shortest arch in-between 2 points, in 
    # a 'great' circle of radius equal to 6371 (the radius of the earth) 
    # source : http://www.movable-type.co.uk/scripts/latlong.html

    # earth radius, in m
    earth_radius = 6371000

    delta_lat = to_radians(lat_end - lat_start)
    delta_lon = to_radians(lon_end - lon_start)

    lat_start = to_radians(lat_start)
    lat_end   = to_radians(lat_end)

    a = (np.sin(delta_lat / 2.0) * np.sin(delta_lat / 2.0)) + (np.sin(delta_lon / 2.0) * np.sin(delta_lon / 2.0)) * np.cos(lat_start) * np.cos(lat_end)
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))

    return earth_radius * c

# north, south, west, east limits of porto map, in terms of geo coordinates
LAT_LIMIT_NORTH = 41.179283 + 0.01
LAT_LIMIT_SOUTH = 41.176796 - 0.01
LON_LIMIT_EAST  = -8.593912 + 0.01
LON_LIMIT_WEST  = -8.598336 - 0.01

BBOX = shapely.geometry.Polygon(
    [
    (LON_LIMIT_WEST, LAT_LIMIT_SOUTH), 
    (LON_LIMIT_EAST, LAT_LIMIT_SOUTH), 
    (LON_LIMIT_EAST, LAT_LIMIT_NORTH), 
    (LON_LIMIT_WEST, LAT_LIMIT_NORTH)
    ])

# gps coords for a 'central' pin on porto, portugal
LAT = (LAT_LIMIT_NORTH + LAT_LIMIT_SOUTH) / 2.0
LON = (LON_LIMIT_WEST + LON_LIMIT_EAST) / 2.0

# x and y span (in meters) of the map, derived from geo coordinate limits
# NOTE : y is the vertical axis (latitude), x is the horizontal axis (longitude)
Y_SPAN = gps_to_dist(LAT_LIMIT_NORTH, 0.0, LAT_LIMIT_SOUTH, 0.0)
# FIXME : an x span depends on the latitude, and we're assuming a fixed latitude
X_SPAN = gps_to_dist(LON_LIMIT_WEST, LAT, LON_LIMIT_EAST, LAT)

class AP:

    def __init__(self, essid, bssid = '38229da24b43', auth_type = 0, channel = 6):

        # basic attributes
        self.bssid = bssid
        self.essid = essid.strip()
        self.auth_type = auth_type
        self.channel = channel

        # FIXME: why do we need this?!??
        self.config_file = os.path.join(WPA_SUPPLICANT_CONF_DIR, ('%s.conf' % (self.essid)))

    def __repr__(self):
        return ("""
[ap id] : %s,
\t[bssid] : %s,
\t[essid] : %s""" % (str(hash(self)), self.bssid.strip(), self.essid))

    def __hash__(self):
        return hash((self.bssid, self.essid))

    def __eq__(self, other):
        try:
            return (self.bssid, self.essid) == (other.bssid, other.essid)
        except AttributeError:
            return NotImplemented

    def get_conn_attrs(self):
        return {'bssid' : self.bssid, 'essid' : self.essid, 
                'auth_type' : self.auth_type, 'channel' : self.channel}

class Cell:

    @staticmethod
    def gen_id(coords, cell_size = 5.0, cntr = (0.0, 0.0)):

        """returns the id of cell containing (GPS) coords"""

        # calc y (latitude) and x (longitude) coords of cell
        y = ((coords[1] - LAT_LIMIT_SOUTH) / (LAT_LIMIT_NORTH - LAT_LIMIT_SOUTH)) * (Y_SPAN / cell_size)
        x = ((coords[0] - LON_LIMIT_WEST)  / (LON_LIMIT_EAST  - LON_LIMIT_WEST))  * (X_SPAN / cell_size)

        # calc bounds of cell
        dy = (LAT_LIMIT_NORTH - LAT_LIMIT_SOUTH) / (Y_SPAN / cell_size)
        dx = (LON_LIMIT_EAST  - LON_LIMIT_WEST) / (X_SPAN / cell_size)

        bounds = (LAT_LIMIT_SOUTH + dy * (y + 1), LON_LIMIT_WEST + dx * x, LAT_LIMIT_SOUTH + dy * y, LON_LIMIT_WEST + dx * (x + 1))

        return hash(str(int(x)) + str(int(y))), bounds, (x, y)

    def __init__(
        self,
        cell_id = None,
        coords = None, 
        bounds = None,
        cell_size = 5.0,
        cntr = (0.0, 0.0)):

        if coords is not None:
            self.id, self.bounds, _ = Cell.gen_id(coords, cell_size, cntr)

        elif bounds is not None:
            self.bounds = bounds

            if cell_id is None:
                coords = ((bounds[0] + bounds[2]) / 2.0, (bounds[1] + bounds[3]) / 2.0)
                self.id, _, _ = Cell.gen_id(coords, cell_size, cntr)

            else:
                self.id = cell_id

        else:
            self.id = cell_id
            self.bounds = (0.0, 0.0, 0.0, 0.0)

        # set of aps ids covering the cell
        self.aps = set([])
        # set of channels of aps in cell
        self.channels = set([])

    def __eq__(self, other):
        try:
            return self.bounds == other.bounds
        except AttributeError:
            return NotImplemented

    def add_ap(self, essid, mac, channel):
        self.aps.add(hash((mac, essid)))
        self.channels.add(int(channel))

class CoverageMap:

    def __init__(self, cell_size = 5.0, cntr = (0.0, 0.0)):

        # hashtable w/ cell info
        #   - indexed by cell id
        #   - cell id can be calculated from any gps coords in O(1) time
        #       - check Cell.gen_id((lat, lon))
        self.map = defaultdict(Cell)
        # hashtable w/ ap info
        #   - indexed by 'hash(bssid:ssid)'
        #   - each Cell has list of aps reachable from it
        self.aps = defaultdict(AP)

        # other map attributes
        self.cell_size = cell_size
        self.cntr = cntr

    def empty():
        return bool(self.map);

    def build(self, gps_file, scan_file, rssi_thrhld = -65.0):
        """builds coverage map from gps & scan files"""

        # load gps & scan files (.csv files)
        locations = pd.read_csv(gps_file)
        scans = pd.read_csv(scan_file)

        # merge locations and scans by 'time'
        # remove rows in which scan info is NaN
        start = timeit.default_timer()
        df = pd.merge(
            locations, 
            scans, 
            how = 'left', on = ['time'])[['time', 'lat', 'lon', 'essid', 'mac', 'channel', 'signal_level_dBm']].dropna()
        print("CoverageMap::build() : [INFO] merge took %.3f sec" % (timeit.default_timer() - start))

        # start building the map by adding cells and aps to it
        start = timeit.default_timer()
        for index, row in df.iterrows():

            # if coords are non plausible, skip
            coords = (float(row['lon']), float(row['lat']))
            if not BBOX.contains(shapely.geometry.Point(coords)):
                continue

            # if signal level is below threshold, skip
            if float(row['signal_level_dBm']) < rssi_thrhld:
                continue

            # calc cell id
            cell_id, bounds, _ = Cell.gen_id(coords, self.cell_size, self.cntr)
            # add cell to map if not existent
            if cell_id not in self.map:
                self.map[cell_id] = Cell(cell_id, bounds)

            # add ap to cell
            bssid = row['mac']
            essid = row['essid']
            channel = row['channel']

            self.map[cell_id].add_ap(row['essid'], row['mac'], row['channel'])

            # add ap obj if not existent
            if hash((bssid, essid)) not in self.aps:
                self.aps[hash((bssid, essid))] = AP(bssid = bssid, essid = essid, channel = channel)
        print("CoverageMap::build() : [INFO] map build took %.3f sec" % (timeit.default_timer() - start))

    def update(self, to_update):
        """adds/updates cells in to_update"""
        updated_map = self.map.copy()
        updated_map.update(to_update)
        self.map = updated_map

    def get_cell(self, coords):
        """returns cell which contains (the GPS) coords"""
        cell_id, _, _ = Cell.gen_id(coords, self.cell_size, self.cntr)
        return self.map[cell_id]



