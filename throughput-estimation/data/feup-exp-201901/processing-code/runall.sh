#!/bin/bash

# This bash script takes in (somewhat) raw experimental data and creates
# a complete summary at ../summary/final-exp-log.csv
#
# Some other auxiliary files may be created as well. Feel free to delete or
# ignore.
#
# Rui Meireles 2019.06.25

python3 1-gen-location-log.py
python3 2-gen-reception-log.py
python3 3-gen-final-exp-log.py
