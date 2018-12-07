#!/bin/sh

if [ $# -lt 2 ]
then
    echo "usage : $0 <trace-nr> <output-dir>"
    exit 1
fi

trace_nr=$1
output_dir=$2

echo $$ > /var/run/get-cpu.pid

stop_loop=false
trap signal_handler INT

# set stop_loop to true after catching CTRL-C signal
signal_handler() {
    echo "** received CTRL-C : quitting cpu script"
    stop_loop=true
}

# create cpu.csv file
output_file="$output_dir"/"cpu.$(date +"%s").csv"
touch $output_file
# add header
echo "timestamp,user,nice,system,idle,iowait,irq,softirq,nprocs" > $output_file

while [ "$stop_loop" = false ]; do
	# extract cpu %
	# FIXME: pretty sure this can be simplified
	cpu=$(cat /proc/stat | head -1 | sed 's/[[:alpha:]]\+//g' | sed 's/^[[:space:]]\+//g' | sed 's/[[:space:]]\+/,/g')
	nprocs=$(($(cat /proc/stat | grep cpu | wc -l) - 1))
	# send csv line to rsyslog (headed by a timestamp)
	echo "$(date +"%s"),$cpu,$nprocs" >> $output_file
	sleep 2

done

exit
