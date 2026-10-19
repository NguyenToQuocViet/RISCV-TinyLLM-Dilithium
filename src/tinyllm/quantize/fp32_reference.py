#!/usr/bin/env python3
"""Chạy bản Transformers gốc và kiểm tra prefill/decode bằng FP32 trên CPU."""

import argparse  # Đọc chế độ chạy và các tùy chọn người dùng nhập ở terminal.
import importlib.metadata  # Đọc phiên bản của những thư viện đã cài.
import json
import os  # Đọc hoặc đặt các biến môi trường dùng để cấu hình thư viện.
from pathlib import Path  # Tạo, ghép và thao tác với đường dẫn file/thư mục.
import platform  # Lấy thông tin Python, hệ điều hành và kiến trúc máy.
import sys  # Lấy phiên bản Python, đường dẫn Python và đối số của lệnh chạy.
import time

# Giới hạn luồng tính toán giúp giảm biến thiên do thứ tự cộng số thực, nhưng không bảo đảm khớp từng bit giữa mọi cách chạy.
# Giới hạn số luồng của các phép tính sử dụng OpenMP.
os.environ["OMP_NUM_THREADS"] = "1"
# Giới hạn số luồng của thư viện toán học Intel MKL.
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import numpy as np
import torch
from huggingface_hub import snapshot_download
from transformers import AutoModelForCausalLM, AutoTokenizer, DynamicCache

# resolve() lấy đường dẫn tuyệt đối và xử lý liên kết; parent lấy thư mục chứa.
# Nhờ vậy các đường dẫn mặc định bám theo script, kể cả khi chạy từ thư mục khác.
ROOT = Path(__file__).resolve().parent
MODEL_ID = "HuggingFaceTB/SmolLM2-135M"
REVISION = "93efa2f097d58c2a74874c7e644dbc9b0cee75a2"
SOURCE_FILES = (
    "config.json", "generation_config.json", "model.safetensors", "merges.txt",
    "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json", "vocab.json",
)
SEED = 1234

# Mỗi phần tử phải thỏa: |actual - expected| <= ATOL + RTOL * |expected|.
ATOL = 2e-4 # Sai số tuyệt đối cho phép, hữu ích cả khi giá trị chuẩn gần bằng 0.
RTOL = 1e-5 # Sai số cho phép tăng theo độ lớn của giá trị chuẩn.
PACKAGES = ("torch", "transformers", "numpy", "huggingface-hub", "safetensors", "tokenizers")


# Đọc một file JSON UTF-8 rồi trả về dữ liệu Python, như dictionary hoặc list.
def read_json(path):
    # read_text lấy văn bản; json.loads phân tích văn bản thành dữ liệu.
    return json.loads(Path(path).read_text(encoding="utf-8"))


# Ghi dữ liệu Python thành file JSON dễ đọc, giữ nguyên các ký tự tiếng Việt.
def write_json(path, value):
    # indent=2 thụt vào hai dấu cách; thêm ký tự xuống dòng ở cuối file.
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# Đặt cấu hình tính toán dùng cho bộ chạy chuẩn.
def configure_runtime():
    # Phiên bản cài đặt được cố định trong requirements.txt và ghi vào báo cáo.
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    torch.set_num_threads(1)
    # Giới hạn luồng dùng để điều phối giữa các tác vụ tính toán PyTorch.
    torch.set_num_interop_threads(1)
    # Yêu cầu các thuật toán xác định; phép toán không đáp ứng có thể báo lỗi.
    torch.use_deterministic_algorithms(True)
    torch.set_float32_matmul_precision("highest")
    # Tắt đường tính MKLDNN để giữ cấu hình backend đã chọn cho bộ chuẩn.
    torch.backends.mkldnn.enabled = False
    # Yêu cầu giữ các số rất nhỏ thay vì chủ động đưa chúng về 0 để tính nhanh.
    torch.set_flush_denormal(False)


# Thu thập thông tin môi trường và lệnh chạy để có thể truy vết kết quả về sau.
def environment():
    # Trả một dictionary (bảng tên-giá trị) để ghi vào metadata/báo cáo.
    return {
        "python": platform.python_version(), "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_capability": torch.backends.cpu.get_cpu_capability(),
        "torch_build": torch.__config__.show(),
        "packages": {name: importlib.metadata.version(name) for name in PACKAGES},
        "device": "cpu", "dtype": "float32", "attention": "eager",
        "seed": SEED, "threads": torch.get_num_threads(),
        "interop_threads": torch.get_num_interop_threads(),
        "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        "mkldnn": torch.backends.mkldnn.enabled,
        "mkl_cbwr": os.environ.get("MKL_CBWR", "unset (default CPU dispatch)"),
        "matmul_precision": torch.get_float32_matmul_precision(),
        "command": [sys.executable, *sys.argv],
    }


# Lấy các file nguồn đúng revision và trả về thư mục chứa chúng trên máy.
def source_snapshot(cache_dir, offline):
    return Path(snapshot_download(
        repo_id=MODEL_ID, revision=REVISION, allow_patterns=list(SOURCE_FILES),
        # Chọn nơi lưu; offline=True chỉ tìm file đã có, thiếu thì báo lỗi.
        cache_dir=str(cache_dir), local_files_only=offline,
    ))


# Nạp tokenizer và model Transformers nguyên bản, chuẩn bị tính FP32 trên CPU.
def load_model(snapshot):
    # Đọc tokenizer, model từ thư mục nguồn; dùng file cục bộ và không chạy mã từ kho model.
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=False,
        # Chọn kiểu số FP32, cách tính attention eager (cách tính thông thường của Transformers) và định dạng trọng số.
        torch_dtype=torch.float32, attn_implementation="eager", use_safetensors=True,
    ).to("cpu").eval()
    return model, tokenizer


# So hai mảng logits theo từng phần tử và trả các số đo sai khác nếu đạt.
def compare_logits(actual, expected):
    """Không dịch vị trí: hàng i luôn là logits sau khi model đọc token i."""
    # Cùng kích thước mới so được đúng từng token và từng phần tử từ vựng.
    # Nếu bỏ qua, NumPy có thể tự lặp một hàng để ghép với nhiều hàng (broadcast).
    if actual.shape != expected.shape:
        raise ValueError(f"Sai shape logits: {actual.shape}, {expected.shape}")
    # NaN không lớn hơn ngưỡng nào, nên phải loại nó trước khi đếm phần tử sai.
    if not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise ValueError("Logits có NaN/Inf.")
    error = np.abs(actual - expected)
    allowed = ATOL + RTOL * np.abs(expected)
    failed = int(np.count_nonzero(error > allowed))
    metrics = {
        "elements": int(error.size), "max_abs_error": float(error.max()),
        "mean_abs_error": float(error.mean()), "max_tolerance_ratio": float((error / allowed).max()),
        "failed_elements": failed,
    }
    if failed:
        raise ValueError(f"Logits vượt tolerance: {metrics}")
    return metrics


# Chạy một lần prefill rồi decode từng token, trả logits ở mọi vị trí đầu vào.
def cached_logits(model, ids, prefill_length):
    # Cache mới giữ K/V của các token đã đọc, không dùng lại cache của lần chia khác.
    cache = DynamicCache()

    result = np.empty((len(ids), model.config.vocab_size), dtype=np.float32)
    chunks = [(0, prefill_length)] + [(i, i + 1) for i in range(prefill_length, len(ids))]
    # Chạy đoạn prefill trước, rồi lần lượt các đoạn decode một token.
    for start, end in chunks:
        output = model(
            # Cặp ngoặc [] ngoài tạo batch 1; torch.long là kiểu số nguyên cho ID.
            input_ids=torch.tensor([ids[start:end]], dtype=torch.long),
            # Cho phép chú ý tới mọi token hợp lệ đã đọc, kể cả token đang ở cache.
            # Model vẫn áp dụng causal mask để không nhìn các token ở tương lai.
            attention_mask=torch.ones((1, end), dtype=torch.long), # 1 là kích thước batch
            # Các vị trí tuyệt đối start..end-1; unsqueeze(0) thêm chiều batch.
            position_ids=torch.arange(start, end).unsqueeze(0),
            # Chỉ rõ vị trí ghi cache, truyền cache cũ và yêu cầu trả cache cập nhật.
            cache_position=torch.arange(start, end), past_key_values=cache, use_cache=True,
        )
        cache = output.past_key_values
        # Bỏ chiều batch bằng [0], chuyển tensor CPU thành mảng NumPy rồi chép vào
        result[start:end] = output.logits[0].numpy()
    return result


# Chạy toàn bộ testcase, so full/cache và giữ logits chuẩn để lưu sau khi đạt.
@torch.inference_mode()
def run_cases(model, cases):
    # results giữ số đo sai khác; outputs giữ các hàng logits cần lưu của mỗi case.
    results, outputs = [], {}
    for case in cases:
        started = time.monotonic()
        ids = case["input_ids"]
        # Oracle là kết quả dùng làm chuẩn đối chiếu: đưa cả chuỗi vào model gốc
        # trong một lần, không tái sử dụng vòng lặp decode cần kiểm tra.
        # Sau lời gọi, lấy logits của chuỗi duy nhất rồi chuyển sang mảng NumPy.
        full = model(
            # Tạo tensor ID nguyên có dạng [1, số token], tức một chuỗi trong batch.
            input_ids=torch.tensor([ids], dtype=torch.long),
            # Chuỗi này không có padding; không lưu K/V cho cách chạy full forward.
            attention_mask=torch.ones((1, len(ids)), dtype=torch.long), use_cache=False,
        ).logits[0].numpy()
        # Giữ các hàng cần lưu; vẫn dùng full để kiểm cache ở mọi vị trí.
        selected = full[case["saved_positions"]]
        # Lập phần thông tin nhận diện testcase trong báo cáo.
        result = {"name": case["name"], "tokens": len(ids), "saved_positions": case["saved_positions"]}
        # Chuẩn bị danh sách kết quả kiểm cache cho từng lựa chọn độ dài prefill.
        result["cache_splits"] = []
        # Thử mọi điểm chia prefill/decode đã ghi trong testcase.
        for split in case["prefill_lengths"]:
            # Chạy lại chuỗi với cache mới, bắt đầu bằng split token prefill.
            actual = cached_logits(model, ids, split)
            # So logits ở mọi vị trí với full forward, kể cả những hàng không lưu.
            metrics = compare_logits(actual, full)
            # Ghi độ dài prefill, số lượt decode và các số đo; **metrics ghép các
            # trường trong dictionary metrics vào dictionary kết quả của split.
            result["cache_splits"].append({"prefill": split, "decode_steps": len(ids) - split, **metrics})
        # Chưa ghi file ở đây; chỉ trả bộ logits nếu toàn bộ testcase đều đạt.
        outputs[case["name"]] = selected
        # Thời gian của toàn bộ case, làm tròn đến ba chữ số sau dấu thập phân.
        result["seconds"] = round(time.monotonic() - started, 3)
        # Thêm số đo case vào danh sách báo cáo chung.
        results.append(result)
        # In tiến độ sau khi case đạt; flush=True đưa thông báo ra ngay.
        print(f"PASS {case['name']}: {len(ids)} token, splits={case['prefill_lengths']}", flush=True)
    return results, outputs


# Đọc lệnh terminal: fetch chuẩn bị nguồn; run chạy và lưu kết quả chuẩn FP32.
def main():
    # Dùng mô tả ở đầu file làm phần giới thiệu khi người dùng gọi --help.
    parser = argparse.ArgumentParser(description=__doc__)
    # mode là đối số bắt buộc, chọn chuẩn bị nguồn hoặc chạy các testcase.
    parser.add_argument("mode", choices=("fetch", "run"))
    # Cho phép chọn nơi lưu model; mặc định là .cache/huggingface cạnh script.
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache" / "huggingface")
    # Có cờ --offline thì nhận True, không có thì False; không cần ghi thêm giá trị.
    parser.add_argument("--offline", action="store_true")
    # File chứa danh sách testcase; type=Path chuyển chuỗi nhập vào thành Path.
    parser.add_argument("--cases", type=Path, default=ROOT / "cases.json")
    # Thư mục lưu logits và metadata; run ghi lại các file cùng tên nếu đã có.
    parser.add_argument("--reference-dir", type=Path, default=ROOT / "reference")
    # Phân tích đối số terminal; ví dụ args.mode và args.offline giữ các lựa chọn.
    args = parser.parse_args()
    # Đặt cấu hình tính toán trước khi tải/nạp/chạy model.
    configure_runtime()
    snapshot = source_snapshot(args.cache_dir, args.offline)
    # fetch chỉ chuẩn bị các file nguồn đúng revision, chưa nạp model để tính logits.
    if args.mode == "fetch":
        print(f"Nguồn đã sẵn sàng: {MODEL_ID} @{REVISION}")
        return
    # Nạp model FP32 và tokenizer nguyên bản từ snapshot đúng revision.
    model, tokenizer = load_model(snapshot)
    cases = read_json(args.cases)
    report = {
        "model_id": MODEL_ID, "revision": REVISION, "atol": ATOL, "rtol": RTOL,
        "environment": environment(), "model_max_positions": model.config.max_position_embeddings,
        "vocab_size": model.config.vocab_size, "model_class": type(model).__name__,
        "tokenizer_class": type(tokenizer).__name__,
        "parameters": sum(parameter.numel() for parameter in model.parameters()),
    }
    # Chỉ bắt đầu ghi file sau khi mọi case và mọi cách chia cache đều đạt.
    report["cases"], outputs = run_cases(model, cases)
    args.reference_dir.mkdir(parents=True, exist_ok=True)
    for case in cases:
        # Mỗi file chứa vị trí đã chọn và logits FP32 tương ứng, nén không mất dữ liệu.
        np.savez_compressed(
            args.reference_dir / f"{case['name']}.npz",
            positions=np.array(case["saved_positions"], dtype=np.int64),
            logits=outputs[case["name"]],
        )
    # Metadata ghi nguồn, môi trường và số đo của lần chạy vừa thành công.
    report["status"] = "PASS"
    write_json(args.reference_dir / "metadata.json", report)
    print(f"PASS run: tất cả testcase đạt atol={ATOL}, rtol={RTOL}")


if __name__ == "__main__":
    main()
