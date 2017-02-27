# Copyright (c) 2016 PaddlePaddle Authors. All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Before this new package paddle.v2.layer, users would need to use functions
in paddle.trainer_config_helpers.layers to configure networks.

The Old Way:
=========
This old way requires that the creation of a network be defined in a Python
function, say network_config, and that this Python function being passed to
paddle.trainer_config_helpers.parse_network_config for the creation of
protobuf message description of this network.

```python
def network_config():
  img = paddle.trainer_config_helpers.data_layer(name="pixel", size=784)
  inference = paddle.trainer_config_helpers.fc_layer(
    input=img,
    size=10,
    act=paddle.trainer_config_helpers.SoftmaxActivation())
  cost = paddle.trainer_config_helpers.classification_cost(
    input=inference,
    label=paddle.trainer_config_helpers.data_layer(name="label", size=10))

proto_desc = parse_network_config(network_config)
```

When parse_network_config executes network_config, those layer definition
functions like data_layer and fc_layer would change some Python global variables,
so that after the execution, parse_network_config could collect information from
these global variables and generates the protobuf message.



The New Way:
=========
In this PR, we define a function in paddle.v2.layer which creates a Python
class for each layer creation function in paddle.trainer_config_helpers.layers.
Users can use create a network as follows:

```python
img = paddle.v2.layer.data(name="pixel", size=784)
inference = paddle.v2.layer.fc(input=img, size=10, act=paddle.v2.layer.Softmax())
cost = paddle.v2.layer.classification(
  input=inference,
  label=paddle.v2.layer.data(name="label", size=10))

parameters = paddle.v2.parameters.create(cost)
```

This new way doesn't require those invocations to layer definition functions
to be in a Python function but could be anywhere.

Also, the creation of a protobuf message is hidden in the invocation of
paddle.v2.parameters.create, no longer exposed to users.
"""

import collections

import paddle.trainer_config_helpers as conf_helps
from paddle.trainer_config_helpers.config_parser_utils import \
    parse_network_config as __parse__
from paddle.trainer_config_helpers.default_decorators import wrap_name_default

import data_type

__all__ = [
    'parse_network', 'data', 'fc', 'conv_shift', 'img_conv', 'img_pool', 'spp',
    'maxout', 'img_cmrnorm', 'batch_norm', 'sum_to_one_norm', 'recurrent',
    'lstmemory', 'grumemory', 'pool', 'last_seq', 'first_seq', 'concat',
    'seq_concat', 'block_expand', 'expand', 'repeat', 'seq_reshape', 'addto',
    'linear_comb', 'interpolation', 'bilinear_interp', 'power', 'scaling',
    'slope_intercept', 'tensor', 'cos_sim', 'trans', 'max_id', 'sampling_id',
    'pad', 'classification_cost', 'cross_entropy_cost',
    'cross_entropy_with_selfnorm_cost', 'regression_cost',
    'multi_binary_label_cross_entropy_cost', 'rank_cost', 'lambda_cost',
    'sum_cost', 'huber_cost', 'crf', 'crf_decoding', 'ctc', 'warp_ctc', 'nce',
    'hsigmoid', 'eos'
]


def parse_network(*outputs):
    """
    parse all output layers and then generate a model config proto.
    :param outputs:
    :return:
    """

    def __real_func__():
        context = dict()
        real_output = [each.to_proto(context=context) for each in outputs]
        conf_helps.outputs(real_output)

    return __parse__(__real_func__)


class Layer(object):
    def __init__(self, name, parent_layers):
        assert isinstance(parent_layers, dict)
        assert isinstance(name, basestring)
        self.name = name
        self.__parent_layers__ = parent_layers

    def to_proto(self, context):
        """
        function to set proto attribute
        """
        kwargs = dict()
        for layer_name in self.__parent_layers__:
            if not isinstance(self.__parent_layers__[layer_name],
                              collections.Sequence):
                v1_layer = self.__parent_layers__[layer_name].to_proto(
                    context=context)
            else:
                v1_layer = map(lambda x: x.to_proto(context=context),
                               self.__parent_layers__[layer_name])
            kwargs[layer_name] = v1_layer

        if self.name not in context:
            context[self.name] = self.to_proto_impl(**kwargs)
        return context[self.name]

    def to_proto_impl(self, **kwargs):
        raise NotImplementedError()


def __convert_to_v2__(method_name, parent_names):
    wrapper = wrap_name_default(name_prefix=method_name)

    class V2LayerImpl(Layer):
        def __init__(self, name=None, **kwargs):
            parent_layers = dict()
            other_kwargs = dict()
            for pname in parent_names:
                if kwargs.has_key(pname):
                    parent_layers[pname] = kwargs[pname]

            for key in kwargs.keys():
                if key not in parent_names:
                    other_kwargs[key] = kwargs[key]

            super(V2LayerImpl, self).__init__(name, parent_layers)
            self.__other_kwargs__ = other_kwargs

        if wrapper is not None:
            __init__ = wrapper(__init__)

        def to_proto_impl(self, **kwargs):
            args = dict()
            for each in kwargs:
                args[each] = kwargs[each]
            for each in self.__other_kwargs__:
                args[each] = self.__other_kwargs__[each]
            return getattr(conf_helps, method_name)(name=self.name, **args)

    return V2LayerImpl


"""
Some layer may need some special config, and can not use __convert_to_v2__ to convert.
So we also need to implement some special LayerV2.
"""


class DataLayerV2(Layer):
    def __init__(self, name, type, **kwargs):
        assert isinstance(type, data_type.InputType)

        self.type = type
        self.__method_name__ = 'data_layer'
        self.__kwargs__ = kwargs

        super(DataLayerV2, self).__init__(name=name, parent_layers=dict())

    def to_proto_impl(self, **kwargs):
        args = dict()
        args['size'] = self.type.dim
        for each in kwargs:
            args[each] = kwargs[each]
        for each in self.__kwargs__:
            args[each] = self.__kwargs__[each]
        return getattr(conf_helps, self.__method_name__)(name=self.name, **args)


data = DataLayerV2
AggregateLevel = conf_helps.layers.AggregateLevel
ExpandLevel = conf_helps.layers.ExpandLevel

layer_list = [
    # [V2LayerImpl, V1_method_name, parent_names]
    # fully connected layers
    ['fc', 'fc_layer', ['input']],
    # conv layers
    ['conv_shift', 'conv_shift_layer', ['a', 'b']],
    ['img_conv', 'img_conv_layer', ['input']],
    # image pooling layers
    ['img_pool', 'img_pool_layer', ['input']],
    ['spp', 'spp_layer', ['input']],
    ['maxout', 'maxout_layer', ['input']],
    # norm layers
    ['img_cmrnorm', 'img_cmrnorm_layer', ['input']],
    ['batch_norm', 'batch_norm_layer', ['input']],
    ['sum_to_one_norm', 'sum_to_one_norm_layer', ['input']],
    # recurrent layers
    ['recurrent', 'recurrent_layer', ['input']],
    ['lstmemory', 'lstmemory', ['input']],
    ['grumemory', 'grumemory', ['input']],
    # aggregate layers
    ['pool', 'pooling_layer', ['input']],
    ['last_seq', 'last_seq', ['input']],
    ['first_seq', 'first_seq', ['input']],
    ['concat', 'concat_layer', ['input']],
    ['seq_concat', 'seq_concat_layer', ['a', 'b']],
    # reshaping layers
    ['block_expand', 'block_expand_layer', ['input']],
    ['expand', 'expand_layer', ['input', 'expand_as']],
    ['repeat', 'repeat_layer', ['input']],
    ['rotate', 'rotate_layer', ['input']],
    ['seq_reshape', 'seq_reshape_layer', ['input']],
    # math layers
    ['addto', 'addto_layer', ['input']],
    ['linear_comb', 'linear_comb_layer', ['weights', 'vectors']],
    ['interpolation', 'interpolation_layer', ['input', 'weight']],
    ['bilinear_interp', 'bilinear_interp_layer', ['input']],
    ['power', 'power_layer', ['input', 'weight']],
    ['scaling', 'scaling_layer', ['input', 'weight']],
    ['slope_intercept', 'slope_intercept_layer', ['input']],
    ['tensor', 'tensor_layer', ['a', 'b']],
    ['cos_sim', 'cos_sim', ['a', 'b']],
    ['trans', 'trans_layer', ['input']],
    # sampling layers
    ['max_id', 'maxid_layer', ['input']],
    ['sampling_id', 'sampling_id_layer', ['input']],
    # slicing and joining layers
    ['pad', 'pad_layer', ['input']],
    # cost layers
    [
        'classification_cost', 'classification_cost',
        ['input', 'label', 'weight']
    ],
    ['regression_cost', 'regression_cost', ['input', 'label', 'weight']],
    ['cross_entropy_cost', 'cross_entropy', ['input', 'label']],
    [
        'cross_entropy_with_selfnorm_cost', 'cross_entropy_with_selfnorm',
        ['input', 'label']
    ],
    [
        'multi_binary_label_cross_entropy_cost',
        'multi_binary_label_cross_entropy', ['input', 'label']
    ],
    ['rank_cost', 'rank_cost', ['left', 'right', 'label', 'weight']],
    ['lambda_cost', 'lambda_cost', ['input', 'score']],
    ['sum_cost', 'sum_cost', ['input']],
    ['huber_cost', 'huber_cost', ['input', 'label']],
    ['crf', 'crf_layer', ['input', 'label']],
    ['crf_decoding', 'crf_decoding_layer', ['input']],
    ['ctc', 'ctc_layer', ['input', 'label']],
    ['warp_ctc', 'warp_ctc_layer', ['input', 'label']],
    ['nce', 'nce_layer', ['input', 'label']],
    ['hsigmoid', 'hsigmoid', ['input', 'label']],
    # check layers
    ['eos', 'eos_layer', ['input']]
]
for l in layer_list:
    globals()[l[0]] = __convert_to_v2__(l[1], l[2])
