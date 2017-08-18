import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import os
import argparse
import sys
import glob
import math
import gmplot
import time

from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict

# custom imports
from plot_utils import *

matplotlib.rcParams.update({'font.size': 16})

# analyze dhcp-focused captures conducted by arr.franco@hotmail.com 
# back in 2014
def analyze_dhcp_capture(
    data_dir, 
    subnets = {'eduroam': '172.30', 'meo': '10.14', 'porto-digital': '192.168.17', 'zon': '192.168.3'}):

    # output data given in dict format
    output_data = defaultdict()

    # analyze data on .csv files with the 'original.csv' suffix. these 
    # correspond to the 'old.pcap' files captured by arr.franco@hotmail
    for file_name in sorted(glob.glob(os.path.join(data_dir, '*original.csv'))):

        # network name (e.g. 'eduroam', 'meo', 'zon', 'pdigital')
        network_name = file_name.split(".")[0].split("/")[-1].split("-original")[0]
        # output data is indexed by the network name
        output_data[network_name] = defaultdict()

        # read the .csv file which refers to network name
        session_data = pd.read_csv(file_name)

        # extract dhcp packets
        dhcp_data = session_data.loc[session_data["Protocol"] == "DHCP"]
        # get dhcp requests
        dhcp_reqs = dhcp_data.loc[(dhcp_data["Info"].str.contains("DHCP Request")) & (dhcp_data["Source"] == '0.0.0.0')]
        # get dhcp acks
        dhcp_acks = dhcp_data.loc[(dhcp_data["Info"].str.contains("DHCP ACK"))]

        # collect dhcp and association times
        output_data[network_name]['dhcp-times'] = OrderedDict()
        output_data[network_name]['assoc-times'] = OrderedDict()
        # aux. variables (names are descriptive enough...)
        last_dhcp_ack_frame_num = 0
        prev_dhcp_req_frame_num = 0
        last_dhcp_ack_network = '0.0'

        # FIXME: it's lame to use cycles w/ pandas dataframes, but i can't 
        # figure out how to do this otherwise
        for index, dhcp_req in dhcp_reqs.iterrows():

            # if the current dhcp_req frame # is strictly less than 
            # the last_dhcp_ack frame #, ignore the current dhcp_req
            if dhcp_req["No."] < last_dhcp_ack_frame_num:
                continue

            # find first dhcp ack frame w/ no. strictly larger than the current dhcp request
            last_dhcp_ack_frame = dhcp_acks.loc[dhcp_acks["No."] > dhcp_req["No."]].iloc[0]
            last_dhcp_ack_frame_num = last_dhcp_ack_frame["No."]

            # dhcp time : time diff in-between first dhcp ack and first dhcp request
            # NOTE: we only record time diffs for allowed subnets (listed in subnets)
            if (subnets[network_name] in last_dhcp_ack_frame["Source"]):
                # indexed by the frame # of the corresponding dhcp request
                output_data[network_name]['dhcp-times'][dhcp_req["No."]] = last_dhcp_ack_frame["Time"] - dhcp_req["Time"]

            # assoc. time: time diff in-between the last ip packet before the next 
            # dhcp request, and said 'next dhcp request'

            # q: why the 'prev_dhcp_req_frame_num > 0'?
            # a: by definition (see above), assoc. times are recorded after the 
            # first dhcp req & ack pair
            if prev_dhcp_req_frame_num > 0:

                # get the last ip packet exchanged in subnet of the previous dhcp 
                # exchange, and before the current dhcp request
                last_ip_packet = session_data.loc[(session_data["No."] < dhcp_req["No."]) 
                    & session_data["Source"].str.contains(last_dhcp_ack_network)].iloc[-1]

                # record the assoc. time
                if (subnets[network_name] in last_dhcp_ack_frame["Source"]):
                    output_data[network_name]['assoc-times'][prev_dhcp_req_frame_num] = (dhcp_req["Time"] - last_ip_packet["Time"])

            last_dhcp_ack_network = ".".join(last_dhcp_ack_frame["Source"].split(".")[:2])
            # save reference to the current dhcp req packet, to serve as index 
            # for the assoc-times dict
            prev_dhcp_req_frame_num = dhcp_req["No."]

    return output_data

def plot(data_dir, out_dir):

    data = analyze_dhcp_capture(data_dir)

    # 2 subfigs, side-by-side:
    #   - cdf of assoc. times, for each of the networks
    #   - cdf of dhcp times, for each of the networks
    fig_1 = plt.figure(figsize = (12, 5))
    axx = [fig_1.add_subplot(121), fig_1.add_subplot(122)]

    # subfigs titles
    axx[0].set_title('(a) wifi assoc. + auth. times*\n*not including web portal auth.')
    axx[1].set_title('(b) dhcp times')
    # network colors
    network_colors = {'eduroam': 'red', 'meo': 'green', 'porto-digital': 'blue', 'zon': 'black'}

    for network_name in data:

        # index for ax array
        axx_i = 0
        for case in data[network_name]:

            time_values = np.array(data[network_name][case].values())
            
            # alternative way of getting a cdf plot, using the plt.step() function
            # https://stackoverflow.com/questions/39728723/vertical-line-at-the-end-of-a-cdf-histogram-using-matplotlib
            n = np.arange(1, len(time_values) + 1) / np.float(len(time_values))
            time_values_sorted = np.sort(time_values)
            axx[axx_i].step(time_values_sorted, n,
                linewidth = 0.8, color = network_colors[network_name], label = network_name)

            axx_i += 1

    # chart details
    for ax in axx:

        # grids on axis
        ax.xaxis.grid(True)
        ax.yaxis.grid(True)
        # legend position
        ax.legend(fontsize = 12, ncol = 1, loc='lower right')
        # axis labels
        ax.set_xlabel("time (s)")
        ax.set_ylabel("CDF")
        # y axis limits
        ax.set_ylim(0, 1.0)

    fig_1.tight_layout()
    fig_1.subplots_adjust(top = 0.95)

    plt.savefig(os.path.join(out_dir, "dhcp-capture.pdf"), bbox_inches = 'tight', format = 'pdf')