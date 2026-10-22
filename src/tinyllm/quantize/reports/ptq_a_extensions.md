# PTQ extension — activation per-channel và SmoothQuant

Trạng thái: **đã chạy trên selection**; không dùng tập heldout. Kết quả này bổ sung cho baseline v0 trong [báo cáo chặng 3](ptq_stage3.md), không tự đổi lựa chọn baseline đã duyệt.

## Kết quả

Mốc giữ nguyên: FP32 full PPL 22.5747142012, PIQA 625/919 (68.0087%), decode PPL 26.6760724985 / 12.0194382541. Các ngưỡng giữ nguyên: full/decode PPL tăng tối đa 5%, PIQA giảm tối đa 2 điểm phần trăm. Mỗi PPL chấm 64 cửa sổ selection, 32,704 targets; decode chấm 512 targets ở mỗi regime.

| Cấu hình | A | Full PPL | Tăng PPL | PIQA | Decode tăng (prefill 32 / 448) | Kết luận |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| [A8 per-input-channel](../results/ptq/extra/w8a8kv8_per_input_channel.ppl.json) | 8 bit, scale theo input channel | 23.116170900 | +2.3985% | 612/919 (66.5941%, −1.4146 pp) | +2.4716% / +2.5922% | Đạt đủ gate; [final](../results/ptq/extra/w8a8kv8_per_input_channel.final.json) |
| [A12 per-input-channel](../results/ptq/extra/w8a12kv8_per_input_channel.ppl.json) | 12 bit, scale theo input channel | 22.876810520 | +1.3382% | 619/919 (67.3558%, −0.6529 pp) | +1.0496% / +1.6406% | Đạt đủ gate; [final](../results/ptq/extra/w8a12kv8_per_input_channel.final.json) |
| [A8 SmoothQuant](../results/ptq/extra/w8a8kv8_smoothquant.ppl.json) | 8 bit, static per-tensor sau cân bằng | 1060.498738135 | +4597.7283% | Không chấm: PPL fail | Không chấm: PPL fail | Loại tại full PPL |
| [A12 SmoothQuant](../results/ptq/extra/w8a12kv8_smoothquant.ppl.json) | 12 bit, static per-tensor sau cân bằng | 22.759422441 | +0.8182% | 619/919 (67.3558%, −0.6529 pp) | +0.5986% / +0.7790% | Đạt đủ gate; [final](../results/ptq/extra/w8a12kv8_smoothquant.final.json) |

PPL ratio dùng baseline FP32, accuracy drop là chênh lệch tuyệt đối theo đơn vị 0–1; cột hiển thị đổi sang điểm phần trăm. “Đạt đủ gate” gồm full PPL, PIQA, hai decode PPL; finalizer cũng xác minh cache, bất biến source/qparams, storage inventory và reload full/cache bitwise. Các ứng viên mới là fake-quant với phép toán FP32, không phải kết quả RTL.

## Tìm alpha cho W8A8 SmoothQuant

Đã rà 13 alpha trên cùng W8A8/KV8, calibration train và 8 cửa sổ selection. Mười quick result đã có sẵn và được kiểm tra lại theo config, calibration IDs, qparams SHA256 và selection IDs; alpha 0.65 dùng calibration đã có. Alpha 0.7 và 0.75 được calibration riêng. Quick PPL chỉ dùng để xếp hạng, không làm tiêu chí đạt.

| Alpha | Quick PPL (8 cửa sổ) | Tỷ lệ so FP32 quick | Full PPL | Kết luận |
| ---: | ---: | ---: | ---: | --- |
| 0.2 | 68.4243 | 3.2803 | — | Không chấm full |
| 0.4 | 33.9753 | 1.6288 | — | Không chấm full |
| 0.6 | 23.9562 | 1.1485 | — | Không chấm full |
| 0.65 | 23.2811 | 1.1161 | — | Chỉ quick; dùng calibration đã có |
| 0.7 | 22.9462 | 1.1001 | — | Không chấm full |
| 0.75 | 22.4924 | 1.0783 | — | Không chấm full |
| 0.8 | 22.2039 | 1.0645 | 24.1616 (+7.0293%) | Loại tại full PPL |
| 0.825 | 22.2951 | 1.0688 | — | Không chấm full |
| 0.85 | 22.2211 | 1.0653 | — | Không chấm full |
| 0.875 | 22.1177 | 1.0603 | 24.0985 (+6.7501%) | Loại tại full PPL; lần chạy đầu bị hủy ở 16/64, kết quả dùng lần chạy lại |
| 0.9 | 22.0173 | 1.0555 | 23.9578 (+6.1267%) | Loại tại full PPL |
| 0.95 | 22.7378 | 1.0901 | — | Không chấm full |
| 1.0 | 22.3238 | 1.0702 | — | Không chấm full |

Ngưỡng full PPL vẫn là +5% (23.7035). Alpha 0.9 đứng đầu quick screen nhưng full PPL vượt ngưỡng; đây là lý do không dùng quick PPL để chọn cấu hình cuối. Hai ứng viên kế tiếp đủ ngân sách full-PPL là 0.875 và 0.8; cả hai cũng trượt. Vì vậy không alpha W8A8 SmoothQuant nào được qualify, và không chạy PIQA/decode/finalizer cho nhánh này. Kết quả alpha 0.5 cũ vẫn là PPL 1060.4987 (+4597.7283%); không chạy lại. Shortlist và W8A16 baseline được giữ nguyên. Alpha 0.65 có calibration hoàn tất nhưng chỉ được quick screen; không đưa vào full ranking ngân sách.

Trong các SmoothQuant A8 được chấm full, alpha 0.9 tốt nhất nhưng PPL 23.9578 vẫn kém A8 per-input-channel (23.1162), A12 SmoothQuant alpha 0.5 (22.7594) và baseline W8A16 (22.7587). Do đó sweep này chưa cho lý do đổi cấu hình A8 đã qualify.

Các lệnh mới dùng CPU/eager/FP32, batch 1, seed 1234, một thread, deterministic và MKLDNN off. Calibration alpha 0.7/0.75 đọc bản cô lập của train/selection/cache-case inputs; SHA256 đầu vào và file cache-case sau calibration khớp dữ liệu gốc. [Execution record](../results/ptq/extra/w8a8kv8_smoothquant_alpha_sweep.json) ghi config, qparams hash, argv, thời gian, artifact được dùng lại và phép chạy bị hủy. `ptq_calibrate.py` thu thống kê train và lưu qparams; `ptq_experiment.py quick` sàng lọc 8 cửa sổ; `ptq_experiment.py ppl` chấm đủ 64 cửa sổ; finalizer không chạy vì không ứng viên nào qua full-PPL gate. Regression suite được chạy lại sau khi ghi nhận campaign.

## Ý nghĩa phép thử

**Per-input-channel A** giữ riêng một scale cho từng feature ở chiều cuối của input Linear; calibration lấy biên độ min/max theo kênh trên tập train rồi áp scale broadcast theo chiều đó. Thay vì một scale dùng chung cho toàn vector, các kênh có biên độ nhỏ giữ được bước lượng tử nhỏ hơn. Cả A8 và A12 qua đủ gate ở lần chạy này. Đây là scale theo kênh của activation input; W vẫn per-output-row, còn K/V giữ per-native-head như baseline. Trong số nguyên, scale khác nhau theo lane input cần được gấp vào hệ số trọng số theo input channel hoặc xử lý bằng các hệ số/tích lũy riêng; một scale chung sau dot-product không đủ. Fake-quant hiện tại chưa đo chi phí RTL.

**SmoothQuant** dùng max activation theo feature thu trên train và max trọng số theo feature đầu vào để tạo scale `s = x_max^alpha / w_max^(1-alpha)`. Adapter biến đổi activation thành `x/s` và trọng số thành `W*s`, giữ nguyên phép Linear trước quantization; scale áp dụng cho Linear decoder, loại trừ `lm_head` để bảo toàn shared embedding/head. Scale `s` vẫn cần ở runtime để chia activation `x/s`, trừ khi datapath gộp tương đương; nó không chỉ là metadata tái dựng. Trong sweep W8A8, alpha 0.9 có quick PPL thấp nhất nhưng thất bại full PPL; hai ứng viên tiếp theo được chấm full cũng vượt ngưỡng. A12 SmoothQuant alpha 0.5 vẫn qua đủ gate. Đây là kết luận trong lưới alpha và ngân sách đã chạy, không phải tối ưu toàn cục.

## Payload và metadata

Các số dưới đây được cộng từ inventory của 211 tensor A ở context 512. A payload là tổng logical tensor qua một prefill hoặc một token decode; đây không phải peak buffer hay traffic đo trên chip. Persistent total tính W/KV payload, metadata scale/zp, A scale/zp và SmoothQuant scale dùng runtime, giả định payload được pack đúng bit; chưa tính alignment/buffer.

| Cấu hình | A payload prefill 512 | A payload mỗi decode token | Metadata scale/zp A | SmoothQuant scale runtime (FP32) | Tổng persistent lý thuyết |
| --- | ---: | ---: | ---: | ---: | ---: |
| A8 per-input-channel | 76,972,032 B | 150,336 B | 1,202,688 B | — | 143,360,160 B |
| A12 per-input-channel | 115,458,048 B | 225,504 B | 1,202,688 B | — | 143,360,160 B |
| A12 SmoothQuant | 115,458,048 B | 225,504 B | 1,688 B | 599,040 B | 142,758,200 B |

Scale A per-channel có 150,336 giá trị tổng cộng; ở FP32 scale + int32 zero-point, metadata là 1,202,688 B. Baseline A per-tensor cần 1,688 B nên per-channel thêm **1,201,000 B** và persistent total tăng cùng lượng này so với W8A16KV8 (142,159,160 B). SmoothQuant dùng 149,760 scale input-feature, tương đương 599,040 B FP32; chúng được tính vào persistent total vì adapter đọc chúng khi chia activation. Nếu datapath gộp phép chia tương đương, phần lưu riêng có thể giảm; inventory hiện tại tính cách giữ vector scale độc lập. A payload A8/A12 lấy từ `static_width_comparison_bytes` trên shape từng input Linear, cộng đủ 211 điểm; không tăng bởi số lượng scale. Đây là ước tính lưu trữ/transfer theo tensor, chưa phải đo area, timing, power hay RTL.

## Code và lệnh đã chạy

| Phần | Công dụng |
| --- | --- |
| `QuantPoint` trong `ptq_fake_quant.py` | Hỗ trợ observer per-input-channel: scale vector theo chiều cuối và kiểm số channel lúc chạy; SmoothQuant dùng effective weight đã nhân scale kênh. |
| `PTQAdapter.begin_smooth_calibration` / `finalize_smoothquant` | Thu activation max trên train, kết hợp weight max, tạo scale alpha=0.5; bỏ shared LM head và lưu contract/scale để reload kiểm tra nghiêm ngặt. |
| `ptq_calibrate.py` | Chạy 64 prefill train + 16 lượt cache train để tạo qparams A/W/K/V và SmoothQuant stats; selection không được dùng trong hiệu chỉnh. |
| `ptq_experiment.py ppl` | Chạy cùng full-PPL scorer trên 64 cửa sổ selection và ghi config, ID, qparams hash, PPL, thời gian. |
| `ptq_finalize.py` | Với PPL-pass: kiểm native/disabled, PIQA, 16 cache/decode checks, prompt greedy, storage, source/qparams immutability và reload bitwise. A8 SmoothQuant fail PPL nên không chạy bước qualify. |
| `test_ptq_a_extensions.py` | Oracle rounding/scale theo channel; kiểm SmoothQuant giữ phép Linear, weight tying, reload từ chối scale sai shape/NaN/0, và inventory tính đúng scale runtime. |

Lệnh chính mỗi cấu hình, chạy từ `src/tinyllm/quantize/`:

```bash
timeout 1800 .venv/bin/python ptq_calibrate.py --offline --config configs/extra/NAME.json --output-dir calibration/NAME
timeout 1800 .venv/bin/python ptq_experiment.py ppl --offline --config configs/extra/NAME.json --qparams calibration/NAME/qparams.safetensors --output results/ptq/extra/NAME.ppl.json
timeout 2400 .venv/bin/python ptq_finalize.py --offline --config configs/extra/NAME.json --qparams calibration/NAME/qparams.safetensors --ppl-result results/ptq/extra/NAME.ppl.json --candidate-dir candidates/NAME --output results/ptq/extra/NAME.final.json
```

`ptq_calibrate.py` tạo tham số chỉ từ train; `ptq_experiment.py ppl` loại nhanh các phương án không qua cổng PPL; `ptq_finalize.py` chấm các cổng còn lại và kiểm khả năng lặp lại sau lưu/nạp. Lệnh finalizer chỉ áp dụng cho ứng viên PPL-pass. Thời gian từng lần, argv đầy đủ, backend và kết quả nằm trong [execution record](../results/ptq/stage3_execution.json). Tất cả campaign chạy CPU/eager/FP32, batch 1, seed 1234, một compute/inter-op thread, deterministic, MKLDNN off. Mỗi calibration mất 289–458 giây; PPL 197–206 giây; finalizer A8/A12 per-channel lần lượt 643.478/633.052 giây, SmoothQuant A12 928.194 giây.

Regression cuối cùng dùng lệnh:

```bash
timeout 300 .venv/bin/python -m pytest -q test_fp32_reference.py test_ptq.py test_ptq_fake_quant.py test_ptq_stage3.py test_ptq_static_a.py test_ptq_a_extensions.py
```

Lệnh regression trên chạy lại sau khi bổ sung kiểm tra SmoothQuant qparams và sửa inventory runtime metadata: **59 passed**, exit 0, 11.62 giây. Các JSON final được cập nhật chỉ từ scale-count đã lưu; không chạy lại model. Đây là fake-quant software evidence, không đo diện tích, timing, năng lượng, integer accumulator hay peak buffer. Tập heldout vẫn chưa được mở.
