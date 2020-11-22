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

    with open(args.tshark_config) as tconfig:
        tshark_config = json.load(tconfig)

    for wifi_type in tshark_config:

        base_dir = args.input_dir

        for pcap_file in sorted(glob.glob(os.path.join(base_dir, ('trace-*/monitor.%s.*.pcap' % (wifi_type))))):
            for mode in tshark_config[wifi_type]:

                output_file = '.'.join(pcap_file.split('.')[:-2]) + ('.%s.csv' % (mode))
                move_loc = os.path.join(args.output_dir, '/'.join(output_file.split('/')[-2:]))

                # if os.path.isfile(move_loc):
                #     print('%s: %s already exists. skipping processing.' % (sys.argv[0], move_loc))
                #     continue

                print('processing %s' % (pcap_file))

                # fields (-e) & filter (-Y) arguments of the tshark command, as str, built from the configs dict
                print(mode)
                print(wifi_type)

                fields = "-e " + " -e ".join(tshark_config[wifi_type][mode]['fields'])
                print(fields)
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
