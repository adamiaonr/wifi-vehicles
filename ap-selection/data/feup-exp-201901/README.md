# FEUP trace Data

## Organization

This dataset contains data for two WiFi mobility traces - numbered 82 and 83 - collected in the FEUP testbed.

The structure of the dataset is as follows:

* `trace-info.csv` : brief description of each trace
* `trace-<nr>`:
	* `node-info.csv` : information about the APs and clients used in the trace
	* `laps.csv` : information about circuit laps (e.g., lap numbers, direction, start & end times, etc.)
	* `gps-log.*.csv` : GPS data over time
	* `cbt.csv` : channel utilization data over time, for all APs
	* `ntpstat.csv` : NTP synch deltas vs. the NTP server (as reported by the `ntpstat` application)
	* `cpu.csv` : CPU utilization over time, for all clients and (some) APs 
	* `m1/monitor.*.csv` to `w3/monitor.*.csv` : WiFi frame data relative to client `m1` (check `node-info.csv` for details) as collected by `tcpdump` (includes Beacons, WLAN data frames and ACKs).
