Understanding final-exp-log.csv.

This is a time-indexed summary of the WiFi experiments performed at FEUP during January 2019.

In these experiments there were 4 stationary APs sending data through UDP to 4 mobile clients.
All APs used 802.11n, but each used its own independent channel.

Clients performed "laps" back and forth around the APs.

AP info:

* ap1, located at (41.178518,-8.595366), running on channel 6 (20 MHz centered at 2437 MHz)
* ap2, located at (41.178518,-8.595366), running on channel 38 (40 MHz centered at 5190 MHz)
* ap3, located at (41.178563,-8.596012), running on channel 11 (20 MHz centered at 2462 MHz)
* ap4, located at (41.178563,-8.596012), running on channel 46 (40 MHz centered at 5230 MHz)



Column explanation:

* senderId: id of the node sending data (one of {ap1, ap2, ap3, ap4}).

* receiverId: id of the client node receiving data (one of {m1, w1, w2, w3}).

* systime: system time (1 Hz resolution) that this row refers to. All node clocks were synchronized through NTP.

* receiverDist: straight-line distance between sender and receiver, in meters, for the 1-second period systime period the row refers to. If we don't have data for a particular systime, linear interpolation between the two closest data points is used.

* receiverX: x coordinate of the receiver's position when space is discretized as a Cartesian plane and the sender is set to be the origin of the coordinate system. The x axis corresponds to east-west (positive values are east, negative values are west). Unit is meters. If we don't have data for a particular systime, linear interpolation between the two closest data points is used.

* receiverY: y coordinate of the receiver's position when space is discretized as a Cartesian plane and the sender is set to be the origin of the coordinate system. The y axis corresponds to north-south (positive values are north, negative values are south). Unit is meters. If we don't have data for a particular systime, linear interpolation between the two closest data points is used.

* receiverAlt: receiver's altitude, in meters.

* receiverSpeed: receiver's speed, in m/s.

* channelFreq: center frequency of the WiFi channel used, in MHz.

* channelBw: bandwidth of the WiFi channel used, in MHz.

* channelUtil: percentage of time the wireless medium was sensed to be busy during the 1-second period systime period the row refers to. If we don't have data for a particular systime, linear interpolation between the two closest data points is used.

* isInLap: 1 if this row's systime has been marked as being part of a time period where clients were doing laps around the APs, 0 otherwise.

* isIperfOn: 1 if row's systime corresponds to a period where iperf is known to have been running on the receiver side.

* rssiMean: the mean of the RSSI (Received Signal Strength Indicator) values of frames received by the client from the sender during the 1-second period systime period the row refers to. If no frames with RSSI information were received, this field is set to -100. Unit is dBm. 

* dataRateMean: the mean of the RSSI (Received Signal Strength Indicator) values of frames received by the client from the sender during the 1-second period systime period the row refers to. If no frames with RSSI information were received, this field is set to 0. Unit is Mbit/s. 

* nBytesReceived: total number of bytes received by the client from the sender during the 1-second period systime period the row refers to.
