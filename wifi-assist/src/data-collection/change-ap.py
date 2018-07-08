import csv
import json
import argparse
import os
import time
import datetime
import subprocess
import sys

def symlink(src, dst):

    print(src)
    print(dst)
    os.unlink(dst)
    os.symlink(src, dst)

    # cmd = ["ln", "-sf", src, dst]
    # print(cmd)
    # proc = subprocess.call(cmd)

if __name__ == "__main__":

    # use an ArgumentParser for a nice CLI
    parser = argparse.ArgumentParser()

    # options (self-explanatory)
    parser.add_argument(
        "--channel", 
         help = """wifi channel nr. to set in ap (e.g. '--channel 6').""")

    parser.add_argument(
        "--bw", 
         help = """bandwidth of wifi channel, in MHz (e.g. '--bw 40' to 40 MHz channel). default is 20 MHz.""")

    parser.add_argument(
        "--auth", 
         help = """authentication of wifi ap (e.g. '--auth wpa2'). default is 'open'.""")

    parser.add_argument(
        "--configs-dir", 
         help = """dir with hostapd.conf files.""")

    args = parser.parse_args()

    if not args.configs_dir:
        sys.stderr.write("""%s: [ERROR] please provide dir w/ hostapd.conf files. aborting.""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.channel:
        sys.stderr.write("""%s: [ERROR] please provide wifi channel nr. aborting.\n""" % sys.argv[0]) 
        parser.print_help()
        sys.exit(1)

    if not args.bw:
        args.bw = '20'

    if not args.auth:
        args.auth = 'open'

    hostapd_filename = os.path.join(args.configs_dir, 'hostapd.conf.' + args.auth + '.' + args.channel + '.' + args.bw + '.conf')
    symlink(
        hostapd_filename,
        os.path.join('/etc/hostapd/', 'hostapd.conf'))

    sys.exit(0)
