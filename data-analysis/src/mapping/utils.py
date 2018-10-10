import math
import numpy as np

def to_radians(degrees):
    return (degrees * math.pi / 180.0)

def to_degrees(radians):
    return (radians / (math.pi / 180.0))

def gps_to_dist(lat_start, lon_start, lat_end, lon_end, radius = 6371000):

    # use the Haversine formula to calculate the great-circle distance between two points on a sphere. 
    # in other words, this calculates the lenght of the shortest arch in-between 2 points in 
    # a 'great' circle of radius equal to 6371 km (the approximate radius of the Earth).
    # source : http://www.movable-type.co.uk/scripts/latlong.html

    delta_lat = to_radians(lat_end - lat_start)
    delta_lon = to_radians(lon_end - lon_start)

    lat_start = to_radians(lat_start)
    lat_end   = to_radians(lat_end)

    # Haversine formula
    a = (np.sin(delta_lat / 2.0) * np.sin(delta_lat / 2.0)) + (np.sin(delta_lon / 2.0) * np.sin(delta_lon / 2.0)) * np.cos(lat_start) * np.cos(lat_end)
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))

    return radius * c