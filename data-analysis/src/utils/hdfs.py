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

import pandas as pd
import os
import sys

def get_db(input_dir, hdfs_file = 'database.hdf5'):
    db_dir = os.path.join(input_dir, ("processed"))
    if not os.path.isdir(db_dir):
        os.makedirs(db_dir)
        
    database = pd.HDFStore(os.path.join(db_dir, hdfs_file))
    return database

def get_db_keys(input_dir, hdfs_file = 'database.hdf5'):
    database = get_db(input_dir, hdfs_file = hdfs_file)
    return database.select('/keys')['keys'].tolist()

def update_db_keys(database, db_keys = None):

    if db_keys is None:
        db_keys = database.keys()

    # FIXME: we keep a special key w/ the keys of the hdfs db, for quick access
    df_keys = pd.DataFrame(columns = ['keys'])
    df_keys['keys'] = db_keys

    if '/keys' in db_keys:
        database.remove('/keys')
    database.append(
        '/keys',
        df_keys,
        data_columns = df_keys.columns,
        format = 'table')

def to_hdfs(data, metric, database):

    database.append(
        ('%s' % (metric)),
        data,
        data_columns = data.columns,
        format = 'table')

    # update database keys whenever table is added
    update_db_keys(database)

def remove_dbs(input_dir, hdfs_file = 'database.hdf5', dbs = []):

    database = get_db(input_dir, hdfs_file = hdfs_file)
    database_keys = get_db_keys(input_dir, hdfs_file = hdfs_file)

    for db in dbs:
        if db in database_keys:
            database.remove(db)
            sys.stderr.write("""%s: [INFO] removed db %s\n""" % (sys.argv[0], db))
        else:
            sys.stderr.write("""%s: [INFO] db %s not in database\n""" % (sys.argv[0], db))

    # update database keys whenever table is removed
    update_db_keys(database)