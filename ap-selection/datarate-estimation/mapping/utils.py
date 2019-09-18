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

def get_cell_num(cell_size, lat, lon):
    # x-axis : longitude
    lat_cntr = sum(np.array(lat)) / 2.0
    xx_num = int(np.ceil((gps_to_dist(lat_cntr, lon[0], lat_cntr, lon[1]) / cell_size)))
    # y-axis : latitude
    yy_num = int(np.ceil((gps_to_dist(lat[0], 0.0, lat[1], 0.0) / cell_size)))

    return xx_num, yy_num

def add_cells(data, cell_size, bbox):

    lat_s = bbox[1]
    lat_n = bbox[3]
    lon_w = bbox[0]
    lon_e = bbox[2]

    # extract nr. of cells in the designated area
    xx, yy = get_cell_num(cell_size = cell_size, lat = [lat_n, lat_s], lon = [lon_w, lon_e])
    # add cell ids to data, based on [new_lat, new_lon]
    data['cell_x'] = data['lon'].apply(lambda x : int((x - lon_w) / (lon_e - lon_w) * xx)).astype(int)
    data['cell_y'] = data['lat'].apply(lambda y : int((y - lat_s) / (lat_n - lat_s) * yy)).astype(int)
    # drop rows with out-of-bounds cell coords
    data.drop(data[(data['cell_y'] < 0) | (data['cell_x'] < 0) | (data['cell_y'] > (yy - 1)) | (data['cell_x'] > (xx - 1))].index, inplace = True)
    # it will be useful to get a single integer id
    data['cell_id'] = (data['cell_y'].apply(lambda y : (y * xx)) + data['cell_x']).astype(int)