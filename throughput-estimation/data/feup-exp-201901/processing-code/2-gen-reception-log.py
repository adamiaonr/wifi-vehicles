#!/usr/bin/env python3

"""
  Generate a time-indexed throughput log for each communicating node pair.

  Communicating pairs:
   ap1 -> w2 (fc:ec:da:1a:63:a6 -> c4:6e:1f:26:35:7e), chan 6, 20 MHz @ 2437
   ap3 -> w3 (78:8a:20:57:1f:6b -> c4:6e:1f:25:d7:26), chan 11, 20 MHz @ 2462
   
   ap2 -> m1 (78:8a:20:58:1f:73 -> 24:05:0f:61:51:14), chan 38, 40 MHz @ 5190
   ap4 -> w1 (78:8a:20:58:25:74 -> 24:05:0f:9e:2c:b1), chan 40, 40 MHz @ 5230

  Output line format:
    systime, senderId, receiverId, channelFreq, channelBw, rssiMean, \
    dataRateMean, nBytesReceived
        
  Rui Meireles 2019.06.25
"""

import pandas, math

IN_FNAMES = ["../trace-082/m1/monitor.1548778990.csv.zip", \
             "../trace-082/w1/monitor.1548779006.csv.zip", \
             "../trace-082/w2/monitor.1548778997.csv.zip", \
             "../trace-082/w3/monitor.1548779019.csv.zip", \
             "../trace-083/m1/monitor.1548781266.csv.zip", \
             "../trace-083/w1/monitor.1548781295.csv.zip", \
             "../trace-083/w2/monitor.1548781277.csv.zip", \
             "../trace-083/w3/monitor.1548781305.csv.zip"
             ]

OUT_FNAME = "../summary/reception-log.csv"

COMM_PAIRS = {("fc:ec:da:1a:63:a6", "c4:6e:1f:26:35:7e"): \
                                                         {'senderId': "ap1", \
                                                          'receiverId': "w2", \
                                                          'channelFreq': 2437, \
                                                          'channelBw': 20}, \
              ("78:8a:20:57:1f:6b", "c4:6e:1f:25:d7:26"): \
                                                         {'senderId': "ap3", \
                                                          'receiverId': "w3", \
                                                          'channelFreq': 2462, \
                                                          'channelBw': 20}, \
              ("78:8a:20:58:1f:73", "24:05:0f:61:51:14"): \
                                                         {'senderId': "ap2", \
                                                          'receiverId': "m1", \
                                                          'channelFreq': 5190, \
                                                          'channelBw': 40}, \
              ("78:8a:20:58:25:74", "24:05:0f:9e:2c:b1"): \
                                                         {'senderId': "ap4", \
                                                          'receiverId': "w1", \
                                                          'channelFreq': 5230, \
                                                          'channelBw': 40}, \
             }


######################
### HELPER METHODS ###
######################
def addTimeEntryIfNeeded(timeDic, systime):
  """
    Adds entry for systime in timeDic, if one does not yet exist.
  """
  if systime not in timeDic:
    timeDic[systime] = {}
    for cp in COMM_PAIRS:
      timeDic[systime][cp] = {'nBytesReceived': 0, \
                              'rssiList': [], \
                              'dataRateList': []}


def getListMean(list, default=math.nan):
  """
    Returns the mean of the values in the list, or default if list is empty.
  """
  llen = len(list)
  return sum(list)/llen if llen > 0 else default


#################
### MAIN CODE ###
#################
if __name__ == "__main__":

  print("Generating throughput log...")

  timeDic = {} # will save time-indexed throughput stats
  
  # stats counters
  nUdpFrames, nQosFrames, nUdpNotQosFrames, nQosNotUdpFrames, \
      nUdpNoRssiFrames = [0] * 5
  
  chunksize = 10 ** 5
  nlines = 0
  for infname in IN_FNAMES:
    print("Processing file " + infname + "...")
    for dframeChunk in pandas.read_csv(infname, chunksize=chunksize, \
        low_memory=False):
      print("\tlines " + str(nlines+1) + " through " + str(nlines + chunksize) + \
            "...")
      nlines += chunksize
    
      # line format: "no","epoch time","frame len","ip hdr length","ip proto", \
      #              "ip src","ip dst","ip id","ip frag offset", \
      #              "ip more frags", "ip reassembled in","udp src port", \
      #              "udp dst port","wlan tsf time","wlan phy", \
      #              "wlan hdr length","wlan src addr","wlan dst addr", \
      #              "wlan type-subtype","wlan rssi","wlan noise", \
      #              "wlan data rate","wlan mcs index","wlan duration", \
      #              "wlan preamble","wlan seq number","wlan frag number", \
      #              "wlan block ack bitmap","wlan block ack starting seq nr", \
      #              "wlan retry","wlan qbss client qty", \
      #              "wlan qbss channel util", \
      #              "wlan mimo vht mu exclusive bf report"
      for index, row in dframeChunk.iterrows():
        systime = int(round(row["epoch time"]))
        
        srcMac = row["wlan src addr"]
        dstMac = row["wlan dst addr"]
        
        commPair = (srcMac, dstMac)
        
        if commPair in COMM_PAIRS: # means it's a row of interest
        
          # add info to dictionary if needed
          addTimeEntryIfNeeded(timeDic, systime)
      
      
          # update frame type-related stats
          if row["ip proto"] == "UDP":
            nUdpFrames += 1
            if row["wlan type-subtype"] != "QoS Data":
              nUdpNotQosFrames += 1
        
          if row["wlan type-subtype"] == "QoS Data":
            nQosFrames += 1
            if row["ip proto"] != "UDP":
              nQosNotUdpFrames += 1
        
          # done with stats update
        
          # is this a frame we care about?
          if row["ip proto"] != "UDP":
            continue
        
          # record data
          # add frame length to throughput
          frameLen = int(row["frame len"])
          timeDic[systime][commPair]['nBytesReceived'] += frameLen

          # record rssi only it is present
          rssi = row["wlan rssi"]
          if type(rssi) != float:
            rssi = int(rssi.split("dBm")[0])
            timeDic[systime][commPair]['rssiList'].append(rssi)
          else: # update missing rssi stats
            if not math.isnan(rssi): print (rssi)
            nUdpNoRssiFrames += 1
          
          # record data rate info (I assume it's always present)
          dataRate = float(row["wlan data rate"])
          timeDic[systime][commPair]['dataRateList'].append(dataRate)


  # fill in any missing timestamps with zeros
  minSystime = min(timeDic)
  maxSystime = max(timeDic)
  for systime in range(minSystime, maxSystime):
    addTimeEntryIfNeeded(timeDic, systime)

  # compute mean rssi for each systime, communication pair combo
  maxdr, maxstime, maxpair = -99999, 0, None # delete
  for systime, commPairDic in timeDic.items():
    for commPair, commInfo in commPairDic.items():
      rssiMean = getListMean(commInfo['rssiList'], default=-100)
      commInfo['rssiMean'] = rssiMean
      del commInfo['rssiList'] # no longer needed
      dataRateMean = getListMean(commInfo['dataRateList'], default=0)
      commInfo['dataRateMean'] = dataRateMean
      del commInfo['dataRateList'] # no longer needed

      if dataRateMean > maxdr:
        maxdr = dataRateMean
        maxstime = systime
        maxpair = commPair

  # write out the results
  outfile = open(OUT_FNAME, 'w')
  headerStr = "systime,senderId,receiverId,channelFreq,channelBw,rssiMean,dataRateMean,nBytesReceived"
  print(headerStr, file=outfile)

  # print out all the rows, in systime order
  commPairs = sorted(COMM_PAIRS.keys())

  for systime in sorted(timeDic.keys()):
    commPairDic = timeDic[systime]
    for commPair in commPairs:
    
      senderId = COMM_PAIRS[commPair]['senderId']
      receiverId = COMM_PAIRS[commPair]['receiverId']
      channelFreq = COMM_PAIRS[commPair]['channelFreq']
      channelBw = COMM_PAIRS[commPair]['channelBw']

      assert commPair in commPairDic
      commInfo = commPairDic[commPair]
      rssiMean = commInfo['rssiMean']
      dataRateMean = commInfo['dataRateMean']
      nBytesReceived = commInfo['nBytesReceived']

      outStr = "%d,%s,%s,%d,%d,%f,%f,%d" % \
               (systime, senderId, receiverId, channelFreq, channelBw, \
              rssiMean, dataRateMean, nBytesReceived)
      print(outStr, file=outfile)

  outfile.close()

  pUdpNotQos = float(nUdpNotQosFrames) / nUdpFrames * 100;
  pQosNotUdp = float(nQosNotUdpFrames) / nQosFrames * 100;
  pUdpNoRssi = float(nUdpNoRssiFrames) / nUdpFrames * 100;

  byeStr = "Done with reception log! Stats: %.2f%% of frames are UDP but not QoS Data, %.2f%% QoS Data but not UDP, %.2f%% of UDP frames are missing RSSI info." % \
      (pUdpNotQos, pQosNotUdp, pUdpNoRssi)
  print(byeStr)
