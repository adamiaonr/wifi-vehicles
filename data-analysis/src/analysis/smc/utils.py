from __future__ import absolute_import

import pandas as pd
import os

# wifi net operators
operators = {
    1 : {'name' : 'eduroam', 'match-str' : 'eduroam', 'public' : ''},
    2 : {'name' : 'zon', 'match-str' : 'FON_ZON_FREE_INTERNET|ZON-|Optimus|NOS', 'public' : 'FON_ZON_FREE_INTERNET'},
    3 : {'name' : 'meo', 'match-str' : 'MEO-|Thomson|MEO-WiFi|PT-WIFI|SAPO|2WIRE-', 'public' : 'MEO-WiFi|PT-WIFI'},
    4 : {'name' : 'vodafone', 'match-str' : 'Vodafone-|VodafoneFibra-|VodafoneMobileWiFi-|Huawei', 'public' : 'VodafoneMobileWiFi-'},
    5 : {'name' : 'porto digital', 'match-str' : 'WiFi Porto Digital', 'public' : 'WiFi Porto Digital'}
}

# FIXME: something wrong here...
auth_types = {
    0 : {'name' : 'unknown', 'types' : [0], 'operators' : []},
    1 : {'name' : 'open', 'types' : [1], 'operators' : [0, 1]},
    2 : {'name' : 'commer.', 'types' : [1], 'operators' : [2, 3, 4, 5]},
    3 : {'name' : 'WPA-x', 'types' : [2, 3, 4], 'operators' : []},
    4 : {'name' : '802.11x', 'types' : [5], 'operators' : []}}

# gps coords for a 'central' pin on porto, portugal
LAT  = 41.163158
LON = -8.6127137
# north, south, west, east limits of map, in terms of geo coordinates
LATN = LAT + 0.03
LATS = LAT - 0.03
LONE = LON + 0.06
LONW = LON - 0.06

def rebrand_auth(data):
    for at in sorted(auth_types.keys()):
        data.loc[(data['auth_orig'].isin(auth_types[at]['types'])) & ((not auth_types[at]['operators']) | (data['operator_id'].isin(auth_types[at]['operators']))), 'auth_custom'] = at
    return data

def add_band(data):
    # add 'band' column for '2.4' and '5.0'
    data['band'] = -1
    data.loc[(data['frequency'].astype(int) >= 2412) & (data['frequency'].astype(int) <= 2484), 'band'] = 0
    data.loc[(data['frequency'].astype(int) >= 5160) & (data['frequency'].astype(int) <= 5825), 'band'] = 1
    data['band'] = data['band'].astype(int)

def get_operator(essid):

    for op in operators:
        if any(ss in essid for ss in operators[op]['match-str'].split('|')):
            return op

    return 0

def is_public(essid, operator):
    
    if operator == 0:
        return 0

    if any(ss in essid for ss in operators[operator]['public'].split('|')):
        return 1
    return 0    

def get_db(input_dir):
    db_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(db_dir):
        os.makedirs(db_dir)
    database = pd.HDFStore(os.path.join(db_dir, "smc.hdf5"))
    return database

def calc_dist(data):
    data['dist'] = mapping.utils.gps_to_dist(data['new_lat'], data['new_lon'], data['new_lat'].shift(1), data['new_lon'].shift(1))
    return data

def mark_size(data):
    data['block-size'] = len(data.drop_duplicates(subset = ['seconds']))
    return data