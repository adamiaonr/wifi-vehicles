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
# add .csv file header
echo "timestamp,cpu,user,nice,system,idle,iowait,irq,softirq" > $output_file
# extract cpu stats per core every 2 sec
while [ "$stop_loop" = false ]; do
	# extract cpu %s
	cpu=$(cat /proc/stat | grep cpu | sed 's/^[[:space:]]\+//g' | sed 's/[[:space:]]\+/,/g' | sed "s/^/$(date +'%s'),/g")
	# send csv line to rsyslog (headed by a timestamp)
	echo "$cpu" >> $output_file

	sleep 2

done

exit
