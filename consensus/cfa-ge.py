from __future__ import absolute_import, division, print_function, unicode_literals
from keras.utils import to_categorical
import numpy as np
import tensorflow as tf
import datetime
import scipy.io as sio
import math
from matplotlib.pyplot import pause
import os
import glob

class CFA_ge_process:
    # sets neighbor indexes for k-regular networks (number of neighbors is 'neighbors'
    def get_connectivity(self, ii_saved_local, neighbors, devices):
        if (ii_saved_local == 0):
            sets_neighbors_final = np.arange(ii_saved_local + 1, ii_saved_local + neighbors + 1)
        elif (ii_saved_local == devices - 1):
            sets_neighbors_final = np.arange(ii_saved_local - neighbors, ii_saved_local)
        elif (ii_saved_local >= math.ceil(neighbors / 2)) and (
                ii_saved_local <= devices - math.ceil(neighbors / 2) - 1):
            sets_neighbors = np.arange(ii_saved_local - math.floor(neighbors / 2),
                                       ii_saved_local + math.floor(neighbors / 2) + 1)
            index_ii = np.where(sets_neighbors == ii_saved_local)
            sets_neighbors_final = np.delete(sets_neighbors, index_ii)
        else:
            if (ii_saved_local - math.ceil(neighbors / 2) < 0):
                sets_neighbors = np.arange(0, neighbors + 1)
            else:
                sets_neighbors = np.arange(devices - neighbors - 1, devices)
            index_ii = np.where(sets_neighbors == ii_saved_local)
            sets_neighbors_final = np.delete(sets_neighbors, index_ii)
        return sets_neighbors_final

    # compute weights for CFA
    def federated_weights_computing2(self, filename, filename2, ii, ii2, epoch, devices, neighbors, eps_t_control):
        saved_epoch = epoch
        b_v = 1 / devices
        # eps_t_control = 1 #from paper
        while not os.path.isfile(filename2):
            print('Waiting..')
            pause(1)

        try:
            mathcontent = sio.loadmat(filename2)
        except:
            print('Detected problem while loading file')
            pause(3)
            mathcontent = sio.loadmat(filename2)

        weights_current_l1 = mathcontent['weights1']
        biases_current_l1 = mathcontent['biases1']
        weights_current_l2 = mathcontent['weights2']
        biases_current_l2 = mathcontent['biases2']

        while not os.path.isfile(filename):
            print('Waiting..')
            pause(1)

        try:
            mathcontent = sio.loadmat(filename)
        except:
            print('Detected problem while loading file')
            pause(3)
            mathcontent = sio.loadmat(filename)

        balancing_vect = np.ones(devices) * b_v
        weight_factor = (balancing_vect[ii2] / (
                    balancing_vect[ii2] + (neighbors - 1) * balancing_vect[ii]))  # equation (11) from paper
        updated_weights_l1 = weights_current_l1 + eps_t_control * weight_factor * (
                    mathcontent['weights1'] - weights_current_l1)  # see paper section 3
        updated_biases_l1 = biases_current_l1 + eps_t_control * weight_factor * (
                    mathcontent['biases1'] - biases_current_l1)
        updated_weights_l2 = weights_current_l2 + eps_t_control * weight_factor * (
                    mathcontent['weights2'] - weights_current_l2)  # see paper section 3
        updated_biases_l2 = biases_current_l2 + eps_t_control * weight_factor * (
                    mathcontent['biases2'] - biases_current_l2)

        weights_l1 = updated_weights_l1
        biases_l1 = updated_biases_l1
        weights_l2 = updated_weights_l2
        biases_l2 = updated_biases_l2

        try:
            sio.savemat('temp_datamat{}_{}.mat'.format(ii, saved_epoch), {
                "weights1": weights_l1, "biases1": biases_l1, "weights2": weights_l2, "biases2": biases_l2})
            mathcontent = sio.loadmat('temp_datamat{}_{}.mat'.format(ii, saved_epoch))
        except:
            print('Unable to save file .. retrying')
            pause(3)
            print(biases)
            sio.savemat('temp_datamat{}_{}.mat'.format(ii, saved_epoch), {
                "weights1": weights_l1, "biases1": biases_l1, "weights2": weights_l2, "biases2": biases_l2})
        return weights_l1, biases_l1, weights_l2, biases_l2

    def __init__(self, federated, devices, ii_saved_local, neighbors):
        self.federated = federated # true for federation active
        self.devices = devices # number of devices
        self.ii_saved_local = ii_saved_local # device index
        self.neighbors = neighbors # neighbors number (given the network topology)
        self.neighbor_vec = self.get_connectivity(ii_saved_local, neighbors, devices) # neighbor list

    # CFA-GE 4 stage implementation
    def getFederatedWeight_gradients(self, n_W_l1, n_W_l2, n_b_l1, n_b_l2, federated, devices, ii_saved_local, epoch, v_loss,
                                     eng, x_train2, y_train2, neighbors, W_l1_saved, W_l2_saved, n_l1_saved,
                                     n_l2_saved):
        x_c = tf.placeholder(tf.float32, [None, 512])  # 512 point FFT range measurements
        y_c = tf.placeholder(tf.float32, [None, 8])  # 0-7 HR distances => 8 classes

        W_ext_c_l1 = tf.placeholder(tf.float32, [filter, 1, number])
        b_ext_c_l1 = tf.placeholder(tf.float32, [number])

        W_ext_c_l2 = tf.placeholder(tf.float32, [multip * number, 8])
        b_ext_c_l2 = tf.placeholder(tf.float32, [8])

        # Construct model Layer #1 CNN 1d, Layer #2 FC
        hidden1 = conv1d(x_c, W_ext_c_l1, b_ext_c_l1)
        hidden1 = tf.layers.max_pooling1d(hidden1, pool_size=stride, strides=stride, padding='SAME')
        fc1 = tf.reshape(hidden1, [-1, multip * number])
        pred_c = tf.nn.softmax(tf.matmul(fc1, W_ext_c_l2) + b_ext_c_l2)  # example 2 layers

        # Minimize error using cross entropy
        cost_c = tf.reduce_mean(
            -tf.reduce_sum(y_c * tf.log(tf.clip_by_value(pred_c, 1e-15, 0.99)), reduction_indices=1))

        # obtain the gradients for each layer
        grad_W_c_l1, grad_b_c_l1, grad_W_c_l2, grad_b_c_l2 = tf.gradients(
            xs=[W_ext_c_l1, b_ext_c_l1, W_ext_c_l2, b_ext_c_l2], ys=cost_c)

        # Initialize the variables (i.e. assign their default value)
        init_c = tf.global_variables_initializer()
        if (federated):
            if devices > 1:
                if epoch == 0:
                    sio.savemat('datamat{}_{}.mat'.format(ii_saved_local, epoch), {
                        "weights1": n_W_l1, "biases1": n_b_l1, "weights2": n_W_l2, "biases2": n_b_l2, "epoch": epoch,
                        "loss_sample": v_loss})
                    W_up_l1 = n_W_l1
                    W_up_l2 = n_W_l2
                    n_up_l1 = n_b_l1
                    n_up_l2 = n_b_l2

                else:
                    sio.savemat('temp_datamat{}_{}.mat'.format(ii_saved_local, epoch), {
                        "weights1": n_W_l1, "biases1": n_b_l1, "weights2": n_W_l2, "biases2": n_b_l2, "epoch": epoch,
                        "loss_sample": v_loss})
                    neighbor_vec = get_connectivity(ii_saved_local, neighbors, devices)
                    for neighbor_index in range(neighbor_vec.size):
                        while not os.path.isfile(
                                'datamat{}_{}.mat'.format(neighbor_vec[neighbor_index],
                                                          epoch - 1)) or not os.path.isfile(
                            'temp_datamat{}_{}.mat'.format(ii_saved_local, epoch)):
                            # print('Waiting for datamat{}_{}.mat'.format(ii_saved_local - 1, epoch - 1))
                            pause(1)
                        [W_up_l1, n_up_l1, W_up_l2, n_up_l2] = federated_weights_computing2(
                            'datamat{}_{}.mat'.format(neighbor_vec[neighbor_index], epoch - 1),
                            'temp_datamat{}_{}.mat'.format(ii_saved_local, epoch), ii_saved_local,
                            neighbor_vec[neighbor_index],
                            epoch, devices, neighbors)
                        pause(5)
                    try:
                        sio.savemat('datamat{}_{}.mat'.format(ii_saved_local, epoch), {
                            "weights1": W_up_l1, "biases1": n_up_l1, "weights2": W_up_l2, "biases2": n_up_l2})
                        mathcontent = sio.loadmat('datamat{}_{}.mat'.format(ii_saved_local, epoch))
                    except:
                        print('Unable to save file .. retrying')
                        pause(3)
                        sio.savemat('datamat{}_{}.mat'.format(ii_saved_local, epoch), {
                            "weights1": W_up_l1, "biases1": n_up_l1, "weights2": W_up_l2, "biases2": n_up_l2})

                    while not os.path.isfile('datamat{}_{}.mat'.format(ii_saved_local, epoch)):
                        # print('Waiting for datamat{}_{}.mat'.format(ii_saved_local, epoch))
                        pause(1)

                    # waiting for other updates
                    # expanded for gradient exchange
                    pause(3)

                    g_W_c_vect_l1 = np.zeros([filter, 1, number, devices])
                    g_b_c_vect_l1 = np.zeros([number, devices])
                    g_W_c_vect_l2 = np.zeros([multip * number, 8, devices])
                    g_b_c_vect_l2 = np.zeros([8, devices])

                    for neighbor_index in range(neighbor_vec.size):
                        while not os.path.isfile(
                                'datamat{}_{}.mat'.format(neighbor_vec[neighbor_index], epoch)):
                            # print('Waiting for datamat{}_{}.mat'.format(ii_saved_local - 1, epoch))
                            pause(1)
                        try:
                            mathcontent = sio.loadmat('datamat{}_{}.mat'.format(neighbor_vec[neighbor_index], epoch))
                            W_up_neigh_l1 = np.asarray(mathcontent['weights1'])
                            n_up_neigh_l1 = np.squeeze(np.asarray(mathcontent['biases1']))
                            W_up_neigh_l2 = np.asarray(mathcontent['weights2'])
                            n_up_neigh_l2 = np.squeeze(np.array(mathcontent['biases2']))
                        except:
                            pause(5)
                            mathcontent = sio.loadmat('datamat{}_{}.mat'.format(neighbor_vec[neighbor_index], epoch))
                            W_up_neigh_l1 = np.asarray(mathcontent['weights1'])
                            n_up_neigh_l1 = np.squeeze(np.asarray(mathcontent['biases1']))
                            W_up_neigh_l2 = np.asarray(mathcontent['weights2'])
                            n_up_neigh_l2 = np.squeeze(np.array(mathcontent['biases2']))

                        with tf.Session() as sess3:
                            sess3.run(init_c)
                            g_W_c_l1, g_b_c_l1, g_W_c_l2, g_b_c_l2 = sess3.run(
                                [grad_W_c_l1, grad_b_c_l1, grad_W_c_l2, grad_b_c_l2],
                                feed_dict={x_c: x_train2, y_c: y_train2, W_ext_c_l1: W_up_neigh_l1,
                                           b_ext_c_l1: n_up_neigh_l1, W_ext_c_l2: W_up_neigh_l2,
                                           b_ext_c_l2: n_up_neigh_l2})
                            g_W_c_vect_l1[:, :, :, neighbor_vec[neighbor_index]] = g_W_c_l1
                            g_b_c_vect_l1[:, neighbor_vec[neighbor_index]] = g_b_c_l1
                            g_W_c_vect_l2[:, :, neighbor_vec[neighbor_index]] = g_W_c_l2
                            g_b_c_vect_l2[:, neighbor_vec[neighbor_index]] = g_b_c_l2

                    # save gradients and upload
                    try:
                        sio.savemat('datagrad{}_{}.mat'.format(ii_saved_local, epoch), {
                            "grad_weights1": g_W_c_vect_l1, "grad_biases1": g_b_c_vect_l1,
                            "grad_weights2": g_W_c_vect_l2,
                            "grad_biases2": g_b_c_vect_l2, "epoch": epoch})
                        # waiting for other gradient updates
                        pause(5)
                        mathcontent = sio.loadmat('datagrad{}_{}.mat'.format(ii_saved_local, epoch))
                        test_var = mathcontent['grad_biases1']
                        del mathcontent
                    except:
                        print('Unable to save file .. retrying')
                        pause(3)
                        sio.savemat('datagrad{}_{}.mat'.format(ii_saved_local, epoch), {
                            "grad_weights1": g_W_c_vect_l1, "grad_biases1": g_b_c_vect_l1,
                            "grad_weights2": g_W_c_vect_l2,
                            "grad_biases2": g_b_c_vect_l2, "epoch": epoch})

                    # waiting for other gradient updates
                    pause(5)
                    try:
                        mathcontent = sio.loadmat('datamat{}_{}.mat'.format(ii_saved_local, epoch))
                        W_up_l1 = np.asarray(mathcontent['weights1'])
                        n_up_l1 = np.squeeze(np.asarray(mathcontent['biases1']))
                        W_up_l2 = np.asarray(mathcontent['weights2'])
                        n_up_l2 = np.squeeze(np.asarray(mathcontent['biases2']))
                    except:
                        pause(5)
                        mathcontent = sio.loadmat('datamat{}_{}.mat'.format(ii_saved_local, epoch))
                        W_up_l1 = np.asarray(mathcontent['weights1'])
                        n_up_l1 = np.squeeze(np.asarray(mathcontent['biases1']))
                        W_up_l2 = np.asarray(mathcontent['weights2'])
                        n_up_l2 = np.squeeze(np.asarray(mathcontent['biases2']))

                    # update local model with neighbor gradients
                    for neighbor_index in range(neighbor_vec.size):
                        while not os.path.isfile(
                                'datagrad{}_{}.mat'.format(neighbor_vec[neighbor_index], epoch)):
                            pause(1)
                        try:
                            mathcontent = sio.loadmat('datagrad{}_{}.mat'.format(neighbor_vec[neighbor_index], epoch))
                        except:
                            pause(3)
                            mathcontent = sio.loadmat('datagrad{}_{}.mat'.format(neighbor_vec[neighbor_index], epoch))
                        gradW_up_neigh_l1 = np.asarray(mathcontent['grad_weights1'])
                        gradW_up_neigh_l2 = np.asarray(mathcontent['grad_weights2'])
                        try:
                            gradn_up_neigh_l1 = np.squeeze(np.asarray(mathcontent['grad_biases1']))
                            gradn_up_neigh_l2 = np.squeeze(np.asarray(mathcontent['grad_biases2']))
                        except:
                            pause(5)
                            print('datagrad{}_{}.mat'.format(neighbor_vec[neighbor_index], epoch))
                            del mathcontent
                            mathcontent = sio.loadmat('datagrad{}_{}.mat'.format(neighbor_vec[neighbor_index], epoch))
                            gradW_up_neigh_l1 = np.asarray(mathcontent['grad_weights1'])
                            gradW_up_neigh_l2 = np.asarray(mathcontent['grad_weights2'])
                            gradn_up_neigh_l1 = np.squeeze(np.asarray(mathcontent['grad_biases1']))
                            gradn_up_neigh_l2 = np.squeeze(np.asarray(mathcontent['grad_biases2']))

                        # MEWMA UPDATE
                        mewma = args.ro
                        # saving gradients
                        if epoch == 1:
                            W_l1_saved[:, :, :, neighbor_index] = gradW_up_neigh_l1[:, :, :, ii_saved_local]
                            W_l2_saved[:, :, neighbor_index] = gradW_up_neigh_l2[:, :, ii_saved_local]
                            n_l1_saved[:, neighbor_index] = gradn_up_neigh_l1[:, ii_saved_local]
                            n_l2_saved[:, neighbor_index] = gradn_up_neigh_l2[:, ii_saved_local]
                        else:
                            W_l1_saved[:, :, :, neighbor_index] = mewma * gradW_up_neigh_l1[:, :, :, ii_saved_local] + (
                                        1 - mewma) * W_l1_saved[:, :, :, neighbor_index]
                            W_l2_saved[:, :, neighbor_index] = mewma * gradW_up_neigh_l2[:, :, ii_saved_local] + (
                                        1 - mewma) * W_l2_saved[:, :, neighbor_index]
                            n_l1_saved[:, neighbor_index] = mewma * gradn_up_neigh_l1[:, ii_saved_local] + (
                                        1 - mewma) * n_l1_saved[:, neighbor_index]
                            n_l2_saved[:, neighbor_index] = mewma * gradn_up_neigh_l2[:, ii_saved_local] + (
                                        1 - mewma) * n_l2_saved[:, neighbor_index]

                        W_up_l1 = W_up_l1 - learning_rate1 * gradW_up_neigh_l1[:, :, :, ii_saved_local]
                        n_up_l1 = n_up_l1 - learning_rate1 * gradn_up_neigh_l1[:, ii_saved_local]
                        W_up_l2 = W_up_l2 - learning_rate2 * gradW_up_neigh_l2[:, :, ii_saved_local]
                        n_up_l2 = n_up_l2 - learning_rate2 * gradn_up_neigh_l2[:, ii_saved_local]
            else:
                W_up_l1 = n_W_l1
                W_up_l2 = n_W_l2
                n_up_l1 = n_b_l1
                n_up_l2 = n_b_l2
        else:
            W_up_l1 = n_W_l1
            W_up_l2 = n_W_l2
            n_up_l1 = n_b_l1
            n_up_l2 = n_b_l2

        return W_up_l1, n_up_l1, W_up_l2, n_up_l2, W_l1_saved, W_l2_saved, n_l1_saved, n_l2_saved