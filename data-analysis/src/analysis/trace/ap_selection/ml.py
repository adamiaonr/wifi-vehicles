# ml.py : ap selection techniques using machine learning
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
import numpy as np
import matplotlib.pyplot as plt
import os
import sys
import seaborn as sns

from sklearn import linear_model
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report

# custom imports
#   - hdfs utils
import utils.hdfs
#   - analysis

def get_beacon_data(input_dir, trace_nr):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = utils.hdfs.get_db(trace_dir, 'database.hdf5')
    database_keys = utils.hdfs.get_db_keys(trace_dir)

    data = pd.DataFrame()
    # merge:
    #   - /<node>/basic/channel-util
    ch_util = database.select('/basic/channel-util')
    #   - /<node>/beacons.csv
    #   - /<node>/basic/bitrates
    nodes = ['m1', 'w1', 'w2', 'w3']
    for node in nodes:

        b = database.select('%s/basic/beacons' % (node))
        t = database.select('%s/basic/bitrates' % (node))
        # FIXME: this results in multiple values per timed-timstmp, since 
        # there are multiple beacons per .5 interval
        bt = pd.merge(b, t[['timed-tmstmp', 'throughput', 'wlan data rate']], on = ['timed-tmstmp'], how = 'left')
        bt['node'] = node
        bt.dropna(subset = ['throughput'], inplace = True)

        data = pd.concat([data, bt])

    # FIXME: rssi as str fix this in the .hdfs files later
    data['wlan rssi'] = data['wlan rssi'].apply(lambda x : x.replace('dBm', '')).astype(float)
    # FIXME: not sure if fillna() is the correct approach
    # data.fillna(0.0, inplace = True)
    data.dropna(axis = 1, how = 'any', inplace = True)
    data.sort_values(by = ['timed-tmstmp'], inplace = True)
    # shuffle rows
    data = data.sample(frac = 1)

    return data

def get_class(value, classes):
    for i, c in enumerate(classes):
        if value < c:
            return i
    return (i + 1)

def classification_beacons(input_dir, trace_nr,
    force_calc = False):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = utils.hdfs.get_db(trace_dir, 'database.hdf5')
    database_keys = utils.hdfs.get_db_keys(trace_dir)

    # get beacon features & labels
    data = get_beacon_data(input_dir, trace_nr)

    # transform labels in classes
    for metric in ['throughput', 'wlan data rate']:
        classes = [data[metric].quantile(.75), data[metric].quantile(.5), data[metric].quantile(.25)]
        print(metric)
        for i, c in enumerate(classes):
            print('%d : if %s > %d Mbps' % (3 - i, metric, int(c / 1000000.0)))
        print('%d : if %s < %d Mbps' % (0, metric, int(classes[-1] / 1000000.0)))

        m = ('%s-class' % (metric.replace(' ', '-')))
        data[m] = data[metric].apply(get_class, classes = classes)

    # filter features:
    #   - out labels & unwanted features
    features = [x for x in list(data.columns) if x not in ['timed-tmstmp', 'wlan ds current channel', 'throughput', 'wlan data rate', 'node', 'trace-nr', 'throughput-class', 'wlan-data-rate-class']]
    # features = ['wlan rssi']
    #   - out features w/ a single distinct value
    features = [x for x in features if len(data[x].unique()) > 1]

    # use p% of data for training
    p = 0.70
    n = int(p * len(data))
    x_train = data[features].head(n).values
    y_train = data[['throughput-class']].head(n).values
    print(x_train)
    print(y_train)

    m = int((1.0 - p) * len(data))
    x_test = data[features].tail(m).values
    y_test = data[['throughput-class']].tail(m).values

    clf_rf = RandomForestClassifier(random_state = 1, n_estimators = 100)
    pred_rf = clf_rf.fit(x_train, y_train).predict(x_test)
    print("accuracy of random forest:", accuracy_score(pred_rf, y_test))
    print(sorted(zip(map(lambda x : round(x, 4), clf_rf.feature_importances_), features), reverse = True))

def regression_beacons(input_dir, trace_nr,
    force_calc = False):

    trace_dir = os.path.join(input_dir, ("trace-%03d" % (int(trace_nr))))
    database = utils.hdfs.get_db(trace_dir, 'database.hdf5')
    database_keys = utils.hdfs.get_db_keys(trace_dir)

    # get beacon features & labels
    data = get_beacon_data(input_dir, trace_nr)
    # filter features:
    #   - out labels & unwanted features
    features = [x for x in list(data.columns) if x not in ['timed-tmstmp', 'wlan ds current channel', 'throughput', 'wlan data rate', 'node', 'trace-nr']]
    #   - out features w/ a single distinct value
    features = [x for x in features if len(data[x].unique()) > 1]

    corr_matrix = data[features + ['wlan data rate', 'throughput']].corr(method = 'pearson')
    # corr_matrix.style.background_gradient(cmap = 'coolwarm', axis = None).set_precision(2)
    sns.heatmap(corr_matrix, xticklabels = corr_matrix.columns, yticklabels = corr_matrix.columns)
    plt.savefig(os.path.join(trace_dir, ("corr-matrix.pdf")), bbox_inches = 'tight', format = 'pdf')

    # use p% of data for training
    p = 0.70
    n = int(p * len(data))
    x_train = data[features].head(n).values
    y_train = data[['wlan data rate']].head(n).values
    print(x_train)
    print(y_train)

    regr = linear_model.LinearRegression()
    regr.fit(x_train, y_train)
    print(regr.coef_)

    m = int((1.0 - p) * len(data))
    x_test = data[features].tail(m).values
    y_test = data[['wlan data rate']].tail(m).values
    print(np.mean((regr.predict(x_test) - y_test)**2))
    print(regr.score(x_test, y_test))



    