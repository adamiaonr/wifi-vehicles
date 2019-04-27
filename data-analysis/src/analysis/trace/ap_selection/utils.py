# analyze-trace.py : code to analyze custom wifi trace collections
# Copyright (C) 2018  adamiaonr@cmu.edu

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from __future__ import absolute_import

import pandas as pd
import os
import sys

# custom imports
#   - hdfs utils
import utils.hdfs
# #   - analysis
# import analysis.utils.metrics
# import analysis.utils.data
# import analysis.gps
# import analysis.ap_selection.rss
# import analysis.ap_selection.gps
# import analysis.ap_selection.utils

def extract_performance(
    input_dir, trace_nr,
    db_selection,
    metric = 'throughput',
    force_calc = False):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = utils.hdfs.get_db(trace_dir, 'database.hdf5')
    # database =     database = pd.HDFStore(os.path.join(trace_dir, "processed/database.hdf5"))
    database_keys = utils.hdfs.get_db_keys(trace_dir)

    perf_db = ('/selection-performance/%s/%s' % (metric, db_selection.replace('/selection/', '')))
    if perf_db in database_keys:
        if force_calc:
            # database.remove(perf_db)
            utils.hdfs.remove_dbs(trace_dir, [perf_db])
        else:
            sys.stderr.write("""[INFO] %s already in database. skipping data extraction.\n""" % (perf_db))
            return

    if db_selection not in database_keys:
        sys.stderr.write("""[ERROR] %s not in database. abort.\n""" % (db_selection))
        return

    # extract selection data
    sel_data = database.select(db_selection).sort_values(by = ['timed-tmstmp']).reset_index(drop = True)
    # sel_data['timed-tmstmp-str'] = sel_data['timed-tmstmp'].astype(str)

    # calculate selection performance data
    sel_perf = pd.DataFrame()
    nodes = ['m1', 'w1', 'w2', 'w3']
    base_db = analysis.trace.extract_best(input_dir, trace_nr, metric)
    perf_data = database.select(base_db)[['timed-tmstmp'] + nodes].sort_values(by = ['timed-tmstmp']).reset_index(drop = True)
    for node in nodes:

        # filter selection data by node
        sd = sel_data[sel_data['best'] == node]
        if sd.empty:
            continue
        # get performance data for node
        perfd = perf_data[['timed-tmstmp', node]]
        perfd[metric] = perfd[node]
        if perfd.empty:
            continue

        # merge perf metric data w/ the selection plan
        sp = pd.merge(sd, perfd[ ['timed-tmstmp', metric] ], on = ['timed-tmstmp'], how = 'left')
        # concat in total selection performance df
        sel_perf = pd.concat([sel_perf, sp], ignore_index = True)

    sel_perf = sel_perf.sort_values(by = ['timed-tmstmp']).reset_index(drop = True)
    sel_perf[metric] = sel_perf[metric].fillna(0.0)
    utils.hdfs.to_hdfs(sel_perf, ('/selection-performance/%s/%s' % (metric, db_selection.replace('/selection/', ''))), database)
