# Data collection

## Testing procedure

The test procedure below refers to a passive measurement setup.
This has been tested with Ubuntu 16.04, on a VMWare Fusion 8.5.10 VM. 

### Pre-requesites

* Install the necessary Linux and Python packages

```
sudo apt-get install iw tcpdump ntpstat timeout gpsd
sudo pip install gps
```

Note: I may have forgotten some, just install them according to the error messages you get.

* Symlink the main scripts to `/usr/local/bin`

```
$ sudo ln -sfv /<src-dir-absolute-path>/run-wardrive /usr/local/bin
$ sudo ln -sfv /<src-dir-absolute-path>/kill-wardrive /usr/local/bin
```

This allows you to call the main scripts without specifying a specific path.

* Since you're using a VM, make sure the VM has access to the WiFi device (e.g., in my case, VMWare Fusion allowed me to get access to a USB dongle).

### Procedure

You can start the complete set of passive measurements by invoking the script `run-wardrive`:

```
$ sudo run-wardrive <trace-nr> <wlan-iface>
```

* `<trace-nr>` : Identifier a particular collection, just so that results from different runs don't get mixed. The collection logs are saved in a dir named `trace-<trace-nr>`, which is a subdir of the dir specified in the variable `output_dir` (set inside the `wardrive` script, you'll need to change this).
* `<wlan-iface>` : The name of the wireless interface used to capture frames, e.g., `wlan0`.

To stop the collection, you can simply call:

```
$ sudo kill-wardrive
```

For reference, the `run-wardrive` script calls 4 other scripts, which you can inspect and run independently:

* `scan-loop.py` : a Python script which starts iterative scans, looping through a list of `<channel>:<bandwidth>` tuples. It also starts `tcpdump` captures, saving the results in .pcap files, which you can read with Wireshark. Read the script's comments for more details.
* `get-cbt.sh` : a bash script that reads channel utilization values via the `iw dev <wlan-iface> survey dump` command. It saves the results in a .csv file.
* `get-gps.py` : reads values from a GPS device via the `gpsd` daemon. Saves the GPS information every second on a .csv file.
* `get-cpu.sh` : logs CPU utilization on the device in a .csv file.

Note: the scripts require `sudo` privileges because they must configure wireless interfaces and run `tcpdump`.

## Setting up GPS devices

### Setup 1 : Stand-alone GPS USB dongle

TODO

### Setup 2 : Share GPS of Android phone over Bluetooth

The GPS USB dongles we have in the lab are unreliable (e.g., poor reception, accuracy, driver-level connection often lost, etc.) and the Trimble setup is too complicated. 

I've found a more reliable setup, which uses the GPS receiver of an Android phone, feeds its output to `gpsd` running in a Linux laptop, using a Bluetooth link. The key to all this is [the Share GPS app](https://play.google.com/store/apps/details?id=com.jillybunch.shareGPS&hl=en).

##### Walkthrough

| Device type | Model | OS |
| --- | --- | --- | 
| Phone | Google Nexus 5 | Android 6.0.1 | 
| Laptop | Asus eeePC | Ubuntu 16.04 LTS |

**1:** Install the [Share GPS app](https://play.google.com/store/apps/details?id=com.jillybunch.shareGPS&hl=en) app on the phone

**2:** Open the Share GPS app, go to the '**Connections**' top-right separator, click the '**Add**' button at the bottom.

Choose the following settings:

| Setting | Option |
| --- | --- |
| Setup by Activity | Uncheck |
| Data type | NMEA |
| Connection Method | Use Bluetooth to send NMEA or host a GPSD server |
| Name | leave empty |

Click the '**Next**' button. 
Leave the '**Auto Find**' option checked, then select the laptop's Bluetooth address on the list that pops up.

**3:** Still on the '**Connections**' menu, you should now have a list of connections, one with the name of the laptop. Click on it, changing its status from '**Idle**' to '**Listening**'

**4:** On the Linux machine, run:

~~~~
$ sudo rfcomm connect /dev/rfcomm1 C4:43:8F:9F:9F:61 2
~~~~

* **connect**: tells `rfcomm` to connect to another BT device
* **/dev/rfcomm1:** the device endpoint in Linux, which will be created as the BT connection is established. The device name `/dev/rfcomm1` used here seems more or less arbitrary: as a rule of thumb, you should use something like `/dev/rfcomm<x>`, replacing `<x>` by an integer.
* **C4:43:8F:9F:9F:61:** BT address of the phone.
* **channel:** Share GPS seems to listen on channel 2 by default.

In Share GPS, the status of the connection should go from 'Listening' to 'Connected'.

**5:** Run the `start-gps` script, using `/dev/rfcomm1` as the device file argument:

~~~~
$ sudo start-gps /dev/rfcomm1
~~~~

After a few seconds - and provided that the Google Nexus 5 can actually get GPS signal - you should be able to see GPS data on your Linux machine via `cgps` and collect it using the `get-gps.py` script.



