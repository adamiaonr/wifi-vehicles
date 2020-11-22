#!/bin/sh

if [ $# -lt 2 ]
then
    echo "usage : $0 <trace-nr> <output-dir>"
    exit 1
fi

trace_nr=$1
output_dir=$2

echo $$ > /var/run/get-ntp.pid

stop_loop=false
trap signal_handler INT

# set stop_loop to true after catching CTRL-C signal
signal_handler() {
    echo "** received CTRL-C : quitting cpu script"
    stop_loop=true
}

# create ntp.csv file
output_file="$output_dir"/"ntp.$(date +"%s").csv"
touch $output_file
# add .ntp file header
echo "timestamp,server,stratum,delta,poll-freq" > $output_file
# extract ntp stats per core every 2 sec
while [ "$stop_loop" = false ]; do
	# extract ntpstat output
	ntp="$(/usr/bin/ntpstat)"

	# fill the columns
	server=$(echo "$ntp" | awk '/synchronised/ {print $5}')
	stratum=$(echo "$ntp" | awk '/synchronised/ {print $8}')
	delta=$(echo "$ntp" | awk '/time correct/ {print $5}')
	poll=$(echo "$ntp" | awk '/polling server/ {print $4}')

	# output to .csv
	echo "$(date +"%s"),$server,$stratum,$delta,$poll" >> $output_file	

	sleep 5
done

exit
