# WiFi ideas

I was asked by thesis committee to improve my thesis plan by adding research ideas which push forward the current industry state by '5 to 10 years', to the point of being 'crazy'.

## 802.11ad

### 802.11ad and V2X

**Problem:** When considering vehicular mobility - specially at high speeds (50 km/h, 70 km/h, 110 km/h) - client and AP need to frequently re-align and undergo an expensive beam steering process, which affects throughput. In any case, the throughput expected from 60 GHz WiFi links is too good to give up on. 

**What have others done:** Current techniques published so far [[COMSNETS 2017]](http://eprints.networks.imdea.org/1500/1/main.pdf) focus on eliminating beam training by fixing antenna orientation and beam width of both Road Side Unit (RSU) and car. While connectivity only happens when both antennas are aligned with each other, the high data rates experienced during limited contact times make it possible to transmit high amounts of data. The design problem then becomes determining the position of RSU and beam width which jointly maximizes contact times & bitrates. Other techniques are only suitable for human speed mobility [[CoNEXT'17]](http://eprints.networks.imdea.org/1673/1/Zero_Overhead_Device_Tracking_in_60_GHz_Wireless_Networks_2017_EN.pdf).

**Idea:** How about mechanically aligning the RSU and client antennas, using some sort of IR tracking? We would be increasing contact times and probably making beam training 'easier' (?) since the only variable would be the distance between the RSU - car pair.
Studies with COTS equipment [[Secon 2018]](http://eprints.networks.imdea.org/1806/1/Fast_Infuriating_Performance_Pitfalls_60_GHz_WLANs_Based_Consumer-Grade_Hardware_2018_EN.pdf) show that variable distance is much more forgiving than variable angles, with decent throughputs (> 1 Gbps) starting at 41 meters (in indoor environments though).

According to [[Secon 2018]](http://eprints.networks.imdea.org/1806/1/Fast_Infuriating_Performance_Pitfalls_60_GHz_WLANs_Based_Consumer-Grade_Hardware_2018_EN.pdf), there are still issues related with the interaction of beam training and rate control: e.g., even if Tx and Rx are aligned, drops in RSS due to distance variability trigger unnecessary beam training when all one needs is rate control.

I believe there could be benefits in doing this, since margin for sub-optimal results is pretty high, and lots of interesting trade-offs and challenges to explore. Even if the mechanical alignment isn't 100% perfect at all times, there's so much bandwidth to take advantage of that we'll still see a benefit.

### 802.11ad beam training overhead: the true story

**Paper:** This CoNEXT'17 paper [[1]](https://www.seemoo.tu-darmstadt.de/dl/seemoo/user_upload/mm-path-tracking_authorversion.pdf) provides some numbers on the overhead of 'beam training'.

Say you have an 802.11ad transmitter (Tx) and a receiver (Rx), typically an AP and a client. 
Beam training is essentially a re-adjustment of the beam pattern on the Tx - a.k.a. antenna sector -, triggered whenever channel conditions deteriorate. 
In [[1]](https://www.seemoo.tu-darmstadt.de/dl/seemoo/user_upload/mm-path-tracking_authorversion.pdf), the authors observe that even for static scenarios, beam training happens approx. once a second.
The authors also observe that probing a single antenna sector takes ~70 us.

In COTS hardware like the TP-Link TALON AD7200, bean training is done using a **Sector Sweep (SS) algorithm**, with a time complexity which is linear on the number of sectors of the antenna array, O(N).
In the TALON, N = 34, leading to a max. of 2.3 ms.
Several optimizations try to reduce this complexity by either reducing N, or fundamentally reduce the complexity of the algorithm to log(N), reducing training time to 0.55 ms in the TALON.

With only a pair of 802.11ad nodes, a reduction of 2.3 ms to 0.5 ms - once per second - doesn't yield that much gain in throughput.
The authors say that: 

* In denser 802.11ad deployments (1 AP, >>1 clients), the throughput gains can be higher.
* Beam training frequencies of 1 Hz occur in a static scenario. Mobile scenarios will require higher beam training frequencies (don't know how much), thus benefiting from lower overhead.
* N will increase in the future.

Using the values for the TALON (N = 34, t_sector = 70 us), I've plotted the overhead for different beam training algorithms and frequencies (or, alternatively, client devices) (% of 1 sec periods), and overhead indeed becomes prohibitive for values over ~30.

![Alt text](/Users/adamiaonr/Downloads/beam-training-overhead.png)

**Idea:** The first insight these results give me is that we should take advantage of 802.11ad as high capacity links, which should remain more-or-less stable over time. 
It doesn't really make sense to re-engineer 802.11ad to serve a large number of 802.11ad clients and/or to cope with a highly mobile environment.
The distribution of 802.11ad's bandwidth can then be done using alternative 802.11 technologies such as 802.11ac.

I would be interesting to know how we can use 802.11ad and 802.11ac in mobility scenarios.
E.g., imagine a set of 802.11ad RSUs alternatively connecting to 802.11ad clients on top of a few busses (busses are good vantage points because of their height), from which we then radiate several 802.11ac links, possibly using MU-MIMO techniques (see more details below).
How well would a setup like this work with the technology 'as is'?
Does something break?
If something does break, what else do we need to do to make it work?

## 802.11ac

**IMPORTANT NOTE:** We're in 2019, and 802.11ac is hardly ahead of the industry. It was introduced in 2013, and looks rather dated when compared to 802.11ax, to be introduced in 2019.

In any case, we can spin these ideas with 802.11ax instead, so read on.

### 802.11ac's MIMO

##### 1 : 802.11ac MIMO and/or 802.11ad

802.11ac extends MIMO techniques used in 802.11n with more spatial streams, downlink Multi-User MIMO (MU-MIMO), standardized beamforming sounding, among others. 

**Idea:** I wonder what the differences in practicality between 802.11ac's MIMO flavors and 802.11ad are, when used for V2X communications. 

Furthermore, since 802.11ac and 802.11ad work in different frequency bands, we could potentially use both at the same time, using MPTCP to manage TCP connections on dual-band devices. I wonder if there are special challenges to MPTCP when these two are used in conjunction.

**NOTE:** The TP-Link TALON AD7200 devices we have here support 802.11ac's MU-MIMO and 802.11ad.

##### 2 : Fast Session Transfer (FST) between 802.11ac and 802.11ad

802.11ad adds a feature called Fast Session Transfer (FST), which allows a pair of of dual-band (e.g., 802.11ad and 802.11ac) to 'seamlessly' switch between ad and ac (and vice-versa).

**Idea:** By reading the literature, it wasn't clear to me how 'seamless' FST is. [This white paper](https://www.arubanetworks.com/assets/wp/WP_80211acInDepth.pdf) by Aruba Networks mentions that true seamlessness is only possible when *"the* [802.11ad and 802.11ac]
*interfaces have the same MAC address and common MAC
management layers for the two links"*. If that's not the case, switches won't be seamless and longer (no numbers given).

Furthermore, note that we're talking about handovers between different WiFi technologies **within the same router**. It would be interesting to see how this works and see if we can extend this between different routers.

I wonder if if we could take advantage of virtualization techniques used in the past in the 2.4 GHz space - e.g., [[Odin, ATC'14]](https://www.usenix.org/conference/atc14/technical-sessions/presentation/schulz-zandery), which uses `openvswitch`, which is available in OpenWRT used by the Talon routers - to make 'seamless' FST possible, even if not available by default. 

##### 3 : AP selection (& client selection?) w/ different 802.11ac MIMO flavors

Let's assume all APs visible from roads have (at least) 802.11ac capabilities, with multiple antennas. There are essentially two 'high-level' MIMO flavors that can be used:

* (1) multiple spatial streams if multiple antennas exist at the car;
* or (2) downlink MU-MIMO 'beamforming' so that an AP serves multiple clients at the same time. 

Option 1 seems more valuable when a vehicle is static so that we increase throughput; option 2 when vehicles are moving, since higher speeds reduce time windows for communication, making it valuable to have an AP transmit to different clients at the same time. 

Both options are highly dependent on multipath characteristics at any particular time, requiring non-negligible overhead of sounding frames exchanged between clients and AP, CSI acquisition and V matrix calculation.

**Idea:** I wonder how does an AP decide which MIMO techniques to use in different situations. How much could we gain from an AP selection system which can go beyond telling the cars which AP to choose? I.e., a system which could tell APs which MIMO flavor to choose for a particular scenario. How much would we gain vs. not using MIMO at all (e.g., relying on typical CSMA/CA instead of MU-MIMO)?

There are several restrictions with the application of MIMO in 802.11ac, which make this more challenging (?). E.g., 802.11ac does not allow more than 4 clients targeted simultaneously, no client can use more than 4 spatial streams, and all streams must use the same bitrate. 

**NOTE:** This problem can be extended with 802.11ax MIMO flavors, including **uplink** MU-MIMO.

### Limitations in Dynamic BW Optimization

**Problem:** 802.11ac introduces wider channel widths - 80 MHz and 160 MHz - thus increasing data rates. To enable co-existence with legacy 802.11a/b/g/n networks working in any of the 20 MHz sub-channels, 802.11ac uses a smart way of re-sizing the channel width, by enabling or disabling sub-channels accordingly.

However, the sub-channel combinations used when adapting channel width are limited. 
E.g., let's say some 802.11ac AP is using an 80 MHz channel width, using 20 MHz sub-channels between 36 to 48.
36 is designated as a primary 20 MHz sub-channel, 40 as the secondary 20 MHz sub-channel.
The sub-channel allocations allowed by 802.11ac are the following 3:

| 36 | 40 | 44 | 48 |
| --- | --- | --- | --- |
| P |   |   |   |
| P | S |   |   |
| P | S | X | X |

This leaves out 5 other combination (considering adjacent channels only).

| 36 | 40 | 44 | 48 |
| --- | --- | --- | --- |
|   | S | X |   |
|   |   | X | X |
|   | S |   |   |
|   |   | X |   |
|   |   |   | X |

**Idea:** How much are we loosing by not using the other 5 combinations? Can we make use of other channels with standardized techniques such as Channel Switch Announcement (CSA) frames to add flexibility and make use of these combinations?

CSA frames are used by an AP to inform its associated clients when it is about to switch channels after radar has been detected in the current channel.


## 802.11ax (2019)

### Target Wake-up Times (TWT) & one-shot packet authentication

Besides improving on the MIMO techniques introduced by 802.11ac, the new 802.11ax standard introduces the idea of **Target Wake-Up Times (TWT)**. The purpose of TWT is to allow battery-constrained devices to allocate specific time-slots during which to communicate with an AP, allowing them to sleep for the rest of the time.

The [early work I've seen so far](https://arxiv.org/pdf/1804.07717.pdf) focuses on simple and simulated scenarios, where APs and clients are static, not taking authentication times into account.

**Idea:** We can think of a more complicated scenario in which constrained devices are 'stuck' to moving nodes, and the deadlines for TWT may not be strictly followed. This can also benefit from a 'one-shot' and/or a 'surrogate' authentication scheme, as in my proposal.

I know what you're thinking... It's a bit hard to find a good reason to explore this idea. 

However, I've noticed that 802.11ax introduces several new methods for multiple access that go beyond the typical CSMA/CA, e.g., [Orthogonal Frequency Division Multiple Access (OFDMA) or uplink MU-MIMO](https://arxiv.org/pdf/1702.05397.pdf), in which uplink and downlink transmissions are scheduled by an AP, in a similar fashion to cellular networks (is this '5G'?!?). TWT is similar in that regard. I'm not trying to suggest CSMA/CA will be abandoned, but in a scenario in which only scheduled multiple access is used, this idea could become relevant.



 