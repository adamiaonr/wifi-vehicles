#!/bin/sh

echo $$ > /var/run/get-cbt.pid

stop_loop=false
trap signal_handler INT

# set stop_loop to true after catching CTRL-C signal
signal_handler() {
    echo "** received CTRL-C : quitting cbt script"
    stop_loop=true
}

# get mac addr of wifi iface
mac_addr=$(iw wlan0 info | awk '/addr/ {print $2}')

while [ "$stop_loop" = false ]; do

	# gather survey dump from active channel
	survey="$(iw wlan0 survey dump | grep "in use" -A 5)"

	# extract cbt survey components
	freq=$(echo "$survey" | awk '/frequency/ {print $2}')
	noise=$(echo "$survey" | awk '/noise/ {print $2}')
	cat=$(echo "$survey" | awk '/channel active time/ {print $4}')
	cbt=$(echo "$survey" | awk '/channel busy time/ {print $4}')
	crt=$(echo "$survey" | awk '/channel receive time/ {print $4}')
	ctt=$(echo "$survey" | awk '/channel transmit time/ {print $4}')

	# send csv line to rsyslog
	echo "$freq,$noise,$cat,$cbt,$crt,$ctt" |  logger -t "$mac_addr""|cbt-log"

	sleep 1

done

exit
