# ac.py : utils to decode ieee 802.11ac-specific wlan frames
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

# subcarriers for which a compressed beamforming feedback matrix subfield is sent back. 
# IEEE Std 802.11ac-2013 amendment
ns_arr = np.array([[52, 30, 16], [108, 58, 30], [234, 122, 62], [468, 244, 124]], np.int32)

# subcarriers for which the delta SNR subfield is sent back to the beamformer
# IEEE Std 802.11ac-2013 amendment
delta_ns_arr = np.array([[30, 16, 10], [58, 30, 16], [122, 62, 32], [244, 124, 64]], np.int32)

# initial values for sscidx (subcarrier indeces)  
sscidx_init = {
    0 : -28,
    1 : -58,
    2 : -122,
    3 : -250
}

sscidx_mapping = {
    0 : {
        0 : np.arange(-28, 0, 2).tolist() + [-1, 1] + np.arange(2, 30, 2).tolist(),
        1 : np.arange(-28, 0, 4).tolist() + [-1, 1] + np.arange(4, 32, 4).tolist(),
        2 : np.arange(-28, 2, 8).tolist() + [-1, 1] + np.arange(4, 34, 8).tolist()
    },
    1 : {
        0 : np.arange(-58, 0, 2).tolist() + np.arange(2, 60, 2).tolist(),
        1 : np.arange(-58, 0, 4).tolist() + np.arange(2, 60, 4).tolist(),
        2 : np.arange(-58, 2, 8).tolist() + np.arange(2, 64, 8).tolist()
    },
    2 : {
        0 : np.arange(-122, 0, 2).tolist() + np.arange(2, 124, 2).tolist(),
        1 : np.arange(-122, 0, 4).tolist() + np.arange(2, 126, 4).tolist(),
        2 : np.arange(-122, 2, 8).tolist() + np.arange(2, 128, 8).tolist()
    }
}

def dequantize_angle(k, bits, psi = True):    
    if psi:
        return ((float(k) * np.pi) / (2**(bits + 1))) + (np.pi / (2**(bits + 2)))
    else:
        return ((float(k) * np.pi) / (2**(bits - 1))) + (np.pi / (2**(bits)))
        
def decode_vht_compressed_bf_report(data):

    bf_data = []
    for i, row in data.iterrows():

        bf_record = defaultdict()
        
        # compressed bf report
        bf_report = row['wlan mimo vht compressed bf report']
        # mimo params
        nc = row['wlan mimo nc'] + 1
        nr = row['wlan mimo nr'] + 1
        feedback_type = row['wlan mimo feedbacktype']
        codebook_info = row['wlan mimo codebookinfo']
#        channel_width = row['wlan mimo channel width']
#        grouping = row['wlan mimo grouping']
#        ns = ns_arr[channel_width][grouping]

        bf_record['no'] = row['no']
        offset = 0
        
        # snr per stream (nc * 1 byte)
        for i in range(nc):
            avg_snr = (((int("0x%s" % (bf_report[offset:(offset + (1*2))]), 0) & 0xFF) / 4.0) + 22.0)
            bf_record[('avg-snr-%d' % (i + 1))] = avg_snr
            offset += 1*2
    
        if (feedback_type):
            if (codebook_info):
                psi = 7
                phi = 9
            else:
                psi = 5
                phi = 7
    
        else:
            if (codebook_info):
                psi = 4
                phi = 6
            else:
                psi = 2
                phi = 4
        
        # phi angle decode
        # FIXME : this needs to be done for all subcarriers or subcarrier groups
        # according to the info in 8.4.1.48 in the ieee 802.11ac spec
        off_pos = 0
        for ic in range(1, nc + 1):
            for ir in range(1, nr):
    
                if (ir >= ic):
                    
                    # phi is between 4 and 9 bit, as such will always be contained within 2 byte (16 bit) after offset
                    wd = int("0x%s" % (bf_report[offset:(offset + (2*2))]), 0)
                    angle_val = wd >> ((2 * 8) - off_pos - phi)
                    angle_val = angle_val & ~(~0 << phi)

                    bf_record[('phi-%d-%d' % (ir, ic))] = dequantize_angle(angle_val, phi, psi = False)
                
                off_pos += phi
                if off_pos >= 8:
                    offset += 1*2
                    off_pos = off_pos % 8
    
        # psi angle decode
        for ic in range(1, nc + 1):
            for ir in range(2, nr + 1):
    
                if (ir > ic):
                    
                    # psi is between 2 and 7 bit, as such will always be contained within 2 byte (16 bit) after offset
                    wd = int("0x%s" % (bf_report[offset:(offset + (2*2))]), 0)
                    angle_val = wd >> ((2 * 8) - off_pos - psi)
                    angle_val = angle_val & ~(~0 << psi)

                    bf_record[('psi-%d-%d' % (ir, ic))] = dequantize_angle(angle_val, psi)
                
                off_pos += psi
                if off_pos >= 8:
                    offset += 1*2
                    off_pos = off_pos % 8
                    
        bf_data.append(bf_record)

    bf_data = pd.DataFrame(bf_data)
    return bf_data

def decode_vht_mu_exclusive_bf_report(data):
    
    data = data.dropna(subset = ['wlan mimo vht exclusive bf report'])
    
    bf_data = []
    for i, row in data.iterrows():
        
        bf_report = row['wlan mimo vht exclusive bf report']
#        print(bf_report)
#        if not bf_report:
#            continue
            
        bf_record = defaultdict()
        
        # compressed bf report
        bf_report = row['wlan mimo vht exclusive bf report']
        # mimo params
        nc = row['wlan mimo nc'] + 1
#        nr = row['wlan mimo nr'] + 1
#        codebook_info = row['wlan mimo codebookinfo']
        channel_width = row['wlan mimo channel width']
        grouping = row['wlan mimo grouping']
#        ns = ns_arr[channel_width][grouping]
#        # nr. of subcarriers for which delta snr is reported by beamformees in MU-MIMO
#        xnsc = delta_ns_arr[channel_width][grouping]

        bf_record['no'] = row['no']
        offset = 0
        
#        # nr. of bytes to represent delta snr : 
#        #   - nc: nr. of spatial streams
#        #   - xnsc: nr. of subcarriers
#        #   - 4: delta snr values represented in 4 bit
#        if ((nc * xnsc * 4) % 8)
#            off_len = (nc * xnsc * 4) / 8 + 1
#        else
#            off_len = (nc * xnsc * 4) / 8
        
#        print('chann. width : %d, ng : %d' % (channel_width, grouping))
        sub_carriers = sscidx_mapping[channel_width][grouping]

        mask = 0xFF 
        shift = 0
        # for each subcarrier k
        for k, sc in enumerate(sub_carriers):
            # for each spatial stream i
            for i in range(1, nc + 1):
                
                if not k % 2:
                    mask = 0x00F0
                    shift = 4
                else:
                    mask = 0x000F
                    shift = 0
                
                # decode next 4 bit
                delta_snr = int("0x%s" % (bf_report[offset:(offset + (1*2))]), 0) & mask
                delta_snr = delta_snr >> shift
                delta_snr = (delta_snr - 16) if delta_snr > 7 else delta_snr
                
#                print('delta-snr-%d-%d : %d' % (k, i, delta_snr))
                bf_record[('delta-snr-%d-%d' % (k, i))] = float(delta_snr)
                
                if k % 2:
                    offset += 1
                
        bf_data.append(bf_record)
                
    bf_data = pd.DataFrame(bf_data)
    return bf_data