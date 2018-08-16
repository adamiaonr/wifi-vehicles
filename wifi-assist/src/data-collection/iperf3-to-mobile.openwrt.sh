#!/bin/sh

# usage: ifperf3-to-mobile.openwrt.sh <bitrate> <server-ip> <server-port> <iface> <remote-logger-ip>

if [ $# -lt 4 ]
then
    echo "usage : $0 <protocol> <trace-nr> <server_ip> <server_port> (if protocol = 'udp': <udp-bitrate>)"
    exit 1
fi

echo $$ > /var/run/iperf3-to-mobile.pid

protocol=$1
trace_nr=$2
# channel=$3
server_ip=$3
server_port=$4

echo "started iperf3 script w/ params:"
echo "  protocol: $protocol"
echo "  ip:port (iperf3 server): $server_ip:$server_port"
# echo "  channel (iperf3 server): $server_ip:$server_port"
echo "  trace-nr: $trace_nr"

if [ "$protocol" == "udp" ]
then

    if [ $# -lt 5 ]
    then
        echo "usage : $0 <protocol> <trace-nr> <server_ip> <server_port> <udp-bitrate>"
        exit 1
    fi

    bitrate=$5
    echo "  bitrate: $bitrateM (bps)"

elif [ "$protocol" != "tcp" ]
then  
    echo "error : unknown protocol : $protocol. aborting."
    exit 1
fi

# trap ctrl-c and call signal_handler()
stop_loop=false
trap signal_handler INT

# set stop_loop to true after catching CTRL-C signal
signal_handler() {
    echo "** received CTRL-C : quitting iperf3 script"
    stop_loop=true
}

# get mac addr of wifi iface
wiface=""
if [ "$(iwinfo wlan0 info | awk '/Access Point/ {print $3}')" == "24:05:0F:61:51:14" ]
then
    wiface="wlan0"
elif [ "$(iwinfo wlan1 info | awk '/Access Point/ {print $3}')" == "24:05:0F:61:51:14" ]
then  
    wiface="wlan1"
else
    echo "error : no wlan iface. aborting."
    exit 1
fi

mac_addr=$(iw $wiface info | awk '/addr/ {print $2}')
# prefix to prepend to logger output:
#   - mac_addr (remove ':')
#   - trace_nr
#   - protocol : 0 for udp, 1 for tcp
#   - log line type : 'cbt' or 'iperf'
logger_prefix="$(echo $mac_addr | sed -r 's/[:]//g')|$trace_nr"

# run iperf3 in captures of 5 seconds (pipe output to logger)
while [ "$stop_loop" = false ]; do

    # extract the output of iperf3
    if [ "$protocol" == "udp" ]
    then
        output=$(iperf3 -V -J -t 5 -c $server_ip -p $server_port -u -b $bitrateM --get-server-output)
        logger_prefix="$logger_prefix|0|iperf"
    else
        output=$(iperf3 -V -J -t 5 -c $server_ip -p $server_port)
        logger_prefix="$logger_prefix|1|iperf"
    fi

    # check for errors in iperf3's output: if errors exist, exit
    error="$(echo "$output" | awk '/error/ {print substr ($2, 2, 6)}')"
    if [ "$error" = "error" ]
    then
        sleep 1
    else
        # otherwise, keep relaying the output to rsyslog
        echo "$output" | logger -t "$logger_prefix"
    fi
done

# kill tcpdump after CTRL+C
# killall tcpdump
# killall logread

exit
