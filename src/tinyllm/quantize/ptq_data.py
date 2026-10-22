#!/usr/bin/env python3
"""Cố định dữ liệu PTQ; chuẩn bị tập để dành nhưng không chạy model trên tập đó."""
import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download
from transformers import AutoTokenizer

from fp32_reference import ROOT, MODEL_ID, REVISION, SEED, source_snapshot, write_json

LENGTH = 512
WINDOWS = 64
WT_ID = "Salesforce/wikitext"
WT_REVISION = "b08601e04326c79dfdd32d625aee71d232d685c3"
PIQA_ID = "baber/piqa"
PIQA_REVISION = "142f6d7367fd9877f0fb3b5734ea6a545f54cdd1"
TASK_REVISION = "d6de81643928d653435c431bae19945d41d32520"
ROLES = {"train": "calibration", "validation": "selection", "test": "heldout"}


def wikitext_windows(rows, split):
    """Nối trước, tokenize ở caller; lấy block độc lập, không chồng lấn."""
    blocks, tail = divmod(len(rows), LENGTH)
    if blocks < WINDOWS:
        raise ValueError(f"{split}: chỉ có {blocks} block, cần {WINDOWS}")
    chosen = np.random.default_rng(SEED).permutation(blocks)[:WINDOWS]
    records = [
        {"id": f"wikitext2:{split}:{int(i)}", "split": split, "role": ROLES[split],
         "block_index": int(i), "token_start": int(i) * LENGTH,
         "input_ids": rows[int(i) * LENGTH:(int(i) + 1) * LENGTH]}
        for i in chosen
    ]
    return records, {"tokens": len(rows), "complete_blocks": blocks, "dropped_tail_tokens": tail}


def encode_choice(tokenizer, prompt, answer):
    """Theo TemplateLM._encode_pair: encode cả chuỗi rồi cắt ở độ dài context."""
    continuation = " " + answer
    context = tokenizer.encode(prompt, add_special_tokens=False)
    whole = tokenizer.encode(prompt + continuation, add_special_tokens=False)
    if not context or whole[:len(context)] != context:
        raise ValueError("Tokenizer đổi prefix tại ranh giới prompt/đáp án")
    if len(whole) <= len(context):
        raise ValueError("Đáp án không có token")
    return {"input_ids": whole, "answer_start": len(context),
            "answer_tokens": len(whole) - len(context)}


def piqa_halves(rows, tokenizer):
    """Xáo trộn theo nhóm goal, chia trước khi loại câu vượt context."""
    groups = defaultdict(list)
    for index, row in enumerate(rows):
        # Nhóm cả biến thể chỉ khác whitespace/chữ hoa để không lọt cùng câu hỏi.
        groups[" ".join(row["goal"].split()).casefold()].append((index, row))
    keys = list(groups)
    order = np.random.default_rng(SEED).permutation(len(keys))
    halves = np.array_split(order, 2)
    records, counts = {}, {}
    for role, half in zip(("selection", "heldout"), halves):
        kept, excluded = [], []
        for group_index in half:
            for index, row in groups[keys[int(group_index)]]:
                prompt = f"Question: {row['goal']}\nAnswer:"
                choices = [encode_choice(tokenizer, prompt, row[k]) for k in ("sol1", "sol2")]
                record = {"id": f"piqa:validation:{index}", "row_index": index,
                          "role": role, "goal": row["goal"], "prompt": prompt,
                          "answers": [row["sol1"], row["sol2"]], "label": int(row["label"]),
                          "choices": choices}
                if max(len(c["input_ids"]) for c in choices) > LENGTH:
                    excluded.append({"id": record["id"], "lengths": [len(c["input_ids"]) for c in choices]})
                else:
                    kept.append(record)
        records[role] = kept
        counts[role] = {"groups": len(half), "kept": len(kept), "excluded_overlength": excluded,
                        "source_questions": len(kept) + len(excluded)}
    counts["source_rows"] = len(rows)
    counts["unique_question_groups"] = len(groups)
    counts["duplicate_question_rows"] = len(rows) - len(groups)
    return records, counts


def prepare(args):
    snapshot = source_snapshot(args.cache_dir, args.offline)
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False)
    args.data_dir.mkdir(parents=True, exist_ok=True)
    metadata = {"model_id": MODEL_ID, "model_revision": REVISION, "seed": SEED,
                "length": LENGTH, "windows_per_split": WINDOWS,
                "wikitext": {"repo": WT_ID, "revision": WT_REVISION,
                             "join": "\n\n", "special_tokens": False, "splits": {}},
                "piqa": {"repo": PIQA_ID, "revision": PIQA_REVISION,
                         "task_revision": TASK_REVISION, "prompt": "Question: {goal}\nAnswer:",
                         "delimiter": " ", "score": "sum continuation log likelihood; tie -> choice 0",
                         "boundary": "joint encode, split at context length; prefix equality required",
                         "overlength": "exclude entire question if either choice exceeds 512; no truncation"}}
    for split, role in ROLES.items():
        filename = f"wikitext-2-raw-v1/{split}-00000-of-00001.parquet"
        path = hf_hub_download(WT_ID, filename, repo_type="dataset", revision=WT_REVISION,
                               cache_dir=args.cache_dir, local_files_only=args.offline)
        text = "\n\n".join(pq.read_table(path, columns=["text"])["text"].to_pylist())
        ids = tokenizer.encode(text, add_special_tokens=False)
        records, counts = wikitext_windows(ids, split)
        metadata["wikitext"]["splits"][split] = {"file": filename, "role": role, **counts}
        write_json(args.data_dir / f"wikitext_{role}.json", records)
        if role == "selection":
            cache = [{"id": r["id"], "selection_index": i,
                      "regimes": [{"prefill": 32, "decode": 64, "input_length": 96},
                                  {"prefill": 448, "decode": 64, "input_length": 512}]}
                     for i, r in enumerate(records[:8])]
            write_json(args.data_dir / "cache_cases.json", cache)
    path = hf_hub_download(PIQA_ID, "piqa_validation.parquet", repo_type="dataset",
                           revision=PIQA_REVISION, cache_dir=args.cache_dir, local_files_only=args.offline)
    records, counts = piqa_halves(pq.read_table(path).to_pylist(), tokenizer)
    for role, values in records.items():
        write_json(args.data_dir / f"piqa_{role}.json", values)
    metadata["piqa"]["counts"] = counts
    write_json(args.data_dir / "metadata.json", metadata)
    print(f"PASS prepare: WT 64 x 512 mỗi split; PIQA {counts}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache/huggingface")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--offline", action="store_true")
    prepare(parser.parse_args())


if __name__ == "__main__":
    main()
