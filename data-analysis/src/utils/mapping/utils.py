import math
import numpy as np

def to_radians(degrees):
    return (degrees * math.pi / 180.0)

def to_degrees(radians):
    return (radians / (math.pi / 180.0))

def gps_to_dist(lat_start, lon_start, lat_end, lon_end, radius = 6371000.0):

    # use the Haversine formula to calculate the great-circle distance between two points on a sphere. 
    # in other words, this calculates the lenght of the shortest arch in-between 2 points in 
    # a 'great' circle of radius equal to 6371 km (the approximate radius of the Earth).
    # source : http://www.movable-type.co.uk/scripts/latlong.html
    # https://nathanrooy.github.io/posts/2016-09-07/haversine-with-python/

    phi_1 = np.radians(lat_start)
    phi_2 = np.radians(lat_end)

    delta_phi = np.radians(lat_end - lat_start)
    delta_lambda = np.radians(lon_end - lon_start)

    # haversine formula
    a = (np.sin(delta_phi / 2.0)**2.0) + (np.sin(delta_lambda / 2.0)**2.0) * np.cos(phi_1) * np.cos(phi_2)
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))

    return radius * c