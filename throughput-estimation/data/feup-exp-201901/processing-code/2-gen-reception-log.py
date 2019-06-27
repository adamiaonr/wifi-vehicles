#!/usr/bin/env python3

"""
  Generate a time-indexed throughput log for each communicating node pair.

  Communicating pairs:
   ap1 -> w2 (fc:ec:da:1a:63:a6 -> c4:6e:1f:26:35:7e), chan 6, 20 MHz @ 2437
   ap3 -> w3 (78:8a:20:57:1f:6b -> c4:6e:1f:25:d7:26), chan 11, 20 MHz @ 2462
   
   ap2 -> m1 (78:8a:20:58:1f:73 -> 24:05:0f:61:51:14), chan 38, 40 MHz @ 5190
   ap4 -> w1 (78:8a:20:58:25:74 -> 24:05:0f:9e:2c:b1), chan 40, 40 MHz @ 5230

  Output line format:
    systime, senderId, receiverId, channelFreq, channelBw, isDataReceived, \
        rssiMean, dataRateMean, nBytesReceived
        
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
             "../trace-083/w3/monitor.1548781305.csv.zip"]

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
                              'isDataReceived': 0, \
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
  
  chunksize = 10 ** 5
  nlines = 0
  for infname in IN_FNAMES:
    print("Processing file " + infname + "...")
    for dframeChunk in pandas.read_csv(infname, chunksize=chunksize, \
        low_memory=False):
      print("\tlines " + str(nlines+1) + " through " + str(nlines + chunksize) + \
            "...")
      nlines += chunksize
    
      for index, row in dframeChunk.iterrows():
        systime = int(round(row["epoch time"]))
        
        srcMac = row["wlan src addr"]
        dstMac = row["wlan dst addr"]
        
        commPair = (srcMac, dstMac)
        
        if commPair in COMM_PAIRS: # means it's a row of interest
        
          # add info to dictionary if needed
          addTimeEntryIfNeeded(timeDic, systime)
        
          # record data
          
          # add frame length to throughput
          frameLen = int(row["frame len"])
          timeDic[systime][commPair]['nBytesReceived'] += frameLen
          
          # data was received on systime if at least one Qos Data frame present
          if row["wlan type-subtype"] == "QoS Data" and \
            timeDic[systime][commPair]['isDataReceived'] == 0:
            timeDic[systime][commPair]['isDataReceived'] = 1
          
          # record rssi and data rate only if rssi info is present
          rssi = row["wlan rssi"]
          if type(rssi) != float:
            rssi = int(rssi.split("dBm")[0])
            dataRate = float(row["wlan data rate"])
            timeDic[systime][commPair]['rssiList'].append(rssi)
            timeDic[systime][commPair]['dataRateList'].append(dataRate)


  # fill in any missing timestamps with zeros
  minSystime = min(timeDic)
  maxSystime = max(timeDic)
  for systime in range(minSystime, maxSystime):
    addTimeEntryIfNeeded(timeDic, systime)

  # compute mean rssi for each systime, communication pair combo
  for systime, commPairDic in timeDic.items():
    for commPair, commInfo in commPairDic.items():
      rssiMean = getListMean(commInfo['rssiList'], default=-100)
      commInfo['rssiMean'] = rssiMean
      del commInfo['rssiList'] # no longer needed
      dataRateMean = getListMean(commInfo['dataRateList'], default=0)
      commInfo['dataRateMean'] = dataRateMean
      del commInfo['dataRateList'] # no longer needed


  # write out the results
  outfile = open(OUT_FNAME, 'w')
  headerStr = "systime,senderId,receiverId,channelFreq,channelBw,isDataReceived,rssiMean,dataRateMean,nBytesReceived"
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
      isDataReceived = commInfo['isDataReceived']
      rssiMean = commInfo['rssiMean']
      dataRateMean = commInfo['dataRateMean']
      nBytesReceived = commInfo['nBytesReceived']

      outStr = "%d,%s,%s,%d,%d,%d,%f,%f,%d" % \
               (systime, senderId, receiverId, channelFreq, channelBw, \
              isDataReceived, rssiMean, dataRateMean, nBytesReceived)
      print(outStr, file=outfile)

  outfile.close()

  print("Done with throughput log!")
