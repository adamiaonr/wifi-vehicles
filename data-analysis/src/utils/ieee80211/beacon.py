# beacon.py : decode hex info elements in beacons, as provided by wireshark
# Copyright (C) 2018  adamiaonr@cmu.edu

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import pandas as pd
import numpy as np

from collections import defaultdict

def decode_ht_supported_channel_width(value):
    if 'Channel of any width supported' in value:
        return {'ht-info-channel-width' : 40}
    else:
        return {'ht-info-channel-width' : 20}

def decode_vht_tpe_tx_pwr_constraint(value):
    try:
        res = float(value.replace('dBm', '').strip())
    except AttributeError as error:
        return np.nan

def decode_vht_op_channel_width(value):
    # FIXME: options missing
    try:
        if '20 MHz or 40 MHz' in value:
            return {'vht-op-channel-width' : 40}
        else:
            return {'vht-op-channel-width' : 20}
    except TypeError as error:
        return {'vht-op-channel-width' : np.nan}

def decode(value, decode_key):

    res = defaultdict()
    
    try:
        value = int(value, 16)
    except TypeError as error:
        for k in decode_key:
            res[k] = np.nan
        return res

    for k in decode_key:
        res[k] = ((value >> decode_key[k]['shift']) & decode_key[k]['mask'])
    return res

def decode_ht_capabilities(value):

    decode_key = {
        'ht-cap-ldpc'          : {'shift' : 0, 'mask' : 0x01},
        'ht-cap-channel-width' : {'shift' : 1, 'mask' : 0x01},
        'ht-cap-sm-power-save' : {'shift' : 2, 'mask' : 0x03},
        'ht-cap-green-field'   : {'shift' : 4, 'mask' : 0x01},
        'ht-cap-short-gi-20'   : {'shift' : 5, 'mask' : 0x01},
        'ht-cap-short-gi-40'   : {'shift' : 6, 'mask' : 0x01},
        'ht-cap-tx-stbc'       : {'shift' : 7, 'mask' : 0x01},
        'ht-cap-rx-stbc'       : {'shift' : 8, 'mask' : 0x03},
        'ht-cap-delayed-block-ack' : {'shift' : 10, 'mask' : 0x01},
        'ht-cap-max-amsdu-len'     : {'shift' : 11, 'mask' : 0x01},
        'ht-cap-dsss-cck-40'       : {'shift' : 12, 'mask' : 0x01},
        'ht-cap-psmp'       : {'shift' : 13, 'mask' : 0x01},
        'ht-cap-40-intolerance'    : {'shift' : 14, 'mask' : 0x01},
        'ht-cap-l-sig-txop-protection' : {'shift' : 15, 'mask' : 0x01}
    }

    ht_cap = decode(value, decode_key)
    return ht_cap

def decode_ht_ampdu(value):

    decode_key = {
        'ht-ampdu-max-rx-ampdu-len' : {'shift' : 0, 'mask' : 0x03},
        'ht-ampdu-mpdu-density' : {'shift' : 2, 'mask' : 0x07}
    }

    ht_ampdu = decode(value, decode_key)
    return ht_ampdu

def decode_txbf(value):
    return {}

def decode_asel(value):
    return {}

def decode_extended_capabilities(value):
    return {}

def decode_ht_info_subset(value, nr = 1):

    if nr == 1:
        decode_key = {
            'ht-info-subset-secondary-channel-offset' : {'shift' : 0, 'mask' : 0x03},
            'ht-info-subset-supp-channel-width' : {'shift' : 2, 'mask' : 0x01},
            'ht-info-subset-rifs' : {'shift' : 3, 'mask' : 0x01},
            'ht-info-subset-psmp' : {'shift' : 4, 'mask' : 0x01},
            'ht-info-subset-shortest-serv-interval' : {'shift' : 5, 'mask' : 0x07}}

    else:
        return {}

    ht_info_subset = decode(value, decode_key)
    return ht_info_subset

def decode_fixed_capabilities(value):
    return {}

def decode_vht_capabilities(value):

    decode_key = {
        'vht-cap-max-mpdu-len' : {'shift' : 0, 'mask' : 0x03},
        'vht-cap-160-channel-width' : {'shift' : 2, 'mask' : 0x03},
        'vht-cap-rx-ldpc' : {'shift' : 4, 'mask' : 0x01},
        'vht-cap-short-gi-80' : {'shift' : 5, 'mask' : 0x01},
        'vht-cap-short-gi-160' : {'shift' : 6, 'mask' : 0x01},
        'vht-cap-tx-stbc' : {'shift' : 7, 'mask' : 0x01},
        'vht-cap-rx-stbc' : {'shift' : 8, 'mask' : 0x07},
        'vht-cap-su-bmfr' : {'shift' : 11, 'mask' : 0x01},
        'vht-cap-su-bmfe' : {'shift' : 12, 'mask' : 0x01},
        'vht-cap-bmfe-sts' : {'shift' : 13, 'mask' : 0x07},
        'vht-cap-sounding-dim' : {'shift' : 16, 'mask' : 0x07},
        'vht-cap-mu-bmfr' : {'shift' : 19, 'mask' : 0x01},
        'vht-cap-mu-bmfe' : {'shift' : 20, 'mask' : 0x01},
        'vht-cap-txop-ps' : {'shift' : 21, 'mask' : 0x01},
        'vht-cap-htc-vht' : {'shift' : 22, 'mask' : 0x01},
        'vht-cap-max-ampdu-len-exp' : {'shift' : 23, 'mask' : 0x07},
        'vht-cap-vht-link-adapt' : {'shift' : 26, 'mask' : 0x03},
        'vht-cap-rx-antn-pat-cons' : {'shift' : 28, 'mask' : 0x01},
        'vht-cap-rx-antn-pat-cons' : {'shift' : 29, 'mask' : 0x01},
        'vht-cap-ext-nss-bw' : {'shift' : 30, 'mask' : 0x03}
    }

    vht_info_cap = decode(value, decode_key)
    return vht_info_cap
