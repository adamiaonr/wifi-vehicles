#!/bin/sh

# usage: ifperf3-to-mobile.sh <bitrate> <server-ip> <server-port> <iface> <remote-logger-ip>

bitrate=$1
server_ip=$2
server_port=$3
iface=$4
remote_logger_ip=$5

# set remote syslog receiver
???

# trap ctrl-c and call signal_handler()
stop_loop=false
trap signal_handler INT

# set stop_loop to true after catching CTRL-C signal
function signal_handler() {
	echo "** trapped CTRL-C"
	stop_loop=true
}

# start tcpdump capture, pipe output to logger
tcpdump -tt -S -e -vvvv -i $4 -s0 | logger

# run iperf3 in captures of 5 seconds (pipe output to logger)
while [ "$stop_loop" = false ]; do
	iperf3 -V -J -t 5 -c $server_ip -p $server_port -u -b $bitrateM | logger
done

# kill tcpdump after CTRL+C
pkill -f tcpdump

exit
