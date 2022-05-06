# coding=utf-8
# Copyright 2020 The HuggingFace Team. All rights reserved.
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


import datetime
import math
import unittest

from transformers import BigScience176BConfig, is_torch_available
from transformers.testing_utils import require_torch, slow, torch_device

from ..generation.test_generation_utils import GenerationTesterMixin
from ..test_configuration_common import ConfigTester
from ..test_modeling_common import ModelTesterMixin, ids_tensor, random_attention_mask


if is_torch_available():
    import torch

    from transformers import (
        BIGSCIENCE176B_PRETRAINED_MODEL_ARCHIVE_LIST,
        BigScience176BLMHeadModel,
        BigScience176BModel,
        BigScience176BTokenizer,
    )


class BigScience176BModelTester:
    def __init__(
        self,
        parent,
        batch_size=14,
        seq_length=7,
        is_training=True,
        use_token_type_ids=True,
        use_input_mask=True,
        use_labels=True,
        use_mc_token_ids=True,
        vocab_size=99,
        hidden_size=32,
        num_hidden_layers=5,
        num_attention_heads=4,
        intermediate_size=37,
        hidden_act="gelu",
        hidden_dropout_prob=0.1,
        attention_probs_dropout_prob=0.1,
        max_position_embeddings=512,
        type_vocab_size=16,
        type_sequence_label_size=2,
        initializer_range=0.02,
        num_labels=3,
        num_choices=4,
        scope=None,
    ):
        self.parent = parent
        self.batch_size = batch_size
        self.seq_length = seq_length
        self.is_training = is_training
        self.use_token_type_ids = use_token_type_ids
        self.use_input_mask = use_input_mask
        self.use_labels = use_labels
        self.use_mc_token_ids = use_mc_token_ids
        self.vocab_size = vocab_size
        self.hidden_size = hidden_size
        self.num_hidden_layers = num_hidden_layers
        self.num_attention_heads = num_attention_heads
        self.intermediate_size = intermediate_size
        self.hidden_act = hidden_act
        self.hidden_dropout_prob = hidden_dropout_prob
        self.attention_probs_dropout_prob = attention_probs_dropout_prob
        self.max_position_embeddings = max_position_embeddings
        self.type_vocab_size = type_vocab_size
        self.type_sequence_label_size = type_sequence_label_size
        self.initializer_range = initializer_range
        self.num_labels = num_labels
        self.num_choices = num_choices
        self.scope = None
        self.bos_token_id = vocab_size - 1
        self.eos_token_id = vocab_size - 1
        self.pad_token_id = vocab_size - 1

    def get_large_model_config(self):
        return BigScience176BConfig.from_pretrained("bigscience176b")

    def prepare_config_and_inputs(self, gradient_checkpointing=False):
        input_ids = ids_tensor([self.batch_size, self.seq_length], self.vocab_size)

        input_mask = None
        if self.use_input_mask:
            input_mask = random_attention_mask([self.batch_size, self.seq_length])

        config = self.get_config(
            gradient_checkpointing=gradient_checkpointing,
        )

        return (
            config,
            input_ids,
            input_mask,
        )

    def get_config(self, gradient_checkpointing=False):
        return BigScience176BConfig(
            vocab_size=self.vocab_size,
            seq_length=self.seq_length,
            n_embd=self.hidden_size,
            n_layer=self.num_hidden_layers,
            n_head=self.num_attention_heads,
            n_inner=self.intermediate_size,
            activation_function=self.hidden_act,
            resid_pdrop=self.hidden_dropout_prob,
            attn_pdrop=self.attention_probs_dropout_prob,
            n_positions=self.max_position_embeddings,
            type_vocab_size=self.type_vocab_size,
            initializer_range=self.initializer_range,
            use_cache=True,
            bos_token_id=self.bos_token_id,
            eos_token_id=self.eos_token_id,
            pad_token_id=self.pad_token_id,
            gradient_checkpointing=gradient_checkpointing,
        )

    def create_and_check_bigscience176b_model(self, config, input_ids, input_mask, *args):
        model = BigScience176BModel(config=config)
        model.to(torch_device)
        model.eval()

        result = model(input_ids)

        self.parent.assertEqual(result.last_hidden_state.shape, (self.batch_size, self.seq_length, self.hidden_size))
        self.parent.assertEqual(len(result.past_key_values), config.n_layer)

    def create_and_check_bigscience176b_model_past(self, config, input_ids, input_mask, *args):
        model = BigScience176BModel(config=config)
        model.to(torch_device)
        model.eval()

        # first forward pass
        outputs = model(input_ids, use_cache=True)
        outputs_use_cache_conf = model(input_ids)
        outputs_no_past = model(input_ids, use_cache=False)

        self.parent.assertTrue(len(outputs) == len(outputs_use_cache_conf))
        self.parent.assertTrue(len(outputs) == len(outputs_no_past) + 1)

        output, past = outputs.to_tuple()

        # create hypothetical next token and extent to next_input_ids
        next_tokens = ids_tensor((self.batch_size, 1), config.vocab_size)

        # append to next input_ids and token_type_ids
        next_input_ids = torch.cat([input_ids, next_tokens], dim=-1)

        output_from_no_past = model(next_input_ids)["last_hidden_state"]
        output_from_past = model(next_tokens, past_key_values=past)["last_hidden_state"]

        # select random slice
        random_slice_idx = ids_tensor((1,), output_from_past.shape[-1]).item()
        output_from_no_past_slice = output_from_no_past[:, -1, random_slice_idx].detach()
        output_from_past_slice = output_from_past[:, 0, random_slice_idx].detach()

        # test that outputs are equal for slice
        self.parent.assertTrue(torch.allclose(output_from_past_slice, output_from_no_past_slice, atol=1e-3))

    def create_and_check_bigscience176b_model_attention_mask_past(self, config, input_ids, input_mask, *args):
        model = BigScience176BModel(config=config)
        model.to(torch_device)
        model.eval()

        # create attention mask
        attn_mask = torch.ones(input_ids.shape, dtype=torch.long, device=torch_device)
        half_seq_length = self.seq_length // 2
        attn_mask[:, half_seq_length:] = 0

        # first forward pass
        output, past = model(input_ids, attention_mask=attn_mask).to_tuple()

        # create hypothetical next token and extent to next_input_ids
        next_tokens = ids_tensor((self.batch_size, 1), config.vocab_size)

        # change a random masked slice from input_ids
        random_seq_idx_to_change = ids_tensor((1,), half_seq_length).item() + 1
        random_other_next_tokens = ids_tensor((self.batch_size, 1), config.vocab_size).squeeze(-1)
        input_ids[:, -random_seq_idx_to_change] = random_other_next_tokens

        # append to next input_ids and attn_mask
        next_input_ids = torch.cat([input_ids, next_tokens], dim=-1)
        attn_mask = torch.cat(
            [attn_mask, torch.ones((attn_mask.shape[0], 1), dtype=torch.long, device=torch_device)],
            dim=1,
        )

        # get two different outputs
        output_from_no_past = model(next_input_ids, attention_mask=attn_mask)["last_hidden_state"]
        output_from_past = model(next_tokens, past_key_values=past, attention_mask=attn_mask)["last_hidden_state"]

        # select random slice
        random_slice_idx = ids_tensor((1,), output_from_past.shape[-1]).item()
        output_from_no_past_slice = output_from_no_past[:, -1, random_slice_idx].detach()
        output_from_past_slice = output_from_past[:, 0, random_slice_idx].detach()

        # test that outputs are equal for slice
        self.parent.assertTrue(torch.allclose(output_from_past_slice, output_from_no_past_slice, atol=1e-3))

    def create_and_check_bigscience176b_model_past_large_inputs(self, config, input_ids, input_mask, *args):
        model = BigScience176BModel(config=config)
        model.to(torch_device)
        model.eval()

        # first forward pass
        outputs = model(input_ids, attention_mask=input_mask, use_cache=True)

        output, past = outputs.to_tuple()

        # create hypothetical next token and extent to next_input_ids
        next_tokens = ids_tensor((self.batch_size, 3), config.vocab_size)
        next_mask = ids_tensor((self.batch_size, 3), vocab_size=2)

        # append to next input_ids and token_type_ids
        next_input_ids = torch.cat([input_ids, next_tokens], dim=-1)
        next_attention_mask = torch.cat([input_mask, next_mask], dim=-1)

        output_from_no_past = model(next_input_ids, attention_mask=next_attention_mask)["last_hidden_state"]
        output_from_past = model(next_tokens, attention_mask=next_attention_mask, past_key_values=past)[
            "last_hidden_state"
        ]
        self.parent.assertTrue(output_from_past.shape[1] == next_tokens.shape[1])

        # select random slice
        random_slice_idx = ids_tensor((1,), output_from_past.shape[-1]).item()
        output_from_no_past_slice = output_from_no_past[:, -3:, random_slice_idx].detach()
        output_from_past_slice = output_from_past[:, :, random_slice_idx].detach()

        # test that outputs are equal for slice
        self.parent.assertTrue(torch.allclose(output_from_past_slice, output_from_no_past_slice, atol=1e-3))

    def create_and_check_lm_head_model(self, config, input_ids, input_mask, *args):
        model = BigScience176BLMHeadModel(config)
        model.to(torch_device)
        model.eval()

        result = model(input_ids, labels=input_ids)
        self.parent.assertEqual(result.loss.shape, ())
        self.parent.assertEqual(result.logits.shape, (self.batch_size, self.seq_length, self.vocab_size))

    def create_and_check_forward_and_backwards(
        self, config, input_ids, input_mask, *args, gradient_checkpointing=False
    ):
        model = BigScience176BLMHeadModel(config)
        model.to(torch_device)
        if gradient_checkpointing:
            model.gradient_checkpointing_enable()

        result = model(input_ids, labels=input_ids)
        self.parent.assertEqual(result.loss.shape, ())
        self.parent.assertEqual(result.logits.shape, (self.batch_size, self.seq_length, self.vocab_size))
        result.loss.backward()

    def create_and_check_bigscience176b_weight_initialization(self, config, *args):
        model = BigScience176BModel(config)
        model_std = model.config.initializer_range / math.sqrt(2 * model.config.n_layer)
        for key in model.state_dict().keys():
            if "c_proj" in key and "weight" in key:
                self.parent.assertLessEqual(abs(torch.std(model.state_dict()[key]) - model_std), 0.001)
                self.parent.assertLessEqual(abs(torch.mean(model.state_dict()[key]) - 0.0), 0.01)

    def prepare_config_and_inputs_for_common(self):
        config_and_inputs = self.prepare_config_and_inputs()

        (
            config,
            input_ids,
            input_mask,
        ) = config_and_inputs

        inputs_dict = {
            "input_ids": input_ids,
        }

        return config, inputs_dict


@require_torch
class BigScience176BModelTest(ModelTesterMixin, GenerationTesterMixin, unittest.TestCase):

    all_model_classes = (BigScience176BModel, BigScience176BLMHeadModel) if is_torch_available() else ()
    all_generative_model_classes = (BigScience176BLMHeadModel,) if is_torch_available() else ()
    all_parallelizable_model_classes = (BigScience176BLMHeadModel,) if is_torch_available() else ()
    fx_compatible = False
    test_missing_keys = False
    test_model_parallel = True

    def setUp(self):
        self.model_tester = BigScience176BModelTester(self)
        self.config_tester = ConfigTester(self, config_class=BigScience176BConfig, n_embd=37)

    def test_config(self):
        self.config_tester.run_common_tests()

    def test_bigscience176b_model(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_bigscience176b_model(*config_and_inputs)

    def test_bigscience176b_model_past(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_bigscience176b_model_past(*config_and_inputs)

    def test_bigscience176b_model_att_mask_past(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_bigscience176b_model_attention_mask_past(*config_and_inputs)

    def test_bigscience176b_model_past_large_inputs(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_bigscience176b_model_past_large_inputs(*config_and_inputs)

    def test_bigscience176b_lm_head_model(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_lm_head_model(*config_and_inputs)

    def test_bigscience176b_gradient_checkpointing(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_forward_and_backwards(*config_and_inputs, gradient_checkpointing=True)

    def test_bigscience176b_weight_initialization(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_bigscience176b_weight_initialization(*config_and_inputs)

    @slow
    def test_batch_generation(self):
        model = BigScience176BLMHeadModel.from_pretrained("bigscience176b")
        model.to(torch_device)
        tokenizer = BigScience176BTokenizer.from_pretrained("bigscience176b")

        tokenizer.padding_side = "left"

        # Define PAD Token = EOS Token = 50256
        tokenizer.pad_token = tokenizer.eos_token
        model.config.pad_token_id = model.config.eos_token_id

        # use different length sentences to test batching
        sentences = [
            "Hello, my dog is a little",
            "Today, I",
        ]

        inputs = tokenizer(sentences, return_tensors="pt", padding=True)
        input_ids = inputs["input_ids"].to(torch_device)
        token_type_ids = torch.cat(
            [
                input_ids.new_full((input_ids.shape[0], input_ids.shape[1] - 1), 0),
                input_ids.new_full((input_ids.shape[0], 1), 500),
            ],
            dim=-1,
        )

        outputs = model.generate(
            input_ids=input_ids,
            attention_mask=inputs["attention_mask"].to(torch_device),
        )

        outputs_tt = model.generate(
            input_ids=input_ids,
            attention_mask=inputs["attention_mask"].to(torch_device),
            token_type_ids=token_type_ids,
        )

        inputs_non_padded = tokenizer(sentences[0], return_tensors="pt").input_ids.to(torch_device)
        output_non_padded = model.generate(input_ids=inputs_non_padded)

        num_paddings = inputs_non_padded.shape[-1] - inputs["attention_mask"][-1].long().sum().cpu().item()
        inputs_padded = tokenizer(sentences[1], return_tensors="pt").input_ids.to(torch_device)
        output_padded = model.generate(input_ids=inputs_padded, max_length=model.config.max_length - num_paddings)

        batch_out_sentence = tokenizer.batch_decode(outputs, skip_special_tokens=True)
        batch_out_sentence_tt = tokenizer.batch_decode(outputs_tt, skip_special_tokens=True)
        non_padded_sentence = tokenizer.decode(output_non_padded[0], skip_special_tokens=True)
        padded_sentence = tokenizer.decode(output_padded[0], skip_special_tokens=True)

        expected_output_sentence = [
            "Hello, my dog is a little bit of a mess. I'm not sure if he's going",
            "Today, I'm going to be doing a lot of research on this. I",
        ]
        self.assertListEqual(expected_output_sentence, batch_out_sentence)
        self.assertTrue(batch_out_sentence_tt != batch_out_sentence)  # token_type_ids should change output
        self.assertListEqual(expected_output_sentence, [non_padded_sentence, padded_sentence])

    @slow
    def test_model_from_pretrained(self):
        for model_name in BIGSCIENCE176B_PRETRAINED_MODEL_ARCHIVE_LIST[:1]:
            model = BigScience176BModel.from_pretrained(model_name)
            self.assertIsNotNone(model)


@require_torch
class BigScience176BModelLanguageGenerationTest(unittest.TestCase):
    def _test_lm_generate_bigscience176b_helper(
        self,
        gradient_checkpointing=False,
        verify_outputs=True,
    ):
        model = BigScience176BLMHeadModel.from_pretrained(
            "bigscience176b",
        )
        if gradient_checkpointing:
            model.gradient_checkpointing_enable()
        else:
            model.gradient_checkpointing_disable()
        model.to(torch_device)

        # The dog
        input_ids = torch.tensor([[464, 3290]], dtype=torch.long, device=torch_device)

        # The dog was found in a field near the intersection of West and West Streets.\n\nThe dog
        # fmt: off
        expected_output_ids = [
            464, 3290, 373, 1043, 287, 257, 2214, 1474, 262, 16246, 286, 2688, 290, 2688, 27262, 13, 198, 198, 464, 3290,
        ]
        # fmt: on
        output_ids = model.generate(input_ids, do_sample=False)
        if verify_outputs:
            self.assertListEqual(output_ids[0].tolist(), expected_output_ids)

    @slow
    def test_lm_generate_bigscience176b(self):
        self._test_lm_generate_bigscience176b_helper()

    @slow
    def test_lm_generate_bigscience176b_with_gradient_checkpointing(self):
        self._test_lm_generate_bigscience176b_helper(gradient_checkpointing=True)

    @slow
    def test_bigscience176b_sample(self):
        tokenizer = BigScience176BTokenizer.from_pretrained("bigscience176b")
        model = BigScience176BLMHeadModel.from_pretrained("bigscience176b")
        model.to(torch_device)

        torch.manual_seed(0)
        tokenized = tokenizer("Today is a nice day and", return_tensors="pt", return_token_type_ids=True)
        input_ids = tokenized.input_ids.to(torch_device)
        output_ids = model.generate(input_ids, do_sample=True)
        output_str = tokenizer.decode(output_ids[0], skip_special_tokens=True)

        token_type_ids = tokenized.token_type_ids.to(torch_device)
        output_seq = model.generate(input_ids=input_ids, do_sample=True, num_return_sequences=5)
        output_seq_tt = model.generate(
            input_ids=input_ids, token_type_ids=token_type_ids, do_sample=True, num_return_sequences=5
        )
        output_seq_strs = tokenizer.batch_decode(output_seq, skip_special_tokens=True)
        output_seq_tt_strs = tokenizer.batch_decode(output_seq_tt, skip_special_tokens=True)

        EXPECTED_OUTPUT_STR = (
            "Today is a nice day and if you don't know anything about the state of play during your holiday"
        )
        self.assertEqual(output_str, EXPECTED_OUTPUT_STR)
        self.assertTrue(
            all([output_seq_strs[idx] != output_seq_tt_strs[idx] for idx in range(len(output_seq_tt_strs))])
        )  # token_type_ids should change output

    @slow
    def test_bigscience176b_sample_max_time(self):
        tokenizer = BigScience176BTokenizer.from_pretrained("bigscience176b")
        model = BigScience176BLMHeadModel.from_pretrained("bigscience176b")
        model.to(torch_device)

        torch.manual_seed(0)
        tokenized = tokenizer("Today is a nice day and", return_tensors="pt", return_token_type_ids=True)
        input_ids = tokenized.input_ids.to(torch_device)

        MAX_TIME = 0.5

        start = datetime.datetime.now()
        model.generate(input_ids, do_sample=True, max_time=MAX_TIME, max_length=256)
        duration = datetime.datetime.now() - start
        self.assertGreater(duration, datetime.timedelta(seconds=MAX_TIME))
        self.assertLess(duration, datetime.timedelta(seconds=1.5 * MAX_TIME))

        start = datetime.datetime.now()
        model.generate(input_ids, do_sample=False, max_time=MAX_TIME, max_length=256)
        duration = datetime.datetime.now() - start
        self.assertGreater(duration, datetime.timedelta(seconds=MAX_TIME))
        self.assertLess(duration, datetime.timedelta(seconds=1.5 * MAX_TIME))

        start = datetime.datetime.now()
        model.generate(input_ids, do_sample=False, num_beams=2, max_time=MAX_TIME, max_length=256)
        duration = datetime.datetime.now() - start
        self.assertGreater(duration, datetime.timedelta(seconds=MAX_TIME))
        self.assertLess(duration, datetime.timedelta(seconds=1.5 * MAX_TIME))

        start = datetime.datetime.now()
        model.generate(input_ids, do_sample=True, num_beams=2, max_time=MAX_TIME, max_length=256)
        duration = datetime.datetime.now() - start
        self.assertGreater(duration, datetime.timedelta(seconds=MAX_TIME))
        self.assertLess(duration, datetime.timedelta(seconds=1.5 * MAX_TIME))

        start = datetime.datetime.now()
        model.generate(input_ids, do_sample=False, max_time=None, max_length=256)
        duration = datetime.datetime.now() - start
        self.assertGreater(duration, datetime.timedelta(seconds=1.5 * MAX_TIME))