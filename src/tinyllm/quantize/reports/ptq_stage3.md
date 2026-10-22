# PTQ chặng 3 — so calibration, độ rộng A và shortlist (bước 5–8)

Trạng thái: **hoàn thành, QA độc lập PASS**. Tập heldout chưa đánh giá. Nguồn FP32/scorer/data/reference và bundle MinMax A8 gốc giữ nguyên.

## Kết quả chất lượng

Mỗi PPL bên dưới dùng đúng 64 cửa sổ selection x512, tổng 32704 targets. Mốc FP32: PPL 22.5747142012, PIQA 625/919=68.008705%; decode 32/448 tương ứng26.6760724985/12.0194382541. Gate giữ nguyên: PPL và từng decode tăng ≤5%, PIQA giảm ≤2 điểm phần trăm.

| Cấu hình | PPL full 64 | Tăng so FP32 | PIQA | Decode PPL 32 /448 | Kết luận |
| --- | ---: | ---: | --- | --- | --- |
| [w8a8kv8_static](../results/ptq/trials/w8a8kv8_static.ppl.json) | 51.700820322 | +129.0209% | Chưa chấm: PPL fail | Chưa chấm: PPL fail | Loại: PPL |
| [w8a8kv8_histogram](../results/ptq/trials/w8a8kv8_histogram.ppl.json) | 165.678476877 | +633.9117% | Chưa chấm: PPL fail | Chưa chấm: PPL fail | Loại: PPL |
| [w8a8kv8_percentile](../results/ptq/trials/w8a8kv8_percentile.ppl.json) | 177.699961057 | +687.1637% | Chưa chấm: PPL fail | Chưa chấm: PPL fail | Loại: PPL |
| [w8a12kv8_static](../results/ptq/trials/w8a12kv8_static.ppl.json) | 24.178355816 | +7.1037% | Chưa chấm: PPL fail | Chưa chấm: PPL fail | Loại: PPL |
| [w8a16kv8_static](../results/ptq/trials/w8a16kv8_static.ppl.json) | 22.758690216 | +0.8150% | 616/919 (67.0294%) | 27.144900 / 12.071378 | Đạt đủ gate |
| [w8a8kv8_dynamic](../results/ptq/trials/w8a8kv8_dynamic.ppl.json) | 24.254060329 | +7.4391% | Chưa chấm: PPL fail | Chưa chấm: PPL fail | Loại: PPL |
| [w4a16kv8_static](../results/ptq/trials/w4a16kv8_static.ppl.json) | 51.357892863 | +127.5019% | Chưa chấm: PPL fail | Chưa chấm: PPL fail | Loại: PPL |

Các ca fail PPL là **full-PPL rejects**: không chấm PIQA/decode chất lượng, không gọi structural-cache checks là vượt quality gate. Dynamic là A8 đối xứng per-current-token; W8/K8/V8 vẫn tĩnh. Dynamic full 64 cũng fail, nên không thay baseline tĩnh. Không suy luận thứ hạng đáng tin từ chênh lệch nhỏ giữa hai ca đều fail A12/Dynamic.

Trong sweep tĩnh per-tensor ban đầu, baseline **w8a16kv8_static** là cấu hình 8/12/16 bit duy nhất vượt đủ gate. Đánh giá mở rộng A per-channel/SmoothQuant được báo cáo riêng tại [ptq_a_extensions.md](ptq_a_extensions.md); kết quả này chưa thay đổi baseline v0. PIQA giảm 0.9793 điểm phần trăm. Decode prefill 32 tăng 1.7575%, prefill 448 tăng 0.4321%; mỗi regime chấm 512 targets trên 8 cửa sổ. Shortlist v0 và các ứng viên mở rộng: [shortlist.json](../results/ptq/shortlist.json).

Chẩn đoán 80 hàng cố định, toàn 49152 vocabulary: top1 FP32/candidate full trung bình 75.0000%, KL(FP32||candidate) 0.21455383; cache top1 75.0000%, KL 0.21477614. Sai khác candidate full/cache lớn nhất 1.72691154; đây là chẩn đoán, không áp bound FP32 cho đường đã lượng tử hóa. Mỗi run dùng các hàng 0, prefill−1, prefill, L−2, L−1.

Hai prompt là 32 token đầu của hai cửa sổ selection đầu tiên; greedy tối đa 64 token mới, tổng không vượt 512. Prompt, token IDs và văn bản FP32/candidate nằm trong [kết quả baseline](../results/ptq/trials/w8a16kv8_static.final.json). Đã xem văn bản: prompt thứ nhất trùng đủ 64 token; prompt thứ hai khác các năm, và cả FP32/candidate đều có đoạn lặp. Phép thử này không chứng minh chất lượng hội thoại. Không so sai số logits sau khi greedy prefix đã phân kỳ. Reload config/qparams tái lập bitwise cả full 96 và cache 32+64.

W4 chỉ đổi 210 ma trận decoder, giữ shared embedding/head W8 và A/K/V của baseline. Oracle NumPy chạy **trước PPL**, tính trực tiếp max|source row|/7, shared /127, kiểm 204672 hàng; bằng chứng `weight_qparam_oracle` trong kết quả W4. Không thử thêm KV 4 hoặc quét sửa W4 khi chưa có bằng chứng khoanh vùng.

## Calibration và chẩn đoán

Bốn calibration mới đều dùng cùng 64 cửa sổ train x512 và 16 cache train (prefill 32/448, decode 64), tổng 37632 KV tokens/layer. Fake-quant tắt khi observe; W từ source weights. [Kiểm đối chứng](../results/ptq/static_calibration_checks.json) xác nhận 542 scale/zp W/K/V bằng bit giữa tất cả cấu hình, kể cả bundle Dynamic sau reload. Data IDs bằng nhau. Mỗi A Histogram/percentile chỉ tính qparams một lần tại freeze.

A8 MinMax giữ toàn range; A12 `[-2047,2047]`, A16 `[-32767,32767]` vẫn giữ range với bước nhỏ hơn. A12/A16 dùng torch.ao FakeQuantize qint32 để hỗ trợ miền rộng, đầu ra vẫn FP32. Histogram A8 dùng qint8/2048 bins và L2 search có sẵn. Fallback duy nhất dùng histogram train trên |A| với 65536 bins, percentile 99.99% lấy mép trên bin đạt CDF; đây là xấp xỉ theo bin, không phải order statistic chính xác. Không sweep percentile hoặc dùng selection để tính scale.

Ở `down_proj` layer 11: scale MinMax A8=19.5700321, Histogram=0.0466113, A12=1.2141641, A16=0.0758505. Histogram bin width 1.2236315, bound chọn 5.9196301; percentile bin width 0.0379241, bound 2.8063837. `down_proj` layer 28 tương ứng bin width Histogram1.3386582/bound 53.7069250 và percentile 0.0404465/bound 46.0281528. Chi tiết các điểm nằm trong metadata từng calibration.

| Candidate | Layer 11 vượt range | Layer 11 nonzero→0 | Layer 28 vượt range | Layer 28 nonzero→0 |
| --- | ---: | ---: | ---: | ---: |
| w8a8kv8_static | 0.000000% | 99.998601% | 0.000000% | 99.847921% |
| w8a8kv8_histogram | 0.002162% | 27.636083% | 0.016530% | 50.911204% |
| w8a8kv8_percentile | 0.010300% | 15.927378% | 0.042597% | 45.954514% |
| w8a12kv8_static | 0.000127% | 99.451319% | 0.000000% | 86.008835% |
| w8a16kv8_static | 0.000127% | 38.495636% | 0.000000% | 20.213064% |
| w8a8kv8_dynamic | 0.000254% | 9.603882% | 0.000127% | 45.086416% |

Đo trên cửa sổ selection đầu tiên, mỗi down_proj input 786432 phần tử. `nonzero→0` là count((input!=0)&(output==0))/tổng elements, loại các zero vốn có; không phải tổng output-zero fraction. `vượt range` là |input|>scale×quant_max; Đếm vượt range ở Dynamic dùng bound FP32, không đo riêng clamp sau integer rounding. Input trung gian thay đổi theo upstream quantization, nên các tỷ lệ mô tả candidate, không chứng minh nhân quả riêng một layer. Bước nhỏ hơn không bảo đảm chất lượng tốt hơn: Histogram/percentile làm PPL xấu hơn control; giảm zeroing không tự thay quality gate.

Chẩn đoán quick trước đó được giữ trong `results/ptq/trials/*.quick.json`: FP32 quick 20.8592541; W8 quick 20.9659077 (+0.5113%), W8A8KV8 static44.6319222 (+113.967%), bỏ A FFN22.0450082 (+5.6845%), Dynamic22.6782699 (+8.7204%). Đây là 8 cửa sổ, chỉ dùng khoanh vùng, không thay các số full 64 ở trên.

## Kiểm chứng thực thi

- 35 tests PTQ PASS, exit 0, 3.88 s, timeout 300 s: oracle Python/NumPy rounding/clamp/half-step/zero/negative cho 4/8/12/16; histogram reset/observe/freeze/recalibration; loader/reload; static/dynamic cache và causality; KL direction; payload.
- Regression cuối cùng chạy cả 5 file test: **55 tests PASS**, exit 0, 8.22 s, timeout 300 s; gồm 20 tests FP32/scorer/data cũ và 35 tests PTQ ở trên. Kiểm diff theo baseline, whitespace cả file untracked và liên kết nội bộ đều đạt.
- Loader chung kiểm bits/policy/observer/bin/axis/count, gồm direct calls và `ptq_validate.py`. Legacy chỉ dùng đúng semantics MinMax gốc. Đổi W bits chỉ cho khi tính lại W từ source. Đối với Dynamic, flag tường minh chỉ tải W/K/V; test đổi scale A lưu sẵn thành 1e6 và zp 13 vẫn cho logits Dynamic giống bit; static không được dùng ngoại lệ này.
- Mỗi cấu hình A đã chạy model thật disabled/native full/cache ở 96/512, audited cache ở 32/448, source-weight fingerprints, qparam-state immutability và saved-config/qparam reload full/cache bitwise. Native 3 KV heads, 9 query heads; prefix cache cũ giữ nguyên, token mới quantize một lần trước cache/GQA. Các ca rejected chỉ có structural checks.
- Có một lỗi harness ở lượt structural Dynamic đầu: thiếu import PTQAdapter tại reload. Đã sửa và chạy lại command thành công; các lượt structural/qualification cuối đều sau sửa. Full PPL không bị ảnh hưởng.

## Payload và phần còn FP32

Baseline có 134,515,008 Parameters; shared embedding/head đếm một lần. Payload W bao gồm norm FP32: **134,620,416 bytes**, W scale+zp **1,637,376**, KV 512 **5,898,240**, KV scale+zp **1,440**, A tĩnh metadata **1,688**. Tổng persistent lý thuyết **142,159,160 bytes**. KV dùng 3 head gốc, không nhân lên 9. Còn 35,136 phần tử norm FP32; W FP32 toàn model 538,060,032 bytes, KV FP32 23,592,960 bytes.

| A width | Tổng input payload 211 điểm, prefill 512 (bytes) | Một lượt decode 1, tổng 211 điểm (bytes) | Scale/zp tĩnh (bytes) |
| --- | ---: | ---: | ---: |
| A8 | 76,972,032 | 150,336 | 1,688 |
| A12 | 115,458,048 | 225,504 | 1,688 |
| A16 | 153,944,064 | 300,672 | 1,688 |

Bảng A là tổng payload/traffic qua từng tensor, **không phải peak resident buffer**. [Inventory từng tensor](../results/ptq/trials/w8a16kv8_static.final.json) lấy shape thực từ Linear in_features; gồm cả so sánh 8/12/16 bit. A16 dùng gấp 2 payload A8 ở cùng shape; W/KV/metadata tĩnh giữ nguyên. Dynamic không lưu scale A tĩnh về mặt lý thuyết, nhưng phải giảm max trên hidden vector, tính scale/reciprocal và quantize từng token/điểm. Với 211 điểm và prefill 512, Dynamic mô phỏng sinh 432,128 bytes scale FP32 và 432,128 bytes zero-point int32; tại một điểm, hai workspace tối đa 2,048+2,048 bytes. Đây là cấp phát tạm của mô phỏng, chưa phải buffer/latency RTL. Inventory Dynamic ghi workspace/scale tạm mô phỏng; zero-point 0 có thể là hằng số trong RTL.

Metadata đang tính scale FP32 và zp int32 tường minh. Archive qparams baseline thực tế 1,818,432 bytes, gồm scale/zp và header; chưa có archive W/KV packed. Archive qparams có header/placeholder; không đồng nhất với logical payload. Chưa tạo packed W/KV hoặc kernel integer: tensor runtime fake-quant vẫn FP32. Chưa tính packing/alignment, buffer/scratch/traffic scheduling, DSP/BRAM, timing/area/power. RMSNorm, RoPE arithmetic, attention QK/scale/mask/softmax/AV, SiLU, FFN gate multiply, residual adds, Linear accumulators và logits vẫn FP32; accumulator/phi tuyến integer/RTL thuộc chặng sau. Fake-quant chưa là golden integer.

## Công dụng của code và lệnh

| Code | Công dụng |
| --- | --- |
| `QuantPoint.__init__`, `__call__` | Chọn miền A12/A16, Histogram qint8; observe histogram giữ input nguyên và không tính qparams mỗi token. |
| `reset_observer`, `finish_observation`, `begin_calibration`, `freeze` | Recreate observer để xóa histogram đúng; tính L2 hoặc percentile một lần, khóa scale/zp trước eval. |
| `calibration_contract`, `save_qparams`, `load_qparams` | Gắn provenance vào safetensors; chặn reuse sai bits/policy/observer/axis; Dynamic bỏ hoàn toàn A tĩnh bằng nhánh tường minh. |
| `dynamic_token_fake_quant` | Lấy scale riêng cho hidden vector token hiện tại; không giảm theo batch/token khác, không đọc tương lai. |
| `ptq_calibrate.calibrate` | Chỉ chạy train/full/cache, kiểm coverage, lưu config/qparams/ID/bin resolution; không lấy stats selection. |
| `ptq_experiment.load_candidate`, `run` | Recompute W đúng bits; dùng scorer chung cho quick/PPL-only/diagnose; hash qparams và config/ID gắn với metric. |
| `validate_weight_qparams` | Oracle NumPy toàn bộ source rows, bắt reuse W8 scale khi W4; chạy trước scoring W4. |
| `focused_contracts` | Kiểm actual disabled/native, cache location/prefix/new-token, source weights và static state cho cấu hình đã sửa. |
| `candidate_cache`, `distribution_diagnostic` | Chấm 64 decode targets/regime/window bằng scorer chung; đo full/cache và top1/KL(FP32||candidate) trên 80 hàng/all vocabulary. |
| `greedy`, `ptq_finalize.run` | Sinh hai prompt cố định, qualify PIQA/decode, lưu candidate và kiểm reload bitwise; chỉ reuse PPL khi config+hash qparams+data IDs khớp. |
| `storage_inventory` | Đếm W tied một lần, KV native heads, metadata thực và payload từng input A theo8/12/16 bit. |
| `test_ptq_static_a.py` và tests giữ lại | Oracles độc lập và lifecycle/contract/regression checks, gồm test stale W8 và A động không phụ thuộc A scale đã lưu. |

Chạy từ `src/tinyllm/quantize/`. [Execution record](../results/ptq/stage3_execution.json) giữ exact argv, timeout, exit và thời gian cho từng command/candidate; metadata mỗi result giữ backend thực. Không lấy số đo từ tên test/file.

| Lệnh | Mục đích và phạm vi |
| --- | --- |
| `timeout 300 .venv/bin/python -m pytest -q test_ptq_fake_quant.py test_ptq_stage3.py test_ptq_static_a.py` |35 tests nêu trên; CPU Llama nhỏ/independent tensor oracles. |
| `timeout 300 .venv/bin/python -m pytest -q test_fp32_reference.py test_ptq.py test_ptq_fake_quant.py test_ptq_stage3.py test_ptq_static_a.py` |Regression cuối: 55 tests, gồm kiểm scorer/data/FP32 nguyên gốc. |
| `timeout 1800 .venv/bin/python ptq_calibrate.py --offline --config configs/stage3/NAME.json --output-dir calibration/NAME` |4 calibration mới: Histogram A8, A12, A16, percentile A8. A8 MinMax control giữ bundle cũ. |
| `timeout 1800 .venv/bin/python ptq_experiment.py ppl --offline --config configs/stage3/NAME.json --qparams BUNDLE --output results/ptq/trials/NAME.ppl.json` |Full64 PPL cho 5 static; Dynamic và W4 cùng CLI, timeout 2400 theo execution record. |
| `timeout 2400 .venv/bin/python ptq_experiment.py diagnose ...` |Đúng 1 cửa sổ selection/511 targets mỗi cấu hình A, chỉ thu counters để giải thích, không cập nhật qparams. |
| `timeout 2400 .venv/bin/python ptq_finalize.py ... --structural-only` |Model checks/reload cho các cấu hình fail PPL; không chấm 919 PIQA/16 quality decode. |
| `timeout 2400 .venv/bin/python ptq_finalize.py ... --ppl-result results/ptq/trials/NAME.ppl.json` |Reuse đúng full PPL, chấm 919 PIQA +16 quality decode, diagnostics/greedy/storage/reload cho ca qua PPL. |
| Inline `safetensors.load_file` + `torch.equal` / so `data_ids.json` |Xác nhận W/K/V bằng bit và cùng train coverage; lưu `static_calibration_checks.json`. |

Tất cả model runs: CPU/eager/FP32, eval/inference, batch1 không padding, L≤512, seed 1234, 1 compute/inter-op thread, deterministic, MKLDNN off; nguồn offline cùng revision FP32. Không có build RTL/integer ở chặng này. Các command kết quả cuối exit 0; quality fail vẫn là execution thành công và được ghi riêng.
