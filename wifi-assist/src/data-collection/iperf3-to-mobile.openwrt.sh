#!/bin/sh

# usage: ifperf3-to-mobile.openwrt.sh <bitrate> <server-ip> <server-port> <iface> <remote-logger-ip>

echo $$ > /var/run/iperf3-to-mobile.pid

bitrate=$1
trace_nr=$2
channel=$3
server_ip=$4
server_port=$5
# iface=$6
# ryslog_ip=$7

echo "started iperf3 script w/ params:"
echo "  bitrate: $bitrate"
echo "  ip:port (iperf3 server): $server_ip:$server_port"
# echo "  wlan iface: $iface"
# echo "  ryslog ip: $ryslog_ip"

# trap ctrl-c and call signal_handler()
stop_loop=false
trap signal_handler INT

# set stop_loop to true after catching CTRL-C signal
signal_handler() {
    echo "** received CTRL-C : quitting iperf3 script"
    stop_loop=true
}

# # set remote syslog receiver
# killall logread
# logread -f -u -r $ryslog_ip 514 -P unifi-ac-lite &

# # start tcpdump capture, pipe output to logger
# tcpdump -tt -S -e -vvvv -i $iface -s0  | logger -t "tcpdump" &

# get mac addr of wifi iface
wiface=""
if [ "$(iwconfig wlan0 | awk '/Access Point/ {print $6}')" == "24:05:0F:61:51:14" ]
then
    wiface="wlan0"
elif [ "$(iwconfig wlan1 | awk '/Access Point/ {print $6}')" == "24:05:0F:61:51:14" ]
then  
    wiface="wlan1"
else
    echo "error : no wlan iface. aborting."
    exit 1
fi

mac_addr=$(iw $wiface info | awk '/addr/ {print $2}')

# run iperf3 in captures of 5 seconds (pipe output to logger)
while [ "$stop_loop" = false ]; do

    # extract the output of iperf3
    output=$(iperf3 -V -J -t 5 -c $server_ip -p $server_port -u -b $bitrate)

    # check for errors in iperf3's output: if errors exist, exit
    error="$(echo "$output" | awk '/error/ {print substr ($2, 2, 6)}')"
    if [ "$error" = "error" ]
    then
        sleep 1
    else
        # otherwise, keep relaying the output to rsyslog
        echo "$output" | logger -t "$mac_addr|$trace_nr|$channel|$bitrate|iperf3-log"
    fi
done

# kill tcpdump after CTRL+C
# killall tcpdump
# killall logread

exit
