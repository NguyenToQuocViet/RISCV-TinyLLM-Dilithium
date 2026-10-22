# PTQ v0 — Chặng 2: bước 3–4

Chặng này thêm adapter fake-quant và calibration tĩnh, dùng cùng checkpoint/backend FP32 đã được kiểm ở [chặng 1](ptq_stage1.md). Cấu hình W8A8KV8 ở đây là cấu hình để kiểm cơ chế; chưa đánh giá hoặc kết luận đạt ngưỡng chất lượng của bước 5–8.

## Kết quả kiểm chứng trên model thật

Validation exit **0**, `status=PASS`, thời gian **315,868 giây**. Bằng chứng đầy đủ: [stage2_validation.json](../results/ptq/stage2_validation.json).

| Phép kiểm | Kết quả thực |
| --- | --- |
| Disabled trước khi bật candidate | **20/20 case**, 26 split cache; **536.444.928 phần tử logits**, 0 vượt bound |
| Disabled sau khi bật candidate | **20/20 case**, 26 split cache; **536.444.928 phần tử logits**, 0 vượt bound |
| Disabled full-forward so native full-forward | Khớp tới từng bit ở cả hai gate; max error = **0** |
| Disabled cache so native full-forward | Max error **0,000151157379**, max error/bound **0,708295345**; giữ nguyên `2e-4 + 1e-5*abs(expected)` |
| K/V ở full-forward không cache | Tất cả 60 điểm có **2 call / 1.024 token**, trên hai cửa sổ selection x512 |
| Cache khi bật fake-quant | Hai protocol 32+64 và 448+64: **7.800 tensor mới** đúng đầu ra FQ, **7.680 prefix tensor** giữ nguyên bit |
| Vị trí K/V khi cache | **130 kiểm K sau RoPE**, **130 kiểm V sau projection** ở layer đầu; mọi layer nhận 3 KV head, trước GQA thành 9 head |
| Số lần FQ K/V | Mỗi điểm **65 call**, 96 hoặc 512 token tùy protocol; không đưa lại lịch sử vào quantizer |
| Tham số tĩnh và nguồn | Mọi buffer qparams/observer giữ nguyên khi eval; mọi Parameter nguồn giữ nguyên; weight tying còn nguyên |
| Embedding/LM head | Dùng cùng một tensor W đã FQ, materialize **một lần** trong phase candidate; lookup và head khớp phép tính trực tiếp với tensor đó |
| Adapter mới nạp config/qparams | **25.165.824 logits khớp bitwise**, max error = **0** |
| Unit/invariant tests | **37/37 PASS**, exit 0, **3,65 giây**, gồm đủ 20 test chặng 1 |

20 case/gate gồm 4 case gốc (1/8/32/256 token, 10 cache split) và 16 case mới từ 8 cửa sổ selection, mỗi cửa sổ hai protocol. So mọi vị trí và toàn vocabulary; không chỉ so các hàng logits đã lưu trong reference cũ. Observer tắt ở toàn bộ eval selection; selection chỉ dùng kiểm adapter, không thu thống kê.

## Cấu hình và dữ liệu

[configs/w8a8kv8_static.json](../configs/w8a8kv8_static.json) và bản config đi cùng [calibration](../calibration/w8a8kv8_static/config.json) ghi lựa chọn đã chạy. [Metadata calibration](../calibration/w8a8kv8_static/metadata.json) có cấu hình backend, coverage và danh sách điểm; [data_ids.json](../calibration/w8a8kv8_static/data_ids.json) truy về từng cửa sổ train và cache protocol.

| Nhóm | Điểm áp dụng | Chính sách | Số điểm / scale |
| --- | --- | --- | ---: |
| W | `q/k/v/o_proj`, `gate/up/down_proj` của 30 layer; embedding/LM head dùng chung | tĩnh per-output-row, axis 0 | 211 / 204.672 |
| A | đầu vào 210 Linear decoder và LM head | tĩnh per-tensor | 211 / 211 |
| K | sau RoPE, trước cache.update và GQA | tĩnh per-native-KV-head, axis 1 của `[B,H,T,D]` | 30 / 90 |
| V | sau projection, trước cache.update và GQA | tĩnh per-native-KV-head, axis 1 của `[B,H,T,D]` | 30 / 90 |
| Tổng | | | **482 / 205.063** |

Miền đối xứng: 8 bit `[-127,127]`, 4 bit `[-7,7]`, zero-point 0. Scale là `max(max(abs(min),abs(max))/qmax, eps_float32)`; W giảm trên chiều còn lại của mỗi hàng, K/V giảm trên B/T/D của từng head. Dùng `torch.ao.quantization.FakeQuantize` với MinMaxObserver/PerChannelMinMaxObserver của PyTorch 2.6, làm tròn nearest ties-to-even và clamp. Test oracle độc lập kiểm cả 4/8 bit. Fake-quant trả tensor FP32, chưa tạo trọng số INT4/INT8 đóng gói hoặc phép tính số nguyên.

Model giữ **Parameter gốc duy nhất** của embedding/LM head. Trong một phase eval không đổi cấu hình, khi bật W một tensor W đã fake-quant được materialize và dùng cho cả lookup và phép chiếu; không ghi đè Parameter gốc. Thay chế độ, bật/tắt nhóm/điểm hoặc load qparams đều xóa tensor materialized. Đổi bit/policy cấu trúc cần tạo adapter mới từ config tương ứng. `enabled` chọn mặc định theo W/A/K/V; API `set_point_enabled` cho phép ghi đè riêng từng điểm.

Attention adapter gắn trên instance trong mã thí nghiệm; không sửa Transformers đã cài. Nó giữ thứ tự của [Llama 4.49](https://github.com/huggingface/transformers/blob/v4.49.0/src/transformers/models/llama/modeling_llama.py), gọi lại `apply_rotary_pos_emb` và `eager_attention_forward`. K/V được fake-quant khi còn **3 KV head**, trước khi thư viện mở rộng thành **9 query head**. Đường full-forward `use_cache=False` cũng đi qua đúng hai điểm này.

RMSNorm, RoPE, attention QK/scaling/mask/softmax/AV, SiLU, gate multiply, residual, accumulator Linear và logits vẫn FP32. Observer/fake-quant là hai điều khiển riêng: thu MinMax với fake-quant tắt; freeze rồi tắt toàn bộ observer; sau đó mới bật fake-quant để kiểm model.

## Kết quả calibration

Lệnh calibration exit **0**, `status=PASS`, thời gian **248,840 giây**. Toàn bộ dữ liệu thống kê là train; không dùng selection hoặc heldout:

- 64 full-prefill × 512 = **32.768 token**.
- 8 cửa sổ train × hai protocol 32+64 và 448+64 = **16 lượt cache**, **1.024 lượt decode**. [calibration_cache_cases.json](../data/calibration_cache_cases.json) giữ ID/split tương ứng.
- Mỗi điểm A/K/V được gọi **1.104 lần**; mỗi K/V quan sát **37.632 token/layer**; mỗi W thu thống kê từ trọng số **một lần**.
- **205.063 scale** dương, hữu hạn; zero-point bằng 0; đủ vector 3 scale cho từng K/V và đủ số hàng W.
- [qparams.safetensors](../calibration/w8a8kv8_static/qparams.safetensors) có **1.745.912 byte**, chỉ lưu scale/zero-point; không lưu thêm checkpoint hoặc tensor trọng số đã fake-quant.

| Nhóm scale | Nhỏ nhất | Lớn nhất |
| --- | ---: | ---: |
| W | 0,000476747053 | 0,0733267739 |
| A | 0,00426451443 | 20,8716831 |
| K | 0,0480736010 | 0,183229819 |
| V | 0,00258266064 | 0,186026588 |

## Công dụng từng phần mã

| File / hàm | Công dụng |
| --- | --- |
| [ptq_fake_quant.py](../ptq_fake_quant.py): `default_config` | Ghi bit, policy, nhóm bật/tắt, weight tying và phần còn FP32; làm đầu vào để tạo lại adapter. |
| `QuantPoint.__init__`, `__call__` | Tạo FakeQuantize/observer đúng trục, kiểm số channel, áp dụng một lần tại điểm biểu diễn và đếm call/token/shape. Callback capture chỉ dùng kiểm vị trí/cache. |
| `QuantPoint.validate`, `reset_counts` | Kiểm scale/zp và xóa counter phục vụ các phép kiểm độc lập; không sửa qparams. |
| `PTQAdapter.__init__`, `_add_point`, `_add_weight`, `_bind` | Tìm đúng các Linear, tạo bank quantizer, gắn forward trên instance; giữ tên module và Parameter/weight tying gốc. |
| Forward Linear / embedding / attention được gắn | Linear dùng A/W đã chọn; embedding dùng cùng W với head; attention chèn K/V sau RoPE/projection trước cache/GQA. Phép toán xen giữa vẫn do FP32/PyTorch thực hiện. |
| `native`, `restore` | Tạm trả nguyên forward gốc để lấy oracle hoặc tháo adapter; không cần sao chép model, không chạm site-packages. |
| `set_mode`, `set_enabled`, `set_point_enabled` | Điều khiển disabled/observe/quantize và nhóm/điểm độc lập; xóa W materialized khi cấu hình thay đổi. Không cho bật quantize trước freeze/load. |
| `begin_calibration`, `freeze` | Reset observer; thu W từ nguồn, bật thống kê A/K/V nhưng tắt FQ; xác nhận mọi điểm đã được quan sát trước khi khóa tham số. |
| `quantized_weight` | Tạo mỗi W một lần khi eval và dùng lại; embedding/head lấy cùng một tensor. Disabled đọc Parameter nguồn. |
| `point_specs`, `qparam_state` | Ghi coverage/trục/count và snapshot buffer để bắt mọi thay đổi scale/zp/observer khi eval. |
| `save_qparams`, `load_qparams` | Lưu/đọc scale và zero-point bằng safetensors; kiểm đúng tên điểm, số scale và giá trị; load xóa W cache và giữ observer tắt. |
| [ptq_calibrate.py](../ptq_calibrate.py): `calibration_cache_cases` | Cố định 8 ID train đầu và hai protocol, tách khỏi cache selection của chặng 1. |
| `stream_cache` | Prefill rồi decode từng token với cache mới, mask/vị trí tuyệt đối; chỉ giữ output hiện tại để không lưu logits toàn chuỗi khi thu thống kê/kiểm append. |
| `calibrate`, `main` | CLI chỉ mở train calibration, chạy đủ full/cache, kiểm coverage/FQoff, freeze và lưu config/qparams/ID/metadata. |
| [ptq_validate.py](../ptq_validate.py): `parameter_fingerprints` | Đối chiếu giá trị tất cả Parameter trước/sau campaign để phát hiện ghi đè nguồn; đây là oracle bất biến trong test, không phải bộ kiểm revision mỗi lần inference. |
| `assert_state_equal` | So toàn bộ buffer quantizer/observer trước/sau eval đến từng bit. |
| `disabled_gate` | So native full-forward độc lập với adapter disabled full/cache trên bốn case cũ và 16 protocol selection; chạy trước và sau khi bật candidate. |
| `probe_cache` | Hook projection/RoPE, tính K sau RoPE độc lập ở layer đầu, xác nhận V sau projection; cache kiểm mọi layer nhận đúng tensor mới, prefix giữ nguyên bit và quantizer không nhận lịch sử lặp lại. |
| `validate_candidate` | Kiểm full-forward không cache có đủ điểm K/V; hai cửa sổ selection không đổi qparams; lookup/head dùng cùng W; chạy cả hai audited-cache protocol. Không chấm chất lượng để chọn ứng viên. |
| `validate`, `main` | Ghép before → candidate → after → adapter mới load config/qparams; kiểm bất biến nguồn, logits tái lập và ghi bằng chứng. |
| [test_ptq_fake_quant.py](../test_ptq_fake_quant.py): `manual_quantize` và các test | Oracle Python/NumPy round/clamp/scale độc lập; dữ liệu âm/0/halfstep/extrema/per-row/per-head, cả 4/8 bit; Llama nhỏ thật kiểm tying, disable, static buffer, cache vị trí và reload. |

Scorer và dữ liệu selection/heldout của chặng 1 không đổi. Các phép kiểm model thật dùng batch 1, không padding, CPU/eager/FP32/eval/inference mode, seed 1234, một compute/inter-op thread, deterministic algorithms và MKLDNN tắt. Không cài thêm dependency ở chặng này.

## Các lệnh đã chạy và ý nghĩa

Chạy từ `src/tinyllm/quantize/`; `timeout` tính bằng giây. Dùng đúng `.venv` của FP32.

```bash
timeout 300 .venv/bin/python -m pytest -q test_fp32_reference.py test_ptq.py test_ptq_fake_quant.py
```

Kết quả **37 passed**, exit 0, 3,65 giây. Kiểm đồng thời oracle/scorer cũ và module fake-quant mới; không chỉ kiểm các tensor model lớn. Selector giữ toàn bộ kiểm tra chặng 1 và thêm test fake-quant.

```bash
timeout 3600 .venv/bin/python ptq_calibrate.py --offline --config configs/w8a8kv8_static.json
```

Tạo qparams tĩnh bằng đúng train/full/cache coverage đã nêu. `--offline` chỉ lấy checkpoint có sẵn; data lấy từ token IDs cố định. Sau freeze, file config, qparams, IDs và metadata nằm trong `calibration/w8a8kv8_static/`.

```bash
timeout 3600 .venv/bin/python ptq_validate.py --offline
```

Đọc lại config/qparams đã lưu, chạy các gate structural/bất biến/tái lập trên model thật và ghi [stage2_validation.json](../results/ptq/stage2_validation.json). Phép so disabled giữ nguyên bound FP32 của chặng 1; candidate đang bật không bị áp một ngưỡng chất lượng hoặc full/cache FP32 không phù hợp.

## Trạng thái và giới hạn

Bước 3–4 đã hiện thực, calibration và validation thực đạt, đã QA PASS; bước 5–8 được ghi tại [báo cáo chặng 3](ptq_stage3.md). Tập heldout chưa đánh giá. W8A8KV8 tĩnh chưa được chấm PPL/PIQA để chọn làm baseline; scale hợp lệ và cache đúng cơ chế không chứng minh chất lượng đủ ngưỡng. Chưa hiện thực A động, grouping mới, packing, kernel số nguyên hoặc thuật toán phi tuyến số nguyên.

Đã đối chiếu staged baseline: scorer/data selection/heldout, runtime/reference FP32 và kết quả chặng 1 giữ nguyên. Chỉ cập nhật status QA của báo cáo chặng 1, README và trạng thái PTQ plan; phần mới nằm trong quantize. Kiểm liên kết cục bộ/whitespace cả file mới và `git diff --check` exit 0. Không commit/push.
