"""Bộ chấm dùng chung FP32/candidate; chỉ nhận token cố định, không tự chọn dữ liệu."""
import math

import torch
import torch.nn.functional as F

from fp32_reference import cached_logits, compare_logits


def score_targets(logits, ids, start=1, stop=None):
    """Chấm target [start, stop), hàng target-1 dự đoán target; trả tổng NLL và count."""
    stop = len(ids) if stop is None else stop
    if not 1 <= start < stop <= len(ids) or logits.shape[0] != len(ids):
        raise ValueError("Khoảng target/shape không hợp lệ")
    rows = torch.as_tensor(logits)[start - 1:stop - 1]
    if not torch.isfinite(rows).all():
        raise ValueError("Logits có NaN/Inf")
    losses = F.cross_entropy(rows, torch.tensor(ids[start:stop], dtype=torch.long), reduction="none")
    return float(losses.double().sum()), stop - start


def aggregate_nll(parts):
    total = sum(p[0] for p in parts)
    tokens = sum(p[1] for p in parts)
    if tokens <= 0:
        raise ValueError("Không có target")
    return {"nll": total, "tokens": tokens, "ppl": math.exp(total / tokens)}


def choose_answer(log_likelihoods):
    """Tổng LL không chuẩn hóa độ dài; hòa điểm chọn đáp án 0."""
    if len(log_likelihoods) != 2 or not all(math.isfinite(s) for s in log_likelihoods):
        raise ValueError("Cần hai điểm hữu hạn")
    return int(log_likelihoods[1] > log_likelihoods[0])


def full_logits(model, ids):
    return model(input_ids=torch.tensor([ids], dtype=torch.long),
                 attention_mask=torch.ones((1, len(ids)), dtype=torch.long),
                 use_cache=False).logits[0]


@torch.inference_mode()
def evaluate_ppl(model, records):
    details = []
    for index, record in enumerate(records):
        logits = full_logits(model, record["input_ids"])
        nll, count = score_targets(logits, record["input_ids"])
        details.append({"id": record["id"], "nll": nll, "tokens": count})
        del logits
        if (index + 1) % 8 == 0:
            print(f"PPL {index + 1}/{len(records)}", flush=True)
    return {**aggregate_nll([(r["nll"], r["tokens"]) for r in details]),
            "windows": len(details), "per_window": details}


@torch.inference_mode()
def evaluate_piqa(model, records):
    details = []
    for index, record in enumerate(records):
        scores, counts = [], []
        for choice in record["choices"]:
            logits = full_logits(model, choice["input_ids"])
            nll, count = score_targets(logits, choice["input_ids"], choice["answer_start"])
            scores.append(-nll)
            counts.append(count)
            del logits
        predicted = choose_answer(scores)
        details.append({"id": record["id"], "label": record["label"], "prediction": predicted,
                        "log_likelihoods": scores, "answer_tokens": counts,
                        "correct": predicted == record["label"]})
        if (index + 1) % 100 == 0:
            print(f"PIQA {index + 1}/{len(records)}", flush=True)
    if not details:
        raise ValueError("PIQA rỗng")
    correct = sum(r["correct"] for r in details)
    return {"questions": len(details), "choices": 2 * len(details), "correct": correct,
            "answer_tokens": sum(sum(r["answer_tokens"]) for r in details),
            "accuracy": correct / len(details), "per_question": details}


@torch.inference_mode()
def evaluate_cache(model, selection, cases, *, check_fp32=True):
    """64 target sau prompt gồm target đầu, được dự đoán bởi hàng prefill cuối."""
    details = []
    for case in cases:
        record = selection[case["selection_index"]]
        for regime in case["regimes"]:
            prefill, decode = regime["prefill"], regime["decode"]
            ids = record["input_ids"][:regime["input_length"]]
            if len(ids) != prefill + decode:
                raise ValueError("Split cache sai độ dài")
            full = full_logits(model, ids).numpy()
            actual = cached_logits(model, ids, prefill)
            metrics = compare_logits(actual, full) if check_fp32 else None
            full_nll, _ = score_targets(full, ids, prefill, prefill + decode)
            nll, count = score_targets(actual, ids, prefill, prefill + decode)
            details.append({"id": case["id"], **regime, "nll": nll, "tokens": count,
                            "full_nll": full_nll, "comparison": metrics})
            del full, actual
            print(f"CACHE {case['id']} prefill={prefill} targets={count}", flush=True)
    regimes = {}
    for prefill in (32, 448):
        rows = [r for r in details if r["prefill"] == prefill]
        regimes[str(prefill)] = aggregate_nll([(r["nll"], r["tokens"]) for r in rows])
    return {"regimes": regimes, "runs": details,
            **aggregate_nll([(r["nll"], r["tokens"]) for r in details])}


@torch.inference_mode()
def check_transformers_loss(model, ids, start=32, stop=96):
    """Oracle độc lập: labels mask, loss/shift do Transformers thực hiện."""
    ids = ids[:stop]
    labels = torch.tensor([ids], dtype=torch.long)
    labels[:, :start] = -100
    output = model(input_ids=torch.tensor([ids]), labels=labels,
                   attention_mask=torch.ones((1, len(ids)), dtype=torch.long), use_cache=False)
    nll, count = score_targets(output.logits[0], ids, start, stop)
    scorer_mean, model_loss = nll / count, float(output.loss)
    if abs(scorer_mean - model_loss) > 1e-6:
        raise ValueError(f"NLL/Transformers loss lệch: {scorer_mean}, {model_loss}")
    return {"target_start": start, "target_stop": stop, "tokens": count,
            "scorer_mean_nll": scorer_mean, "transformers_loss": model_loss,
            "absolute_error": abs(scorer_mean - model_loss), "tolerance": 1e-6}
