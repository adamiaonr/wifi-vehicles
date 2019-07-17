#!/usr/bin/env python3

import numpy
import pandas

# 4 Supervised Classification Learning Algorithms
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier

from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report


IN_FNAME = "../data/feup-exp-201901/summary/final-exp-log-log.csv"





if __name__ == "__main__":
  """
    Does the bulk of the heavy lifting.
  """

  # 1. load dataset
  # line format: senderId,receiverId,systime,receiverX,receiverY,receiverAlt,
  #              receiverSpeed,channelFreq,channelBw,chanUtil,isInLap,isIperfOn,
  #              isDataReceived,rssiMean,dataRateMean,nBytesReceived
  dataset = pandas.read_csv(IN_FNAME)
  
  
  # 2. split dataset into training and test
  X = dataset.drop("result", axis=1) # X contains all the features
  y = dataset["result"] # y contains only the label
  

  # X_train contains features for training, X_test contains features for testing
  # test_size = 0.3 means 30% data for testing
  # random_state = 1, is the seed value used by the random number generator
  X_train, X_test, y_train, y_test = train_test_split(X, y, test_size = 0.3, random_state = 1)

  # 3. train model
  clf_lr = LogisticRegression(solver='lbfgs')

  # fit the dataset into LogisticRegression Classifier
  clf_lr.fit(X_train, y_train)
  # predict on the unseen data
  pred_lr = clf_lr.predict(X_test)

  clf_knn = KNeighborsClassifier()
  pred_knn = clf_knn.fit(X_train, y_train).predict(X_test) # method chainning

  clf_rf = RandomForestClassifier(random_state=1, n_estimators=100)
  pred_rf = clf_rf.fit(X_train, y_train).predict(X_test)

  clf_dt = DecisionTreeClassifier()
  pred_dt = clf_dt.fit(X_train, y_train).predict(X_test)

  # 4. evaluate quality of resulting model
  print("pred_lr:")
  print(pred_lr)
  print("ground_truth:")
  print(y_test)

  # accuracy score of LR, KNN, RF, DT
  # accuracy score is basically ratio of labels that were accurately predicted
  print("Accuracy of Logistic Regression:", accuracy_score(pred_lr, y_test))
  print("Accuracy of KNN:", accuracy_score(pred_knn, y_test))
  print("Accuracy of Random Forest:", accuracy_score(pred_rf, y_test))
  print("Accuracy of Decision Tree:", accuracy_score(pred_dt, y_test))

  # classification report of Logistic Regression
  print(classification_report(pred_lr, y_test))

  # confusion matrix of Logistic Regression
  confusion_matrix(pred_lr, y_test)
