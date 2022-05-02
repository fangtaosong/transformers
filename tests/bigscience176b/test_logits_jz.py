import unittest

import torch
# import deepspeed

from transformers import AutoModel, AutoTokenizer
from transformers.models.bigscience176b import BigScience176BLMHeadModel


class BigScienceEmbeddingTest(unittest.TestCase):
    """
    The goal here is to compare the embeddings generated by the model trained
    using Megatron-LM with the one from the transformers library, with a small GPT2-like model
    to ensure that the conversion from Megatron-LM to transformers has been done successfully.
    The script compares the logits of the embedding layer and the transformer layers.

    WARNING: It is expected that these logits will not have exactly the same statistics when running
    the code on CPU or GPU. For more info, please visit:
      - https://github.com/pytorch/pytorch/issues/76052#issuecomment-1103193548
      - https://discuss.pytorch.org/t/reproducibility-issue-between-intel-and-amd-cpus/144779/9


    You need to install tokenizers following this readme:
        - https://huggingface.co/bigscience-catalogue-data-dev/byte-level-bpe-tokenizer-no-norm-250k-whitespace-and-eos-regex-alpha-v3-dedup-lines-articles

    Tokenizer used during training:
        - https://huggingface.co/bigscience-catalogue-data-dev/byte-level-bpe-tokenizer-no-norm-250k-whitespace-and-eos-regex-alpha-v3-dedup-lines-articles

    # TODO change the script (or just add skip) when building the env with tokenizers 0.12.0
    """

    def setUp(self):
        super().setUp()
        # self.path_tokenizer = "bigscience-catalogue-data-dev/byte-level-bpe-tokenizer-no-norm-250k-whitespace-and-eos-regex-alpha-v3-dedup-lines-articles"
        # self.tokenizer = AutoTokenizer.from_pretrained(self.path_tokenizer)
        self.path_bigscience_model = "/gpfswork/rech/six/uan68tv/model-conversion/tr11e-350M-transformers-sharded"

    # @unittest.skip("demonstrating skipping")
    @torch.no_grad()
    def test_logits(self):
        # TODO ifelse device
        model = BigScience176BLMHeadModel.from_pretrained(self.path_bigscience_model, use_cache=False)
        device_map = {
            0: [0, 1, 2, 3, 4, 5],
            1: [6, 7, 8, 9, 10, 11],
            2: [12, 13, 14, 15, 16, 17],
            3: [18, 19, 20, 21, 22, 23],
        }
        # device_map = {
        #     0: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        #     1: [10, 11, 12, 13, 14, 15, 16, 17, 18],
        #     2: [19, 20, 21, 22, 23, 24, 25, 26, 27],
        #     3: [28, 29, 30, 31, 32, 33, 34, 35, 36],
        #     4: [37, 38, 39, 40, 41, 42, 43, 44, 45],
        #     5: [46, 47, 48, 49, 50, 51, 52, 53, 54],
        #     6: [55, 56, 57, 58, 59, 60, 61, 62, 63],
        #     8: [64, 65, 66, 67, 68, 69, 70],
        # }
        model.parallelize(device_map)
        model.eval()

        EXAMPLE_IDS = [[2175,  23714,  73173, 144252, 2, 77, 132619, 3478, 368, 109586, 35433, 2, 2175,  23714,  73173, 144252, 2, 2175, 23714, 73173]]

        # a = torch.randn(1, 1, 20, 20)
        # ATTN_MASK = (torch.triu(a, diagonal=1) != 0).to("cuda:0")
        ATTN_MASK = torch.triu(torch.ones(1, 1, 20, 20), diagonal=1).to("cuda:0").to(model.dtype)
        
        # ATTN_MASK = torch.tensor([[[[False,  True,  True,  True,  True,  True,  True,  True,  True,  True,
        #         True,  True,  True,  True,  True,  True,  True,  True,  True,  True],
        #     [False, False,  True,  True,  True,  True,  True,  True,  True,  True,
        #         True,  True,  True,  True,  True,  True,  True,  True,  True,  True],
        #     [False, False, False,  True,  True,  True,  True,  True,  True,  True,
        #         True,  True,  True,  True,  True,  True,  True,  True,  True,  True],
        #     [False, False, False, False,  True,  True,  True,  True,  True,  True,
        #         True,  True,  True,  True,  True,  True,  True,  True,  True,  True],
        #     [False, False, False, False, False,  True,  True,  True,  True,  True,
        #         True,  True,  True,  True,  True,  True,  True,  True,  True,  True],
        #     [False, False, False, False, False, False,  True,  True,  True,  True,
        #         True,  True,  True,  True,  True,  True,  True,  True,  True,  True],
        #     [False, False, False, False, False, False, False,  True,  True,  True,
        #         True,  True,  True,  True,  True,  True,  True,  True,  True,  True],
        #     [False, False, False, False, False, False, False, False,  True,  True,
        #         True,  True,  True,  True,  True,  True,  True,  True,  True,  True],
        #     [False, False, False, False, False, False, False, False, False,  True,
        #         True,  True,  True,  True,  True,  True,  True,  True,  True,  True],
        #     [False, False, False, False, False, False, False, False, False, False,
        #         True,  True,  True,  True,  True,  True,  True,  True,  True,  True],
        #     [False, False, False, False, False, False, False, False, False, False,
        #         False,  True,  True,  True,  True,  True,  True,  True,  True,  True],
        #     [False, False, False, False, False, False, False, False, False, False,
        #         False, False,  True,  True,  True,  True,  True,  True,  True,  True],
        #     [False, False, False, False, False, False, False, False, False, False,
        #         False, False, False,  True,  True,  True,  True,  True,  True,  True],
        #     [False, False, False, False, False, False, False, False, False, False,
        #         False, False, False, False,  True,  True,  True,  True,  True,  True],
        #     [False, False, False, False, False, False, False, False, False, False,
        #         False, False, False, False, False,  True,  True,  True,  True,  True],
        #     [False, False, False, False, False, False, False, False, False, False,
        #         False, False, False, False, False, False,  True,  True,  True,  True],
        #     [False, False, False, False, False, False, False, False, False, False,
        #         False, False, False, False, False, False, False,  True,  True,  True],
        #     [False, False, False, False, False, False, False, False, False, False,
        #         False, False, False, False, False, False, False, False,  True,  True],
        #     [False, False, False, False, False, False, False, False, False, False,
        #         False, False, False, False, False, False, False, False, False,  True],
        #     [False, False, False, False, False, False, False, False, False, False,
        #         False, False, False, False, False, False, False, False, False, False]]]],device='cuda:0')

        input_tensor = torch.LongTensor(EXAMPLE_IDS).to("cuda:0")

        logits = model(input_tensor, attention_mask=ATTN_MASK).logits

        print("Logits shape: ", logits.shape)
        print("Logits: ", logits.mean().item())
        print("Max: ", logits.max().item())
        print("Min: ", logits.min().item())
        print("Mean: ", logits.mean(dim=-1))
        print("Some values: ", logits[0,:, 0])
        print("Argmax: ", torch.argmax(logits, dim=-1))
        torch.save(logits, "/gpfswork/rech/six/uan68tv/data/tensors_to_test/logits_1_tr_apex_fixed_mask.pt")

        EXAMPLE_IDS = [[144252, 2, 2175,  23714,  73173, 144252, 2, 77, 132619, 3478, 368, 109586,  35433, 2, 77, 132619,   3478,    368, 109586,  35433]]

        input_tensor = torch.LongTensor(EXAMPLE_IDS).to("cuda:0")

        logits = model(input_tensor, attention_mask=ATTN_MASK).logits
        torch.save(logits, "/gpfswork/rech/six/uan68tv/data/tensors_to_test/logits_2_tr_apex_fixed_mask.pt")
        print("Logits2 shape: ", logits.shape)
        print("Logits2: ", logits.mean().item())
        print("Max: ", logits.max().item())
        print("Min: ", logits.min().item())
        print("Mean: ", logits.mean(dim=-1))
        print("Some values: ", logits[0,:, 0])
        print("Argmax: ", torch.argmax(logits, dim=-1))



if __name__ == "__main__":
    unittest.main()
