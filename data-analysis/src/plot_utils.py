import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import os
import argparse
import sys
import glob
import math

import xml.etree.cElementTree as et

from datetime import date
from datetime import datetime
from collections import defaultdict
from collections import OrderedDict
from itertools import chain, izip

ileave = lambda *iters: list(chain(*izip(*iters)))

def custom_ceil(num_to_round, step = 0.25):
    return (step * math.ceil(num_to_round / step))

# full method with doctests
def interleave_n(*iters):
    """
    Given two or more iterables, return a list containing 
    the elements of the input list interleaved.
    
    >>> x = [1, 2, 3, 4]
    >>> y = ('a', 'b', 'c', 'd')
    >>> interleave(x, x)
    [1, 1, 2, 2, 3, 3, 4, 4]
    >>> interleave(x, y, x)
    [1, 'a', 1, 2, 'b', 2, 3, 'c', 3, 4, 'd', 4]
    
    On a list of lists:
    >>> interleave(*[x, x])
    [1, 1, 2, 2, 3, 3, 4, 4]
    
    Note that inputs of different lengths will cause the 
    result to be truncated at the length of the shortest iterable.
    >>> z = [9, 8, 7]
    >>> interleave(x, z)
    [1, 9, 2, 8, 3, 7]
    
    On single iterable, or nothing:
    >>> interleave(x)
    [1, 2, 3, 4]
    >>> interleave()
    []
    """
    return list(chain(*izip(*iters)))

def interleave(a, b):
    c = list(zip(a, b))
    return [elt for sublist in c for elt in sublist]

def extract_data(file_name):

    """ given a dir w/ .csv files, extracts data from .csv file into 
    a pandas data frame"""

    return pd.read_csv(file_name, sep = ",")

def merge_two_dicts(x, y):
    """Given two dicts, merge them into a new dict as a shallow copy."""
    z = x.copy()
    z.update(y)
    return z
