#!/usr/bin/env python3

"""
  Generate time-indexed log of client locations relative to the AP locations.
  Relative location is measured in meters, in a cartesian system with the AP's
  location at the origin. Longitude corresponds to the x coordinate, latitude to
  the y coordinate.
  
  Note that all clients are co-located so the log doesn't need to distinguish
  between different clients.
  
  Output line format:
    gpstime, lat, lon, speed, alt, ap1Dist, ap1DeltaX, ap1DeltaY, ap2Dist, \
        ap2DeltaX, ap2DeltaY, ap3Dist, ap3DeltaX, ap3DeltaY, ap4Dist, \
        ap4DeltaX, ap4DeltaY
        
  Rui Meireles 2019.06.25
"""

import pandas, math, numpy

IN_FNAMES = ["../trace-082/gps-log.1548779007.csv", \
             "../trace-083/gps-log.1548781295.csv"]

OUT_FNAME = "../summary/location-log.csv"


AP_COORDS_LIST = [{'lat': 41.178518, 'lon': -8.595366}, \
                  {'lat': 41.178518, 'lon': -8.595366}, \
                  {'lat': 41.178563, 'lon': -8.596012}, \
                  {'lat': 41.178563, 'lon': -8.596012}]

######################
### HELPER METHODS ###
######################
def compDist(p1, p2):
  """
    Computes shortest distance, in meters, between input coordinate points.
    Assumes input coordinates are in decimal degrees.

    Uses haversine formula for best precision.
  """

  dlat = math.radians(p2['lat']-p1['lat'])
  dlon = math.radians(p2['lon']-p1['lon'])
  lat1Rad = math.radians(p1['lat'])
  lat2Rad = math.radians(p2['lat'])

  a = ((math.sin(dlat/2.0)**2) + (math.sin(dlon/2.0)**2)) * \
       math.cos(lat1Rad) * math.cos(lat2Rad);
  c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a));
  d = 6371000 * c # earth radius * c

  return d


def compDeltaCartesian(p1, p2):
  """
    Computes x and y offsets (in meters) for p2 using p1 as an origin.
  """

  p1x = {'lat': p2["lat"], 'lon': p1["lon"]} # same lat, different lon
  deltaX = compDist(p1x, p2)
  if p2['lon'] < p1['lon']:
    deltaX *= -1

  p1y = {'lat': p1["lat"], 'lon': p2["lon"]} # same lon, different lat
  deltaY = compDist(p1y, p2)
  if p2['lat'] < p1['lat']:
    deltaY *= -1

  return deltaX, deltaY


#################
### MAIN CODE ###
#################
if __name__ == "__main__":

  print("Generating location log...")

  # get them dataframes
  dframeList = []
  for infname in IN_FNAMES:
    # line template: timestamp,time,lon,lat,alt,speed,epx,epy,epv,eps
    dframe = pandas.read_csv(infname)
    
    
    dframe.rename(columns = {'time':'gpstime'}, inplace = True) # rename
    dframe.drop("timestamp", axis=1, inplace=True)
    dframe.drop("epx", axis=1, inplace=True)
    dframe.drop("epy", axis=1, inplace=True)
    dframe.drop("epv", axis=1, inplace=True)
    dframe.drop("eps", axis=1, inplace=True)
    dframeList.append(dframe)

  dframe = pandas.concat(dframeList, ignore_index=True) # concat all frames

  # compute relative distances for each row

  # add new rows
  apIdxRange = range(len(AP_COORDS_LIST))
  for idx in apIdxRange:
    apId = "ap" + str(idx+1)

    distColName = apId + "Dist"
    dframe[distColName] = numpy.nan

    deltaXColName = apId + "DeltaX"
    dframe[deltaXColName] = numpy.nan

    deltaYColName = apId + "DeltaY"
    dframe[deltaYColName] = numpy.nan


  # compute position deltas
  for index, row in dframe.iterrows():
    p2 = {'lat': row["lat"], 'lon': row["lon"]} # point p2
    for idx in apIdxRange:
      apId = "ap" + str(idx+1)

      # compute tx-rx distance
      dist = compDist(AP_COORDS_LIST[idx], p2)
      distColName = apId + "Dist"
      dframe.at[index,distColName] = dist

      # compute tx-rx distance (x,y) deltas
      deltaX, deltaY = compDeltaCartesian(AP_COORDS_LIST[idx], p2)
      deltaXColName = apId + "DeltaX"
      dframe.at[index,deltaXColName] = deltaX
      deltaYColName = apId + "DeltaY"
      dframe.at[index,deltaYColName] = deltaY

  # reorder colums
  colTitles = ['gpstime', 'lat', 'lon', 'speed', 'alt', 'ap1Dist', \
               'ap1DeltaX', 'ap1DeltaY', 'ap2Dist', 'ap2DeltaX', 'ap2DeltaY', \
               'ap3Dist', 'ap3DeltaX', 'ap3DeltaY', 'ap4Dist', 'ap4DeltaX', \
               'ap4DeltaY']
  dframe = dframe.reindex(columns=colTitles)

  # write out the results
  dframe.to_csv(OUT_FNAME, index=False)

  print("Done with location log!")
