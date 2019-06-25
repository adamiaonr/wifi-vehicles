#!/bin/sh

if [ $# -lt 3 ]
then
    echo "usage : $0 <trace-nr> <output-dir> <wlan-iface>"
    exit 1
fi

trace_nr=$1
output_dir=$2
wiface=$3

echo $$ > /var/run/get-cbt.pid

stop_loop=false
trap signal_handler INT

# set stop_loop to true after catching CTRL-C signal
signal_handler() {
    echo "** received CTRL-C : quitting cbt script"
    stop_loop=true
}

# # get wifi iface name
# wiface="$(ifconfig | awk '/wlan/ {print $1}')"
# if [ "$wiface" == '' ]
# then
# 	echo "error : no wlan iface. aborting."
# 	exit 1
# fi

# create cbt.csv file
output_file="$output_dir"/"cbt.$(date +"%s").csv"
touch $output_file
# add header
# echo "timestamp,freq,noise,cat,cbt,crt,ctt" > $output_file
echo "timestamp,freq,cat,cbt" > $output_file

while [ "$stop_loop" = false ]; do

	# gather survey dump from active channel
	survey="$(iw $wiface survey dump | grep "in use" -A 2)"

	# extract cbt survey components
	freq=$(echo "$survey" | awk '/frequency/ {print $2}')
	# noise=$(echo "$survey" | awk '/noise/ {print $2}')
	cat=$(echo "$survey" | awk '/channel active time/ {print $4}')
	cbt=$(echo "$survey" | awk '/channel busy time/ {print $4}')
	# crt=$(echo "$survey" | awk '/channel receive time/ {print $4}')
	# ctt=$(echo "$survey" | awk '/channel transmit time/ {print $4}')

	# send csv line to rsyslog (headed by a timestamp)
	# echo "$(date +"%s"),$freq,$noise,$cat,$cbt,$crt,$ctt" >> $output_file
	echo "$(date +"%s"),$freq,$cat,$cbt" >> $output_file	

	sleep 1

done

exit
