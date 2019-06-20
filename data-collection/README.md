# Data collection

## Authentication data

## GPS data

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



