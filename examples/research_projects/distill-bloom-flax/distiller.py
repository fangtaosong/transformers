# coding=utf-8
# Copyright 2022-present, the HuggingFace Inc. team.
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
import math
import os
import time

import jax
import jax.nn as nn
import jax.numpy as jnp
import wandb

import optax

# from flax.training.train_state import TrainState
import flax
from flax import optim
from flax.linen import partitioning as flax_partitioning
from flax.core.frozen_dict import freeze
from flax.core.frozen_dict import FrozenDict
from jax import jit, vmap, pmap
from jax.experimental import PartitionSpec as P

from t5x.partitioning import PjitPartitioner
from t5x.train_state import FlaxOptimTrainState, InferenceState


from logging_utils import logger
from utils.distill_utils import one_hot, logical_axis_rules_full

AxisMetadata = flax_partitioning.AxisMetadata

# copied from: https://github.com/sanchit-gandhi/seq2seq-speech/blob/cfc6d73959486f5bd71c623ddd95843d62f5a614/run_flax_speech_recognition_seq2seq.py#L338
def to_bf16(t):
    return jax.tree_map(lambda x: x.astype(jnp.bfloat16) if x.dtype == jnp.float32 else x, t)

class Distiller:
    def __init__(self, params, dataset, teacher, student, student_params, teacher_params, dtype):
        self.params = params
        self.dataset = dataset
        self.dtype = dtype

        self.teacher_model = teacher  # Empty modules
        self.student_model = student

        self.student_params = student_params
        self.teacher_params = teacher_params

        logger.info("Initializing Flax functions and utilities")

        rng = jax.random.PRNGKey(self.params.seed)
        self.rng, self.dropout_rng = jax.random.split(rng)

        logger.info("Initializing Partitionner")

        # Here we initialize the Jax partitionner to get the param specs
        self._init_partitionner()

        # Step 1: partition the student model! 
        self._partition_student_model()

        # Step 2: initialize optimizer
        # No need to partition the optimizer state since this is done automatically if the student
        # model is partitioned
        self._init_optimizer()

        # Step 3: partition the student model
        self._partition_teacher_model()

        # Step 4: partition all the necessary forward functions
        self._init_p_forward_fn()

    def _init_partitionner(self):
        r"""
            Utility function to initialize the partitionner. This is needed to partition the rest 
            of the attributes (model, optimizer) that are used later.

            A dummy state needs to be created to get the mesh_axes object.
            Function inspired from the snippet: https://github.com/huggingface/bloom-jax-inference/blob/2a04aa519d262729d54adef3d19d63879f81ea89/sharding_example.py#L67-L82 
        """
        num_mp_partitions = jax.device_count()
        self.partitioner = PjitPartitioner(num_mp_partitions, logical_axis_rules=logical_axis_rules_full)

        param_axes = jax.eval_shape(self._init_fn)["params_axes"]

        dummy_state = InferenceState(
            step=jnp.array(0),
            params=freeze(self.student_model.params_shape_tree),
            params_axes=freeze(param_axes),
            flax_mutables=None,
            flax_mutables_axes=param_axes,
        )

        mesh_axes = self.partitioner.get_mesh_axes(dummy_state)
        self.params_spec = mesh_axes.params

        # Delete the intermediate variable
        dummy_state = None

    def _init_optimizer(self):
        r"""
            Initialize the optimizer by just creating it using t5x.FlaxOptimTrainState
            The optimizer does not need to be partitionned if the partition function of the model has been called before 
            calling this function.
        """
        # tx = getattr(optax, self.params.optimizer_name)(self.params.learning_rate)
        optimizer_def = optim.GradientDescent(learning_rate=self.params.learning_rate)
        param_axes = jax.tree_map(lambda x: AxisMetadata(tuple(x)), self.params_spec)
        # optimizer = optimizer_def.create(self.student_params)
        model_variables = flax.core.freeze({"params": self.student_params, "params_axes": param_axes})
        self.state = FlaxOptimTrainState.create(optimizer_def, model_variables)

    def _init_fn(self):
        input_shape = (1, 1)
        input_ids = jnp.zeros(input_shape, dtype="i4")
        attention_mask = jnp.ones_like(input_ids)
        rng = jax.random.PRNGKey(0)
        return self.student_model.module.init(rng, input_ids, attention_mask, return_dict=False)

    def _partition_student_model(self):
        r"""
            Function to partition the student model 
            Snippet inspired from: https://github.com/huggingface/bloom-jax-inference/blob/2a04aa519d262729d54adef3d19d63879f81ea89/sharding_example.py#L84
        """
        shard_params = self.partitioner.partition(lambda x: x, (self.params_spec,), self.params_spec)
        self.student_params = shard_params(freeze(self.student_params))

    def _partition_teacher_model(self):
        r"""
            Function to partition the teacher model 
            Snippet inspired from: https://github.com/huggingface/bloom-jax-inference/blob/2a04aa519d262729d54adef3d19d63879f81ea89/sharding_example.py#L84
        """
        shard_params = self.partitioner.partition(lambda x: x, (self.params_spec,), self.params_spec)
        self.teacher_params = shard_params(freeze(self.teacher_params))

    def _init_p_forward_fn(self):
        r"""
            Utility function to partition the loss computations and forward functions
        """
        self._ce_loss = self.partitioner.partition(
            self._ce_loss, in_axis_resources=(P("data"), P("data")), out_axis_resources=None
        )
        # out axis has to be None since the output is a scalar

        self._lm_loss = self.partitioner.partition(
            self._lm_loss, in_axis_resources=(P("data"), P("data")), out_axis_resources=None
        )
        # out axis has to be None since the output is a scalar

        self.batched_student_step = self.partitioner.partition(
            self._student_step,
            in_axis_resources=(self.params_spec, P("data"), P("data"), P("data")),
            out_axis_resources=None,
        )
        self.batched_teacher_step = self.partitioner.partition(
            self._teacher_step, in_axis_resources=(self.params_spec, P("data")), out_axis_resources=P("data")
        )

    def _compute_loss(self, params, logits_teacher, batch, one_hot_labels):
        loss = self.batched_student_step(params, logits_teacher, batch, one_hot_labels)
        return jnp.mean(loss)

    def _student_step(self, params, logits_teacher, sequence, one_hot_label):
        # STEP1: get student logits
        logits_student = self.student_model(sequence, params=params).logits[:, -1, :]

        # STEP2: get ce loss
        _ce_loss = self._ce_loss(logits_student, logits_teacher)
        _lm_loss = self._lm_loss(logits_student, one_hot_label)

        return jnp.array(_ce_loss + _lm_loss)

    def _teacher_step(self, params, sequence):
        # sequence = jnp.expand_dims(sequence, 0)
        final_logits = self.teacher_model(sequence, params=params).logits[:, -1, :]
        return final_logits

    def _ce_loss(self, logits_student, logits_teacher):
        """
        Distillation loss as defined in Distill-BERT https://arxiv.org/pdf/1910.01108.pdf
        """
        if self.dtype != jnp.float32:
            logits_student = to_bf16(logits_student)
            logits_teacher = to_bf16(logits_teacher)
        probs_teacher = nn.softmax(logits_teacher, axis=-1) + 1e-8
        probs_student = nn.softmax(logits_student, axis=-1) + 1e-8

        loss = probs_teacher * (-jnp.log(probs_student))
        return jnp.array(jnp.sum(loss))

    def _lm_loss(self, logits_student, one_hot_label):
        """
        Distillation loss as defined in Distill-BERT https://arxiv.org/pdf/1910.01108.pdf
        """
        if self.dtype != jnp.float32:
            logits_student = to_bf16(logits_student)
            one_hot_label = to_bf16(one_hot_label)
        probs_student = nn.softmax(logits_student, axis=-1) + 1e-8

        loss = one_hot_label * (-jnp.log(probs_student))
        return jnp.array(jnp.sum(loss))

    def _log_param_norm(self, grad):
        layer_grad_norm = jax.tree_map(jnp.linalg.norm, grad).unfreeze()
        logs = {
            "layer_grad_norm": layer_grad_norm,
            "transformer_norm": jnp.linalg.norm(jax.tree_util.tree_leaves(layer_grad_norm["transformer"])),
        }
        logs["transformer_grad_norm"] = jnp.linalg.norm([logs["transformer_norm"]])

        # compute parameter norms over all layers, total encoder, total decoder and global for detailed monitoring
        layer_param_norm = jax.tree_map(jnp.linalg.norm, self.state.params).unfreeze()
        logs["layer_param_norm"] = layer_param_norm
        logs["transformer_norm"] = jnp.linalg.norm(jax.tree_util.tree_leaves(layer_param_norm["transformer"]))
        logs["param_norm"] = jnp.linalg.norm(jax.tree_util.tree_leaves(layer_param_norm))
        return logs

    def _log_metrics(self, metrics, step, prefix=None):
        if jax.process_index() == 0:
            log_metrics = {}
            for k, v in metrics.items():
                if "layer" in k:
                    log_metrics[f"{k}/"] = v
                elif prefix is not None:
                    log_metrics[f"{prefix}/{k}"] = v
                else:
                    log_metrics[k] = v

            wandb.log(log_metrics, step)

    def train(self):
        wandb.init(
            project=self.params.wandb_project,
            entity=self.params.wandb_entity,
            config=self.params,
            dir=self.params.wandb_logs,
        )

        step = 0

        for epoch in range(self.params.epochs):
            for batch in self.dataset:

                # Loop over each token, get the predictions from the teacher + student and perform backpropagation
                for i in range(1, self.params.max_seq_len - 1):
                    # step 1: get the teacher loss
                    # logits_teacher = self.batched_teacher_step(teacher_model.params, batch[:, :i])
                    logits_teacher = self.batched_teacher_step(self.teacher_params, batch[:, :i])
                    # step2: one hot encode the next tokens
                    one_hot_labels = one_hot(batch[:, i + 1], self.params.vocab_size)

                    # step3: perform backpropagation by computing student's loss
                    # Line below are copied and adapted from https://github.com/huggingface/transformers/blob/2c5747edfe383eee073119de784fa148befe9f2d/examples/flax/summarization/run_summarization_flax.py#L786
                    grad_fn = jax.value_and_grad(self._compute_loss)
                    loss, grad = grad_fn(self.state.params, logits_teacher, batch[:, :i], one_hot_labels)

                    print("Loss ={}".format(loss.item()))

                    # Average the gradients and the loss
                    grad = jax.tree_map(lambda g: g / self.params.batch_size, grad)
                    loss = jax.tree_map(lambda l: l / self.params.batch_size, loss)
                    # End copied lines

                    # Inspired from: https://github.com/google-research/t5x/blob/29a14ae2d77e74800f7f66645b333d9faf83ae61/t5x/train_state_test.py#L226
                    self.state = self.state.apply_gradient(grads=grad, learning_rate=self.params.learning_rate)
                    self.student_params = self.state.params

                    # step4: yey! log the results
                    logs = {"loss": loss.item(), "learning_rate": self.params.learning_rate}

                    # log param norm and grad norm
                    # Copied from: https://github.com/sanchit-gandhi/seq2seq-speech/blob/cfc6d73959486f5bd71c623ddd95843d62f5a614/run_flax_speech_recognition_seq2seq.py#L638
                    # compute gradient norms over all layers, total encoder, total decoder and global for detailed monitoring
                    norm_logs = self._log_param_norm(grad)
                    logs.update(norm_logs)
                    self._log_metrics(logs, step)

                    step += 1

                break
