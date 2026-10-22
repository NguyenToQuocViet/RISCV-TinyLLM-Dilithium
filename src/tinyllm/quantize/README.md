# Bản chuẩn FP32 và thí nghiệm PTQ của SmolLM2-135M

Thư mục này thực hiện [chặng 1 của kế hoạch TinyLLM](../docs/PLAN.md#1-cố-định-nguồn-model-và-tạo-bản-chạy-chuẩn-fp32): cố định nguồn model, chạy Transformers gốc bằng FP32 và kiểm tra KV cache.

Model là **base** `HuggingFaceTB/SmolLM2-135M`, commit
`93efa2f097d58c2a74874c7e644dbc9b0cee75a2`. Config, trọng số và tokenizer đều được lấy từ commit này bằng `snapshot_download`. Trọng số nguồn BF16 được nạp thành FP32.

## Cài đặt và chạy lại

Yêu cầu Linux x86_64, Python **3.12**, kết nối mạng cho lần tải đầu. Dùng môi trường riêng trong thư mục này:

```bash
cd /home/hoang_hung/RISCV-TinyLLM-Dilithium/src/tinyllm/quantize
/usr/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python fp32_reference.py fetch
timeout 600 .venv/bin/python fp32_reference.py run --offline
timeout 300 .venv/bin/python -m pytest -q test_fp32_reference.py
```

`timeout 600` và `timeout 300` giới hạn thời gian chạy lần lượt là 600 và 300 giây. Có thể bỏ tiền tố này nếu không muốn giới hạn thời gian.

`fetch` chuẩn bị các file của đúng revision trong `.cache/huggingface/`, dùng lại cache và tải file còn thiếu. Các lần chạy sau dùng `--offline`, không cần truy cập Hugging Face. Không đưa checkpoint hoặc `.venv/` vào Git. Máy khác có thể thay tiền tố đường dẫn tới repository.

`run` chạy model thật, so full forward với prefill/decode có KV cache, rồi lưu logits chuẩn và báo cáo `metadata.json` trong `reference/`. Các file cùng tên được ghi lại nếu đã tồn tại. Chỉ exit code **0** cùng thông báo `PASS run` mới là thành công; kiểm exit code của lần chạy hiện tại thay vì chỉ xem metadata đã có từ trước.

Bộ kiểm tra gồm **4 case, 10 split**, so 43.696.128 phần tử logits. Sai khác full-vs-cache lớn nhất đã đo là `1.5116e-4`. Các file logits chuẩn chiếm khoảng 7,94 MB.

## Cú pháp các lệnh

Chạy các ví dụ dưới đây từ thư mục `quantize/`, sau khi cài đặt như trên. Cú pháp chung:

```text
.venv/bin/python fp32_reference.py MODE [TÙY_CHỌN ...]
```

Thay `MODE` bằng `fetch` hoặc `run`. Phần trong ngoặc vuông là tùy chọn, không gõ nguyên dấu ngoặc vào lệnh.

| Tùy chọn                    | Tác dụng                                                                                      | Giá trị mặc định             |
| ----------------------------- | ----------------------------------------------------------------------------------------------- | --------------------------------- |
| `-h`, `--help`            | Hiện hướng dẫn rồi thoát, không chạy model                                              | Không bật                       |
| `--cache-dir THƯ_MỤC`     | Nơi lưu/tìm các file model và tokenizer; dùng cho cả hai chế độ                       | `.cache/huggingface/`           |
| `--offline`                 | Chỉ dùng nguồn đã có trong cache, thiếu thì báo lỗi; không nhận giá trị phía sau | Cho phép tải nguồn còn thiếu |
| `--cases FILE`              | File JSON chứa token đầu vào và cách chia prefill/decode cho `run`                   | `cases.json`                    |
| `--reference-dir THƯ_MỤC` | Nơi `run` lưu các file logits `.npz` và `metadata.json`                               | `reference/`                    |

Các đường dẫn mặc định tính từ thư mục chứa script. Đường dẫn tương đối tự truyền vào được tính từ thư mục terminal đang đứng. Nếu chọn cache khác bằng `--cache-dir`, dùng cùng đường dẫn đó khi tải nguồn và khi chạy model.

Xem hướng dẫn ngay trên terminal:

```bash
.venv/bin/python fp32_reference.py --help
```

### `fetch`: chuẩn bị nguồn model

```bash
# Dùng lại cache và tải các file còn thiếu.
.venv/bin/python fp32_reference.py fetch

# Chỉ tìm nguồn trong cache, không tải qua mạng.
.venv/bin/python fp32_reference.py fetch --offline
```

Chế độ này chưa nạp model để tính logits. Thành công sẽ in `Nguồn đã sẵn sàng: ...`.

### `run`: kiểm tra KV cache và lưu kết quả chuẩn FP32

Chạy với các đường dẫn mặc định:

```bash
.venv/bin/python fp32_reference.py run --offline
```

Chương trình dùng kết quả full forward làm chuẩn để so với cách chạy có cache. Sau khi toàn bộ case đạt, nó lưu các hàng logits đã chọn vào `.npz` và ghi thông tin nguồn, phiên bản thư viện, cấu hình cùng số đo sai khác vào `metadata.json`.

Lệnh sau ghi rõ toàn bộ tùy chọn đường dẫn, với các giá trị giống mặc định:

```bash
.venv/bin/python fp32_reference.py run \
    --offline \
    --cache-dir .cache/huggingface \
    --cases cases.json \
    --reference-dir reference
```

Dấu `\` ở cuối dòng nối lệnh sang dòng tiếp theo; cũng có thể viết cả lệnh trên một dòng.

Để lưu một lần chạy riêng mà giữ nguyên bộ chuẩn trong `reference/`:

```bash
.venv/bin/python fp32_reference.py run --offline --reference-dir results/fp32
```

Thư mục đích được tạo nếu chưa có; nếu đã có, các file kết quả cùng tên được ghi lại. Giữ bộ đầu vào và logits chuẩn đã chọn để đối chiếu với bản fake-quant và số nguyên ở chặng sau.

## Quy tắc so sánh và bộ kiểm tra

Backend cố định: PyTorch CPU, attention `eager`, FP32, `eval()` và `torch.inference_mode()`, một compute thread và một interop thread, seed **1234**, deterministic algorithms, không dùng MKLDNN. [requirements.txt](requirements.txt) khóa dependency, kể cả các dependency gián tiếp. Phiên bản model, tokenizer, thư viện, Python và cách chạy được ghi trong [metadata của bộ chuẩn](reference/metadata.json) để người chạy đối chiếu. Chương trình không dùng metadata để kiểm tra hay ép phiên bản môi trường.

Ngưỡng dùng để so full-vs-cache, áp dụng cho **mọi** phần tử:

```text
abs(actual - expected) <= 2e-4 + 1e-5 * abs(expected)
```

Phép so sánh yêu cầu hai mảng cùng kích thước và không có NaN/Inf, để tránh báo đạt sai. Kiểu FP32 được chọn khi nạp model. Không yêu cầu khớp từng bit giữa full forward và decode vì hai cách chia phép nhân/cộng có thể cho sai số FP32 nhỏ.

Kiểm tra cùng token đầu với input dài 1 và 8 token, đều không dùng cache, đã đo sai khác tối đa khoảng `1.52e-4`; cùng kích thước input thì bật/tắt cache cho kết quả khớp bit. Vì vậy dùng bound tuyệt đối `2e-4` và giữ bound tương đối `1e-5`. Đây là ngưỡng cho campaign này, không phải bảo đảm sai số trên mọi phần cứng; [PyTorch giải thích khác biệt khi tính theo batch hoặc từng phần](https://docs.pytorch.org/docs/2.6/notes/numerical_accuracy.html#batched-computations-or-slice-computations).

[cases.json](cases.json) lưu token IDs cố định, văn bản nguồn, cách lặp/cắt và các vị trí kết quả được giữ. Các IDs được chuẩn bị không thêm special token tự động; mỗi lần chạy dùng trực tiếp các IDs đã lưu.

| Case           | Số token | Độ dài prefill | Decode sau prefill    | Logits giữ trong Git                          |
| -------------- | --------: | ----------------- | --------------------- | ---------------------------------------------- |
| `one_token`  |         1 | 1                 | 0                     | Mọi vị trí, toàn vocabulary                |
| `short_text` |         8 | 1, 4, 7           | Từng token còn lại | Mọi vị trí, toàn vocabulary                |
| `mixed_text` |        32 | 1, 16, 31         | Từng token còn lại | Mọi vị trí, toàn vocabulary                |
| `long_text`  |       256 | 1, 128, 255       | Từng token còn lại | Vị trí 0, 1, 127, 254, 255; toàn vocabulary |

Với mỗi case, full forward **không dùng cache** là oracle. Cách chạy còn lại tạo cache mới, đưa đoạn prefill vào rồi đưa từng token cố định tiếp theo vào, đồng thời cập nhật mask và vị trí. Hàng logits `i` được so với hàng `i` của full forward: cả hai đều là dự đoán sau khi đọc token `i`. Không lấy token argmax làm đầu vào cho lượt sau.

Toàn bộ logits ở **mọi vị trí** của cả bốn case được so full-vs-cache cho từng split, dù chỉ một phần logits của case dài được lưu lâu dài. Các file `.npz` lưu vị trí và logits FP32, không làm tròn thêm.

Campaign đã chạy các độ dài **1, 8, 32 và 256 token**, batch 1, không padding. Config model cho phép 8192 vị trí; campaign này **không kiểm tra 8192 token**, padding, nhiều chuỗi trong một batch hoặc chất lượng sinh văn bản. Đây cũng chưa phải quyết định độ dài hỗ trợ của RTL.

## Chạy test

```bash
.venv/bin/python -m pytest -q test_fp32_reference.py
```

`-q` yêu cầu pytest in kết quả gọn. `pytest` kiểm phép so logits: chấp nhận sai số trong ngưỡng, phát hiện sai số vượt ngưỡng hoặc đảo vị trí token, từ chối NaN/Inf và hai mảng khác kích thước. Lệnh `run` ở trên kiểm kết quả chạy model thật trên cả bốn case.

Tham khảo API: [KV cache trong Transformers 4.49.0](https://huggingface.co/docs/transformers/v4.49.0/en/kv_cache), [checkpoint chính thức](https://huggingface.co/HuggingFaceTB/SmolLM2-135M/tree/93efa2f097d58c2a74874c7e644dbc9b0cee75a2). [fp32_reference.py](fp32_reference.py) chỉ điều khiển input/cache và kiểm kết quả; các phép tính bên trong model dùng nguyên bản Transformers.

## Đánh giá PTQ v0

Bộ công cụ [PTQ v0](plans/ptq_plan.md) dùng lại backend FP32 trên để chuẩn bị dữ liệu và đo chất lượng trước khi lượng tử hóa. Chặng bước 1–2 đã có dữ liệu cố định và bộ chấm PPL/PIQA/cache; kết quả, quy tắc chấm, công dụng từng module và lệnh chạy nằm trong [báo cáo chặng 1](reports/ptq_stage1.md). Bước 1–2 đã qua QA. Adapter fake-quant và calibration bước 3–4 đã QA PASS; xem [báo cáo chặng 2](reports/ptq_stage2.md) về cấu hình, tham số tĩnh và kiểm chứng model thật.

```bash
# Lần đầu tải parquet và cố định token IDs; dùng --offline ở lần sau.
timeout 300 .venv/bin/python ptq_data.py
timeout 300 .venv/bin/python -m pytest -q test_fp32_reference.py test_ptq.py
timeout 7200 .venv/bin/python ptq_run.py fp32 --offline
```

Dữ liệu và metadata nằm ở `data/`; kết quả FP32 ở `results/ptq/fp32.json`. Lệnh đánh giá chỉ mở tập selection, không đánh giá tập heldout.

Chạy calibration và kiểm adapter bằng cùng checkpoint đã cache:

```bash
timeout 300 .venv/bin/python -m pytest -q test_ptq_fake_quant.py
timeout 3600 .venv/bin/python ptq_calibrate.py --offline --config configs/w8a8kv8_static.json
timeout 3600 .venv/bin/python ptq_validate.py --offline
```

Config và qparams tĩnh nằm trong `calibration/w8a8kv8_static/`; kiểm chứng trước/sau bật fake-quant và reload nằm trong `results/ptq/stage2_validation.json`. A8 MinMax này đã bị loại bởi full PPL; baseline được giữ sau bước 5–8 là W8A16KV8 tĩnh, đã QA PASS chặng 3.


Kết quả bước 5–8 và công dụng từng module/lệnh nằm trong [báo cáo chặng 3](reports/ptq_stage3.md). Trong sweep ban đầu, đã so full64 PPL cho A8 MinMax/Histogram/percentile, A12/A16 MinMax và A8 Dynamic per-token; chỉ W8A16KV8 tĩnh vượt đủ PPL, PIQA và cả hai decode gate. W4 decoder (shared head/embedding W8) đã bị loại bởi full PPL. `candidates/` giữ năm bundle được chọn theo vai trò và trạng thái trong [shortlist](results/ptq/shortlist.json); `calibration/` giữ các kết quả trung gian. A8 SmoothQuant alpha 0,9 là mục tiêu nghiên cứu, chưa đạt ngưỡng chất lượng. Heldout chưa đánh giá.

Đánh giá bổ sung A per-channel và SmoothQuant, gồm PPL đầy đủ và qualify các ứng viên qua PPL, nằm trong [báo cáo mở rộng](reports/ptq_a_extensions.md). Kết quả này giữ nguyên baseline v0 và cung cấp thêm các ứng viên đã qua đủ quality gate; tập heldout vẫn chưa dùng.

Đọc lại baseline và kiểm/chấm bằng PPL đã đo, dùng cùng môi trường và dữ liệu:

```bash
timeout 300 .venv/bin/python -m pytest -q test_ptq_fake_quant.py test_ptq_stage3.py test_ptq_static_a.py
timeout 2400 .venv/bin/python ptq_finalize.py --offline \
    --config candidates/w8a16kv8_static/config.json \
    --qparams candidates/w8a16kv8_static/qparams.safetensors \
    --ppl-result results/ptq/trials/w8a16kv8_static.ppl.json \
    --candidate-dir candidates/w8a16kv8_static \
    --output results/ptq/trials/w8a16kv8_static.final.json
```

Bundle mới ghi bits/policy/observer/trục trong header safetensors. Load sai calibration bị từ chối; khi W bits đổi, phải yêu cầu tính lại W từ source. A Dynamic chỉ tải W/K/V tĩnh bằng nhánh tường minh, không dùng A scale lưu sẵn. Fake-quant vẫn tính FP32 giữa các điểm quantize; payload báo cáo là lý thuyết, chưa có packing/kernel integer hoặc số đo RTL.

`ptq_experiment.py` (`quick`, `diagnose`, `ppl`, `full`) và `ptq_finalize.py` dùng bộ chuẩn FP32 cố định ở `results/ptq/fp32.json`. Finalizer kiểm kết quả PPL được dùng lại thuộc đúng config và qparams của ứng viên. `diagnose` hỗ trợ A per-tensor, per-input-channel (báo số scale cùng min/max) và dynamic per-token.

Kiểm cấu trúc adapter, bất biến trọng số/qparams và oracle W4 chạy riêng bằng `ptq_validate.py`; `ptq_finalize.py --structural-only` giữ chế độ kiểm cấu trúc tường minh. Các lượt đo thường không lặp lại những kiểm tra này; finalizer vẫn so logits full/cache tới từng bit sau khi lưu và nạp lại bundle.

Các lệnh đánh giá và calibration mặc định đọc trực tiếp `data/`; calibration chỉ ghi vào `--output-dir`. Khi chạy lại lệnh lịch sử dùng `--data-dir data/alpha_sweep_runtime`, thay bằng `--data-dir data`: ba file đầu vào cũ giống hệt dữ liệu gốc.
