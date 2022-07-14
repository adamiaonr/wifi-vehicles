# WiFi Vehicles

A framework to collect data in vehicular & distributed WiFi environments.

## General operation

Our software can run in 3 types of nodes:

* APs
* Client nodes
* Server nodes

We assume a network infrastructure like the following (just a simple example, there may be more instances of each node type):

![](https://github.com/adamiaonr/wifi-vehicles/blob/802.11ad/docs/img/network-example.png)

Data is collected in groups of sessions, or "**traces**".
Typically, the flow of execution of a trace is as follows :

TODO

In general, scripts must be passed a three digit trace number that uniquely identifies a collection session, e.g.: 
 
 `$ script.sh 123 <other script-specific options>`

All output files are saved in the filesystems of each node, under a sub-directory named according to the format `<base-dir>/trace-<trace-nr>/`. For devices with low disk space (e.g., routers), the control scripts take care of mounting directories from external disks over the network via NFS.

Data is stored in .csv format, except for `.pcap` files produced by `tcpdump`.

## Script description

### Data collection scripts

---

Data collection scripts are used on multiple nodes to collect different types of data. These scripts are called by 'control' scripts (see other sections).

All of these scripts output data in the form of .csv files. The filename will include a timestamp of when the file was created in order to avoid overwrites by mistake, e.g. `cpu.<timestamp>.csv`.

#### Script list

| script | collected data | output (e.g.) |
|:--|:--|:--|
| [get-cpu.sh](https://github.com/adamiaonr/wifi-vehicles/blob/802.11ad/testbed-setup/configs/openwrt/tp-03/root/workbench/get-cpu.sh) | CPU stats | [cpu.1605565386.csv](https://mega.nz/file/nbZSHTwS#vTrL1zyYn0RnG6tFFKSg7ya97L1GNZ35RHQgJ7lNwCI) |
| [get-ntpdate.sh](https://github.com/adamiaonr/wifi-vehicles/blob/802.11ad/testbed-setup/configs/openwrt/tp-03/root/workbench/get-ntpdate.sh) | NTP synch offset to local server | [ntpdate.1622400329.csv](https://mega.nz/file/3GYQETLD#QXBwcP1aGvbrtgM7q5TG7cHJS_SpExDzj-veyfKgDfU) |
| [get-cbt.sh](https://github.com/adamiaonr/wifi-vehicles/blob/802.11ad/data-collection/get-cbt.sh) | Channel busy time data (802.11n/ac only)[^1] | [cbt.wlan-monitor.1566469161.csv](https://mega.nz/file/DHYCxDKK#xJD5Pq7J8oLTbFhIv_6Nm69T0uK7hOep8RJ6bh8Fct8)[^2] |
| [get-sweep-dump.sh](https://github.com/adamiaonr/wifi-vehicles/blob/802.11ad/testbed-setup/configs/openwrt/tp-03/root/workbench/get-sweep-dump.sh) | SNR from received SLS frames (802.11ad only)  | [sweep.1622400329.dump](https://mega.nz/file/TTJmSR5a#Ue1ZBZ6omaBri9nbIz1yZ6xupU3kF8bD4Ab0pWfbpLo) |
|[get-gps.py](https://github.com/adamiaonr/wifi-vehicles/blob/802.11ad/data-collection/get-gps.py)|Gets GPS data from `gpsd`[^3]|[gps.1566469161.csv](https://mega.nz/file/7DgGTYYL#qM7DrPIHO0LfubBSlwhDIxioeHXplO_yPULgp9QYmnA)|

[^1]: From our experience, this only worked with the following wifi drivers: `ath9k`, `ath10k` or ` rt2800usb`

[^2]: Output filenames follow the format `cbt.<iface-name>.<timestamp>.csv`

[^3]: Assumes a GPS device is available in the system providing data to `gpsd` (e.g., using the [start-gps](https://github.com/adamiaonr/wifi-vehicles/blob/802.11ad/testbed-setup/configs/ubuntu/it-eeepc-maroon-001/usr/local/bin/start-gps) script)

#### Usage

In general, data collection scripts must be passed a trace number and the directory on which the output .csv files shall be stored, e.g.:

`$ get-cpu.sh <trace-nr> <output-dir>`

### Client control scripts

---

Client control scripts run on client nodes, and serve 3 main purposes : (1) start data collection scripts on client nodes; (2) start AP control scripts; and (3) start the flow of data between WiFi APs and STAs via the `consumer` and `producer` apps.

These scripts can be found in the following repo folders:

* `testbed-setup/configs/ubuntu/<node>/usr/bin/`
* `testbed-setup/configs/openwrt/<node>/usr/bin/`

The table below summarizes the purpose of each script.

| script | description |
|:--|:--|
| init-client [[1]](https://github.com/adamiaonr/wifi-vehicles/blob/802.11ad/testbed-setup/configs/ubuntu/it-eeepc-maroon-001/usr/local/bin/init-client), [[2]](https://github.com/adamiaonr/wifi-vehicles/blob/802.11ad/testbed-setup/configs/openwrt/tp-04/usr/bin/init-client) | Mounts external dirs via NFS (if applicable) & creates output dirs<br />Sets up tx-rx and monitor interfaces<br />Starts data collection scripts<br />Starts remote AP control scripts |
| restart-client [[1]](https://github.com/adamiaonr/wifi-vehicles/blob/802.11ad/testbed-setup/configs/ubuntu/it-eeepc-maroon-001/usr/local/bin/restart-client) [[2]](https://github.com/adamiaonr/wifi-vehicles/blob/802.11ad/testbed-setup/configs/openwrt/tp-04/usr/bin/restart-client) | Starts `consumer` app locally<br />Starts remote `producer` app + server collection scripts |
| kill-client [[1]](https://github.com/adamiaonr/wifi-vehicles/blob/802.11ad/testbed-setup/configs/ubuntu/it-eeepc-maroon-001/usr/local/bin/kill-client) [[2]](https://github.com/adamiaonr/wifi-vehicles/blob/802.11ad/testbed-setup/configs/openwrt/tp-04/usr/bin/kill-client) | Stops all data collection processes <br />Stops `consumer`<br /> Stops remote `producer` app and data collection scripts<br />Stops remote AP control scripts |

### AP control scripts

---

The AP control scripts were designed for COTS routers running Openwrt. The purpose of these scripts is summarized in the table below.

| script | description |
|:--|:--|
| [run-ap](https://github.com/adamiaonr/wifi-vehicles/blob/master/testbed-setup/configs/openwrt/unifi-ac-lite-001/usr/bin/run-ap) | Starts all data collection processes on the router |
| [kill-ap](https://github.com/adamiaonr/wifi-vehicles/blob/master/testbed-setup/configs/openwrt/unifi-ac-lite-001/usr/bin/kill-ap) | Terminates all data collection processes on the router |

### Server nodes

---

The server node serves two purposes : (1) it runs **a local NTP server** with which all other nodes synchronize time with; and (2) a **simple web server**, which provides a simple webpage showing the status of the collection process in the different nodes.

The table below shows a distribution of the different scripts and configurations per function.

TODO
