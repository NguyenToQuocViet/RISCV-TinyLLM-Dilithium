# PTQ v0 — Chặng 1: bước 1–2

Chặng này chuẩn bị dữ liệu cố định và bộ chấm trên Transformers FP32 nguyên bản, làm mốc cho các ứng viên fake-quant. Chưa chèn fake-quant hoặc calibration. Kế hoạch thực hiện: [ptq_plan.md](../plans/ptq_plan.md).

## Kết quả thực đo

Campaign FP32 exit **0**, `status=PASS`, thời gian tính 660,165 giây. Kết quả đầy đủ theo từng ID/lượt chạy nằm trong [fp32.json](../results/ptq/fp32.json).

| Phép đo                     |                                   Kết quả |                                       Số lượng thực chấm |
| ----------------------------- | ------------------------------------------: | ------------------------------------------------------------: |
| WikiText selection PPL        |                     **22,5747142012** |         64 cửa sổ, 32.704 target; tổng NLL 101.932,8226854 |
| PIQA selection accuracy       |                        **68,008705%** | 625/919 câu đúng, 1.838 lựa chọn, 42.209 token đáp án |
| Decode PPL, prefill 32        |                     **26,6760724985** |                8 lượt × 64 = 512 target; NLL 1.681,2887053 |
| Decode PPL, prefill 448       |                     **12,0194382541** |                8 lượt × 64 = 512 target; NLL 1.273,1008992 |
| Full/cache FP32               |                       **16/16 đạt** |        239.075.328 phần tử logits, 0 phần tử vượt bound |
| Max absolute error full/cache |                    **0,000147819519** |                         Max tỷ lệ error/bound = 0,499802798 |
| NLL so với Transformers loss | **sai khác 3,7618×10⁻⁷ < 10⁻⁶** |             64 target `[32,96)` ở cửa sổ selection đầu |
| Test scorer/oracle/dữ liệu  |                       **20/20 đạt** |                                            Exit 0, 4,03 giây |

Mean NLL từ scorer là 4,6250601821; Transformers loss cùng mask là 4,6250605583. Accuracy FP32 cao hơn rõ mức chọn ngẫu nhiên 50% (nhãn selection: 449 đáp án 0, 470 đáp án 1); không có dấu hiệu chấm gần ngẫu nhiên cần điều tra lại trước khi dùng ngưỡng v0. Mọi chế độ cache dùng nguyên bound `abs(error) <= 2e-4 + 1e-5*abs(expected)`, không nới ngưỡng.

## Dữ liệu và quy tắc đã cố định

Model/tokenizer là `HuggingFaceTB/SmolLM2-135M@93efa2f097d58c2a74874c7e644dbc9b0cee75a2`. Nguồn, seed, cách cắt và số lượng nằm trong [data/metadata.json](../data/metadata.json); token IDs và vai trò được giữ trong các file `data/*.json`.

| Nguồn                                                                                                                                                       | Revision                                     | Cách sử dụng                                                |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------- | -------------------------------------------------------------- |
| `Salesforce/wikitext`, `wikitext-2-raw-v1`                                                                                                               | `b08601e04326c79dfdd32d625aee71d232d685c3` | train → calibration; validation → selection; test → heldout |
| `baber/piqa`, `piqa_validation.parquet`                                                                                                                  | `142f6d7367fd9877f0fb3b5734ea6a545f54cdd1` | chia theo nhóm câu hỏi thành selection và heldout         |
| [lm-evaluation-harness: PIQA](https://github.com/EleutherAI/lm-evaluation-harness/blob/d6de81643928d653435c431bae19945d41d32520/lm_eval/tasks/piqa/piqa.yaml) | `d6de81643928d653435c431bae19945d41d32520` | prompt, hai lựa chọn, nhãn và accuracy                     |

WikiText nối toàn bộ hàng `text` bằng `\n\n`, tokenize không special token, chia block liên tiếp 512 token và bỏ đuôi thiếu. Mỗi split tạo riêng `numpy.random.default_rng(1234)` (PCG64), hoán vị chỉ số block rồi lấy 64 block. Mỗi record lưu `id`, split, role, `block_index`, `token_start` và `input_ids`.

| Split / vai trò       | Token nguồn | Block đầy đủ | Token đuôi bỏ | Cửa sổ giữ |
| ---------------------- | -----------: | ---------------: | ---------------: | ------------: |
| train / calibration    |    2.567.892 |            5.015 |              212 |     64 × 512 |
| validation / selection |      268.271 |              523 |              495 |     64 × 512 |
| test / heldout         |      304.978 |              595 |              338 |     64 × 512 |

PIQA có 1.838 dòng nhưng chỉ 1.802 nhóm goal sau khi chuẩn hóa whitespace/chữ hoa, tức 36 dòng trùng câu hỏi. Hoán vị nhóm với seed 1234 rồi chia hai nửa: mỗi nửa 901 nhóm, thực tế 919 dòng. Giữ các bản trùng trong cùng nửa để không rò câu hỏi giữa selection và heldout. Không có câu bị loại vì vượt L; quy tắc chung là loại cả câu nếu một trong hai lựa chọn dài hơn 512, không cắt đáp án. Không có goal chuẩn hóa xuất hiện ở cả hai nửa.

8 cửa sổ đầu của selection được cố định trong [cache_cases.json](../data/cache_cases.json). Mỗi cửa sổ chạy hai chế độ: prefill 32 + decode 64 (96 token đầu vào), và prefill 448 + decode 64 (512 token). Đầu vào luôn là token thật đã lưu.

**Cách chấm:**

- PPL: hàng logits `i−1` dự đoán target `i`; chấm 511 target/cửa sổ, cộng NLL trên toàn tập rồi tính `exp(total_nll / total_targets)`. Mẫu số selection là `64 × 511 = 32.704`; không trung bình PPL từng cửa sổ.
- PIQA: prompt `Question: {goal}\nAnswer:`, nối một dấu cách và đáp án. Tokenize cả chuỗi rồi cắt tại độ dài tokenized prompt, xác nhận prefix token khớp. Chỉ cộng LL của continuation; tổng LL cao hơn thắng, hòa chọn 0. Đây là `acc`, không dùng `acc_norm`. Cách encode theo [TemplateLM._encode_pair](https://github.com/EleutherAI/lm-evaluation-harness/blob/d6de81643928d653435c431bae19945d41d32520/lm_eval/api/model.py#L358); cách chọn đáp án theo [process_results](https://github.com/EleutherAI/lm-evaluation-harness/blob/d6de81643928d653435c431bae19945d41d32520/lm_eval/api/task.py#L1397).
- Decode: target `[prefill, prefill+64)`, dùng hàng logits `[prefill−1, prefill+63)`. Vì vậy dự đoán token đầu sau prompt lấy từ hàng prefill cuối. Mỗi chế độ có `8 × 64 = 512` target, cả hai có 1.024 target.
- Giữ ngưỡng candidate: PPL tăng ≤5% và accuracy giảm ≤2 điểm phần trăm so FP32 trên cùng dữ liệu; áp dụng ngưỡng PPL cho từng chế độ decode. Heldout chỉ được chuẩn bị, chưa đánh giá hoặc dùng để chọn cấu hình.

Kiểm tra thủ công ba câu đầu selection với định nghĩa task và tokenizer thật; khoảng dưới đây là chỉ số target `[start, stop)`:

| ID validation                           | Độ dài prompt (`answer_start`) | Target đáp án 0 / 1      | Điều kiểm tra                                                             |
| --------------------------------------- | ----------------------------------: | --------------------------- | ---------------------------------------------------------------------------- |
| 320 — Add more fluff to whip cream.    |                                  13 | `[13,25)` / `[13,25)`   | Continuation có dấu cách đầu; nhãn 1; prompt không được chấm      |
| 234 — Create a Mask Armature           |                                  10 | `[10,134)` / `[10,135)` | Hai đáp án khác độ dài, giữ nguyên toàn bộ, không chuẩn hóa LL |
| 1094 — how do you prepare for surgery? |                                  12 | `[12,24)` / `[12,22)`   | Hàng dự đoán bắt đầu ở 11, không dịch sai target                   |

## Công dụng của phần mã đã thêm

| File / hàm                                        | Công dụng và lý do                                                                                                                                                                                                                                                   |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [ptq_data.py](../ptq_data.py): `wikitext_windows` | Chọn block có seed, lưu vị trí gốc và role; báo lỗi nếu nguồn thiếu 64 block.                                                                                                                                                                                |
| `encode_choice`                                  | Cố định ranh giới prompt/answer bằng joint tokenization, kiểm prefix không bị đổi bởi BPE.                                                                                                                                                                    |
| `piqa_halves`                                    | Chia nhóm câu hỏi trước khi loại mẫu quá dài, lưu nhãn và cả hai continuation; ngăn rò câu hỏi sang heldout.                                                                                                                                            |
| `prepare`, `main`                              | CLI lấy parquet pinned, tokenize, lưu bộ dữ liệu/metadata/cache cases. Chỉ nạp tokenizer, không chạy model.                                                                                                                                                     |
| [ptq_eval.py](../ptq_eval.py): `score_targets`    | Thực hiện shift và mask bằng khoảng target, trả tổng NLL/count; dùng nguyên hàm cho FP32 và candidate sau này.                                                                                                                                               |
| `aggregate_nll`                                  | Cộng NLL và số target trước khi lấy exp, tránh sai PPL khi số token khác nhau.                                                                                                                                                                                  |
| `choose_answer`                                  | Chọn bằng tổng LL, tie 0, từ chối điểm NaN/Inf.                                                                                                                                                                                                                   |
| `full_logits`                                    | Chạy một chuỗi batch 1, không padding, `use_cache=False`; là đường full forward độc lập với vòng decode.                                                                                                                                                  |
| `evaluate_ppl`, `evaluate_piqa`                | Lần lượt chấm mỗi cửa sổ/đáp án và giải phóng logits; giữ số đo và ID từng mẫu, không giữ tensor logits toàn tập.                                                                                                                                 |
| `evaluate_cache`                                 | Cache mới mỗi lượt; gọi vòng prefill/decode có sẵn, so mọi hàng và toàn vocabulary với full forward, rồi chấm đúng 64 target/chế độ.                                                                                                                 |
| `check_transformers_loss`                        | Dùng `labels=-100` để Transformers tự shift/mask; đối chiếu mean NLL của scorer với loss thư viện trên cùng 64 target.                                                                                                                                    |
| [ptq_run.py](../ptq_run.py): `run_fp32`, `main` | Cố định backend bằng `fp32_reference.configure_runtime`, chỉ mở selection; chạy loss/PPL/cache/PIQA và ghi kết quả sau khi toàn bộ đạt.                                                                                                                  |
| [test_ptq.py](../test_ptq.py)                       | Oracle nhỏ tính bằng xác suất/log tay: shift/mask, 64 target gồm target đầu, PPL gộp, tổng LL/tie và case hai đáp án đảo thứ hạng nếu dùng mean LL; kiểm dữ liệu/role/group/length/boundary thật và trường hợp nguồn thiếu/mẫu quá dài. |
| [test_fp32_reference.py](../test_fp32_reference.py) | Kiểm oracle logits: đúng tolerance/số phần tử, phát hiện vượt bound, đảo vị trí, khác shape, NaN và Inf. Bổ sung file mà README cũ đã tham chiếu.                                                                                                  |

`fp32_reference.py`, `cases.json` và các artifact `reference/` giữ nguyên. Backend vẫn Python 3.12.3, PyTorch 2.6.0+cpu, Transformers 4.49.0, CPU/eager/FP32, `eval`, inference mode, một compute/inter-op thread, seed 1234, deterministic algorithms, MKLDNN tắt. Chỉ thêm `pyarrow==20.0.0` để đọc parquet; không thay phiên bản thư viện nền. Mỗi lúc chỉ giữ logits của một cửa sổ/đáp án hoặc một cặp full/cache.

## Các lệnh chạy và ý nghĩa

Chạy từ `src/tinyllm/quantize/` trong `.venv` FP32 đã có. Các lệnh dưới là lệnh đã dùng cho chặng này; `timeout` tính bằng giây, exit 0 là thành công.

```bash
.venv/bin/python -m pip install pyarrow==20.0.0
.venv/bin/python -m pip check
```

Lệnh đầu cài reader parquet duy nhất được thêm; lệnh sau kiểm dependency không xung đột. Cả hai exit 0; `No broken requirements found`. `requirements.txt` đã ghi pin để máy mới cài đủ bằng lệnh setup README.

```bash
timeout 300 .venv/bin/python ptq_data.py
# Lần phát lại từ nguồn đã cache:
timeout 300 .venv/bin/python ptq_data.py --offline
```

Tải nguồn pinned và tạo token IDs/role/metadata/cache cases. Exit 0. Cảnh báo tokenizer về chiều dài corpus 2.567.892 token xảy ra trước khi chia block; corpus không được đưa nguyên vào model, mọi đầu vào đánh giá ≤512.

```bash
timeout 300 .venv/bin/python ptq_data.py --offline --data-dir /tmp/tinyllm-ptq-stage1-data-replay
diff -qr data /tmp/tinyllm-ptq-stage1-data-replay
```

Dựng lại dữ liệu từ cache vào nơi tạm và so với bộ đã cố định; cả hai exit 0, không có file khác. Đây là phép kiểm tái lập dữ liệu một lần, không thêm cơ chế kiểm revision/hash vào mỗi lượt đánh giá.

```bash
timeout 300 .venv/bin/python -m pytest -q test_fp32_reference.py test_ptq.py
```

Chạy kiểm oracle/scorer và invariant dữ liệu trên backend thật đang cài; **20 passed**, exit 0, 4,03 giây ở lần chạy sau thay đổi test cuối.

```bash
timeout 7200 .venv/bin/python ptq_run.py fp32 --offline
```

Chạy model FP32 thật trên selection: 64 cửa sổ WT, 16 cache runs, 1.838 lượt đáp án PIQA, kèm đối chiếu loss. Kết quả chi tiết và cấu hình runtime nằm trong [results/ptq/fp32.json](../results/ptq/fp32.json). Không chạy lại campaign FP32 cũ vì model, code reference và dependency nền không đổi; campaign mới bổ sung L=512 theo yêu cầu.

## Giới hạn và bàn giao

Bước 1–2 đã có dữ liệu, scorer và kết quả FP32; QA đã PASS để tiếp tục bước 3–4. Calibration chưa chạy model, heldout chưa đánh giá. PPL là protocol cửa sổ độc lập L=512 để so ứng viên cùng điều kiện, không phải phép đo trực tiếp tương đương các số trong paper. PIQA là nửa validation đã cố định với scorer riêng theo task pinned; chưa tích hợp toàn bộ lm-evaluation-harness. Chưa đánh giá padding, batch lớn hoặc context trên 512.

Kiểm tra diff so baseline xác nhận chỉ README, requirements và liên kết/trạng thái PTQ plan được sửa trong các file có sẵn; source FP32, cases, references và tài liệu ngoài quantize giữ nguyên. Link cục bộ và whitespace được kiểm cả file mới; `git diff --check` exit 0. Không commit/push.
