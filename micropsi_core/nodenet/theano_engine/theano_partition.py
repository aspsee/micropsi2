

import os

import theano
from theano import tensor as T
import numpy as np
import scipy.sparse as sp
import theano.sparse as ST
from theano.tensor import nnet as N

from micropsi_core.nodenet.theano_engine.theano_definitions import *


class TheanoPartition():

    @property
    def spid(self):
        return "%03i" % self.pid

    @property
    def rootnodespace_uid(self):
        return "s%s1" % self.spid

    @property
    def has_new_usages(self):
        return self.__has_new_usages

    @has_new_usages.setter
    def has_new_usages(self, value):
        self.__has_new_usages = value

    @property
    def has_pipes(self):
        return self.__has_pipes

    @has_pipes.setter
    def has_pipes(self, value):
        if value != self.__has_pipes:
            self.__has_new_usages = True
            self.__has_pipes = value

    @property
    def has_lstms(self):
        return self.__has_lstms

    @has_lstms.setter
    def has_lstms(self, value):
        if value != self.__has_lstms:
            self.__has_new_usages = True
            self.__has_lstms = value

    @property
    def has_directional_activators(self):
        return self.__has_directional_activators

    @has_directional_activators.setter
    def has_directional_activators(self, value):
        if value != self.__has_directional_activators:
            self.__has_new_usages = True
            self.__has_directional_activators = value

    @property
    def has_sampling_activators(self):
        return self.__has_sampling_activators

    @has_sampling_activators.setter
    def has_sampling_activators(self, value):
        if value != self.__has_sampling_activators:
            self.__has_new_usages = True
            self.__has_sampling_activators = value

    @property
    def has_gatefunction_absolute(self):
        return self.__has_gatefunction_absolute

    @has_gatefunction_absolute.setter
    def has_gatefunction_absolute(self, value):
        if value != self.__has_gatefunction_absolute:
            self.__has_new_usages = True
            self.__has_gatefunction_absolute = value

    @property
    def has_gatefunction_sigmoid(self):
        return self.__has_gatefunction_sigmoid

    @has_gatefunction_sigmoid.setter
    def has_gatefunction_sigmoid(self, value):
        if value != self.__has_gatefunction_sigmoid:
            self.__has_new_usages = True
            self.__has_gatefunction_sigmoid = value

    @property
    def has_gatefunction_tanh(self):
        return self.__has_gatefunction_tanh

    @has_gatefunction_tanh.setter
    def has_gatefunction_tanh(self, value):
        if value != self.__has_gatefunction_tanh:
            self.__has_new_usages = True
            self.__has_gatefunction_tanh = value

    @property
    def has_gatefunction_rect(self):
        return self.__has_gatefunction_rect

    @has_gatefunction_rect.setter
    def has_gatefunction_rect(self, value):
        if value != self.__has_gatefunction_rect:
            self.__has_new_usages = True
            self.__has_gatefunction_rect = value

    @property
    def has_gatefunction_one_over_x(self):
        return self.__has_gatefunction_one_over_x

    @has_gatefunction_one_over_x.setter
    def has_gatefunction_one_over_x(self, value):
        if value != self.__has_gatefunction_one_over_x:
            self.__has_new_usages = True
            self.__has_gatefunction_one_over_x = value

    def __init__(self, nodenet, pid, sparse=True, initial_number_of_nodes=2000, average_elements_per_node_assumption=5, initial_number_of_nodespaces=10):

        # logger used by this partition
        self.logger = nodenet.logger

        # uids to instances of TheanoNode objects for living native modules
        self.native_module_instances = {}

        # uids to TheanoNode objects for comments
        self.comment_instances = {}

        # noddespace_uids to map map. level-2 map is groupname to list of numeric IDs
        self.nodegroups = {}

        # nodenet partition ID
        self.pid = pid

        # number of nodes allocated in this partition
        self.NoN = initial_number_of_nodes

        # numer of elements allocated in this partition
        self.NoE = initial_number_of_nodes * average_elements_per_node_assumption

        # numer of nodespaces allocated in this partition
        self.NoNS = initial_number_of_nodespaces

        # the nodenet this partition belongs to
        self.nodenet = nodenet

        # sparsity flag for this partition
        self.sparse = sparse

        # array, index is node id, value is numeric node type
        self.allocated_nodes = None

        # array, index is node id, value is nodenet-step where node was last modified
        self.nodes_last_changed = np.zeros(self.NoN, dtype=np.int32) - 1

        # array, index is node id, value is offset in a and w
        self.allocated_node_offsets = None

        # array, index is element index, value is node id
        self.allocated_elements_to_nodes = None

        # array, index is node id, value is nodespace id
        self.allocated_node_parents = None

        # array, index is nodespace id, value is parent nodespace id
        self.allocated_nodespaces = None

        # array, index is nodespace id, value is nodenet-step where nodespace was last modified
        self.nodespaces_last_changed = np.zeros(self.NoNS, dtype=np.int32) - 1

        # array, index is nodespace id, value is nodenet-step where the immediate children of this nodespace were last modified
        self.nodespaces_contents_last_changed = np.zeros(self.NoNS, dtype=np.int32) - 1

        # directional activator assignment, key is nodespace ID, value is activator ID
        self.allocated_nodespaces_por_activators = None
        self.allocated_nodespaces_ret_activators = None
        self.allocated_nodespaces_sub_activators = None
        self.allocated_nodespaces_sur_activators = None
        self.allocated_nodespaces_cat_activators = None
        self.allocated_nodespaces_exp_activators = None

        self.allocated_nodespaces_sampling_activators = None

        # directional activators map, index is element id, value is the directional activator's element id
        self.allocated_elements_to_activators = None

        # theano tensors for performing operations
        self.w = None            # matrix of weights
        self.a = None            # vector of activations
        self.a_shifted = None    # matrix with each row defined as [a[n], a[n+1], a[n+2], a[n+3], a[n+4], a[n+5], a[n+6]]
                            # this is a view on the activation values instrumental in calculating concept node functions

        self.a_in = None         # vector of activations coming in from the outside (other partitions typically)
        self.a_prev = None       # vector of output activations at t-1 (not all gate types maintain this)

        self.g_factor = None     # vector of gate factors, controlled by activators, semantics differ by node type
        self.g_threshold = None  # vector of thresholds (gate parameters)
        self.g_amplification = None  # vector of amplification factors
        self.g_min = None        # vector of lower bounds
        self.g_max = None        # vector of upper bounds

        self.g_function_selector = None # vector of gate function selectors

        self.g_theta = None      # vector of thetas (i.e. biases, use depending on gate function)

        self.g_expect = None     # vector of expectations
        self.g_countdown = None  # vector of number of steps until expectation needs to be met
        self.g_wait = None       # vector of initial values for g_countdown

        self.n_function_selector = None      # vector of per-gate node function selectors
        self.n_node_porlinked = None         # vector with 0/1 flags to indicated whether the element belongs to a por-linked
                                             # node. This could in theory be inferred with T.max() on upshifted versions of w,
                                             # but for now, we manually track this property
        self.n_node_retlinked = None         # same for ret

        # instantiate numpy data structures
        self.allocated_nodes = np.zeros(self.NoN, dtype=np.int32)
        self.allocated_node_offsets = np.zeros(self.NoN, dtype=np.int32)
        self.allocated_elements_to_nodes = np.zeros(self.NoE, dtype=np.int32)

        self.allocated_node_parents = np.zeros(self.NoN, dtype=np.int32)
        self.allocated_nodespaces = np.zeros(self.NoNS, dtype=np.int32)

        self.allocated_nodespaces_por_activators = np.zeros(self.NoNS, dtype=np.int32)
        self.allocated_nodespaces_ret_activators = np.zeros(self.NoNS, dtype=np.int32)
        self.allocated_nodespaces_sub_activators = np.zeros(self.NoNS, dtype=np.int32)
        self.allocated_nodespaces_sur_activators = np.zeros(self.NoNS, dtype=np.int32)
        self.allocated_nodespaces_cat_activators = np.zeros(self.NoNS, dtype=np.int32)
        self.allocated_nodespaces_exp_activators = np.zeros(self.NoNS, dtype=np.int32)

        self.allocated_nodespaces_sampling_activators = np.zeros(self.NoNS, dtype=np.int32)

        self.allocated_elements_to_activators = np.zeros(self.NoE, dtype=np.int32)

        self.sensor_indices = np.zeros(0, dtype=np.int32)  # index := datasource, value:=node_id
        self.actuator_indices = np.zeros(0, dtype=np.int32)  # index := datatarget, value:=node_id

        self.inlinks = {}

        self.deleted_items = {}

        # instantiate theano data structures
        if self.sparse:
            self.w = theano.shared(sp.csr_matrix((self.NoE, self.NoE), dtype=nodenet.scipyfloatX), name="w")
        else:
            w_matrix = np.zeros((self.NoE, self.NoE), dtype=nodenet.scipyfloatX)
            self.w = theano.shared(value=w_matrix.astype(T.config.floatX), name="w", borrow=True)

        self.t = theano.shared(value=np.int32(0), name="t")

        a_array = np.zeros(self.NoE, dtype=nodenet.numpyfloatX)
        self.a = theano.shared(value=a_array.astype(T.config.floatX), name="a", borrow=True)

        a_shifted_matrix = np.lib.stride_tricks.as_strided(a_array, shape=(self.NoE, 7), strides=(nodenet.byte_per_float, nodenet.byte_per_float))
        self.a_shifted = theano.shared(value=a_shifted_matrix.astype(T.config.floatX), name="a_shifted", borrow=True)

        a_in_array = np.zeros(self.NoE, dtype=nodenet.numpyfloatX)
        self.a_in = theano.shared(value=a_in_array.astype(T.config.floatX), name="a_in", borrow=True)

        a_prev_array = np.zeros(self.NoE, dtype=nodenet.numpyfloatX)
        self.a_prev = theano.shared(value=a_prev_array.astype(T.config.floatX), name="a_prev", borrow=True)

        g_theta_array = np.zeros(self.NoE, dtype=nodenet.numpyfloatX)
        self.g_theta = theano.shared(value=g_theta_array.astype(T.config.floatX), name="theta", borrow=True)

        g_theta_shifted_matrix = np.lib.stride_tricks.as_strided(g_theta_array, shape=(self.NoE, 7), strides=(nodenet.byte_per_float, nodenet.byte_per_float))
        self.g_theta_shifted = theano.shared(value=g_theta_shifted_matrix.astype(T.config.floatX), name="g_theta_shifted_shifted", borrow=True)

        g_factor_array = np.ones(self.NoE, dtype=nodenet.numpyfloatX)
        self.g_factor = theano.shared(value=g_factor_array.astype(T.config.floatX), name="g_factor", borrow=True)

        g_threshold_array = np.zeros(self.NoE, dtype=nodenet.numpyfloatX)
        self.g_threshold = theano.shared(value=g_threshold_array.astype(T.config.floatX), name="g_threshold", borrow=True)

        g_amplification_array = np.ones(self.NoE, dtype=nodenet.numpyfloatX)
        self.g_amplification = theano.shared(value=g_amplification_array.astype(T.config.floatX), name="g_amplification", borrow=True)

        g_min_array = np.zeros(self.NoE, dtype=nodenet.numpyfloatX)
        self.g_min = theano.shared(value=g_min_array.astype(T.config.floatX), name="g_min", borrow=True)

        g_max_array = np.ones(self.NoE, dtype=nodenet.numpyfloatX)
        self.g_max = theano.shared(value=g_max_array.astype(T.config.floatX), name="g_max", borrow=True)

        g_function_selector_array = np.zeros(self.NoE, dtype=np.int8)
        self.g_function_selector = theano.shared(value=g_function_selector_array, name="gatefunction", borrow=True)

        g_expect_array = np.ones(self.NoE, dtype=nodenet.numpyfloatX)
        self.g_expect = theano.shared(value=g_expect_array, name="expectation", borrow=True)

        g_countdown_array = np.zeros(self.NoE, dtype=np.int16)
        self.g_countdown = theano.shared(value=g_countdown_array, name="countdown", borrow=True)

        g_wait_array = np.ones(self.NoE, dtype=np.int16)
        self.g_wait = theano.shared(value=g_wait_array, name="wait", borrow=True)

        n_function_selector_array = np.zeros(self.NoE, dtype=np.int8)
        self.n_function_selector = theano.shared(value=n_function_selector_array, name="nodefunction_per_gate", borrow=True)

        n_node_porlinked_array = np.zeros(self.NoE, dtype=np.int8)
        self.n_node_porlinked = theano.shared(value=n_node_porlinked_array, name="porlinked", borrow=True)

        n_node_retlinked_array = np.zeros(self.NoE, dtype=np.int8)
        self.n_node_retlinked = theano.shared(value=n_node_retlinked_array, name="retlinked", borrow=True)

        self.__has_new_usages = True
        self.__has_pipes = False
        self.__has_lstms = False
        self.__has_directional_activators = False
        self.__has_sampling_activators = False
        self.__has_gatefunction_absolute = False
        self.__has_gatefunction_sigmoid = False
        self.__has_gatefunction_tanh = False
        self.__has_gatefunction_rect = False
        self.__has_gatefunction_one_over_x = False
        self.por_ret_dirty = True

        self.last_allocated_node = 0
        self.last_allocated_offset = 0
        self.last_allocated_nodespace = 0

        self.compile_propagate()

    def compile_propagate(self):
        if self.sparse:
            self.propagate = theano.function([], None, updates=[(self.a_prev, self.a), (self.a, self.a_in + ST.dot(self.w, self.a)),
                                                                          (self.a_in, T.zeros_like(self.a_in))])
        else:
            self.propagate = theano.function([], None, updates=[(self.a_prev, self.a), (self.a, self.a_in + T.dot(self.w, self.a)),
                                                                          (self.a_in, T.zeros_like(self.a_in))])

    def compile_calculate_nodes(self):
        slots = self.a_shifted
        biases = self.g_theta_shifted
        countdown = self.g_countdown
        por_linked = self.n_node_porlinked
        ret_linked = self.n_node_retlinked

        # node functions implemented with identity by default (native modules are calculated by python)
        nodefunctions = self.a
        a_prev = self.a_prev
        t = self.t

        # pipe logic

        ###############################################################
        # lookup table for source activation in a_shifted
        # when calculating the gate on the y axis...
        # ... find the slot at the given index on the x axis
        #
        #       0   1   2   3   4   5   6   7   8   9   10  11  12  13
        # gen                               gen por ret sub sur cat exp
        # por                           gen por ret sub sur cat exp
        # ret                       gen por ret sub sur cat exp
        # sub                   gen por ret sub sur cat exp
        # sur               gen por ret sub sur cat exp
        # cat           gen por ret sub sur cat exp
        # exp       gen por ret sub sur cat exp
        #

        ### gen plumbing
        pipe_gen_sur_exp = slots[:, 11] + slots[:, 13]                              # sum of sur and exp as default
                                                                                    # drop to 0 if < expectation
        pipe_gen_sur_exp = T.switch(T.lt(pipe_gen_sur_exp, self.g_expect) * T.gt(pipe_gen_sur_exp, 0), 0, pipe_gen_sur_exp)


        pipe_gen = slots[:, 7] * slots[:, 10]                                       # gen * sub
        pipe_gen = T.switch(abs(pipe_gen) > 0.1, pipe_gen, pipe_gen_sur_exp)        # drop to def. if below 0.1
                                                                                    # drop to def. if por == 0 and por slot is linked
        pipe_gen = T.switch(T.eq(slots[:, 8], 0) * T.eq(por_linked, 1), pipe_gen_sur_exp, pipe_gen)

        ### por plumbing
                                                                                    # reset if no sub, or por-linked but 0
        cdrc_por = T.le(slots[:, 9], 0) + (T.eq(por_linked, 1) * T.le(slots[:, 7], 0))
                                                                                    # count down failure countdown
        countdown_por = T.switch(cdrc_por, self.g_wait, T.maximum(countdown - 1, -1))

        pipe_por_cond = T.switch(T.eq(por_linked, 1), T.gt(slots[:, 7], 0), 1)      # (if linked, por must be > 0)
        pipe_por_cond = pipe_por_cond * T.gt(slots[:, 9], 0)                        # and (sub > 0)

        pipe_por = slots[:, 10]                                                     # start with sur
        pipe_por = pipe_por + T.gt(slots[:, 6], 0.1)                                # add gen-loop 1 if por > 0
                                                                                    # check if we're in timeout
        pipe_por = T.switch(T.le(countdown, 0) * T.lt(pipe_por, self.g_expect), -1, pipe_por)
        pipe_por = pipe_por * pipe_por_cond                                         # apply conditions
                                                                                    # add por (for search) if sub=sur=0
        pipe_por = pipe_por + (slots[:, 7] * T.eq(slots[:, 9], 0) * T.eq(slots[:, 10], 0))
                                                                                    # reset failure countdown on confirm
        countdown_por = T.switch(T.ge(pipe_por, self.g_expect), self.g_wait, countdown_por)

        ### ret plumbing
        pipe_ret = T.lt(slots[:, 6], 0)                                             # 1 if por is negative
                                                                                    # add ret (for search) if sub=sur=0
        pipe_ret = pipe_ret + (slots[:, 7] * T.eq(slots[:, 8], 0) * T.eq(slots[:, 9], 0))

        ### sub plumbing
        pipe_sub_cond = T.switch(T.eq(por_linked, 1), T.gt(slots[:, 5], 0), 1)      # (if linked, por must be > 0)
        pipe_sub_cond = pipe_sub_cond * T.eq(slots[:, 4], 0)                        # and (gen == 0)

        pipe_sub = slots[:, 7]                                                      # start with sub
        pipe_sub = pipe_sub + slots[:, 9]                                           # add cat
        pipe_sub = pipe_sub * pipe_sub_cond                                         # apply conditions

        ### sur plumbing
                                                                                    # reset if no sub, or por-linked but 0
        cd_reset_cond = T.le(slots[:, 6],0) + (T.eq(por_linked, 1) * T.le(slots[:, 4], 0))
                                                                                    # count down failure countdown
        countdown_sur = T.switch(cd_reset_cond, self.g_wait, T.maximum(countdown - 1, -1))

        pipe_sur_cond = T.eq(por_linked, 0) + T.gt(slots[:, 4], 0)                  # not por-linked or por > 0
        pipe_sur_cond = T.gt(pipe_sur_cond, 0)

        pipe_sur = slots[:, 7]                                                      # start with sur
        pipe_sur = pipe_sur + T.gt(slots[:, 3], 0.2)                                # add gen-loop 1
        pipe_sur = pipe_sur + (slots[:, 9] * slots[:, 6])                           # add exp * sub
                                                                                    # drop to zero if < expectation
        pipe_sur = T.switch(T.lt(pipe_sur, self.g_expect) * T.gt(pipe_sur, 0), 0, pipe_sur)
                                                                                    # check if we're in timeout
        pipe_sur = T.switch(T.le(countdown, 0) * T.lt(pipe_sur, self.g_expect), -1, pipe_sur)
                                                                                    # reset failure countdown on confirm
        countdown_sur = T.switch(T.ge(pipe_sur, self.g_expect), self.g_wait, countdown_sur)

        pipe_sur = pipe_sur * T.switch(T.eq(ret_linked, 1), slots[:, 5], 1)         # multiply ret if ret-linked
        pipe_sur = pipe_sur * pipe_sur_cond                                         # apply conditions

        ### cat plumbing
        pipe_cat_cond = T.switch(T.eq(por_linked, 1), T.gt(slots[:, 3], 0), 1)      # (if linked, por must be > 0)
        pipe_cat_cond = pipe_cat_cond * T.eq(slots[:, 2], 0)                        # and (gen == 0)

        pipe_cat = T.clip(slots[:, 6], 0, 1)                                        # bubble: start with sur if sur > 0
        pipe_cat = pipe_cat + slots[:, 5]                                           # add sub
        pipe_cat = pipe_cat + slots[:, 7]                                           # add cat
        pipe_cat = pipe_cat * pipe_cat_cond                                         # apply conditions
                                                                                    # add cat (for search) if sub=sur=0
        pipe_cat = pipe_cat + (slots[:, 7] * T.eq(slots[:, 5], 0) * T.eq(slots[:, 6], 0))

        ### exp plumbing
        pipe_exp = slots[:, 5]                                                      # start with sur
        pipe_exp = pipe_exp + slots[:, 7]                                           # add exp
        pipe_exp = pipe_exp + T.gt(slots[:, 1] * slots[:, 4], 0.2)                  # add gen-loop 1

        if self.has_pipes:
            if self.has_directional_activators:
                nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_PIPE_GEN), pipe_gen, nodefunctions)
                nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_PIPE_POR), pipe_por * self.g_factor, nodefunctions)
                nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_PIPE_RET), pipe_ret * self.g_factor, nodefunctions)
                nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_PIPE_SUB), pipe_sub * self.g_factor, nodefunctions)
                nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_PIPE_SUR), pipe_sur * self.g_factor, nodefunctions)
                nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_PIPE_CAT), pipe_cat * self.g_factor, nodefunctions)
                nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_PIPE_EXP), pipe_exp * self.g_factor, nodefunctions)
            else:
                nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_PIPE_GEN), pipe_gen, nodefunctions)
                nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_PIPE_POR), pipe_por, nodefunctions)
                nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_PIPE_RET), pipe_ret, nodefunctions)
                nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_PIPE_SUB), pipe_sub, nodefunctions)
                nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_PIPE_SUR), pipe_sur, nodefunctions)
                nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_PIPE_CAT), pipe_cat, nodefunctions)
                nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_PIPE_EXP), pipe_exp, nodefunctions)
            countdown = T.switch(T.eq(self.n_function_selector, NFPG_PIPE_POR), countdown_por, countdown)
            countdown = T.switch(T.eq(self.n_function_selector, NFPG_PIPE_SUR), countdown_sur, countdown)

        # lstm logic

        ###############################################################
        # lookup table for source activation in a_shifted
        # when calculating the gate on the y axis...
        # ... find the slot at the given index on the x axis
        #
        #       0   1   2   3   4   5   6   7   8   9   10  11  12  13
        # gen                               gen por gin gou gfg
        # por                           gen por gin gou gfg
        # gin                       gen por gin gou gfg
        # gou                   gen por gin gou gfg
        # gfg               gen por gin gou gfg
        #

        sample = T.eq(T.mod(t, 3), 0)
        if self.has_sampling_activators:
            sample = sample * T.gt(self.g_factor, 0.99)

        ### gen
        s = slots[:, 7]
        net_c = slots[:, 8] + biases[:, 8]
        net_in = slots[:, 9] + biases[:, 9]
        net_phi = slots[:, 11] + biases[:, 11]
        y_in = T.nnet.sigmoid(net_in)
        y_phi = T.nnet.sigmoid(net_phi)
        g = (4 * T.nnet.sigmoid(net_c)-2)
        lstm_gen = s * y_phi + g * y_in                                          # gen is next step's s
        lstm_gen = T.switch(sample, lstm_gen, a_prev)

        ### por
        s = slots[:, 6]
        net_c = slots[:, 7] + biases[:, 7]
        net_in = slots[:, 8] + biases[:, 8]
        net_out = slots[:, 9] + biases[:, 9]
        net_phi = slots[:, 10] + biases[:, 10]
        y_in = T.nnet.sigmoid(net_in)
        y_out = T.nnet.sigmoid(net_out)
        y_phi = T.nnet.sigmoid(net_phi)
        g = (4 * T.nnet.sigmoid(net_c)-2)
        s = s * y_phi + g * y_in
        h = (2 * T.nnet.sigmoid(s)-1)                                            # por biases will be ignored
        lstm_por = h * y_out
        lstm_por = T.switch(sample, lstm_por, a_prev)

        ### gin
        lstm_gin = T.nnet.sigmoid(slots[:, 7] + biases[:, 7])
        lstm_gin = T.switch(sample, lstm_gin, a_prev)

        ### gou
        lstm_gou = T.nnet.sigmoid(slots[:, 7] + biases[:, 7])
        lstm_gou = T.switch(sample, lstm_gou, a_prev)

        ### gfg
        lstm_gfg = T.nnet.sigmoid(slots[:, 7] + biases[:, 7])
        lstm_gfg = T.switch(sample, lstm_gfg, a_prev)

        if self.has_lstms:
            nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_LSTM_GEN), lstm_gen, nodefunctions)
            nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_LSTM_POR), lstm_por, nodefunctions)
            nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_LSTM_GIN), lstm_gin, nodefunctions)
            nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_LSTM_GOU), lstm_gou, nodefunctions)
            nodefunctions = T.switch(T.eq(self.n_function_selector, NFPG_LSTM_GFG), lstm_gfg, nodefunctions)

        # gate logic

        # apply actual gate functions
        gate_function_output = nodefunctions

        # apply GATE_FUNCTION_ABS to masked gates
        if self.has_gatefunction_absolute:
            gate_function_output = T.switch(T.eq(self.g_function_selector, GATE_FUNCTION_ABSOLUTE), abs(gate_function_output), gate_function_output)
        # apply GATE_FUNCTION_SIGMOID to masked gates
        if self.has_gatefunction_sigmoid:
            gate_function_output = T.switch(T.eq(self.g_function_selector, GATE_FUNCTION_SIGMOID), N.sigmoid(gate_function_output + self.g_theta), gate_function_output)
        # apply GATE_FUNCTION_TANH to masked gates
        if self.has_gatefunction_tanh:
            gate_function_output = T.switch(T.eq(self.g_function_selector, GATE_FUNCTION_TANH), T.tanh(gate_function_output + self.g_theta), gate_function_output)
        # apply GATE_FUNCTION_RECT to masked gates
        if self.has_gatefunction_rect:
            gate_function_output = T.switch(T.eq(self.g_function_selector, GATE_FUNCTION_RECT), T.switch(gate_function_output + self.g_theta > 0, gate_function_output - self.g_theta, 0), gate_function_output)
        # apply GATE_FUNCTION_DIST to masked gates
        if self.has_gatefunction_one_over_x:
            gate_function_output = T.switch(T.eq(self.g_function_selector, GATE_FUNCTION_DIST), T.switch(T.neq(0, gate_function_output), 1 / gate_function_output, 0), gate_function_output)

        # apply threshold
        thresholded_gate_function_output = \
            T.switch(T.ge(gate_function_output, self.g_threshold), gate_function_output, 0)

        # apply amplification
        amplified_gate_function_output = thresholded_gate_function_output * self.g_amplification

        # apply minimum and maximum
        limited_gate_function_output = T.clip(amplified_gate_function_output, self.g_min, self.g_max)

        gatefunctions = limited_gate_function_output

        # put the theano graph into a callable function to be executed
        if self.has_pipes:
            self.calculate_nodes = theano.function([], None, updates=[(self.a, gatefunctions), (self.g_countdown, countdown)])
        else:
            self.calculate_nodes = theano.function([], None, updates=[(self.a, gatefunctions)])

    def get_compiled_propagate_inlinks(self, from_partition, from_elements, to_elements, weights):
        propagated_a = T.dot(weights, from_partition.a[from_elements])
        a_in = T.inc_subtensor(self.a_in[to_elements], propagated_a, inplace=True, tolerate_inplace_aliasing=True)
        return theano.function([], None, updates=[(self.a_in, a_in)], accept_inplace=True)

    def calculate(self):

        self.t.set_value(np.int32(self.nodenet.current_step))

        if self.has_new_usages:
            self.compile_propagate()
            self.compile_calculate_nodes()
            self.has_new_usages = False

        if self.por_ret_dirty:
            self.rebuild_por_linked()
            self.rebuild_ret_linked()
            self.por_ret_dirty = False

        self.__take_native_module_slot_snapshots()
        if self.has_pipes or self.has_lstms:
            self.__rebuild_shifted()
        if self.has_directional_activators or self.__has_sampling_activators:
            self.__calculate_g_factors()
        self.calculate_nodes()
        self.__calculate_native_modules()

    def __take_native_module_slot_snapshots(self):
        for uid, instance in self.native_module_instances.items():
            instance.take_slot_activation_snapshot()

    def __calculate_native_modules(self):
        for uid, instance in self.native_module_instances.items():
            instance.node_function()

    def __calculate_g_factors(self):
        a = self.a.get_value(borrow=True)
        a[0] = 1.
        g_factor = a[self.allocated_elements_to_activators]
        self.g_factor.set_value(g_factor, borrow=True)

    def __rebuild_shifted(self):
        a_array = self.a.get_value(borrow=True)
        a_rolled_array = np.roll(a_array, 7)
        a_shifted_matrix = np.lib.stride_tricks.as_strided(a_rolled_array, shape=(self.NoE, 14), strides=(self.nodenet.byte_per_float, self.nodenet.byte_per_float))
        self.a_shifted.set_value(a_shifted_matrix, borrow=True)

        g_theta_array = self.g_theta.get_value(borrow=True)
        g_theta_rolled_array = np.roll(g_theta_array, 7)
        g_theta_shifted_matrix = np.lib.stride_tricks.as_strided(g_theta_rolled_array, shape=(self.NoE, 14), strides=(self.nodenet.byte_per_float, self.nodenet.byte_per_float))
        self.g_theta_shifted.set_value(g_theta_shifted_matrix, borrow=True)

    def rebuild_por_linked(self):

        n_node_porlinked_array = np.zeros(self.NoE, dtype=np.int8)

        n_function_selector_array = self.n_function_selector.get_value(borrow=True)
        w_matrix = self.w.get_value(borrow=True)

        por_indices = np.where(n_function_selector_array == NFPG_PIPE_POR)[0]

        slotrows = w_matrix[por_indices, :]
        if not self.sparse:
            linkedflags = np.any(slotrows, axis=1)
        else:
            linkedflags = np.zeros_like(por_indices)
            linkedflags[np.nonzero(slotrows)[0]] = 1

        n_node_porlinked_array[por_indices - 1] = linkedflags       # gen
        n_node_porlinked_array[por_indices] = linkedflags           # por
        n_node_porlinked_array[por_indices + 1] = linkedflags       # ret
        n_node_porlinked_array[por_indices + 2] = linkedflags       # sub
        n_node_porlinked_array[por_indices + 3] = linkedflags       # sur
        n_node_porlinked_array[por_indices + 4] = linkedflags       # sub
        n_node_porlinked_array[por_indices + 5] = linkedflags       # sur

        self.n_node_porlinked.set_value(n_node_porlinked_array)

    def rebuild_ret_linked(self):

        n_node_retlinked_array = np.zeros(self.NoE, dtype=np.int8)

        n_function_selector_array = self.n_function_selector.get_value(borrow=True)
        w_matrix = self.w.get_value(borrow=True)

        ret_indices = np.where(n_function_selector_array == NFPG_PIPE_RET)[0]

        slotrows = w_matrix[ret_indices, :]
        if not self.sparse:
            linkedflags = np.any(slotrows, axis=1)
        else:
            linkedflags = np.zeros_like(ret_indices)
            linkedflags[np.nonzero(slotrows)[0]] = 1

        n_node_retlinked_array[ret_indices - 2] = linkedflags       # gen
        n_node_retlinked_array[ret_indices - 1] = linkedflags       # por
        n_node_retlinked_array[ret_indices] = linkedflags           # ret
        n_node_retlinked_array[ret_indices + 1] = linkedflags       # sub
        n_node_retlinked_array[ret_indices + 2] = linkedflags       # sur
        n_node_retlinked_array[ret_indices + 3] = linkedflags       # cat
        n_node_retlinked_array[ret_indices + 4] = linkedflags       # exp

        self.n_node_retlinked.set_value(n_node_retlinked_array)

    def grow_number_of_nodes(self, growby):
        new_NoN = int(self.NoN + growby)

        new_allocated_nodes = np.zeros(new_NoN, dtype=np.int32)
        new_allocated_nodes[0:self.NoN] = self.allocated_nodes
        self.allocated_nodes = new_allocated_nodes

        new_allocated_node_parents = np.zeros(new_NoN, dtype=np.int32)
        new_allocated_node_parents[0:self.NoN] = self.allocated_node_parents
        self.allocated_node_parents = new_allocated_node_parents

        new_allocated_node_offsets = np.zeros(new_NoN, dtype=np.int32)
        new_allocated_node_offsets[0:self.NoN] = self.allocated_node_offsets
        self.allocated_node_offsets = new_allocated_node_offsets

        new_node_changed_offsets = np.zeros(new_NoN, dtype=np.int32)
        new_node_changed_offsets[0:self.NoN] = self.nodes_last_changed
        self.nodes_last_changed = new_node_changed_offsets

        self.NoN = new_NoN
        self.has_new_usages = True

    def save(self, datafilename):

        allocated_nodes = self.allocated_nodes
        allocated_node_offsets = self.allocated_node_offsets
        allocated_elements_to_nodes = self.allocated_elements_to_nodes
        allocated_node_parents = self.allocated_node_parents
        allocated_nodespaces = self.allocated_nodespaces
        allocated_elements_to_activators = self.allocated_elements_to_activators

        allocated_nodespaces_por_activators = self.allocated_nodespaces_por_activators
        allocated_nodespaces_ret_activators = self.allocated_nodespaces_ret_activators
        allocated_nodespaces_sub_activators = self.allocated_nodespaces_sub_activators
        allocated_nodespaces_sur_activators = self.allocated_nodespaces_sur_activators
        allocated_nodespaces_cat_activators = self.allocated_nodespaces_cat_activators
        allocated_nodespaces_exp_activators = self.allocated_nodespaces_exp_activators

        allocated_nodespaces_sampling_activators = self.allocated_nodespaces_sampling_activators

        w = self.w.get_value(borrow=True)

        # if we're sparse, convert to sparse matrix for persistency
        if not self.sparse:
            w = sp.csr_matrix(w)

        a = self.a.get_value(borrow=True)
        g_theta = self.g_theta.get_value(borrow=True)
        g_factor = self.g_factor.get_value(borrow=True)
        g_threshold = self.g_threshold.get_value(borrow=True)
        g_amplification = self.g_amplification.get_value(borrow=True)
        g_min = self.g_min.get_value(borrow=True)
        g_max = self.g_max.get_value(borrow=True)
        g_function_selector = self.g_function_selector.get_value(borrow=True)
        g_expect = self.g_expect.get_value(borrow=True)
        g_countdown = self.g_countdown.get_value(borrow=True)
        g_wait = self.g_wait.get_value(borrow=True)
        n_function_selector = self.n_function_selector.get_value(borrow=True)

        sizeinformation = [self.NoN, self.NoE, self.NoNS]

        inlink_from_element_count = 0
        inlink_to_element_count = 0
        weight_count = 0
        for spid, inlinks in self.inlinks.items():
            inlink_from_element_count += len(inlinks[0].get_value(borrow=True))
            inlink_to_element_count += len(inlinks[1].get_value(borrow=True))
            weight_count += len(inlinks[0].get_value(borrow=True)) * len(inlinks[1].get_value(borrow=True))
        inlinks_pids = np.zeros(len(self.inlinks), dtype=np.int16)
        inlink_from_lengths = np.zeros(len(self.inlinks), dtype=np.int32)
        inlink_to_lengths = np.zeros(len(self.inlinks), dtype=np.int32)
        inlink_from_elements = np.zeros(inlink_from_element_count, dtype=np.int32)
        inlink_to_elements = np.zeros(inlink_to_element_count, dtype=np.int32)
        inlink_weights = np.zeros(weight_count, dtype=self.nodenet.numpyfloatX)

        from_offset = 0
        to_offset = 0
        weight_offset = 0
        for i, spid in enumerate(self.inlinks.keys()):
            inlinks_pids[i] = int(spid)
            from_elements = self.inlinks[spid][0].get_value(borrow=True)
            to_elements = self.inlinks[spid][1].get_value(borrow=True)
            weights = self.inlinks[spid][2].get_value(borrow=True)
            from_length = len(from_elements)
            to_length = len(to_elements)
            inlink_from_lengths[i] = from_length
            inlink_to_lengths[i] = to_length
            inlink_from_elements[from_offset:from_offset+from_length] = from_elements
            inlink_to_elements[to_offset:to_offset+to_length] = to_elements
            inlink_weights[weight_offset:weight_offset+(from_length*to_length)] = np.ravel(weights)
            weight_offset += from_length * to_length
            from_offset += from_length
            to_offset += to_length

        np.savez(datafilename,
                 allocated_nodes=allocated_nodes,
                 allocated_node_offsets=allocated_node_offsets,
                 allocated_elements_to_nodes=allocated_elements_to_nodes,
                 allocated_node_parents=allocated_node_parents,
                 allocated_nodespaces=allocated_nodespaces,
                 w_data=w.data,
                 w_indices=w.indices,
                 w_indptr=w.indptr,
                 a=a,
                 g_theta=g_theta,
                 g_factor=g_factor,
                 g_threshold=g_threshold,
                 g_amplification=g_amplification,
                 g_min=g_min,
                 g_max=g_max,
                 g_function_selector=g_function_selector,
                 g_expect=g_expect,
                 g_countdown=g_countdown,
                 g_wait=g_wait,
                 n_function_selector=n_function_selector,
                 sizeinformation=sizeinformation,
                 allocated_elements_to_activators=allocated_elements_to_activators,
                 allocated_nodespaces_por_activators=allocated_nodespaces_por_activators,
                 allocated_nodespaces_ret_activators=allocated_nodespaces_ret_activators,
                 allocated_nodespaces_sub_activators=allocated_nodespaces_sub_activators,
                 allocated_nodespaces_sur_activators=allocated_nodespaces_sur_activators,
                 allocated_nodespaces_cat_activators=allocated_nodespaces_cat_activators,
                 allocated_nodespaces_exp_activators=allocated_nodespaces_exp_activators,
                 allocated_nodespaces_sampling_activators=allocated_nodespaces_sampling_activators,
                 inlink_pids=inlinks_pids,
                 inlink_from_lengths=inlink_from_lengths,
                 inlink_to_lengths=inlink_to_lengths,
                 inlink_from_elements=inlink_from_elements,
                 inlink_to_elements=inlink_to_elements,
                 inlink_weights=inlink_weights)

    def load_data(self, datafilename, nodes_data):
        """Load the node net from a file"""
        # try to access file

        datafile = None
        if os.path.isfile(datafilename):
            try:
                self.logger.info("Loading nodenet %s partition %i bulk data from file %s" % (self.nodenet.name, self.pid, datafilename))
                datafile = np.load(datafilename)
            except ValueError:  # pragma: no cover
                self.logger.warn("Could not read nodenet data from file %s" % datafile)
                return False
            except IOError:  # pragma: no cover
                self.logger.warn("Could not open nodenet file %s" % datafile)
                return False

        if not datafile:
            return

        if 'sizeinformation' in datafile:
            self.NoN = datafile['sizeinformation'][0]
            self.NoE = datafile['sizeinformation'][1]
            self.NoNS = datafile['sizeinformation'][2]

            # rebuild the ephemerals
            self.nodes_last_changed = np.zeros(self.NoN, dtype=np.int32) - 1
            self.nodespaces_last_changed = np.zeros(self.NoNS, dtype=np.int32) - 1
            self.nodespaces_contents_last_changed = np.zeros(self.NoNS, dtype=np.int32) - 1

            a_prev_array = np.zeros(self.NoE, dtype=self.nodenet.numpyfloatX)
            self.a_prev = theano.shared(value=a_prev_array.astype(T.config.floatX), name="a_prev", borrow=True)

        else:
            self.logger.warn("no sizeinformation in file, falling back to defaults")  # pragma: no cover

        # the load bulk data into numpy arrays
        if 'allocated_nodes' in datafile:
            self.allocated_nodes = datafile['allocated_nodes']
        else:
            self.logger.warn("no allocated_nodes in file, falling back to defaults")  # pragma: no cover

        if 'allocated_node_offsets' in datafile:
            self.allocated_node_offsets = datafile['allocated_node_offsets']
        else:
            self.logger.warn("no allocated_node_offsets in file, falling back to defaults")  # pragma: no cover

        if 'allocated_elements_to_nodes' in datafile:
            self.allocated_elements_to_nodes = datafile['allocated_elements_to_nodes']
        else:
            self.logger.warn("no allocated_elements_to_nodes in file, falling back to defaults")  # pragma: no cover

        if 'allocated_nodespaces' in datafile:
            self.allocated_nodespaces = datafile['allocated_nodespaces']
        else:
            self.logger.warn("no allocated_nodespaces in file, falling back to defaults")  # pragma: no cover

        if 'allocated_node_parents' in datafile:
            self.allocated_node_parents = datafile['allocated_node_parents']
        else:
            self.logger.warn("no allocated_node_parents in file, falling back to defaults")  # pragma: no cover

        if 'allocated_elements_to_activators' in datafile:
            self.allocated_elements_to_activators = datafile['allocated_elements_to_activators']
        else:
            self.logger.warn("no allocated_elements_to_activators in file, falling back to defaults")  # pragma: no cover

        if 'allocated_nodespaces_por_activators' in datafile:
            self.allocated_nodespaces_por_activators = datafile['allocated_nodespaces_por_activators']
        else:
            self.logger.warn("no allocated_nodespaces_por_activators in file, falling back to defaults")  # pragma: no cover

        if 'allocated_nodespaces_ret_activators' in datafile:
            self.allocated_nodespaces_ret_activators = datafile['allocated_nodespaces_ret_activators']
        else:
            self.logger.warn("no allocated_nodespaces_ret_activators in file, falling back to defaults")  # pragma: no cover

        if 'allocated_nodespaces_sub_activators' in datafile:
            self.allocated_nodespaces_sub_activators = datafile['allocated_nodespaces_sub_activators']
        else:
            self.logger.warn("no allocated_nodespaces_sub_activators in file, falling back to defaults")  # pragma: no cover

        if 'allocated_nodespaces_sur_activators' in datafile:
            self.allocated_nodespaces_sur_activators = datafile['allocated_nodespaces_sur_activators']
        else:
            self.logger.warn("no allocated_nodespaces_sur_activators in file, falling back to defaults")  # pragma: no cover

        if 'allocated_nodespaces_cat_activators' in datafile:
            self.allocated_nodespaces_cat_activators = datafile['allocated_nodespaces_cat_activators']
        else:
            self.logger.warn("no allocated_nodespaces_cat_activators in file, falling back to defaults")  # pragma: no cover

        if 'allocated_nodespaces_exp_activators' in datafile:
            self.allocated_nodespaces_exp_activators = datafile['allocated_nodespaces_exp_activators']
        else:
            self.logger.warn("no allocated_nodespaces_exp_activators in file, falling back to defaults")  # pragma: no cover

        if 'allocated_nodespaces_sampling_activators' in datafile:
            self.allocated_nodespaces_sampling_activators = datafile['allocated_nodespaces_sampling_activators']
        else:
            self.logger.warn("no allocated_nodespaces_por_activators in file, falling back to defaults")  # pragma: no cover

        if 'w_data' in datafile and 'w_indices' in datafile and 'w_indptr' in datafile:
            w = sp.csr_matrix((datafile['w_data'], datafile['w_indices'], datafile['w_indptr']), shape = (self.NoE, self.NoE))
            # if we're configured to be dense, convert from csr
            if not self.sparse:
                w = w.todense()
            self.w = theano.shared(value=w.astype(T.config.floatX), name="w", borrow=False)
            self.a = theano.shared(value=datafile['a'].astype(T.config.floatX), name="a", borrow=False)
            self.a_in = theano.shared(value=np.zeros_like(datafile['a']).astype(T.config.floatX), name="a_in", borrow=False)
        else:
            self.logger.warn("no w_data, w_indices or w_indptr in file, falling back to defaults")  # pragma: no cover

        if 'g_theta' in datafile:
            self.g_theta = theano.shared(value=datafile['g_theta'].astype(T.config.floatX), name="theta", borrow=False)
        else:
            self.logger.warn("no g_theta in file, falling back to defaults")  # pragma: no cover

        if 'g_factor' in datafile:
            self.g_factor = theano.shared(value=datafile['g_factor'].astype(T.config.floatX), name="g_factor", borrow=False)
        else:
            self.logger.warn("no g_factor in file, falling back to defaults")  # pragma: no cover

        if 'g_threshold' in datafile:
            self.g_threshold = theano.shared(value=datafile['g_threshold'].astype(T.config.floatX), name="g_threshold", borrow=False)
        else:
            self.logger.warn("no g_threshold in file, falling back to defaults")  # pragma: no cover

        if 'g_amplification' in datafile:
            self.g_amplification = theano.shared(value=datafile['g_amplification'].astype(T.config.floatX), name="g_amplification", borrow=False)
        else:
            self.logger.warn("no g_amplification in file, falling back to defaults")  # pragma: no cover

        if 'g_min' in datafile:
            self.g_min = theano.shared(value=datafile['g_min'].astype(T.config.floatX), name="g_min", borrow=False)
        else:
            self.logger.warn("no g_min in file, falling back to defaults")  # pragma: no cover

        if 'g_max' in datafile:
            self.g_max = theano.shared(value=datafile['g_max'].astype(T.config.floatX), name="g_max", borrow=False)
        else:
            self.logger.warn("no g_max in file, falling back to defaults")  # pragma: no cover

        if 'g_function_selector' in datafile:
            self.g_function_selector = theano.shared(value=datafile['g_function_selector'], name="gatefunction", borrow=False)
        else:
            self.logger.warn("no g_function_selector in file, falling back to defaults")  # pragma: no cover

        if 'g_expect' in datafile:
            self.g_expect = theano.shared(value=datafile['g_expect'], name="expectation", borrow=False)
        else:
            self.logger.warn("no g_expect in file, falling back to defaults")  # pragma: no cover

        if 'g_countdown' in datafile:
            self.g_countdown = theano.shared(value=datafile['g_countdown'], name="countdown", borrow=False)
        else:
            self.logger.warn("no g_countdown in file, falling back to defaults")  # pragma: no cover

        if 'g_wait' in datafile:
            self.g_wait = theano.shared(value=datafile['g_wait'], name="wait", borrow=False)
        else:
            self.logger.warn("no g_wait in file, falling back to defaults")  # pragma: no cover

        if 'n_function_selector' in datafile:
            self.n_function_selector = theano.shared(value=datafile['n_function_selector'], name="nodefunction_per_gate", borrow=False)
        else:
            self.logger.warn("no n_function_selector in file, falling back to defaults")  # pragma: no cover

        # reconstruct other states
        self.por_ret_dirty = True

        if 'g_function_selector' in datafile:
            g_function_selector = datafile['g_function_selector']
            self.has_new_usages = True
            self.has_pipes = PIPE in self.allocated_nodes
            self.has_lstms = LSTM in self.allocated_nodes
            self.has_directional_activators = \
                np.sum(self.allocated_nodespaces_por_activators) > 0 or \
                np.sum(self.allocated_nodespaces_ret_activators) > 0 or \
                np.sum(self.allocated_nodespaces_sub_activators) > 0 or \
                np.sum(self.allocated_nodespaces_sur_activators) > 0 or \
                np.sum(self.allocated_nodespaces_cat_activators) > 0 or \
                np.sum(self.allocated_nodespaces_exp_activators) > 0

            self.has_sampling_activators = np.sum(self.allocated_nodespaces_sampling_activators) > 0
            self.has_gatefunction_absolute = GATE_FUNCTION_ABSOLUTE in g_function_selector
            self.has_gatefunction_sigmoid = GATE_FUNCTION_SIGMOID in g_function_selector
            self.has_gatefunction_tanh = GATE_FUNCTION_TANH in g_function_selector
            self.has_gatefunction_rect = GATE_FUNCTION_RECT in g_function_selector
            self.has_gatefunction_one_over_x = GATE_FUNCTION_DIST in g_function_selector
        else:
            self.logger.warn("no g_function_selector in file, falling back to defaults")

        for id in np.nonzero(self.allocated_nodes)[0]:
            if self.allocated_nodes[id] > MAX_STD_NODETYPE:
                uid = node_to_id(id, self.pid)
                if uid in nodes_data:
                    self.allocated_nodes[id] = get_numerical_node_type(nodes_data[uid]['type'], self.nodenet.native_modules)
            if self.allocated_nodes[id] > MAX_STD_NODETYPE:
                self.native_module_instances[uid] = self.nodenet.get_node(uid)
            elif self.allocated_nodes[id] == COMMENT:
                uid = node_to_id(id, self.pid)
                self.comment_instances[uid] = self.nodenet.get_node(uid)

        # initialize early
        self.t.set_value(np.int32(self.nodenet.current_step))

        if self.has_new_usages:
            self.compile_propagate()
            self.compile_calculate_nodes()
            self.has_new_usages = False

        if self.por_ret_dirty:
            self.rebuild_por_linked()
            self.rebuild_ret_linked()
            self.por_ret_dirty = False

        self.__take_native_module_slot_snapshots()
        if self.has_pipes or self.has_lstms:
            self.__rebuild_shifted()
        if self.has_directional_activators or self.__has_sampling_activators:
            self.__calculate_g_factors()

    def load_inlinks(self, datafilename):
        datafile = None
        if os.path.isfile(datafilename):
            try:
                datafile = np.load(datafilename)
            except ValueError:  # pragma: no cover
                self.logger.warn("Could not read nodenet data from file %s" % datafile)
                return False
            except IOError:  # pragma: no cover
                self.logger.warn("Could not open nodenet file %s" % datafile)
                return False

        if not datafile:
            return

        if 'inlink_pids' in datafile and \
            'inlink_from_lengths' in datafile and \
            'inlink_to_lengths' in datafile and \
            'inlink_from_elements' in datafile and \
            'inlink_to_elements' in datafile and \
            'inlink_weights' in datafile:

            inlink_pids = datafile['inlink_pids']
            inlink_from_lengths = datafile['inlink_from_lengths']
            inlink_to_lengths = datafile['inlink_to_lengths']

            inlink_from_offset = 0
            inlink_to_offset = 0
            weight_offset = 0

            for i, pid in enumerate(inlink_pids):

                inlink_from_elements = datafile['inlink_from_elements'][inlink_from_offset:inlink_from_offset+inlink_from_lengths[i]]
                inlink_to_elements = datafile['inlink_to_elements'][inlink_to_offset:inlink_to_offset+inlink_to_lengths[i]]
                inlink_weights = datafile['inlink_weights'][weight_offset:weight_offset+(inlink_from_lengths[i]*inlink_to_lengths[i])]

                self.set_inlink_weights(
                    "%03i" % pid,
                    inlink_from_elements.astype(np.int32),
                    inlink_to_elements.astype(np.int32),
                    np.reshape(inlink_weights, (inlink_to_lengths[i], inlink_from_lengths[i]))
                )

                weight_offset += inlink_from_lengths[i]*inlink_to_lengths[i]
                inlink_from_offset += inlink_from_lengths[i]
                inlink_to_offset += inlink_to_lengths[i]
        else:
            self.logger.warn("no or incomplete inlink information in file, no inter-partition links will be loaded")  # pragma: no cover

    def grow_number_of_nodespaces(self, growby):

        new_NoNS = int(self.NoNS + growby)

        new_allocated_nodespaces = np.zeros(new_NoNS, dtype=np.int32)
        new_allocated_nodespaces[0:self.NoNS] = self.allocated_nodespaces
        self.allocated_nodespaces = new_allocated_nodespaces

        new_allocated_nodespaces_por_activators = np.zeros(new_NoNS, dtype=np.int32)
        new_allocated_nodespaces_por_activators[0:self.NoNS] = self.allocated_nodespaces_por_activators
        self.allocated_nodespaces_por_activators = new_allocated_nodespaces_por_activators

        new_allocated_nodespaces_ret_activators = np.zeros(new_NoNS, dtype=np.int32)
        new_allocated_nodespaces_ret_activators[0:self.NoNS] = self.allocated_nodespaces_ret_activators
        self.allocated_nodespaces_ret_activators = new_allocated_nodespaces_ret_activators

        new_allocated_nodespaces_sub_activators = np.zeros(new_NoNS, dtype=np.int32)
        new_allocated_nodespaces_sub_activators[0:self.NoNS] = self.allocated_nodespaces_sub_activators
        self.allocated_nodespaces_sub_activators = new_allocated_nodespaces_sub_activators

        new_allocated_nodespaces_sur_activators = np.zeros(new_NoNS, dtype=np.int32)
        new_allocated_nodespaces_sur_activators[0:self.NoNS] = self.allocated_nodespaces_sur_activators
        self.allocated_nodespaces_sur_activators = new_allocated_nodespaces_sur_activators

        new_allocated_nodespaces_cat_activators = np.zeros(new_NoNS, dtype=np.int32)
        new_allocated_nodespaces_cat_activators[0:self.NoNS] = self.allocated_nodespaces_cat_activators
        self.allocated_nodespaces_cat_activators = new_allocated_nodespaces_cat_activators

        new_allocated_nodespaces_exp_activators = np.zeros(new_NoNS, dtype=np.int32)
        new_allocated_nodespaces_exp_activators[0:self.NoNS] = self.allocated_nodespaces_exp_activators
        self.allocated_nodespaces_exp_activators = new_allocated_nodespaces_exp_activators

        new_allocated_nodespaces_sampling_activators = np.zeros(new_NoNS, dtype=np.int32)
        new_allocated_nodespaces_sampling_activators[0:self.NoNS] = self.allocated_nodespaces_sampling_activators
        self.allocated_nodespaces_sampling_activators = new_allocated_nodespaces_sampling_activators

        new_nodespaces_last_changed = np.zeros(new_NoNS, dtype=np.int32)
        new_nodespaces_last_changed[0:self.NoNS] = self.nodespaces_last_changed
        self.nodespaces_last_changed = new_nodespaces_last_changed

        new_nodespaces_contents_last_changed = np.zeros(new_NoNS, dtype=np.int32)
        new_nodespaces_contents_last_changed[0:self.NoNS] = self.nodespaces_contents_last_changed
        self.nodespaces_contents_last_changed = new_nodespaces_contents_last_changed

        self.has_new_usages = True
        self.NoNS = new_NoNS

    def grow_number_of_elements(self, growby):

        new_NoE = int(self.NoE + growby)

        new_allocated_elements_to_nodes = np.zeros(new_NoE, dtype=np.int32)
        new_allocated_elements_to_nodes[0:self.NoE] = self.allocated_elements_to_nodes
        self.allocated_elements_to_nodes = new_allocated_elements_to_nodes

        new_allocated_elements_to_activators = np.zeros(new_NoE, dtype=np.int32)
        new_allocated_elements_to_activators[0:self.NoE] = self.allocated_elements_to_activators
        self.allocated_elements_to_activators = new_allocated_elements_to_activators

        if self.sparse:
            new_w = sp.csr_matrix((new_NoE, new_NoE), dtype=self.nodenet.scipyfloatX)
        else:
            new_w = np.zeros((new_NoE, new_NoE), dtype=self.nodenet.scipyfloatX)
        new_w[0:self.NoE, 0:self.NoE] = self.w.get_value(borrow=True)
        self.w.set_value(new_w, borrow=True)

        new_a = np.zeros(new_NoE, dtype=self.nodenet.numpyfloatX)
        new_a[0:self.NoE] = self.a.get_value(borrow=True)
        self.a.set_value(new_a, borrow=True)

        new_a_shifted = np.lib.stride_tricks.as_strided(new_a, shape=(new_NoE, 7), strides=(self.nodenet.byte_per_float, self.nodenet.byte_per_float))
        self.a_shifted.set_value(new_a_shifted, borrow=True)

        new_a_in = np.zeros(new_NoE, dtype=self.nodenet.numpyfloatX)
        new_a_in[0:self.NoE] = self.a_in.get_value(borrow=True)
        self.a_in.set_value(new_a_in, borrow=True)

        new_a_prev = np.zeros(new_NoE, dtype=self.nodenet.numpyfloatX)
        new_a_prev[0:self.NoE] = self.a_prev.get_value(borrow=True)
        self.a_prev.set_value(new_a_prev, borrow=True)

        new_g_theta = np.zeros(new_NoE, dtype=self.nodenet.numpyfloatX)
        new_g_theta[0:self.NoE] = self.g_theta.get_value(borrow=True)
        self.g_theta.set_value(new_g_theta, borrow=True)

        new_g_theta_shifted = np.lib.stride_tricks.as_strided(new_g_theta, shape=(self.NoE, 7), strides=(self.nodenet.byte_per_float, self.nodenet.byte_per_float))
        self.g_theta_shifted.set_value(new_g_theta_shifted, borrow=True)

        new_g_factor = np.ones(new_NoE, dtype=self.nodenet.numpyfloatX)
        new_g_factor[0:self.NoE] = self.g_factor.get_value(borrow=True)
        self.g_factor.set_value(new_g_factor, borrow=True)

        new_g_threshold = np.zeros(new_NoE, dtype=self.nodenet.numpyfloatX)
        new_g_threshold[0:self.NoE] = self.g_threshold.get_value(borrow=True)
        self.g_threshold.set_value(new_g_threshold, borrow=True)

        new_g_amplification = np.ones(new_NoE, dtype=self.nodenet.numpyfloatX)
        new_g_amplification[0:self.NoE] = self.g_amplification.get_value(borrow=True)
        self.g_amplification.set_value(new_g_amplification, borrow=True)

        new_g_min = np.zeros(new_NoE, dtype=self.nodenet.numpyfloatX)
        new_g_min[0:self.NoE] = self.g_min.get_value(borrow=True)
        self.g_min.set_value(new_g_min, borrow=True)

        new_g_max = np.ones(new_NoE, dtype=self.nodenet.numpyfloatX)
        new_g_max[0:self.NoE] =  self.g_max.get_value(borrow=True)
        self.g_max.set_value(new_g_max, borrow=True)

        new_g_function_selector = np.zeros(new_NoE, dtype=np.int8)
        new_g_function_selector[0:self.NoE] = self.g_function_selector.get_value(borrow=True)
        self.g_function_selector.set_value(new_g_function_selector, borrow=True)

        new_g_expect = np.ones(new_NoE, dtype=self.nodenet.numpyfloatX)
        new_g_expect[0:self.NoE] = self.g_expect.get_value(borrow=True)
        self.g_expect.set_value(new_g_expect, borrow=True)

        new_g_countdown = np.zeros(new_NoE, dtype=np.int16)
        new_g_countdown[0:self.NoE] = self.g_countdown.get_value(borrow=True)
        self.g_countdown.set_value(new_g_countdown, borrow=True)

        new_g_wait = np.ones(new_NoE, dtype=np.int16)
        new_g_wait[0:self.NoE] = self.g_wait.get_value(borrow=True)
        self.g_wait.set_value(new_g_wait, borrow=True)

        new_n_function_selector = np.zeros(new_NoE, dtype=np.int8)
        new_n_function_selector[0:self.NoE] = self.n_function_selector.get_value(borrow=True)
        self.n_function_selector.set_value(new_n_function_selector, borrow=True)

        new_n_node_porlinked = np.zeros(new_NoE, dtype=np.int8)
        self.n_node_porlinked.set_value(new_n_node_porlinked, borrow=True)

        new_n_node_retlinked = np.zeros(new_NoE, dtype=np.int8)
        self.n_node_retlinked.set_value(new_n_node_retlinked, borrow=True)

        self.NoE = new_NoE
        self.has_new_usages = True

        if self.has_pipes:
            self.por_ret_dirty = True

    def announce_nodes(self, number_of_nodes, average_elements_per_node):

        free_nodes = self.NoN - np.count_nonzero(self.allocated_nodes)
        free_elements = self.NoE - np.count_nonzero(self.allocated_elements_to_nodes)

        if number_of_nodes > free_nodes:
            gap = number_of_nodes - free_nodes
            growby = gap + (gap // 3)
            self.logger.info("Per announcement in partition %i, growing ID vectors by %d elements" % (self.pid, growby))
            self.grow_number_of_nodes(growby)

        number_of_elements = number_of_nodes*average_elements_per_node
        if number_of_elements > free_elements:
            gap = number_of_elements - free_elements
            growby = gap + (gap // 3)
            self.logger.info("Per announcement in partition %i, growing elements vectors by %d elements" % (self.pid, growby))
            self.grow_number_of_elements(gap + (gap //3))

    def create_node(self, nodetype, nodespace_id, id=None, parameters=None, gate_parameters=None, gate_functions=None):

        # find a free ID / index in the allocated_nodes vector to hold the node type
        if id is None:
            id = 0
            for i in range((self.last_allocated_node + 1), self.NoN):
                if self.allocated_nodes[i] == 0:
                    id = i
                    break

            if id < 1:
                for i in range(self.last_allocated_node - 1):
                    if self.allocated_nodes[i] == 0:
                        id = i
                        break

            if id < 1:
                growby = self.NoN // 2
                self.logger.info("All %d node IDs in partition %i in use, growing id vectors by %d elements" % (self.NoN, self.pid, growby))
                id = self.NoN
                self.grow_number_of_nodes(growby)

        else:
            if id > self.NoN:
                growby = id - (self.NoN - 2)
                self.logger.info("Requested ID larger than current size in partition %i, growing id vectors by %d elements" % (self.pid, growby))
                self.grow_number_of_nodes(growby)

        # now find a range of free elements to be used by this node
        number_of_elements = get_elements_per_type(get_numerical_node_type(nodetype, self.nodenet.native_modules), self.nodenet.native_modules)
        has_restarted_from_zero = False
        offset = 0
        i = self.last_allocated_offset + 1
        while offset < 1:
            freecount = 0
            for j in range(0, number_of_elements):
                if i+j < len(self.allocated_elements_to_nodes) and self.allocated_elements_to_nodes[i+j] == 0:
                    freecount += 1
                else:
                    break
            if freecount >= number_of_elements:
                offset = i
                break
            else:
                i += freecount+1

            if i >= self.NoE:
                if not has_restarted_from_zero:
                    i = 0
                    has_restarted_from_zero = True
                else:
                    growby = max(number_of_elements +1, self.NoE // 2)
                    self.logger.info("All %d elements in use in partition %i, growing elements vectors by %d elements" % (self.NoE, self.pid, growby))
                    offset = self.NoE
                    self.grow_number_of_elements(growby)

        uid = node_to_id(id, self.pid)

        self.last_allocated_node = id
        self.last_allocated_offset = offset
        self.allocated_nodes[id] = get_numerical_node_type(nodetype, self.nodenet.native_modules)
        self.nodes_last_changed[id] = self.nodenet.current_step
        self.allocated_node_parents[id] = nodespace_id
        self.allocated_node_offsets[id] = offset
        if nodespace_id < len(self.nodespaces_contents_last_changed):
            # due to the order of initializing, nodespaces might just not be here yet.
            self.nodespaces_contents_last_changed[nodespace_id] = self.nodenet.current_step

        for element in range (0, get_elements_per_type(self.allocated_nodes[id], self.nodenet.native_modules)):
            self.allocated_elements_to_nodes[offset + element] = id

        if parameters is None:
            parameters = {}

        nto = self.nodenet.get_nodetype(nodetype)

        if nodetype == "Pipe":
            self.has_pipes = True
            n_function_selector_array = self.n_function_selector.get_value(borrow=True)
            n_function_selector_array[offset + GEN] = NFPG_PIPE_GEN
            n_function_selector_array[offset + POR] = NFPG_PIPE_POR
            n_function_selector_array[offset + RET] = NFPG_PIPE_RET
            n_function_selector_array[offset + SUB] = NFPG_PIPE_SUB
            n_function_selector_array[offset + SUR] = NFPG_PIPE_SUR
            n_function_selector_array[offset + CAT] = NFPG_PIPE_CAT
            n_function_selector_array[offset + EXP] = NFPG_PIPE_EXP
            self.n_function_selector.set_value(n_function_selector_array, borrow=True)
            self.allocated_elements_to_activators[offset + POR] = \
                self.allocated_node_offsets[self.allocated_nodespaces_por_activators[nodespace_id]]
            self.allocated_elements_to_activators[offset + RET] = \
                self.allocated_node_offsets[self.allocated_nodespaces_ret_activators[nodespace_id]]
            self.allocated_elements_to_activators[offset + SUB] = \
                self.allocated_node_offsets[self.allocated_nodespaces_sub_activators[nodespace_id]]
            self.allocated_elements_to_activators[offset + SUR] = \
                self.allocated_node_offsets[self.allocated_nodespaces_sur_activators[nodespace_id]]
            self.allocated_elements_to_activators[offset + CAT] = \
                self.allocated_node_offsets[self.allocated_nodespaces_cat_activators[nodespace_id]]
            self.allocated_elements_to_activators[offset + EXP] = \
                self.allocated_node_offsets[self.allocated_nodespaces_exp_activators[nodespace_id]]

            if nto.parameter_defaults.get('expectation'):
                value = nto.parameter_defaults['expectation']
                g_expect_array = self.g_expect.get_value(borrow=True)
                g_expect_array[offset + GEN] = float(value)
                g_expect_array[offset + SUR] = float(value)
                g_expect_array[offset + POR] = float(value)
                self.g_expect.set_value(g_expect_array, borrow=True)

            if nto.parameter_defaults.get('wait'):
                value = nto.parameter_defaults['wait']
                g_wait_array = self.g_wait.get_value(borrow=True)
                g_wait_array[offset + SUR] = int(min(value, 128))
                g_wait_array[offset + POR] = int(min(value, 128))
                self.g_wait.set_value(g_wait_array, borrow=True)
        elif nodetype == "LSTM":
            self.has_lstms = True
            n_function_selector_array = self.n_function_selector.get_value(borrow=True)
            n_function_selector_array[offset + GEN] = NFPG_LSTM_GEN
            n_function_selector_array[offset + POR] = NFPG_LSTM_POR
            n_function_selector_array[offset + GIN] = NFPG_LSTM_GIN
            n_function_selector_array[offset + GOU] = NFPG_LSTM_GOU
            n_function_selector_array[offset + GFG] = NFPG_LSTM_GFG
            self.n_function_selector.set_value(n_function_selector_array, borrow=True)

            self.allocated_elements_to_activators[offset + GEN] = \
                self.allocated_node_offsets[self.allocated_nodespaces_sampling_activators[nodespace_id]]
            self.allocated_elements_to_activators[offset + POR] = \
                self.allocated_node_offsets[self.allocated_nodespaces_sampling_activators[nodespace_id]]
            self.allocated_elements_to_activators[offset + GIN] = \
                self.allocated_node_offsets[self.allocated_nodespaces_sampling_activators[nodespace_id]]
            self.allocated_elements_to_activators[offset + GOU] = \
                self.allocated_node_offsets[self.allocated_nodespaces_sampling_activators[nodespace_id]]
            self.allocated_elements_to_activators[offset + GFG] = \
                self.allocated_node_offsets[self.allocated_nodespaces_sampling_activators[nodespace_id]]

        elif nodetype == "Activator":
            self.has_directional_activators = True
            activator_type = parameters.get("type")
            if activator_type is not None and len(activator_type) > 0:
                if activator_type != "sampling":
                    self.set_nodespace_gatetype_activator(nodespace_id, activator_type, id)
                else:
                    self.set_nodespace_sampling_activator(nodespace_id, id)

        if nodetype not in self.nodenet.get_standard_nodetype_definitions():
            node_proxy = self.nodenet.get_node(uid)
            self.native_module_instances[uid] = node_proxy
            for key, value in parameters.items():
                node_proxy.set_parameter(key, value)
        elif nodetype == "Comment":
            node_proxy = self.nodenet.get_node(uid)
            self.comment_instances[uid] = node_proxy
            for key in self.nodenet.get_standard_nodetype_definitions()[nodetype]['parameters']:
                node_proxy.set_parameter(key, parameters.get(key, ''))

        for gate, parameters in nto.gate_defaults.items():
            if gate in nto.gatetypes:
                for gate_parameter in parameters:
                    self.set_node_gate_parameter(id, gate, gate_parameter, parameters[gate_parameter])
        if gate_parameters is not None:
            for gate, parameters in gate_parameters.items():
                if gate in nto.gatetypes:
                    for gate_parameter in parameters:
                        self.set_node_gate_parameter(id, gate, gate_parameter, parameters[gate_parameter])

        if gate_functions is not None:
            for gate, gate_function in gate_functions.items():
                if gate in nto.gatetypes:
                    self.set_node_gatefunction_name(id, gate, gate_function)

        # initialize activation to zero
        a_array = self.a.get_value(borrow=True)
        for element in range (0, get_elements_per_type(get_numerical_node_type(nodetype, self.nodenet.native_modules), self.nodenet.native_modules)):
            a_array[offset + element] = 0
        self.a.set_value(a_array)

        return id

    def delete_node(self, node_id):

        type = self.allocated_nodes[node_id]
        offset = self.allocated_node_offsets[node_id]
        parent = self.allocated_node_parents[node_id]

        self.unlink_node_completely(node_id)
        self.nodenet._track_deletion('nodes', node_to_id(node_id, self.pid))
        self.nodespaces_contents_last_changed[self.allocated_node_parents[node_id]] = self.nodenet.current_step

        # forget
        self.allocated_nodes[node_id] = 0
        self.allocated_node_offsets[node_id] = 0
        self.allocated_node_parents[node_id] = 0
        g_function_selector_array = self.g_function_selector.get_value(borrow=True)
        for element in range (0, get_elements_per_type(type, self.nodenet.native_modules)):
            self.allocated_elements_to_nodes[offset + element] = 0
            g_function_selector_array[offset + element] = 0
        self.g_function_selector.set_value(g_function_selector_array, borrow=True)
        self.allocated_elements_to_nodes[np.where(self.allocated_elements_to_nodes == node_id)[0]] = 0

        if type == SENSOR:
            sensor_index = np.where(self.sensor_indices == node_id)[0]
            self.sensor_indices[sensor_index] = 0

        if type == ACTUATOR:
            actuator_index = np.where(self.actuator_indices == node_id)[0]
            self.actuator_indices[actuator_index] = 0

        if type == PIPE:
            n_function_selector_array = self.n_function_selector.get_value(borrow=True)
            n_function_selector_array[offset + GEN] = NFPG_PIPE_NON
            n_function_selector_array[offset + POR] = NFPG_PIPE_NON
            n_function_selector_array[offset + RET] = NFPG_PIPE_NON
            n_function_selector_array[offset + SUB] = NFPG_PIPE_NON
            n_function_selector_array[offset + SUR] = NFPG_PIPE_NON
            n_function_selector_array[offset + CAT] = NFPG_PIPE_NON
            n_function_selector_array[offset + EXP] = NFPG_PIPE_NON
            self.n_function_selector.set_value(n_function_selector_array, borrow=True)

        if type == LSTM:
            n_function_selector_array = self.n_function_selector.get_value(borrow=True)
            n_function_selector_array[offset + GEN] = NFPG_PIPE_NON
            n_function_selector_array[offset + POR] = NFPG_PIPE_NON
            n_function_selector_array[offset + GIN] = NFPG_PIPE_NON
            n_function_selector_array[offset + GOU] = NFPG_PIPE_NON
            n_function_selector_array[offset + GFG] = NFPG_PIPE_NON
            self.n_function_selector.set_value(n_function_selector_array, borrow=True)

        # hint at the free ID
        self.last_allocated_node = node_id - 1

        # remove the native module or comment instance if there should be one
        uid = node_to_id(node_id, self.pid)
        if uid in self.native_module_instances:
            del self.native_module_instances[uid]
        if uid in self.comment_instances:
            del self.comment_instances[uid]

        # clear activator usage if there should be one
        used_as_activator_by = np.where(self.allocated_elements_to_activators == offset)
        if len(used_as_activator_by) > 0:
            self.allocated_elements_to_activators[used_as_activator_by] = 0

        if self.allocated_nodespaces_por_activators[parent] == node_id:
            self.allocated_nodespaces_por_activators[parent] = 0
        elif self.allocated_nodespaces_ret_activators[parent] == node_id:
            self.allocated_nodespaces_ret_activators[parent] = 0
        elif self.allocated_nodespaces_sub_activators[parent] == node_id:
            self.allocated_nodespaces_sub_activators[parent] = 0
        elif self.allocated_nodespaces_sur_activators[parent] == node_id:
            self.allocated_nodespaces_sur_activators[parent] = 0
        elif self.allocated_nodespaces_cat_activators[parent] == node_id:
            self.allocated_nodespaces_cat_activators[parent] = 0
        elif self.allocated_nodespaces_exp_activators[parent] == node_id:
            self.allocated_nodespaces_exp_activators[parent] = 0
        if self.allocated_nodespaces_sampling_activators[parent] == node_id:
            self.allocated_nodespaces_sampling_activators[parent] = 0

    def node_changed(self, uid):
        node_id = node_from_id(uid)
        self.nodes_last_changed[node_id] = self.nodenet.current_step
        self.nodespaces_contents_last_changed[self.allocated_node_parents[node_id]] = self.nodenet.current_step

    def unlink_node_completely(self, node_id):
        type = self.allocated_nodes[node_id]
        offset = self.allocated_node_offsets[node_id]
        w_matrix = self.w.get_value(borrow=True)
        number_of_elements = get_elements_per_type(type, self.nodenet.native_modules)
        connecting_elements = np.nonzero(w_matrix[offset:offset+number_of_elements, :])[1]
        connected_elements = np.nonzero(w_matrix[:, offset:offset+number_of_elements])[0]
        w_matrix[offset:offset+number_of_elements, connecting_elements] = 0
        w_matrix[connected_elements, offset:offset+number_of_elements] = 0
        self.w.set_value(w_matrix, borrow=True)
        connecting_nodes = self.allocated_elements_to_nodes[connecting_elements]
        connected_nodes = self.allocated_elements_to_nodes[connected_elements]
        # update all involved elements' changed-steps
        self.nodes_last_changed[node_id] = self.nodenet.current_step
        self.nodes_last_changed[connected_nodes] = self.nodenet.current_step
        self.nodes_last_changed[connecting_nodes] = self.nodenet.current_step
        # update all involved elements' parents' changed-steps
        self.nodespaces_contents_last_changed[self.allocated_node_parents[node_id]] = self.nodenet.current_step
        self.nodespaces_contents_last_changed[self.allocated_node_parents[connected_nodes]] = self.nodenet.current_step
        self.nodespaces_contents_last_changed[self.allocated_node_parents[connecting_nodes]] = self.nodenet.current_step

    def get_associated_elements(self, node_id):
        type = self.allocated_nodes[node_id]
        offset = self.allocated_node_offsets[node_id]
        w_matrix = self.w.get_value(borrow=True)
        number_of_elements = get_elements_per_type(type, self.nodenet.native_modules)
        connecting_elements = np.nonzero(w_matrix[offset:offset+number_of_elements, :])[1]
        connected_elements = np.nonzero(w_matrix[:, offset:offset+number_of_elements])[0]
        return connecting_elements, connected_elements

    def get_associated_node_ids(self, node_id):
        connecting_elements, connected_elements = self.get_associated_elements(node_id)
        connecting_nodes = np.unique(self.allocated_elements_to_nodes[connecting_elements])
        connected_nodes = np.unique(self.allocated_elements_to_nodes[connected_elements])
        return np.unique(np.concatenate((connecting_nodes, connected_nodes)))

    def create_nodespace(self, parent_id, id=None):

        # find a free ID / index in the allocated_nodespaces vector to hold the nodespaces's parent
        if id is None:
            id = 0
            for i in range((self.last_allocated_nodespace + 1), self.NoNS):
                if self.allocated_nodespaces[i] == 0:
                    id = i
                    break

            if id < 1:
                for i in range(self.last_allocated_nodespace - 1):
                    if self.allocated_nodespaces[i] == 0:
                        id = i
                        break

            if id < 1:
                growby = self.NoNS // 2 or 1
                self.logger.info("All %d nodespace IDs in use in partition %i, growing nodespace ID vector by %d elements" % (self.NoNS, self.pid, growby))
                id = self.NoNS
                self.grow_number_of_nodespaces(growby)

        self.last_allocated_nodespace = id
        self.allocated_nodespaces[id] = parent_id
        self.nodespaces_last_changed[id] = self.nodenet.current_step
        self.nodespaces_contents_last_changed[parent_id] = self.nodenet.current_step
        return id

    def delete_nodespace(self, nodespace_id):
        children_ids = np.where(self.allocated_nodespaces == nodespace_id)[0]
        for child_id in children_ids:
            self.nodenet.delete_nodespace(nodespace_to_id(child_id, self.pid))
        node_ids = np.where(self.allocated_node_parents == nodespace_id)[0]
        for node_id in node_ids:
            self.nodenet.delete_node(node_to_id(node_id, self.pid))
            self.nodenet.clear_supplements(node_to_id(node_id, self.pid))

        self.nodenet.clear_supplements(nodespace_to_id(nodespace_id, self.pid))
        self.allocated_nodespaces[nodespace_id] = 0
        self.last_allocated_nodespace = nodespace_id
        self.nodenet._track_deletion('nodespaces', nodespace_to_id(nodespace_id, self.pid))
        self.nodespaces_contents_last_changed[self.allocated_nodespaces[nodespace_id]] = self.nodenet.current_step

    def set_node_gate_parameter(self, id, gate_type, parameter, value):
        numerical_node_type = self.allocated_nodes[id]
        nodetype = None
        if numerical_node_type > MAX_STD_NODETYPE:
            nodetype = self.nodenet.get_nodetype(get_string_node_type(numerical_node_type, self.nodenet.native_modules))

        elementindex = self.allocated_node_offsets[id] + get_numerical_gate_type(gate_type, nodetype)
        if parameter == 'threshold':
            g_threshold_array = self.g_threshold.get_value(borrow=True)
            g_threshold_array[elementindex] = value
            self.g_threshold.set_value(g_threshold_array, borrow=True)
        elif parameter == 'amplification':
            g_amplification_array = self.g_amplification.get_value(borrow=True)
            g_amplification_array[elementindex] = value
            self.g_amplification.set_value(g_amplification_array, borrow=True)
        elif parameter == 'minimum':
            g_min_array = self.g_min.get_value(borrow=True)
            g_min_array[elementindex] = value
            self.g_min.set_value(g_min_array, borrow=True)
        elif parameter == 'maximum':
            g_max_array = self.g_max.get_value(borrow=True)
            g_max_array[elementindex] = value
            self.g_max.set_value(g_max_array, borrow=True)
        elif parameter == 'theta':
            g_theta_array = self.g_theta.get_value(borrow=True)
            g_theta_array[elementindex] = value
            self.g_theta.set_value(g_theta_array, borrow=True)

    def set_node_gatefunction_name(self, id, gate_type, gatefunction_name):
        numerical_node_type = self.allocated_nodes[id]
        nodetype = None
        if numerical_node_type > MAX_STD_NODETYPE:
            nodetype = self.nodenet.get_nodetype(get_string_node_type(numerical_node_type, self.nodenet.native_modules))

        elementindex = self.allocated_node_offsets[id] + get_numerical_gate_type(gate_type, nodetype)
        g_function_selector = self.g_function_selector.get_value(borrow=True)
        g_function_selector[elementindex] = get_numerical_gatefunction_type(gatefunction_name)
        self.g_function_selector.set_value(g_function_selector, borrow=True)
        if g_function_selector[elementindex] == GATE_FUNCTION_ABSOLUTE:
            self.has_gatefunction_absolute = True
        elif g_function_selector[elementindex] == GATE_FUNCTION_SIGMOID:
            self.has_gatefunction_sigmoid = True
        elif g_function_selector[elementindex] == GATE_FUNCTION_TANH:
            self.has_gatefunction_tanh = True
        elif g_function_selector[elementindex] == GATE_FUNCTION_RECT:
            self.has_gatefunction_rect = True
        elif g_function_selector[elementindex] == GATE_FUNCTION_DIST:
            self.has_gatefunction_one_over_x = True

    def set_nodespace_gatetype_activator(self, nodespace_id, gate_type, activator_id):
        if gate_type == "por":
            self.allocated_nodespaces_por_activators[nodespace_id] = activator_id
            self.has_directional_activators = True
        elif gate_type == "ret":
            self.allocated_nodespaces_ret_activators[nodespace_id] = activator_id
            self.has_directional_activators = True
        elif gate_type == "sub":
            self.allocated_nodespaces_sub_activators[nodespace_id] = activator_id
            self.has_directional_activators = True
        elif gate_type == "sur":
            self.allocated_nodespaces_sur_activators[nodespace_id] = activator_id
            self.has_directional_activators = True
        elif gate_type == "cat":
            self.allocated_nodespaces_cat_activators[nodespace_id] = activator_id
            self.has_directional_activators = True
        elif gate_type == "exp":
            self.allocated_nodespaces_exp_activators[nodespace_id] = activator_id
            self.has_directional_activators = True

        nodes_in_nodespace = np.where(self.allocated_node_parents == nodespace_id)[0]
        for nid in nodes_in_nodespace:
            if self.allocated_nodes[nid] == PIPE:
                self.allocated_elements_to_activators[self.allocated_node_offsets[nid] +
                                                      get_numerical_gate_type(gate_type)] = self.allocated_node_offsets[activator_id]

    def set_nodespace_sampling_activator(self, nodespace_id, activator_id):
        self.allocated_nodespaces_sampling_activators[nodespace_id] = activator_id
        self.has_sampling_activators = True

        nodes_in_nodespace = np.where(self.allocated_node_parents == nodespace_id)[0]
        for nid in nodes_in_nodespace:
            if self.allocated_nodes[nid] == LSTM:
                self.allocated_elements_to_activators[self.allocated_node_offsets[nid] + GEN] = self.allocated_node_offsets[activator_id]
                self.allocated_elements_to_activators[self.allocated_node_offsets[nid] + POR] = self.allocated_node_offsets[activator_id]
                self.allocated_elements_to_activators[self.allocated_node_offsets[nid] + GIN] = self.allocated_node_offsets[activator_id]
                self.allocated_elements_to_activators[self.allocated_node_offsets[nid] + GOU] = self.allocated_node_offsets[activator_id]
                self.allocated_elements_to_activators[self.allocated_node_offsets[nid] + GFG] = self.allocated_node_offsets[activator_id]

    def set_link_weight(self, source_node_id, gate_type, target_node_id, slot_type, weight=1):
        source_nodetype = None
        target_nodetype = None
        if self.allocated_nodes[source_node_id] > MAX_STD_NODETYPE:
            source_nodetype = self.nodenet.get_nodetype(get_string_node_type(self.allocated_nodes[source_node_id], self.nodenet.native_modules))
        if self.allocated_nodes[target_node_id] > MAX_STD_NODETYPE:
            target_nodetype = self.nodenet.get_nodetype(get_string_node_type(self.allocated_nodes[target_node_id], self.nodenet.native_modules))

        ngt = get_numerical_gate_type(gate_type, source_nodetype)
        nst = get_numerical_slot_type(slot_type, target_nodetype)

        if ngt > get_gates_per_type(self.allocated_nodes[source_node_id], self.nodenet.native_modules):
            raise ValueError("Node %s does not have a gate of type %s" % (node_to_id(source_node_id, self.pid), gate_type))

        if nst > get_slots_per_type(self.allocated_nodes[target_node_id], self.nodenet.native_modules):
            raise ValueError("Node %s does not have a slot of type %s" % (node_to_id(target_node_id, self.pid), slot_type))

        w_matrix = self.w.get_value(borrow=True)
        x = self.allocated_node_offsets[target_node_id] + nst
        y = self.allocated_node_offsets[source_node_id] + ngt
        if self.sparse:
            w_matrix[x, y] = weight
        else:
            w_matrix[x][y] = weight
        self.w.set_value(w_matrix, borrow=True)

        self.nodes_last_changed[source_node_id] = self.nodenet.current_step
        self.nodes_last_changed[target_node_id] = self.nodenet.current_step
        self.nodespaces_contents_last_changed[self.allocated_node_parents[source_node_id]] = self.nodenet.current_step
        self.nodespaces_contents_last_changed[self.allocated_node_parents[target_node_id]] = self.nodenet.current_step

        # if (slot_type == "por" or slot_type == "ret") and self.allocated_nodes[node_from_id(target_node_uid)] == PIPE:
        #     self.__por_ret_dirty = False

        if slot_type == "por" and self.allocated_nodes[target_node_id] == PIPE:
            n_node_porlinked_array = self.n_node_porlinked.get_value(borrow=True)
            if weight == 0:
                for g in range(7):
                    n_node_porlinked_array[self.allocated_node_offsets[target_node_id] + g] = 0
            else:
                for g in range(7):
                    n_node_porlinked_array[self.allocated_node_offsets[target_node_id] + g] = 1
            self.n_node_porlinked.set_value(n_node_porlinked_array, borrow=True)
        if slot_type == "ret" and self.allocated_nodes[target_node_id] == PIPE:
            n_node_retlinked_array = self.n_node_retlinked.get_value(borrow=True)
            if weight == 0:
                for g in range(7):
                    n_node_retlinked_array[self.allocated_node_offsets[target_node_id] + g] = 0
            else:
                for g in range(7):
                    n_node_retlinked_array[self.allocated_node_offsets[target_node_id] + g] = 1
            self.n_node_retlinked.set_value(n_node_retlinked_array, borrow=True)

    def group_nodes_by_ids(self, nodespace_uid, ids, group_name, gatetype="gen"):

        if nodespace_uid not in self.nodegroups:
            self.nodegroups[nodespace_uid] = {}
        parent_id = nodespace_from_id(nodespace_uid)

        non_children = np.where(self.allocated_node_parents[ids] != parent_id)[0]
        if len(non_children) > 0:
            raise ValueError("One ore more given nodes are not in nodespace %s" % nodespace_uid)

        gate = get_numerical_gate_type(gatetype)
        self.nodegroups[nodespace_uid][group_name] = self.allocated_node_offsets[ids] + gate

    def ungroup_nodes(self, nodespace_uid, group):
        if nodespace_uid in self.nodegroups and group in self.nodegroups[nodespace_uid]:
            del self.nodegroups[nodespace_uid][group]

    def get_activations(self, nodespace_uid, group):
        if nodespace_uid not in self.nodegroups or group not in self.nodegroups[nodespace_uid]:
            raise ValueError("Group %s does not exist in nodespace %s." % (group, nodespace_uid))
        a_array = self.a.get_value(borrow=True)
        return a_array[self.nodegroups[nodespace_uid][group]]

    def set_activations(self, nodespace_uid, group, new_activations):
        if nodespace_uid not in self.nodegroups or group not in self.nodegroups[nodespace_uid]:
            raise ValueError("Group %s does not exist in nodespace %s." % (group, nodespace_uid))
        a_array = self.a.get_value(borrow=True)
        a_array[self.nodegroups[nodespace_uid][group]] = new_activations
        self.a.set_value(a_array, borrow=True)

    def get_thetas(self, nodespace_uid, group):
        if nodespace_uid not in self.nodegroups or group not in self.nodegroups[nodespace_uid]:
            raise ValueError("Group %s does not exist in nodespace %s." % (group, nodespace_uid))
        g_theta_array = self.g_theta.get_value(borrow=True)
        return g_theta_array[self.nodegroups[nodespace_uid][group]]

    def set_thetas(self, nodespace_uid, group, thetas):
        if nodespace_uid not in self.nodegroups or group not in self.nodegroups[nodespace_uid]:
            raise ValueError("Group %s does not exist in nodespace %s." % (group, nodespace_uid))
        g_theta_array = self.g_theta.get_value(borrow=True)
        g_theta_array[self.nodegroups[nodespace_uid][group]] = thetas
        self.g_theta.set_value(g_theta_array, borrow=True)

    def get_link_weights(self, nodespace_from_uid, group_from, nodespace_to_uid, group_to):
        if nodespace_from_uid not in self.nodegroups or group_from not in self.nodegroups[nodespace_from_uid]:
            raise ValueError("Group %s does not exist in nodespace %s." % (group_from, nodespace_from_uid))
        if nodespace_to_uid not in self.nodegroups or group_to not in self.nodegroups[nodespace_to_uid]:
            raise ValueError("Group %s does not exist in nodespace %s." % (group_to, nodespace_to_uid))
        w_matrix = self.w.get_value(borrow=True)
        cols, rows = np.meshgrid(self.nodegroups[nodespace_from_uid][group_from], self.nodegroups[nodespace_to_uid][group_to])
        if self.sparse:
            return w_matrix[rows,cols].toarray()
        else:
            return w_matrix[rows,cols]

    def set_link_weights(self, nodespace_from_uid, group_from, nodespace_to_uid, group_to, new_w):
        #if nodespace_from_uid not in self.nodegroups or group_from not in self.nodegroups[nodespace_from_uid]:
        #    raise ValueError("Group %s does not exist in nodespace %s." % (group_from, nodespace_from_uid))
        #if nodespace_to_uid not in self.nodegroups or group_to not in self.nodegroups[nodespace_to_uid]:
        #    raise ValueError("Group %s does not exist in nodespace %s." % (group_to, nodespace_to_uid))
        #if len(self.nodegroups[nodespace_from_uid][group_from]) != new_w.shape[1]:
        #    raise ValueError("group_from %s has length %i, but new_w.shape[1] is %i" % (group_from, len(self.nodegroups[nodespace_from_uid][group_from]), new_w.shape[1]))
        #if len(self.nodegroups[nodespace_to_uid][group_to]) != new_w.shape[0]:
        #    raise ValueError("group_to %s has length %i, but new_w.shape[0] is %i" % (group_to, len(self.nodegroups[nodespace_to_uid][group_to]), new_w.shape[0]))

        w_matrix = self.w.get_value(borrow=True)
        grp_from = self.nodegroups[nodespace_from_uid][group_from]
        grp_to = self.nodegroups[nodespace_to_uid][group_to]
        cols, rows = np.meshgrid(grp_from, grp_to)
        w_matrix[rows, cols] = new_w
        self.w.set_value(w_matrix, borrow=True)

        cstep = self.nodenet.current_step
        self.nodes_last_changed[self.allocated_elements_to_nodes[grp_from]] = cstep
        self.nodespaces_contents_last_changed[self.allocated_node_parents[self.allocated_elements_to_nodes[grp_from]]] = cstep
        self.nodes_last_changed[self.allocated_elements_to_nodes[grp_to]] = cstep
        self.nodespaces_contents_last_changed[self.allocated_node_parents[self.allocated_elements_to_nodes[grp_to]]] = cstep

        self.por_ret_dirty = self.has_pipes

    def set_inlink_weights(self, partition_from_spid, new_from_elements, new_to_elements, new_weights):
        from_partition = self.nodenet.partitions[partition_from_spid]
        if partition_from_spid in self.inlinks:
            theano_from_elements = self.inlinks[partition_from_spid][0]
            theano_to_elements = self.inlinks[partition_from_spid][1]
            theano_weights = self.inlinks[partition_from_spid][2]
            old_from_elements = theano_from_elements.get_value(borrow=True)
            old_to_elements = theano_to_elements.get_value(borrow=True)
            old_weights = theano_weights.get_value(borrow=True)
            propagation_function = self.inlinks[partition_from_spid][3]
        else:
            old_from_elements = np.zeros(0, dtype=np.int32)
            old_to_elements = np.zeros(0, dtype=np.int32)
            old_weights = np.eye(0, dtype=T.config.floatX)

            weightsname = "w_%s_%s" % (partition_from_spid, self.spid)
            fromname = "in_from_%s_%s" % (partition_from_spid, self.spid)
            toname = "in_to_%s_%s" % (partition_from_spid, self.spid)
            theano_from_elements = theano.shared(value=old_from_elements, name=fromname, borrow=True)
            theano_to_elements = theano.shared(value=old_to_elements, name=toname, borrow=True)
            theano_weights = theano.shared(value=old_weights.astype(T.config.floatX), name=weightsname, borrow=True)

            propagation_function = self.get_compiled_propagate_inlinks(
                from_partition,
                theano_from_elements,
                theano_to_elements,
                theano_weights)

        from_elements = np.union1d(old_from_elements, new_from_elements)
        to_elements = np.union1d(old_to_elements, new_to_elements)
        weights = np.zeros((len(to_elements), len(from_elements)), dtype=T.config.floatX)

        old_from_indices = np.searchsorted(from_elements, old_from_elements)
        old_to_indices = np.searchsorted(to_elements, old_to_elements)
        oldcols, oldrows = np.meshgrid(old_from_indices, old_to_indices)
        weights[oldrows, oldcols] = old_weights

        new_from_indices = np.searchsorted(from_elements, new_from_elements)
        new_to_indices = np.searchsorted(to_elements, new_to_elements)
        newcols, newrows = np.meshgrid(new_from_indices, new_to_indices)
        weights[newrows, newcols] = new_weights

        theano_from_elements.set_value(from_elements, borrow=True)
        theano_to_elements.set_value(to_elements, borrow=True)
        theano_weights.set_value(weights, borrow=True)

        for id in from_partition.allocated_elements_to_nodes[theano_from_elements.get_value()]:
            from_partition.nodes_last_changed[id] = self.nodenet.current_step
            from_partition.nodespaces_contents_last_changed[from_partition.allocated_node_parents[id]] = self.nodenet.current_step
        for id in self.allocated_elements_to_nodes[theano_to_elements.get_value()]:
            self.nodes_last_changed[id] = self.nodenet.current_step
            self.nodespaces_contents_last_changed[self.allocated_node_parents[id]] = self.nodenet.current_step

        self.inlinks[partition_from_spid] = (
            theano_from_elements,
            theano_to_elements,
            theano_weights,
            propagation_function)

    def has_nodespace_changes(self, nodespace_uid, since_step):
        ns_id = nodespace_from_id(nodespace_uid)
        return (self.nodespaces_contents_last_changed[ns_id] >= since_step).__bool__()

    def get_nodespace_changes(self, nodespace_uid, since_step):
        ns_id = nodespace_from_id(nodespace_uid)
        node_ids = np.where(self.nodes_last_changed >= since_step)[0]
        node_ids = node_ids[np.where(self.allocated_node_parents[node_ids] == ns_id)[0]]
        nodespace_ids = np.where(self.nodespaces_last_changed >= since_step)[0]
        nodespace_ids = nodespace_ids[np.where(self.allocated_nodespaces[nodespace_ids] == ns_id)[0]]
        return node_ids, nodespace_ids

    def get_node_data(self, ids=None, nodespace_ids=None, complete=False, include_links=True, include_followupnodes=True):

        a = self.a.get_value(borrow=True)
        g_threshold_array = self.g_threshold.get_value(borrow=True)
        g_amplification_array = self.g_amplification.get_value(borrow=True)
        g_min_array = self.g_min.get_value(borrow=True)
        g_max_array = self.g_max.get_value(borrow=True)
        g_theta = self.g_theta.get_value(borrow=True)
        g_function_selector = self.g_function_selector.get_value(borrow=True)
        w = self.w.get_value(borrow=True)

        if nodespace_ids is not None:
            node_ids = np.where(self.allocated_node_parents == nodespace_ids)[0]
        else:
            node_ids = np.nonzero(self.allocated_nodes)[0]

        if ids is not None:
            node_ids = np.intersect1d(node_ids, ids)

        nodes = {}
        followupuids = set()
        for id in node_ids:
            uid = node_to_id(id, self.pid)
            strtype = get_string_node_type(self.allocated_nodes[id], self.nodenet.native_modules)
            nodetype = self.nodenet.get_nodetype(strtype)

            gate_functions = {}
            gate_parameters = {}
            gate_activations = {}
            links = {}
            for gate in self.nodenet.get_nodetype(strtype).gatetypes:
                numericalgate = get_numerical_gate_type(gate, self.nodenet.get_nodetype(strtype))
                element = self.allocated_node_offsets[id] + numericalgate
                gate_functions[gate] = get_string_gatefunction_type(g_function_selector[element])

                parameters = {}
                threshold = g_threshold_array[element].item()
                if 'threshold' not in nodetype.gate_defaults[gate] or threshold != nodetype.gate_defaults[gate]['threshold']:
                    parameters['threshold'] = float(threshold)

                amplification = g_amplification_array[element].item()
                if 'amplification' not in nodetype.gate_defaults[gate] or amplification != nodetype.gate_defaults[gate]['amplification']:
                    parameters['amplification'] = float(amplification)

                minimum = g_min_array[element].item()
                if 'minimum' not in nodetype.gate_defaults[gate] or minimum != nodetype.gate_defaults[gate]['minimum']:
                    parameters['minimum'] = float(minimum)

                maximum = g_max_array[element].item()
                if 'maximum' not in nodetype.gate_defaults[gate] or maximum != nodetype.gate_defaults[gate]['maximum']:
                    parameters['maximum'] = float(maximum)

                theta = g_theta[element].item()
                if 'theta' not in nodetype.gate_defaults[gate] or theta != nodetype.gate_defaults[gate]['theta']:
                    parameters['theta'] = float(theta)

                if not len(parameters) == 0:
                    gate_parameters[gate] = parameters

                gate_activations[gate] = {"default": {
                    "name": "default",
                    "uid": "default",
                    "activation": float(a[element])}}

            state = None
            if uid in self.native_module_instances:
                state = self.native_module_instances.get(uid).clone_state()

            parameters = {}
            if strtype == "Sensor":
                sensor_element = self.allocated_node_offsets[id] + GEN
                datasource_index = np.where(self.sensor_indices == sensor_element)[0]
                if len(datasource_index) == 0:
                    parameters['datasource'] = None
                else:
                    parameters['datasource'] = self.nodenet.get_datasources()[datasource_index[0]]
            elif strtype == "Actor":
                actuator_element = self.allocated_node_offsets[id] + GEN
                datatarget_index = np.where(self.actuator_indices == actuator_element)[0]
                if len(datatarget_index) == 0:
                    parameters['datatarget'] = None
                else:
                    parameters['datatarget'] = self.nodenet.get_datatargets()[datatarget_index[0]]
            elif strtype == "Activator":
                activator_type = None
                if id in self.allocated_nodespaces_por_activators:
                    activator_type = "por"
                elif id in self.allocated_nodespaces_ret_activators:
                    activator_type = "ret"
                elif id in self.allocated_nodespaces_sub_activators:
                    activator_type = "sub"
                elif id in self.allocated_nodespaces_sur_activators:
                    activator_type = "sur"
                elif id in self.allocated_nodespaces_cat_activators:
                    activator_type = "cat"
                elif id in self.allocated_nodespaces_exp_activators:
                    activator_type = "exp"
                elif id in self.allocated_nodespaces_sampling_activators:
                    activator_type = "sampling"
                parameters['type'] = activator_type
            elif strtype == "Pipe":
                g_expect_array = self.g_expect.get_value(borrow=True)
                value = g_expect_array[self.allocated_node_offsets[id] + get_numerical_gate_type("sur")].item()
                parameters['expectation'] = value
                g_wait_array = self.g_wait.get_value(borrow=True)
                parameters['wait'] = g_wait_array[self.allocated_node_offsets[id] + get_numerical_gate_type("sur")].item()
            elif strtype == "Comment":
                parameters = self.comment_instances.get(uid).clone_parameters()
            elif strtype in self.nodenet.native_modules:
                parameters = self.native_module_instances.get(uid).clone_parameters()

            data = {"uid": uid,
                    "name": self.nodenet.names.get(uid, uid),
                    "position": self.nodenet.positions.get(uid, (10, 10, 10)),
                    "parent_nodespace": nodespace_to_id(self.allocated_node_parents[id], self.pid),
                    "type": strtype,
                    "parameters": parameters,
                    "state": state,
                    "gate_parameters": gate_parameters,
                    "sheaves": {"default": {"name": "default",
                                "uid": "default",
                                "activation": float(a[self.allocated_node_offsets[id] + GEN])}},
                    "activation": float(a[self.allocated_node_offsets[id] + GEN]),
                    "gate_activations": gate_activations,
                    "gate_functions": gate_functions}
            if complete:
                data['index'] = id
            if include_links:
                data['links'] = {}

            nodes[uid] = data

        # fill in links if requested
        if include_links:
            slots, gates = np.nonzero(w)
            for index, gate_index in enumerate(gates):
                source_id = self.allocated_elements_to_nodes[gate_index]
                source_uid = node_to_id(source_id, self.pid)
                if source_uid not in nodes:
                    continue

                source_type = self.allocated_nodes[source_id]
                source_nodetype = self.nodenet.get_nodetype(get_string_node_type(source_type, self.nodenet.native_modules))
                source_gate_numerical = gate_index - self.allocated_node_offsets[source_id]
                source_gate_type = get_string_gate_type(source_gate_numerical, source_nodetype)

                slot_index = slots[index]
                target_id = self.allocated_elements_to_nodes[slot_index]
                target_uid = node_to_id(target_id, self.pid)
                target_type = self.allocated_nodes[target_id]
                target_nodetype = self.nodenet.get_nodetype(get_string_node_type(target_type, self.nodenet.native_modules))
                target_slot_numerical = slot_index - self.allocated_node_offsets[target_id]
                target_slot_type = get_string_slot_type(target_slot_numerical, target_nodetype)
                linkdict = {"weight": float(w[slot_index, gate_index]),
                            "certainty": 1,
                            "target_slot_name": target_slot_type,
                            "target_node_uid": target_uid}
                if source_gate_type not in nodes[source_uid]["links"]:
                    nodes[source_uid]["links"][source_gate_type] = []
                nodes[source_uid]["links"][source_gate_type].append(linkdict)
                followupuids.add(target_uid)

            # outgoing cross-partition links
            for partition_to_spid, to_partition in self.nodenet.partitions.items():
                if self.spid in to_partition.inlinks:
                    inlinks = to_partition.inlinks[self.spid]
                    from_elements = inlinks[0].get_value(borrow=True)
                    to_elements = inlinks[1].get_value(borrow=True)
                    w = inlinks[2].get_value(borrow=True)
                    slots, gates = np.nonzero(w)
                    for index, gate_index in enumerate(gates):
                        source_id = self.allocated_elements_to_nodes[from_elements[gate_index]]
                        source_uid = node_to_id(source_id, self.pid)
                        if source_uid not in nodes:
                            continue

                        source_type = self.allocated_nodes[source_id]
                        source_nodetype = self.nodenet.get_nodetype(get_string_node_type(source_type, self.nodenet.native_modules))
                        source_gate_numerical = from_elements[gate_index] - self.allocated_node_offsets[source_id]
                        source_gate_type = get_string_gate_type(source_gate_numerical, source_nodetype)

                        slot_index = slots[index]
                        target_id = to_partition.allocated_elements_to_nodes[to_elements[slot_index]]
                        target_uid = node_to_id(target_id, to_partition.pid)
                        target_type = to_partition.allocated_nodes[target_id]
                        target_nodetype = to_partition.nodenet.get_nodetype(get_string_node_type(target_type, to_partition.nodenet.native_modules))
                        target_slot_numerical = to_elements[slot_index] - to_partition.allocated_node_offsets[target_id]
                        target_slot_type = get_string_slot_type(target_slot_numerical, target_nodetype)
                        linkdict = {"weight": float(w[slot_index, gate_index]),
                                    "certainty": 1,
                                    "target_slot_name": target_slot_type,
                                    "target_node_uid": target_uid}
                        if source_gate_type not in nodes[source_uid]["links"]:
                            nodes[source_uid]["links"][source_gate_type] = []
                        nodes[source_uid]["links"][source_gate_type].append(linkdict)
                        followupuids.add(target_uid)

            # incoming cross-partition links need to be checked for followup nodes in the other partition
            # even though we're not interested in the links themselves as they will be delivered with the nodes
            # in the other partition.
            # having to deliver followupnodes for links that aren't even our business is really annoying.
            for from_partition_id, inlinks in self.inlinks.items():
                from_partition = self.nodenet.partitions[from_partition_id]
                from_elements = inlinks[0].get_value(borrow=True)
                to_elements = inlinks[1].get_value(borrow=True)
                w = inlinks[2].get_value(borrow=True)
                slots, gates = np.nonzero(w)
                for index, gate_index in enumerate(gates):
                    source_id = from_partition.allocated_elements_to_nodes[from_elements[gate_index]]
                    source_uid = node_to_id(source_id, from_partition.pid)

                    slot_index = slots[index]
                    target_id = self.allocated_elements_to_nodes[to_elements[slot_index]]
                    target_uid = node_to_id(target_id, self.pid)
                    if target_uid in nodes:
                        followupuids.add(source_uid)

        return nodes, followupuids

    def integrity_check(self):

        for nid in range(self.NoN):
            nodetype = self.allocated_nodes[nid]

            if nodetype == 0:
                continue

            number_of_elements = get_elements_per_type(nodetype, self.nodenet.native_modules)

            elements = np.where(self.allocated_elements_to_nodes == nid)[0]
            if len(elements) != number_of_elements:
                self.logger.error("Integrity check error: Number of elements for node n%i should be %i, but is %i" % (nid, number_of_elements, len(elements)))

            if number_of_elements > 0:
                offset = self.allocated_node_offsets[nid]
                if elements[0] != offset:
                    self.logger.error("Integrity check error: First element for node n%i should be at %i, but is at %i" % (nid, offset, elements[0]))

                for eid in range(number_of_elements):
                    if self.allocated_elements_to_nodes[offset+eid] != nid:
                        self.logger.error("Integrity check error: Element %i of node n%i is allocated to node n%i" % (eid, nid, self.allocated_elements_to_nodes[offset+eid]))

                for snid in range(self.NoN):

                    if snid == nid:
                        continue

                    snodetype = self.allocated_nodes[snid]

                    if snodetype == 0:
                        continue

                    soffset = self.allocated_node_offsets[snid]
                    snumber_of_elements = get_elements_per_type(snodetype, self.nodenet.native_modules)

                    for selement in range(soffset, snumber_of_elements):
                        for element in range(offset, number_of_elements):
                            if element == selement:
                                self.logger.error("Integrity check error: Overlap at element %i, claimed by nodes n%i and n%i" % (element, nid, snid))
