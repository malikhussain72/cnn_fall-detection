from __future__ import print_function
from numpy.random import seed
seed(1)
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import os
from PIL import Image
import io
from sklearn.model_selection import StratifiedShuffleSplit
from vgg16module import VGG16

from keras.models import Model, model_from_json, model_from_yaml, Sequential
from keras.layers import Input, Convolution2D, MaxPooling2D, LSTM, Reshape, Merge, TimeDistributed, Flatten, Activation, Dense, Dropout, merge, AveragePooling2D, ZeroPadding2D, Lambda
from keras.optimizers import Adam, SGD
from keras.layers.normalization import BatchNormalization 
from keras import backend as K
K.set_image_dim_ordering('th')
from keras.utils import np_utils
from sklearn.metrics import confusion_matrix, accuracy_score
from skimage.io import imsave
from keras.callbacks import Callback, ModelCheckpoint, EarlyStopping, ReduceLROnPlateau, LearningRateScheduler
from keras.utils.np_utils import to_categorical
import json
from scipy.ndimage import minimum, maximum, imread
import math
import numpy.ma as ma
import matplotlib.cm as cm
import h5py
import random
from collections import OrderedDict
import scipy.io as sio
import cv2
import glob
import gc
from scipy.stats import mode
from collections import Counter
from sklearn import svm
from sklearn.metrics import roc_curve, auc
from sklearn.model_selection import KFold
from keras.layers.advanced_activations import ELU
     
def plot_training_info(case, metrics, save, history):
    # summarize history for accuracy
    plt.ioff()
    if 'accuracy' in metrics:     
        fig = plt.figure()
        plt.plot(history['acc'])
        plt.plot(history['val_acc'])
        plt.title('model accuracy')
        plt.ylabel('accuracy')
        plt.xlabel('epoch')
        plt.legend(['train', 'val'], loc='upper left')
        if save == True:
            plt.savefig(case + 'accuracy.png')
            plt.gcf().clear()
        else:
            plt.show()
        plt.close(fig)

    # summarize history for loss
    if 'loss' in metrics:
        fig = plt.figure()
        plt.plot(history['loss'])
        plt.plot(history['val_loss'])
        plt.title('model loss')
        plt.ylabel('loss')
        plt.xlabel('epoch')
        #plt.ylim(1e-3, 1e-2)
        plt.yscale("log")
        plt.legend(['train', 'val'], loc='upper left')
        if save == True:
            plt.savefig(case + 'loss.png')
            plt.gcf().clear()
        else:
            plt.show()
        plt.close(fig)
    
def generator(folder1, folder2):
    for x, y in zip(folder1, folder2):
        yield x, y
          
def saveFeatures(feature_extractor, features_file, labels_file):
        data_folder = '/ssd_drive/FDD_Fall_OF/'
        mean_file = '/ssd_drive/flow_mean.mat'
        L = 10 
        
        class0 = 'Falls'
        class1 = 'NotFalls'

        d = sio.loadmat(mean_file)
        flow_mean = d['image_mean']
        num_features = 4096
      
        folders, classes = [], []
        fall_videos = [f for f in os.listdir(data_folder + class0) if os.path.isdir(os.path.join(data_folder + class0, f))]
        fall_videos.sort()
        for fall_video in fall_videos:
            x_images = glob.glob(data_folder + class0 + '/' + fall_video + '/flow_x*.jpg')
            if int(len(x_images)) >= 10:
                folders.append(data_folder + class0 + '/' + fall_video)
                classes.append(0)

        not_fall_videos = [f for f in os.listdir(data_folder + class1) if os.path.isdir(os.path.join(data_folder + class1, f))]
        not_fall_videos.sort()
        for not_fall_video in not_fall_videos:
            x_images = glob.glob(data_folder + class1 + '/' + not_fall_video + '/flow_x*.jpg')
            if int(len(x_images)) >= 10:
                folders.append(data_folder + class1 + '/' + not_fall_video)
                classes.append(1)

        h5features = h5py.File(features_file,'w')
        h5labels = h5py.File(labels_file,'w')
       
        nb_total_stacks = 0
        for folder in folders:
            x_images = glob.glob(folder + '/flow_x*.jpg')
            nb_total_stacks += int(len(x_images))-L+1
               
        X = folders
        y = classes
        dataset_features = h5features.create_dataset('features', shape=(nb_total_stacks, num_features), dtype='float64')
        dataset_labels = h5labels.create_dataset('labels', shape=(nb_total_stacks, 1), dtype='float64')  
      
        cont = 0

	for folder, label in zip(X, y):
	    x_images = glob.glob(folder + '/flow_x*.jpg')
	    x_images.sort()
	    y_images = glob.glob(folder + '/flow_y*.jpg')
	    y_images.sort()
	    nb_stacks = int(len(x_images))-L+1
	    flow = np.zeros(shape=(224,224,2*L,nb_stacks), dtype=np.float64)
	    gen = generator(x_images,y_images)
	    for i in range(len(x_images)):
		flow_x_file, flow_y_file = gen.next()
		img_x = cv2.imread(flow_x_file, cv2.IMREAD_GRAYSCALE)
		img_y = cv2.imread(flow_y_file, cv2.IMREAD_GRAYSCALE)
		for s in list(reversed(range(min(10,i+1)))):
		    if i-s < nb_stacks:
			flow[:,:,2*s,  i-s] = img_x
			flow[:,:,2*s+1,i-s] = img_y
		del img_x,img_y
		gc.collect()
	    flow = flow - np.tile(flow_mean[...,np.newaxis], (1, 1, 1, flow.shape[3]))
	    flow = np.transpose(flow, (3, 2, 0, 1)) 
	    predictions = np.zeros((flow.shape[0], num_features), dtype=np.float64)
	    truth = np.zeros((flow.shape[0], 1), dtype=np.float64)
	    for i in range(flow.shape[0]):
		prediction = feature_extractor.predict(np.expand_dims(flow[i, ...],0))
		predictions[i, ...] = prediction
		truth[i] = label
	    dataset_features[cont:cont+flow.shape[0],:] = predictions
	    dataset_labels[cont:cont+flow.shape[0],:] = truth
	    cont += flow.shape[0]
        h5features.close()
        h5labels.close()

def main(learning_rate, batch_size, batch_norm, weight_0, epochs, model_file, weights_file): 
    exp = 'lr{}_batchs{}_batchnorm{}_w0_{}'.format(learning_rate, mini_batch_size, batch_norm, w0)
    best_model = 'best_weights/best_weights_{}.hdf5'.format(exp)
    balance_dataset = True
    save_plots = True
    num_features = 4096
    features_file = 'features_fdd.h5'
    labels_file = 'labels_fdd.h5'
    save_features = False
         
    model = Sequential()
    
    model.add(ZeroPadding2D((1, 1), input_shape=(20, 224, 224)))
    model.add(Convolution2D(64, 3, 3, activation='relu', name='conv1_1'))
    model.add(ZeroPadding2D((1, 1)))
    model.add(Convolution2D(64, 3, 3, activation='relu', name='conv1_2'))
    model.add(MaxPooling2D((2, 2), strides=(2, 2)))

    model.add(ZeroPadding2D((1, 1)))
    model.add(Convolution2D(128, 3, 3, activation='relu', name='conv2_1'))
    model.add(ZeroPadding2D((1, 1)))
    model.add(Convolution2D(128, 3, 3, activation='relu', name='conv2_2'))
    model.add(MaxPooling2D((2, 2), strides=(2, 2)))

    model.add(ZeroPadding2D((1, 1)))
    model.add(Convolution2D(256, 3, 3, activation='relu', name='conv3_1'))
    model.add(ZeroPadding2D((1, 1)))
    model.add(Convolution2D(256, 3, 3, activation='relu', name='conv3_2'))
    model.add(ZeroPadding2D((1, 1)))
    model.add(Convolution2D(256, 3, 3, activation='relu', name='conv3_3'))
    model.add(MaxPooling2D((2, 2), strides=(2, 2)))

    model.add(ZeroPadding2D((1, 1)))
    model.add(Convolution2D(512, 3, 3, activation='relu', name='conv4_1'))
    model.add(ZeroPadding2D((1, 1)))
    model.add(Convolution2D(512, 3, 3, activation='relu', name='conv4_2'))
    model.add(ZeroPadding2D((1, 1)))
    model.add(Convolution2D(512, 3, 3, activation='relu', name='conv4_3'))
    model.add(MaxPooling2D((2, 2), strides=(2, 2)))

    model.add(ZeroPadding2D((1, 1)))
    model.add(Convolution2D(512, 3, 3, activation='relu', name='conv5_1'))
    model.add(ZeroPadding2D((1, 1)))
    model.add(Convolution2D(512, 3, 3, activation='relu', name='conv5_2'))
    model.add(ZeroPadding2D((1, 1)))
    model.add(Convolution2D(512, 3, 3, activation='relu', name='conv5_3'))
    model.add(MaxPooling2D((2, 2), strides=(2, 2)))
    
    model.add(Flatten())
    model.add(Dense(4096, name='fc6', init='glorot_uniform'))
   
    

    layerskeras = ['block1_conv1', 'block1_conv2', 'block2_conv1', 'block2_conv2', 'block3_conv1', 'block3_conv2', 'block3_conv3', 'block4_conv1', 'block4_conv2', 'block4_conv3', 'block5_conv1', 'block5_conv2', 'block5_conv3', 'fc1', 'fc2', 'predictions']
    layerscaffe = ['conv1_1', 'conv1_2', 'conv2_1', 'conv2_2', 'conv3_1', 'conv3_2', 'conv3_3', 'conv4_1', 'conv4_2', 'conv4_3', 'conv5_1', 'conv5_2', 'conv5_3', 'fc6', 'fc7', 'fc8']
    i = 0
    h5 = h5py.File('/home/anunez/project/caffedata.h5')
    
    layer_dict = dict([(layer.name, layer) for layer in model.layers])

    for layer in layerscaffe[:-3]:
        w2, b2 = h5['data'][layer]['0'], h5['data'][layer]['1']
        w2 = np.transpose(np.asarray(w2), (0,1,2,3))
        w2 = w2[:, :, ::-1, ::-1]
        b2 = np.asarray(b2)
        layer_dict[layer].W.set_value(w2)
        layer_dict[layer].b.set_value(b2)
        i += 1
        
    layer = layerscaffe[-3]
    w2, b2 = h5['data'][layer]['0'], h5['data'][layer]['1']
    w2 = np.transpose(np.asarray(w2), (1,0))
    b2 = np.asarray(b2)
    layer_dict[layer].W.set_value(w2)
    layer_dict[layer].b.set_value(b2)
    i += 1
    
    copy_dense_weights = False
    if copy_dense_weights:
        layer = layerscaffe[-2]
        w2, b2 = h5['data'][layer]['0'], h5['data'][layer]['1']      
        w2 = np.transpose(w2,(1,0))
        b2 = np.asarray(b2)
        i += 1

    adam = Adam(lr=learning_rate, beta_1=0.9, beta_2=0.999, epsilon=1e-08, decay=0.0005)
    model.compile(optimizer=adam, loss='categorical_crossentropy', metrics=['accuracy'])
    c = ModelCheckpoint(filepath=best_model, monitor='val_acc', verbose=1, save_best_only=True, save_weights_only=False, mode='auto')
    e = EarlyStopping(monitor='loss', min_delta=0, patience=0, verbose=0, mode='auto')

    # =============================================================================================================
    # FEATURE EXTRACTION
    # =============================================================================================================
    
    if save_features:
        saveFeatures(model, features_file, labels_file)

    # =============================================================================================================
    # TRAINING
    # =============================================================================================================
    do_training = True   
    compute_metrics = True
    
    if do_training:
        h5features = h5py.File(features_file, 'r')
        h5labels = h5py.File(labels_file, 'r')
        
        X_full = np.asarray(h5features['features'])
        _y_full = np.asarray(h5labels['labels'])
            
        zeroes = np.asarray(np.where(_y_full==0)[0])
        ones = np.asarray(np.where(_y_full==1)[0])
        zeroes.sort()
        ones.sort()
        
        kf_falls = KFold(n_splits=5)
        kf_falls.get_n_splits(X_full[zeroes, ...])
        
        kf_nofalls = KFold(n_splits=5)
        kf_nofalls.get_n_splits(X_full[ones, ...])        
            
        sensitivities = []
        specificities = []
        accuracies = []
        
        for (train_index_falls, test_index_falls), (train_index_nofalls, test_index_nofalls) in zip(kf_falls.split(X_full[zeroes, ...]), kf_nofalls.split(X_full[ones, ...])):

            train_index_falls = np.asarray(train_index_falls)
            test_index_falls = np.asarray(test_index_falls)
            train_index_nofalls = np.asarray(train_index_nofalls)
            test_index_nofalls = np.asarray(test_index_nofalls)
            train_index = np.concatenate((train_index_falls, train_index_nofalls), axis=0)
            test_index = np.concatenate((test_index_falls, test_index_nofalls), axis=0)
            train_index.sort()
            test_index.sort()
            X = np.concatenate((X_full[train_index_falls, ...], X_full[train_index_nofalls, ...]))
            _y = np.concatenate((_y_full[train_index_falls, ...], _y_full[train_index_nofalls, ...]))
            X2 = np.concatenate((X_full[test_index_falls, ...], X_full[test_index_nofalls, ...]))
            _y2 = np.concatenate((_y_full[test_index_falls, ...], _y_full[test_index_nofalls, ...]))
        
         
            all0 = np.asarray(np.where(_y==0)[0])
            all1 = np.asarray(np.where(_y==1)[0])   
            if balance_dataset:
                if len(all0) < len(all1):
                    all1 = np.random.choice(all1, len(all0), replace=False)
                else:
                    all0 = np.random.choice(all0, len(all1), replace=False)
                allin = np.concatenate((all0.flatten(),all1.flatten()))
                allin.sort()
                X = X[allin,...]
                _y = _y[allin]

            # ==================== CLASSIFIER ========================
            extracted_features = Input(shape=(4096,), dtype='float32', name='input')
            if batch_norm:
                x = BatchNormalization(axis=-1, momentum=0.99, epsilon=0.001)(extracted_features)
                x = ELU(alpha=1.0)(x)
	    else:
            	x = ELU(alpha=1.0)(extracted_features)
	    
            x = Dropout(0.9)(x)
            x = Dense(4096, name='fc2', init='glorot_uniform')(x)
            if batch_norm:
                x = BatchNormalization(axis=-1, momentum=0.99, epsilon=0.001)(x)
		x = Activation('relu')(x)
            else:
		x = ELU(alpha=1.0)(x)

            x = Dropout(0.8)(x)
            x = Dense(1, name='predictions', init='glorot_uniform')(x)
            x = Activation('sigmoid')(x)

            classifier = Model(input=extracted_features, output=x, name='classifier')
            classifier.compile(optimizer=adam, loss='binary_crossentropy',  metrics=['accuracy'])
	    # ==================== CLASSIFIER ========================
           
            class_weight = {0:weight_0, 1:1}
            if batch_size == 0:
            	history = classifier.fit(X,_y, validation_data=(X2,_y2), batch_size=X.shape[0], nb_epoch=epochs, shuffle='batch', class_weight=class_weight)
	    else:
		history = classifier.fit(X,_y, validation_data=(X2,_y2), batch_size=batch_size, nb_epoch=epochs, shuffle='batch', class_weight=class_weight)
            plot_training_info('prueba', ['accuracy', 'loss'], save_plots, history.history)

            if compute_metrics:
               threshold = 0.5
               predicted = classifier.predict(np.asarray(X2))
               ind0 = np.where(np.asarray(_y2)<threshold)[0]
               ind1 = np.where(np.asarray(_y2)>=threshold)[0]
	       for i in range(len(predicted)):
                   if predicted[i] < threshold:
               		predicted[i] = 0
                   else:
               		predicted[i] = 1
               predicted = np.asarray(predicted)
               cm = confusion_matrix(_y2, predicted,labels=[0,1])
               tp = cm[0][0]
               fn = cm[0][1]
               fp = cm[1][0]
               tn = cm[1][1]
               tpr = tp/float(tp+fn)
               fpr = fp/float(fp+tn)
               fnr = fn/float(fn+tp)
               tnr = tn/float(tn+fp)
	       precision = tp/float(tp+fp)
               recall = tp/float(tp+fn)
	       specificity = tn/float(tn+fp)
	       f1 = 2*float(precision*recall)/float(precision+recall)
	       accuracy = accuracy_score(_y2, predicted)
               print('TP: {}, TN: {}, FP: {}, FN: {}'.format(tp,tn,fp,fn))
               print('TPR: {}, TNR: {}, FPR: {}, FNR: {}'.format(tpr,tnr,fpr,fnr))   
               print('Sensitivity/Recall: {}'.format(recall))
               print('Specificity: {}'.format(specificity))
               print('Precision: {}'.format(precision))
               print('F1-measure: {}'.format(f1))
	       print('Accuracy: {}'.format(accuracy))
               sensitivities.append(tp/float(tp+fn))
               specificities.append(tn/float(tn+fp))
               accuracies.append(accuracy)
        print('5-FOLD CROSS-VALIDATION RESULTS ===================')
        print("Sensitivity: %.2f%% (+/- %.2f%%)" % (np.mean(sensitivities), np.std(sensitivities)))
        print("Specificity: %.2f%% (+/- %.2f%%)" % (np.mean(specificities), np.std(specificities)))
        print("Accuracy: %.2f%% (+/- %.2f%%)" % (np.mean(accuracies), np.std(accuracies)))
        print(exp)             
        
if __name__ == '__main__':
    model_file = '/home/anunez/project/models/exp_'
    weights_file = '/home/anunez/project/weights/exp_'
    batch_norm = True
    learning_rate = 0.001
    mini_batch_size = 0
    w0 = 2
    epochs = 3000
  
    main(learning_rate, mini_batch_size, batch_norm, w0, epochs, model_file, weights_file)
