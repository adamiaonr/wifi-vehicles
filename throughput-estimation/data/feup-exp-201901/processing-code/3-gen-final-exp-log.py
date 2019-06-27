#!/usr/bin/env python3

"""
  Generates a final experiment log.
  
  Uses the following logs as inputs:
  
  throughput log: give throughput as function of time
  location log:
  laps log: tells us whether a lap was being per
  
  Output line format:
    systime, senderId, receiverId, receiverX, receiverY, receiverAlt, \
        receiverSpeed, channelFreq, channelBw, chanUtil, isInLap, isIperfOn, \
        isDataReceived, rssiMean, dataRateMean, nBytesReceived

  Rui Meireles 2019.06.25
"""

import pandas, math

LOCATION_LOG_FNAME = "../summary/location-log.csv"
THROUGHPUT_LOG_FNAME = "../summary/reception-log.csv"

LAPS_FNAMES = ["../trace-082/laps.csv", "../trace-083/laps.csv"]

CHANUTIL_FNAMES = ["../trace-082/cbt.csv", "../trace-083/cbt.csv"]

IPERF_FNAMES =["../trace-082/iperf3.csv", "../trace-083/iperf3.csv"]

OUT_FNAME = "../summary/final-exp-log.csv"

VALID_AP_IDS = ("ap1","ap2","ap3","ap4")

VALID_CLI_IDS = ("m1","w1","w2","w3")


######################
### HELPER METHODS ###
######################

def getLoc(locDic, systime, xColName, yColName):
  """
    Uses location dictionary to extract location for a given system time,
    using X and Y column names.
    If system time is not present in the dictionary, but inside its boundaries,
    we perform a linear interpolation between the two closest points.
    If system time is outside the dictionary's boundaries, we throw our hands
    up in the air and return None.
  """

  if systime in locDic:
    receiverX = locDic[systime][xColName]
    receiverY = locDic[systime][yColName]
    receiverAlt = locDic[systime]['alt']
    receiverSpeed = locDic[systime]['speed']
  elif systime >= min(locDic) and systime <= max(locDic): # within bounds
    
    prevSystime, nextSystime = math.inf*-1, math.inf
    for t in locDic:
      if t > prevSystime and t < systime:
        prevSystime = t
      if t < nextSystime and t > systime:
        nextSystime = t

    assert prevSystime != None
    assert nextSystime != None
    assert nextSystime - prevSystime > 1 # otherwise systime would exist

    # do the weighted average
    prevRatio = (systime-prevSystime)/(nextSystime-prevSystime)
    nextRatio = 1-prevRatio

    receiverX = locDic[prevSystime][xColName]*prevRatio + \
              locDic[nextSystime][xColName]*nextRatio
    receiverY = locDic[prevSystime][yColName]*prevRatio + \
              locDic[nextSystime][yColName]*nextRatio

    receiverAlt = locDic[prevSystime]['alt']*prevRatio + \
              locDic[nextSystime]['alt']*nextRatio
    receiverSpeed = locDic[prevSystime]['speed']*prevRatio + \
              locDic[nextSystime]['speed']*nextRatio

  else: receiverX, receiverY, receiverAlt, receiverSpeed = \
        None, None, None, None # nothing we can do about this

  return receiverX, receiverY, receiverAlt, receiverSpeed


def getChanUtil(chanUtilDic, systime, senderId):
  """
    Uses busyTimeDic dictionary to extract busy time infor for sender senderId
    at system time systime.
    If system time is not present in the dictionary, but inside its time
    boundaries, we perform a linear interpolation between the two closest
    points. If systime is outside the dictionary's boundaries, we throw our
    hands up in the air and return None.
  """
  
  assert senderId in VALID_AP_IDS

  if systime in chanUtilDic[senderId]:
    chanUtil = chanUtilDic[senderId][systime]
  
  elif systime >= min(chanUtilDic[senderId]) and \
       systime <= max(chanUtilDic[senderId]): # within bounds
    
    prevSystime, nextSystime = math.inf*-1, math.inf
    for t in chanUtilDic[senderId]:
      if t > prevSystime and t < systime:
        prevSystime = t
      if t < nextSystime and t > systime:
        nextSystime = t

    assert prevSystime != None
    assert nextSystime != None
    assert nextSystime - prevSystime > 1 # otherwise systime would exist

    # do the weighted average
    prevRatio = (systime-prevSystime)/(nextSystime-prevSystime)
    nextRatio = 1-prevRatio

    chanUtil = chanUtilDic[senderId][prevSystime]*prevRatio + \
    chanUtilDic[senderId][nextSystime]*nextRatio

  else: chanUtil = None

  return chanUtil


def isTimeInLap(lapTimesSet, systime):
  """
    Checks whether systime is part of a lap in lapTimesSet.
    Returns 1 if it is, 0 otherwise.
  """
  
  isInLap = 0
  for lapTimes in lapTimesSet:
    if systime >= lapTimes[0] and systime <= lapTimes[1]:
      isInLap = 1
      break
  return isInLap


def IsTimeInIperfOn(iperfTimesDicSet, systime, receiverId):
  """
    Checks whether systime is part of an iperf running period in iperfTimesSet.
    Returns 1 if it is, 0 otherwise.
  """
  
  assert receiverId in iperfTimesDicSet
  
  isIperfOn = 0
  for iperfTimes in iperfTimesDicSet[receiverId]:
    if systime >= iperfTimes[0] and systime <= iperfTimes[1]:
      isIperfOn = 1
      break
  return isIperfOn


#################
### MAIN CODE ###
#################
if __name__ == "__main__":

  print("Generating final log...")

  # read location info
  locDic = {} # location as a function of time
  locDframe = pandas.read_csv(LOCATION_LOG_FNAME)
  
  # line format: gpstime, lat, lon, speed, alt, ap1DeltaX, ap1DeltaY, \
  #             ap2DeltaX, ap2DeltaY, ap3DeltaX, ap3DeltaY, ap1DeltaX, ap4DeltaY
  for index, row in locDframe.iterrows():
    gpstime = int(row["gpstime"])
    locDic[gpstime] = { 'lat': row["lat"], \
                        'lon': row["lon"], \
                        'speed': row["speed"], \
                        'alt': row["alt"], \
                        'ap1DeltaX': row["ap1DeltaX"], \
                        'ap1DeltaY': row["ap1DeltaY"], \
                        'ap2DeltaX': row["ap2DeltaX"], \
                        'ap2DeltaY': row["ap2DeltaY"], \
                        'ap3DeltaX': row["ap3DeltaX"], \
                        'ap3DeltaY': row["ap3DeltaY"], \
                        'ap4DeltaX': row["ap4DeltaX"], \
                        'ap4DeltaY': row["ap4DeltaY"]}
  del locDframe # no longer needed

  # read busy time info
  chanUtilDic = {}
  for chanUtilFname in CHANUTIL_FNAMES:
    chanUtilDframe = pandas.read_csv(chanUtilFname)
    # line format: ,timestamp,freq,noise,cat,cbt,crt,ctt,ch-util,id,mac-addr
    for index, row in chanUtilDframe.iterrows():
      id = row["id"]
      assert id in VALID_AP_IDS
      if id not in chanUtilDic: # first time we're seeing this id
        chanUtilDic[id] = {}
      systime = row["timestamp"]
      chanUtil = row["ch-util"]
      assert systime not in chanUtilDic[id]
      chanUtilDic[id][systime] = chanUtil

  # read laps info
  lapTimesSet = set()
  for lapsFname in LAPS_FNAMES:
    lapsDframe = pandas.read_csv(lapsFname)
    # line format: lap,direction,start-xx,end xx,start-time,end-time
    for index, row in lapsDframe.iterrows():
      if row["lap"] >= 0: # negative laps are invalid
        lapTimes = (row["start-time"], row["end-time"])
        lapTimesSet.add(lapTimes)

  # read iperf info
  iperfTimesDicSet = {}
  for iperfFname in IPERF_FNAMES:
    iperfDframe = pandas.read_csv(iperfFname)
    # line format: ,client-id,data-rate,data-volume,dst-addr,dst-port,\
    #              interval-end,interval-start,jitter,pckt-lost,pckt-total,\
    #              protocol,src-addr,src-port
    for index, row in iperfDframe.iterrows():
      receiverId = row["client-id"]
      assert receiverId in VALID_CLI_IDS
      if receiverId not in iperfTimesDicSet: # add if not there already
        iperfTimesDicSet[receiverId] = set()
      iperfStartTime = int(row["interval-start"])
      iperfEndTime = int(row["interval-end"])
      iperfTimes = (iperfStartTime, iperfEndTime)
      iperfTimesDicSet[receiverId].add(iperfTimes)
  
  # go through throughput log and modify it to create final data frame
  # prepare receiverX, receiverY, and isInLap lists to add to data frame
  receiverXList, receiverYList, receiverAltList, receiverSpeedList, \
      chanUtilList, isInLapList, isIperfOnList = [], [], [], [], [], [], []
  finalDframe = pandas.read_csv(THROUGHPUT_LOG_FNAME)
  
  # line format: systime, senderId, receiverId, channelFreq, channelBw, \
  #              isDataReceived, rssiMean, dataRateMean, nBytesReceived
  idxToDropList = []
  for index, row in finalDframe.iterrows():
    systime = row["systime"]

    # figure out client's position relative to the sender
    senderId = row["senderId"]
    assert senderId in VALID_AP_IDS
    xColName = senderId + "DeltaX"
    yColName = senderId + "DeltaY"
    
    receiverX, receiverY, receiverAlt, receiverSpeed = \
        getLoc(locDic, systime, xColName, yColName)
    
    if receiverX == None: # can not find location, skip
      idxToDropList.append(index)
      continue

    # add channel utilization information
    chanUtil = getChanUtil(chanUtilDic, systime, senderId)
    if chanUtil == None:
      idxToDropList.append(index)
      continue

    # now that we know we have a good row, add all relevant information
    receiverXList.append(receiverX)
    receiverYList.append(receiverY)
    receiverAltList.append(receiverAlt)
    receiverSpeedList.append(receiverSpeed)
    chanUtilList.append(chanUtil)

    isInLap = isTimeInLap(lapTimesSet, systime) # are we in a lap or not?
    isInLapList.append(isInLap)

   # is iperf on on the receiver side or not?
    receiverId = row["receiverId"]
    isIperfOn = IsTimeInIperfOn(iperfTimesDicSet, systime, receiverId)
    isIperfOnList.append(isIperfOn)

  # delete all the rows we could find a location for
  finalDframe.drop(index=idxToDropList, inplace=True)
  
  # add new columns to data frame
  finalDframe["receiverX"] = pandas.Series(receiverXList, name="receiverX")
  finalDframe["receiverY"] = pandas.Series(receiverYList, name="receiverY")
  finalDframe["receiverAlt"] = pandas.Series(receiverAltList, \
                               name="receiverAlt")
  finalDframe["receiverSpeed"] = pandas.Series(receiverSpeedList, \
                               name="receiverSpeed")
  finalDframe["chanUtil"] = pandas.Series(chanUtilList, name="chanUtil")
  finalDframe["isInLap"] = pandas.Series(isInLapList, name="isInLap")
  finalDframe["isIperfOn"] = pandas.Series(isIperfOnList, name="isIperfOn")

  # reorder colums
  colTitles = ['senderId', 'receiverId', 'systime', 'receiverX', 'receiverY', \
               'receiverAlt', 'receiverSpeed', 'channelFreq', 'channelBw', \
               'chanUtil', 'isInLap', 'isIperfOn', 'isDataReceived', \
               'rssiMean', 'dataRateMean', 'nBytesReceived']
  finalDframe = finalDframe.reindex(columns=colTitles)
  
  # sort by senderId, receiverId, systime (in that order)
  finalDframe.sort_values(['senderId','receiverId','systime'], inplace=True)

  finalDframe.to_csv(OUT_FNAME, index=False) # write out the results

  print("Done with final log!")
