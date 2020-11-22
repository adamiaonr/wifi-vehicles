#!/bin/sh

if [ $# -lt 2 ]
then
    echo "usage : $0 <trace-nr> <output-dir>"
    exit 1
fi

#NTP_SERVER=10.10.10.113
NTP_SERVER=192.168.1.104
trace_nr=$1
output_dir=$2

echo $$ > /var/run/get-ntpdate.pid

stop_loop=false
trap signal_handler INT

# set stop_loop to true after catching CTRL-C signal
signal_handler() {
    echo "** received CTRL-C : quitting ntpdate script"
    stop_loop=true
}

# create ntpdate.csv file
output_file="$output_dir"/"ntpdate.$(date +"%s").csv"
touch $output_file
# add .csv file header
echo "timestamp,server,offset" > $output_file
# extract ntp stats per core every n sec
while [ "$stop_loop" = false ]; do
	# extract ntpdate output
	ntp="$(/usr/sbin/ntpdate $NTP_SERVER)"
	# fill the columns
	server=$(echo "$ntp" | awk '/adjust/ {print $8}')
	offset=$(echo "$ntp" | awk '/adjust/ {print $10}')
	# output to .csv
	echo "$(date +"%s"),$server,$offset" >> $output_file	

	sleep 30
done

exit
