#!/bin/sh

if [ $# -lt 2 ]
then
    echo "usage : $0 <trace-nr> <output-dir>"
    exit 1
fi

trace_nr=$1
output_dir=$2

echo $$ > /var/run/get-sweep-dump.pid

stop_loop=false
trap signal_handler INT

# set stop_loop to true after catching CTRL-C signal
signal_handler() {
    echo "** received CTRL-C : quitting sweep dump script"
    stop_loop=true
}

# create output file
output_file="$output_dir"/"sweep.$(date +"%s").dump"
touch $output_file

while [ "$stop_loop" = false ]; do

	echo "<record date=$(date +"%s%N")>" >> $output_file
	cat /sys/kernel/debug/ieee80211/phy2/wil6210/sweep_dump >> $output_file
	echo "</record>" >> $output_file
	sleep 3

done

exit
