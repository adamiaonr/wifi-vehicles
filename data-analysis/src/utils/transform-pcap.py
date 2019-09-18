# transform-pcap.py : transform .pcap files into .csv files
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

import os
import sys
import json
import argparse
import glob
import timeit

configs = {
    'n' : {
        'folder' : 'm1',
        'mgmt' : {
            'fields' : ['frame.number', 'frame.time_epoch', 'frame.time_delta', 'frame.len', 
                'wlan_radio.phy', 'wlan_radio.channel', 'wlan_radio.frequency', 'wlan_radio.signal_dbm', 'wlan_radio.noise_dbm', 
                'wlan_radio.data_rate', 'wlan_radio.11n.mcs_index', 'wlan_radio.duration', 'wlan_radio.preamble', 'wlan_radio.timestamp', 
                'radiotap.length', 'radiotap.channel.flags.2ghz', 'radiotap.channel.flags.5ghz', 'radiotap.channel.freq', 
                'wlan.ta', 'wlan.ra', 'wlan.fc.type_subtype', 'wlan.fc.retry', 'wlan.seq', 'wlan.frag', 
                'wlan.fixed.beacon', 'wlan.fixed.timestamp', 'wlan.ds.current_channel',
                # 'wlan.ht.info.chanwidth', 'wlan.ht.capabilities', 'wlan.ht.ampduparam',
                # 'wlan.ht.info.delim1', 'wlan.ht.info.delim2', 'wlan.ht.info.delim3',
                ],

            'filter' : '(wlan.ta == 78:8a:20:57:1f:6b) && (wlan.fc.type == 0)',
        },
        'data' : {
            'fields' : [
                'frame.number', 'frame.time_epoch', 'frame.time_delta', 'frame.len',
                'ip.hdr_len', 'ip.proto', 'ip.src', 'ip.dst', 'ip.id', 'ip.frag_offset', 'ip.flags', 'ip.reassembled_in',
                'udp.srcport', 'udp.dstport',
                'wlan_radio.phy', 'wlan_radio.channel', 'wlan_radio.frequency', 'wlan_radio.signal_dbm', 'wlan_radio.noise_dbm', 'wlan_radio.data_rate', 'wlan_radio.11n.mcs_index', 'wlan_radio.duration', 'wlan_radio.preamble', 'wlan_radio.timestamp',
                'radiotap.length', 'radiotap.channel.flags.2ghz', 'radiotap.channel.flags.5ghz', 'radiotap.channel.freq',
                'wlan.ta', 'wlan.ra', 'wlan.fc.type_subtype', 'wlan.fc.retry', 'wlan.seq', 'wlan.frag', 'wlan.ba.bm', 'wlan.fixed.ssc.sequence'],

            'filter' : '(((wlan.ta == 78:8a:20:57:1f:6b) && (wlan.ra == 24:05:0f:61:51:14 || wlan.ra == c4:6e:1f:25:d7:d8 || wlan.ra == c4:6e:1f:25:cb:df)) || ((wlan.ra == 78:8a:20:57:1f:6b) && (wlan.ta == 24:05:0f:61:51:14 || wlan.ta == c4:6e:1f:25:d7:d8 || wlan.ta == c4:6e:1f:25:cb:df))) && ((wlan.fc.type_subtype == 25) || (wlan.fc.type_subtype == 29) || (wlan.fc.type_subtype == 40))',
        }
    },
    'ac' : {
        'folder' : 'w4/tp-02',
        'mgmt' : {
            'fields' : [
                'frame.number', 'frame.time_epoch', 'frame.time_delta', 'frame.len',
                'wlan_radio.phy', 'wlan_radio.channel', 'wlan_radio.frequency', 'wlan_radio.signal_dbm', 'wlan_radio.noise_dbm', 'wlan_radio.data_rate', 'wlan_radio.11ac.mcs', 'wlan_radio.11ac.nss', 'wlan_radio.duration', 'wlan_radio.preamble', 'wlan_radio.timestamp',
                'radiotap.length', 'radiotap.vht.beamformed', 'radiotap.channel.flags.2ghz', 'radiotap.channel.flags.5ghz', 'radiotap.channel.freq',
                'radiotap.vht.beamformed',
                'wlan.ta', 'wlan.ra', 'wlan.fc.type_subtype', 'wlan.fc.retry', 'wlan.seq', 'wlan.frag',
                'wlan.fixed.beacon', 'wlan.fixed.timestamp'],

            'filter' : '(wlan.ta == fc:ec:da:1b:63:a6) && (wlan.fc.type == 0)',
        },

        'data' : {
            'fields' : [
                'frame.number', 'frame.time_epoch', 'frame.time_delta', 'frame.len',
                'ip.hdr_len', 'ip.proto', 'ip.src', 'ip.dst', 'ip.id', 'ip.frag_offset', 'ip.flags', 'ip.reassembled_in',
                'udp.srcport', 'udp.dstport',
                'wlan_radio.phy', 'wlan_radio.channel', 'wlan_radio.frequency', 'wlan_radio.signal_dbm', 'wlan_radio.noise_dbm', 'wlan_radio.data_rate', 'wlan_radio.11ac.mcs', 'wlan_radio.11ac.nss', 'wlan_radio.duration', 'wlan_radio.preamble', 'wlan_radio.timestamp',
                'radiotap.length', 'radiotap.vht.beamformed', 'radiotap.channel.flags.2ghz', 'radiotap.channel.flags.5ghz', 'radiotap.channel.freq', 'radiotap.vht.beamformed',
                'wlan.ta', 'wlan.ra', 'wlan.fc.type_subtype', 'wlan.fc.retry', 'wlan.seq', 'wlan.frag', 'wlan.ba.bm', 'wlan.fixed.ssc.sequence',
#                'wlan.vht_ndp.token.number', 'wlan.vht_ndp.sta_info.feedback_type', 'wlan.vht.exclusive_beamforming_report', 'wlan.vht.capabilities', 'wlan.vht.mcsset.rxmcsmap', 'wlan.vht.mcsset.txmcsmap', 'wlan.vht.op.channelwidth', 'wlan.vht.op.channelcenter0', 'wlan.vht.op.channelcenter1', 'wlan.vht.tpe.pwr_constr_20', 'wlan.vht.tpe.pwr_constr_40', 'wlan.vht.mimo_control.sounding_dialog_tocken_nbr', 'wlan.vht.mimo_control.feedbacktype', 'wlan.vht.mimo_control.ncindex', 'wlan.vht.mimo_control.nrindex', 'wlan.vht.mimo_control.grouping', 'wlan.vht.mimo_control.chanwidth', 'wlan.vht.mimo_control.codebookinfo', 'wlan.vht.exclusive_beamforming_report',
                ],

            'filter' : '(((wlan.ta == fc:ec:da:1b:63:a6) && (wlan.ra == c4:e9:84:09:4a:5e || wlan.ra == 24:05:0f:61:52:99 || wlan.ra == 24:05:0f:aa:ab:5d)) || ((wlan.ra == fc:ec:da:1b:63:a6) && (wlan.ta == c4:e9:84:09:4a:5e || wlan.ta == 24:05:0f:61:52:99 || wlan.ta == 24:05:0f:aa:ab:5d))) && ((wlan.fc.type_subtype == 25) || (wlan.fc.type_subtype == 29) || (wlan.fc.type_subtype == 40))',
        },
    },
    'ad' : {
        'folder' : 'w4/tp-02',
        'mgmt' : {
            'fields' : [
                'frame.number', 'frame.time_epoch', 'frame.time_delta', 'frame.len',
                'wlan_radio.phy', 'wlan_radio.channel', 'wlan_radio.frequency', 'wlan_radio.signal_dbm', 'wlan_radio.noise_dbm', 
                'wlan_radio.data_rate', 'wlan_radio.11n.mcs_index', 'wlan_radio.duration', 'wlan_radio.preamble', 'wlan_radio.timestamp', 
                'radiotap.length', 'radiotap.channel.flags.2ghz', 'radiotap.channel.flags.5ghz', 'radiotap.channel.freq', 
                'wlan.ta', 'wlan.ra', 'wlan.fc.type_subtype', 'wlan.fc.retry', 'wlan.seq', 'wlan.frag',
                'wlan.fixed.beacon', 'wlan.fixed.timestamp',
                'wlan.ssw', 'wlan.sswf', 'wlan.bf', 'wlan.sswf.sector_select', 'wlan.sswf.snr_report', 'wlan.ssw.cdown', 'wlan.ssw.sector_id', 'wlan.ssw.direction',
            ],
            'filter' : 'wlan.fc.type_subtype == 0x0000 || wlan.fc.type_subtype == 0x0001 || wlan.fc.type_subtype == 0x0002 || wlan.fc.type_subtype == 0x0003 || wlan.fc.type_subtype == 0x000a || wlan.fc.type_subtype == 0x000b || wlan.fc.type_subtype == 0x000c',
        },
        'sweep' : {
            'fields' : [
                'frame.number', 'frame.time_epoch', 'frame.time_delta', 'frame.len',
                'wlan_radio.phy', 'wlan_radio.channel', 'wlan_radio.frequency', 'wlan_radio.signal_dbm', 'wlan_radio.noise_dbm', 
                'wlan_radio.data_rate', 'wlan_radio.11n.mcs_index', 'wlan_radio.duration', 'wlan_radio.preamble', 'wlan_radio.timestamp', 
                'radiotap.length', 'radiotap.channel.flags.2ghz', 'radiotap.channel.flags.5ghz', 'radiotap.channel.freq', 
                'wlan.ta', 'wlan.ra', 'wlan.fc.type_subtype', 'wlan.fc.retry', 'wlan.seq', 'wlan.frag',
                'wlan.ssw', 'wlan.sswf', 'wlan.bf', 'wlan.sswf.sector_select', 'wlan.sswf.snr_report', 'wlan.ssw.cdown', 'wlan.ssw.sector_id', 'wlan.ssw.direction',
            ],
            'filter' : 'wlan.fc.type_subtype == 0x0168 || wlan.fc.type_subtype == 0x0169 || wlan.fc.type_subtype == 0x016A',
        },

        'data' : {
            'fields' : [
                'frame.number', 'frame.time_epoch', 'frame.time_delta', 'frame.len',
                'ip.hdr_len', 'ip.proto', 'ip.src', 'ip.dst', 'ip.id', 'ip.frag_offset', 'ip.flags', 'ip.reassembled_in',
                'udp.srcport', 'udp.dstport',
                'wlan_radio.phy', 'wlan_radio.channel', 'wlan_radio.frequency', 'wlan_radio.signal_dbm', 'wlan_radio.noise_dbm', 
                'wlan_radio.data_rate', 'wlan_radio.11n.mcs_index', 'wlan_radio.duration', 'wlan_radio.preamble', 'wlan_radio.timestamp', 
                'radiotap.length', 'radiotap.channel.flags.2ghz', 'radiotap.channel.flags.5ghz', 'radiotap.channel.freq', 
                'wlan.ta', 'wlan.ra', 'wlan.fc.type_subtype', 'wlan.fc.retry', 'wlan.seq', 'wlan.frag', 'wlan.ba.bm', 'wlan.fixed.ssc.sequence'
            ],
            'filter' : '(((wlan.ta == 50:c7:bf:3c:53:1c || wlan.ta == 70:4f:57:72:b2:58) && (wlan.ra == 50:c7:bf:97:8a:a6)) || ((wlan.ra == 50:c7:bf:3c:53:1c || wlan.ra == 70:4f:57:72:b2:58) && (wlan.ta == 50:c7:bf:97:8a:a6))) && ((wlan.fc.type_subtype == 25) || (wlan.fc.type_subtype == 29) || (wlan.fc.type_subtype == 40))',
        },
    },
}

def gen_config(configs, filename):
    with open(filename, 'w') as cf:
        json.dump(configs, cf)

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input-dir", 
         help = """dir w/ .pcap data""")

    parser.add_argument(
        "--output-dir", 
         help = """dir to hold final """)

    parser.add_argument(
        "--tshark-config", 
         help = """.json file w/ tshark config""")

    args = parser.parse_args()

    if not args.input_dir:
        sys.stderr.write("""%s: [ERROR] must provide a dir w/ .pcap files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.output_dir:
        sys.stderr.write("""%s: [ERROR] must provide an output dir for .csv files\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.tshark_config:
        sys.stderr.write("""%s: [ERROR] must provide .config file for tshark\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)    

    gen_config(configs, args.tshark_config)
    with open(args.tshark_config) as tconfig:
        tshark_config = json.load(tconfig)

    for wifi_type in tshark_config:

        if wifi_type not in ['ac']:
            continue
        
        base_dir = os.path.join(args.input_dir, tshark_config[wifi_type]['folder'])
        for pcap_file in sorted(glob.glob(os.path.join(base_dir, ('trace-*/monitor.%s.*.pcap' % (wifi_type))))):

            for mode in tshark_config[wifi_type]:

                if mode not in ['mgmt', 'data', 'sweep']:
                    continue

                output_file = '.'.join(pcap_file.split('.')[:-2]) + ('.%s.csv' % (mode))
                move_loc = os.path.join(os.path.join(args.output_dir, tshark_config[wifi_type]['folder']), '/'.join(output_file.split('/')[-2:]))

                if os.path.isfile(move_loc):
                    print('%s: %s already exists. skipping processing.' % (sys.argv[0], move_loc))
                    continue

                print('processing %s' % (pcap_file))

                # fields (-e) & filter (-Y) arguments of the tshark command, as str, built from the configs dict
                fields = "-e " + " -e ".join(tshark_config[wifi_type][mode]['fields'])
                filtr = tshark_config[wifi_type][mode]['filter']

                cmd = 'tshark -r %s -2 -T fields %s -Y "%s" -E header=y -E separator=, -E quote=d -E occurrence=f > %s' % (pcap_file, fields, filtr, output_file)
                # print(cmd)
                start = timeit.default_timer()
                os.system(cmd)

                if os.path.isfile(output_file):
                    print('%s : processed %s (%.3f sec)' % (sys.argv[0], pcap_file, timeit.default_timer() - start))

                # move file to final location (external data bank)
                print('moving %s > %s' % (output_file, move_loc))
                start = timeit.default_timer()
                os.system('mv %s %s' % (output_file, move_loc))

                if os.path.isfile(move_loc):
                    print('%s : moved %s > %s (%.3f sec)' % (sys.argv[0], output_file, move_loc, timeit.default_timer() - start))

    sys.exit(0)
