#!/bin/bash

# usage: ifperf3-to-mobile.openwrt.sh <bitrate> <server-ip> <server-port> <iface> <remote-logger-ip>

if [ $# -lt 5 ]
then
    echo "usage : $0 <protocol> <trace-nr> <output-dir> <server_ip> <server_port> (if protocol = 'udp': <udp-bitrate>) (optional: <iface-for-capture>)"
    exit 1
fi

protocol=$1
trace_nr=$2
# channel=$3
output_dir=$3
server_ip=$4
server_port=$5
bitrate=""

echo "started iperf3 script w/ params:"
echo "  protocol: $protocol"
echo "  trace-nr: $trace_nr"
echo "  output-dir: $output_dir"
echo "  ip:port: $server_ip:$server_port"
# echo "  channel (iperf3 server): $server_ip:$server_port"

# trap ctrl-c and call signal_handler()
stop_loop=false
trap signal_handler INT

# set stop_loop to true after catching CTRL-C signal
signal_handler() {
    echo "** received CTRL-C : quitting iperf3 script"
    stop_loop=true
}

if [ "$protocol" == "udp" ]
then

    if [ $# -lt 6 ]
    then
        echo "usage : $0 <protocol> <trace-nr> <output-dir> <server_ip> <server_port> <udp-bitrate> (optional: <iface-for-capture>)"
        exit 1
    fi

    bitrate="$6""M"
    echo "  bitrate: $bitrate (bps)"

    if [ "$7" ]
    then
        echo "  capture: yes"
        tcpdump -i "$7" -s0 udp -w "$output_dir"/"iperf3-to-mobile.capture.$(date +"%s").pcap" &
    fi

elif [ "$protocol" == "tcp" ]
then  

    if [ "$6" ]
    then
        echo "  capture: yes"
        tcpdump -i "$6" -s0 tcp -w "$output_dir"/"iperf3-to-mobile.capture.$(date +"%s").pcap" &
    fi

else
    echo "error : unknown protocol : $protocol. aborting."
    exit 1
fi

# create .json file
output_file="$output_dir"/"iperf3-to-mobile.report.$(date +"%s").json"
touch $output_file
# clear .json file
echo -e "" > $output_file

# # run iperf3 in captures of 5 seconds (pipe output to logger)
# while [ "$stop_loop" = false ]; do

#     # extract the output of iperf3
#     if [ "$protocol" == "udp" ]
#     then
#         iperf3 -V -J -t 5 -c $server_ip -p $server_port -u -b $bitrate --get-server-output
#     else
#         iperf3 -V -J -t 10 -c $server_ip -p $server_port
#     fi

#     # check for errors in iperf3's output: if errors exist, exit
#     error="$(echo "$output" | awk '/error/ {print substr ($2, 2, 6)}')"
#     if [ "$error" = "error" ]
#     then
#         sleep 1
#     else
#         echo -e "$output" >> $output_file
#     fi
# done

# extract the output of iperf3
if [ "$protocol" == "udp" ]
then
    iperf3 -V -J -t 10 -c $server_ip -p $server_port -u -b $bitrate --get-server-output
else
    iperf3 -V -J -t 10 -c $server_ip -p $server_port
fi

echo -e "iperf3 test over..."

# check for errors in iperf3's output: if errors exist, exit
error="$(echo "$output" | awk '/error/ {print substr ($2, 2, 6)}')"
if [ "$error" = "error" ]
then
    sleep 1
else
    echo -e "$output" >> $output_file
fi

# kill tcpdump
pkill -f tcpdump

exit
