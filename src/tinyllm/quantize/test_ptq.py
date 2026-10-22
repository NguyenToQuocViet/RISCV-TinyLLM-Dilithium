"""Oracle độc lập cho bộ chấm và thuật toán chuẩn bị dữ liệu."""
import math
from types import SimpleNamespace

import pytest
import torch

from ptq_data import encode_choice, piqa_halves, wikitext_windows
from ptq_eval import aggregate_nll, choose_answer, score_targets, evaluate_piqa


def test_shift_and_continuation_mask():
    # Mỗi hàng là một phân bố khác nhau: dùng sai row/target sẽ cho số khác.
    probabilities = [[.1, .6, .3], [.2, .3, .5], [.7, .2, .1], [.3, .4, .3]]
    logits = torch.tensor([[math.log(p) for p in row] for row in probabilities], dtype=torch.float64)
    ids = [2, 1, 2, 0]
    nll, count = score_targets(logits, ids)
    assert count == 3
    assert nll == pytest.approx(-math.log(.6) - math.log(.5) - math.log(.7), abs=1e-12)
    nll, count = score_targets(logits, ids, start=2, stop=4)
    assert count == 2
    assert nll == pytest.approx(-math.log(.5) - math.log(.7), abs=1e-12)


def test_decode_scores_exactly_64_including_first_after_prompt():
    probabilities = [[.5, .5] for _ in range(96)]
    probabilities[31] = [.8, .2]  # Hàng prefill cuối dự đoán target đầu ở vị trí 32.
    probabilities[95] = [.01, .99]  # Hàng cuối không dự đoán target trong cửa sổ.
    logits = torch.tensor([[math.log(p) for p in row] for row in probabilities], dtype=torch.float64)
    nll, count = score_targets(logits, [0] * 96, start=32, stop=96)
    assert count == 64
    assert nll == pytest.approx(-math.log(.8) - 63 * math.log(.5), abs=1e-12)


def test_ppl_uses_token_weighted_nll():
    result = aggregate_nll([(2 * math.log(2), 2), (math.log(8), 1)])
    assert result["tokens"] == 3
    assert result["ppl"] == pytest.approx(32 ** (1 / 3))
    assert result["ppl"] != pytest.approx((2 + 8) / 2)


def test_piqa_sum_and_tie():
    # Đáp án dài có mean LL tốt hơn nhưng tổng LL thấp hơn: acc phải chọn 0.
    assert choose_answer([-2.0, -3.0]) == 0
    assert choose_answer([-3.0, -2.0]) == 1
    assert choose_answer([-2.0, -2.0]) == 0
    with pytest.raises(ValueError):
        choose_answer([float("nan"), -1])


def test_piqa_evaluation_uses_sum_instead_of_length_normalization():
    class ControlledModel:
        def __call__(self, input_ids, attention_mask, use_cache):
            assert not use_cache and input_ids.shape[0] == 1
            assert torch.all(attention_mask == 1)
            length = input_ids.shape[1]
            target_probability = .2 if length == 2 else .4
            logits = torch.tensor([math.log(1 - target_probability), math.log(target_probability)])
            return SimpleNamespace(logits=logits.repeat(1, length, 1))

    # LL(short) = log(.2) > 2*log(.4) = LL(long).
    # Chia theo độ dài đảo thứ hạng, vì log(.2) < log(.4).
    record = {"id": "synthetic", "label": 0,
              "choices": [{"input_ids": [0, 1], "answer_start": 1},
                          {"input_ids": [0, 1, 1], "answer_start": 1}]}
    result = evaluate_piqa(ControlledModel(), [record])
    row = result["per_question"][0]
    assert row["prediction"] == 0 and result["accuracy"] == 1
    assert row["answer_tokens"] == [1, 2] and result["answer_tokens"] == 3
    assert row["log_likelihoods"] == pytest.approx([math.log(.2), 2 * math.log(.4)], abs=1e-6)


@pytest.mark.parametrize("start,stop", [(0, 3), (2, 2), (1, 5)])
def test_bad_mask_rejected(start, stop):
    with pytest.raises(ValueError):
        score_targets(torch.zeros(4, 3), [0, 1, 2, 1], start, stop)


def test_nonfinite_logits_rejected():
    with pytest.raises(ValueError):
        score_targets(torch.full((3, 2), float("nan")), [0, 1, 0])


def test_wikitext_seed_block_offsets_and_insufficient_source():
    ids = list(range(65 * 512 + 11))
    first, counts = wikitext_windows(ids, "train")
    second, _ = wikitext_windows(ids, "train")
    assert first == second and len(first) == 64
    assert counts == {"tokens": len(ids), "complete_blocks": 65, "dropped_tail_tokens": 11}
    assert len({r["block_index"] for r in first}) == 64
    for record in first:
        assert record["role"] == "calibration"
        assert record["input_ids"][0] == record["token_start"] == record["block_index"] * 512
    with pytest.raises(ValueError):
        wikitext_windows([0] * 511, "train")


class CharacterTokenizer:
    def encode(self, text, add_special_tokens=False):
        assert not add_special_tokens
        return [ord(c) for c in text]


def test_piqa_group_split_and_overlength_excludes_whole_question():
    rows = [{"goal": goal, "sol1": "one", "sol2": "two", "label": 0}
            for goal in ("Same question", " SAME  QUESTION ", "Other question", "Last question")]
    rows[-1]["sol2"] = "x" * 513
    records, counts = piqa_halves(rows, CharacterTokenizer())
    normalized = [{" ".join(r["goal"].split()).casefold() for r in records[role]}
                  for role in ("selection", "heldout")]
    assert normalized[0].isdisjoint(normalized[1])
    assert counts["duplicate_question_rows"] == 1
    assert sum(counts[r]["kept"] for r in records) == 3
    assert sum(len(counts[r]["excluded_overlength"]) for r in records) == 1


def test_joint_encoding_includes_delimiter():
    choice = encode_choice(CharacterTokenizer(), "Answer:", "hello")
    assert choice["answer_start"] == 7
    assert choice["input_ids"][7:] == [ord(c) for c in " hello"]
    assert choice["answer_tokens"] == 6
