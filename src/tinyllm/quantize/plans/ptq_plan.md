# Plan v0 — Chặng 2: đánh giá và sàng lọc ứng viên PTQ

**Trạng thái:** bước 1–2 đã QA PASS ([kết quả](../reports/ptq_stage1.md)); bước 3–4 đã QA PASS ([kết quả](../reports/ptq_stage2.md)); bước 5–8 đã QA PASS ([kết quả](../reports/ptq_stage3.md)). Sweep per-tensor ban đầu giữ W8A16KV8; [mở rộng](../reports/ptq_a_extensions.md) có thêm A8/A12 per-input-channel và A12 SmoothQuant qua đủ quality gates. Heldout chưa đánh giá.

**Bàn giao:** tạm dừng mở rộng sweep để bắt đầu numerical contract theo [D02](../../docs/DECISIONS.md#d02-phát-triển-datapath-số-nguyên-theo-smoothquant-ưu-tiên-w8a8). [Shortlist](../results/ptq/shortlist.json) giữ baseline v0 làm đối chứng và ghi A12 SmoothQuant làm reference đã qualify, A8 SmoothQuant alpha 0.9 làm mục tiêu khảo sát chưa đạt gate PPL, chưa có PIQA/decode. Khảo sát ngân sách phần cứng/băng thông sơ bộ chưa được ghi nhận; cần bổ sung khi phát triển và sàng lọc numerical contract ở chặng 3–4. Đây chưa phải chốt cấu hình số học cuối cùng.

Thực hiện [chặng 2 của kế hoạch TinyLLM](../../docs/PLAN.md#2-thống-nhất-cách-đánh-giá-và-thử-lượng-tử-hóa): tìm cấu hình lượng tử hóa đạt chất lượng, giữ một cấu hình nền và danh sách ngắn để chuyển sang bản số nguyên và khảo sát RTL. Dùng lại [bản chuẩn FP32](../README.md) theo [D01](../../docs/DECISIONS.md#d01-dùng-fp32-làm-chuẩn-và-nền-tính-toán-cho-fake-quant).

Luồng công việc: **chuẩn bị dữ liệu → đo FP32 → chèn fake-quant → calibration → tìm cấu hình nền → thử giảm bit → kiểm tra và bàn giao shortlist**.

## 1. Một ứng viên cần chứa gì?

Fake-quant mô phỏng việc mất độ chính xác khi biểu diễn dữ liệu bằng ít mức giá trị; các phép tính giữa những điểm đó vẫn dùng FP32. Người thực hiện đề xuất cấu hình, chạy đánh giá rồi quyết định giữ hay loại.

| Mục phải ghi | Nội dung cần xác định |
| --- | --- |
| Điểm áp dụng | Tên module/tensor và vị trí trước hoặc sau phép toán; điểm chưa lượng tử hóa ghi rõ FP32. |
| Số bit và miền số nguyên | Bit của W, A, K, V; signed/unsigned, `quant_min`, `quant_max`, zero-point. |
| Cách chia scale | Per-tensor, per-channel hoặc per-head; ghi trục và các chiều dùng để tính thống kê. |
| Cách lấy scale | Observer/calibration nếu tĩnh; công thức và phạm vi dữ liệu được dùng nếu tính khi chạy. |
| Ngoại lệ | Module/layer giữ bit cao hơn hoặc FP32; cách xử lý embedding và LM head dùng chung trọng số. |
| Bằng chứng | Dữ liệu, cấu hình chạy, chất lượng và dung lượng dữ liệu dự kiến. |

Ví dụ, “W8A8KV8” trong v0 nghĩa là W8 và đầu vào A8 của các Linear được liệt kê, cùng K8/V8 tại điểm cache. Tên này không mặc định mọi trung gian, phép nhân attention hoặc phép phi tuyến đều đã thành INT8. Độ rộng accumulator và thuật toán số nguyên thuộc chặng 3.

## 2. Các bước thực hiện

### Bước 1 — Chuẩn bị ba tập dữ liệu và các lượt chạy cache

**Đầu vào:** batch 1, không padding, tổng context tối đa `L = 512` token; model/tokenizer đúng revision của bản chuẩn. Phạm vi v0 chưa quyết định giới hạn RTL cuối cùng.

**Việc cần làm:**

1. Lấy [WikiText-2 raw, cấu hình `wikitext-2-raw-v1`](https://huggingface.co/datasets/Salesforce/wikitext). Dùng `train` cho calibration, `validation` cho chọn phương án, `test` cho tập để dành; lấy **64 cửa sổ ở mỗi tập**, mỗi cửa sổ dài L token. Ghi revision dữ liệu, việc ghi revision chỉ là note lại nó vào file ghi chú nào đó có thể là file README hoặc file note khác chứ không phải làm cho đoạn code dài dòng thêm bằng các script trong code để kiểm tra lại revision mỗi lần chạy.
2. Trong mỗi split, nối các hàng `text` bằng hai ký tự xuống dòng, tokenize không tự thêm special token; chia thành các block liên tiếp dài L, bỏ phần đuôi không đủ block. Xáo trộn chỉ số block theo seed 1234 rồi lấy số lượng đã chốt. Lưu token IDs và vị trí bắt đầu. Nếu nguồn không đủ số block, giải quyết trước khi cố định bộ dữ liệu.
3. Đánh giá **PIQA zero-shot**, cố định nguồn dữ liệu, prompt và quy tắc chấm theo [định nghĩa task](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/lm_eval/tasks/piqa/piqa.yaml). Chia validation thành hai nửa theo câu hỏi bằng seed đã ghi cho chọn phương án và xác nhận cuối; không để một câu xuất hiện ở cả hai nửa. Pin revision và cố định cách xử lý mẫu vượt L trước khi chạy; không cắt mất đáp án để ép vừa context.
4. Chọn cố định 8 cửa sổ từ tập chọn để chạy nhanh và kiểm tra decode. Mỗi cửa sổ có hai lượt: prefill 32 rồi decode 64 token, và prefill L−64 rồi decode 64 token, dùng token thật của cửa sổ làm đầu vào. Lưu các split này cùng dữ liệu; kết quả chạy nhanh chỉ dùng chẩn đoán, không dùng để kết luận ứng viên đạt.

Calibration dùng để tính tham số lượng tử hóa. Tập chọn dùng để so, sửa và loại phương án. Tập để dành được giữ cho lần xác nhận sau khi chốt ở chặng 4; không chạy đánh giá tập này trong chặng 2.

**Đầu ra và tiêu chí hoàn thành:** bộ token IDs/câu hỏi được cố định; truy được nguồn và vai trò từng mẫu; ba tập tách biệt và các lượt prefill/decode hợp lệ. Chưa cần chạy model trên tập để dành.

### Bước 2 — Có bộ chấm chất lượng chạy được trên FP32

**Đầu vào:** dữ liệu bước 1; bản Transformers gốc và môi trường của bản chuẩn.

**Việc cần làm:**

1. Chạy lại phép kiểm FP32 đã có nếu nguồn hoặc môi trường thay đổi. Với chiều dài L, kiểm tra thêm full forward so với prefill/decode bằng cùng token; dùng quy tắc so FP32 hiện có.
2. Viết bộ chấm PPL: logits tại vị trí `i` dự đoán token `i+1`; cộng tổng negative log-likelihood và chia tổng số token thực sự được chấm rồi lấy hàm mũ. V0 dùng cửa sổ độc lập, không padding; bỏ target đầu cửa sổ, không lấy trung bình các PPL riêng lẻ.
3. Chấm PIQA bằng log-likelihood của hai đáp án nối sau cùng prompt; chỉ tính token đáp án, lấy đáp án có tổng log-likelihood cao hơn và báo accuracy. Cố định cách tokenize ranh giới prompt/đáp án và cách xử lý hòa điểm. Kiểm tra một vài câu với định nghĩa task; chưa cần tích hợp cả một bộ benchmark.
4. Đo FP32 trên tập chọn và các đoạn decode đã chọn. Lưu PPL, accuracy, số mẫu/token được chấm và cấu hình chạy. Trên một đoạn ngắn, đối chiếu NLL tính từ logits với loss của Transformers khi dùng cùng target mask.

**Ngưỡng chất lượng khởi đầu:** PPL tăng tương đối không quá **5%** so với FP32 trên cùng dữ liệu/cách chạy; PIQA accuracy giảm không quá **2 điểm phần trăm**. Áp dụng cùng ngưỡng tăng PPL cho phần decode ở bước 7.

PPL cửa sổ độc lập là phép đo nội bộ để so cùng điều kiện; không đối chiếu trực tiếp với PPL trong paper dùng context, tokenizer hoặc sliding window khác. Nếu điểm PIQA của FP32 gần đoán ngẫu nhiên, ghi rõ giới hạn này và xem lại bài kiểm tra trước khi dùng nó làm tiêu chí chất lượng.

**Đầu ra và tiêu chí hoàn thành:** có điểm FP32 làm mốc; bộ chấm xác định đúng vị trí target và mẫu số; kiểm tra cache ở chiều dài L đạt. Công cụ chấm phải dùng lại nguyên vẹn cho candidate.

### Bước 3 — Chèn fake-quant mà vẫn giữ được đường chạy gốc

**Đầu vào:** bộ chấm đã kiểm tra; mã Transformers đang dùng.

**Việc cần làm:**

1. Tạo bản thí nghiệm riêng từ cùng checkpoint; dùng `eval()` và tắt gradient. Dùng `torch.ao.quantization.FakeQuantize` cùng observer phù hợp, không huấn luyện trọng số. Giữ phiên bản môi trường hiện tại trước; không nâng thư viện chỉ để khớp tài liệu 2.9.
2. Gắn fake-quant vào W và đầu vào A của `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj` và `lm_head`. Chỉ đổi điểm biểu diễn, giữ phép toán Transformers gốc giữa các điểm đó.
3. Với embedding/LM head, dùng cùng một bộ trọng số đã fake-quant cho cả lookup và phép chiếu; không làm mất quan hệ dùng chung, không lượng tử hóa một phía rồi báo là toàn bộ trọng số đã W8.
4. Với K/V, đặt điểm lượng tử hóa K **sau RoPE**, V sau projection, trước khi lưu cache và trước khi nhân rộng KV head cho GQA. Cả full forward không cache lẫn đường cache phải áp dụng cùng quy tắc tại vị trí này. Dùng adapter trong mã thí nghiệm, không sửa gói Transformers đã cài.
5. Dùng miền đối xứng: 8 bit `[-127,127]`, 4 bit `[-7,7]`, zero-point 0. W dùng scale tĩnh per-output-channel, tính trên từng hàng trọng số; A tĩnh per-tensor tại mỗi điểm; K/V tĩnh per-KV-head tại mỗi layer, thống kê trên các chiều còn lại. Ghi rõ các điểm vẫn FP32, gồm phép tính phi tuyến, residual và các trung gian chưa khảo sát.
6. Kiểm tra bật/tắt fake-quant trên tensor nhỏ với kết quả làm tròn/giới hạn tính độc lập. Tắt toàn bộ fake-quant phải khớp model gốc trên bộ đầu vào chuẩn và các lượt cache mới theo phép so FP32 ở bước 2. Sau khi thử một candidate, tắt fake-quant vẫn phải phục hồi đường chạy này.

PyTorch có thể mô phỏng miền 4 bit bằng giới hạn số nguyên hẹp; kết quả vẫn là tensor FP32. Điều này chưa tạo trọng số đóng gói 4 bit hoặc kernel INT4. Những điểm per-head/per-token cần bố trí tensor và observer đúng trục, không có sẵn chỉ nhờ đặt tên cấu hình.

**Đầu ra và tiêu chí hoàn thành:** các điểm fake-quant bật/tắt độc lập được; tắt toàn bộ khớp reference; không sửa trọng số nguồn và không mất weight tying. Kiểm tra cache cho thấy token cũ giữ nguyên khi append, token mới được lượng tử hóa đúng một lần tại điểm đã quy định.

### Bước 4 — Calibration rồi cố định tham số tĩnh

**Đầu vào:** wrapper đúng; tập calibration; quy tắc chia scale đã ghi.

**Việc cần làm:**

1. Tính tham số W từ trọng số. Thu thống kê A và K/V trên tập calibration bằng MinMax observer, với fake-quant tắt ở lượt lấy thống kê ban đầu. Thu cả lượt prefill và một số đoạn decode của chính tập calibration.
2. Lưu scale/zero-point tĩnh, tắt observer rồi bật fake-quant để đánh giá. Chạy nhiều mẫu chọn phải không làm thay đổi các tham số tĩnh này. Mỗi cấu hình phải truy được về tham số đã dùng.
3. Nếu nhánh A động được chọn, tính scale riêng từ các phần tử của **token hiện tại** tại từng điểm, dùng cùng quy tắc ở prefill và decode. Không lấy max chung của cả prompt, không tích lũy thống kê của các mẫu đánh giá; chỉ đặt `is_dynamic=True` chưa đủ để bảo đảm hành vi này.
4. Mỗi lần chạy tạo cache mới; với K/V tĩnh, append giá trị đã fake-quant và giữ nguyên phần cũ. Không tính lại scale hoặc lượng tử hóa lại toàn bộ lịch sử sau mỗi token.

**Đầu ra và tiêu chí hoàn thành:** tham số tĩnh hữu hạn, scale dương và có đủ số lượng theo trục; bộ chấm không cập nhật chúng. Nhánh động, nếu có, không nhìn token tương lai. Đọc lại cấu hình và tham số cho kết quả chạy lại tương ứng.

### Điều chỉnh thí nghiệm A tĩnh

Theo phạm vi mở rộng đã chốt: so W8/K8/V8 với A8 MinMax đối chứng, A8 HistogramObserver/L2 tĩnh (2048 bin), A12 MinMax `[-2047,2047]`, A16 MinMax `[-32767,32767]`. A12/A16 dùng FakeQuantize qint32; kết quả vẫn FP32. Mỗi cấu hình mới phải calibration lại cùng 64 cửa sổ train và 16 lượt cache; W/K/V phải có qparams bằng nhau. Histogram chỉ thu thống kê khi observe, tính qparams một lần khi freeze. Bundle khác bits/policy/observer/trục phải bị từ chối khi load.

Chấm PPL toàn bộ 64 cửa sổ cho cả bốn cấu hình; chỉ ứng viên qua PPL mới chạy PIQA và decode. Nếu Histogram A8 không đạt, thử đúng một percentile tuyệt đối 99,99% tĩnh từ histogram train 65536 bin, lấy mép trên bin chứa quantile; ghi độ phân giải và sai số xấp xỉ. Không quét percentile. Đánh giá bổ sung A8 động per-token trên full64 PPL theo yêu cầu mới; PIQA và hai decode gate nếu qua PPL. W/K/V dùng cùng qparams train; việc load từ bundle tĩnh phải tường minh bỏ A tĩnh và vẫn kiểm W/K/V. Ưu tiên baseline tĩnh; báo dynamic như đối chứng với chi phí runtime riêng. Chọn A có số bit thấp nhất qua tất cả ngưỡng rồi tiếp tục bước 6–8. Nếu không có baseline tĩnh đạt, báo thất bại và dừng nhánh phụ thuộc.

### Bước 5 — Tìm cấu hình nền đạt chất lượng

**Đầu vào:** bộ chấm, wrapper và calibration đã kiểm tra; ngưỡng chất lượng ở bước 2.

**Việc cần làm:**

1. Trên 8 cửa sổ chạy nhanh, thêm lần lượt **W8 → W8+A8 → W8+A8+K8/V8**. Mục đích là biết nhóm thay đổi nào gây giảm chất lượng; các cấu hình trung gian chưa phải shortlist cuối.
2. Đánh giá cấu hình kết hợp 8 bit trên toàn tập chọn. Đo mức tăng PPL so với FP32 và mức giảm accuracy; không kết luận từ kết quả lượng tử hóa riêng từng tensor.
3. Nếu chất lượng không đạt, chỉ khoanh vùng phần gây lỗi: tách W/A/K/V hoặc nhóm attention/FFN/embedding–LM head, rồi khảo sát layer cụ thể khi cần. Ghi tỷ lệ clipping tại điểm nghi ngờ và mức cải thiện khi phục hồi riêng điểm đó.
4. Thử sửa đơn giản có căn cứ: đổi cách chia scale, thử A động per-token nếu A tĩnh không đạt hoặc giữ độ chính xác cao hơn ở ít điểm nhạy. Mỗi sửa đổi cần được ghi thành cấu hình mới và đo lại kết hợp. Nếu cần độ rộng ngoài miền module đang hỗ trợ hoặc cần PTQ hiệu chỉnh như SmoothQuant, nêu phần cần mở rộng trước khi hiện thực; không mặc định triển khai thêm thuật toán.

**Đầu ra và tiêu chí hoàn thành:** có cấu hình nền đạt ngưỡng chất lượng ở bước 2 với danh sách ngoại lệ đầy đủ. Nếu chưa tìm được, báo rõ điểm gây mất chất lượng và phép thử tiếp theo; không hạ ngưỡng chỉ để tạo một cấu hình đạt.

### Bước 6 — Thử một hướng giảm bit, chỉ mở rộng khi có lý do

**Đầu vào:** cấu hình nền đạt chất lượng.

**Việc cần làm:**

1. Ưu tiên thử W4: chỉ đổi W của các Linear trong decoder từ 8 xuống 4 bit; giữ embedding/LM head W8 và các lựa chọn A/K/V của cấu hình nền. Mục đích là giảm dung lượng trọng số, chưa khẳng định giảm DSP hoặc tăng tốc.
2. Nếu W4 kết hợp không đạt, thử phục hồi bit tại nhóm/layer đã thấy nhạy, hoặc chia group ở đúng ma trận cần thiết. Chỉ thêm một cách chia group có kích thước/trục cụ thể khi có bằng chứng per-channel chưa đủ; tính thêm scale đi kèm.
3. Nếu cần thêm một ứng viên khác biệt về dung lượng cache, thử K4/V8 hoặc K8/V4 trước khi ghép K4/V4. Giữ các lựa chọn còn lại như cấu hình nền, tránh thay W/A/K/V cùng lúc rồi không biết nguyên nhân.
4. Mỗi ứng viên có triển vọng trên tập chạy nhanh phải được đánh giá toàn tập chọn. Không quét toàn bộ tổ hợp số bit, layer, group size và phương pháp PTQ.

**Đầu ra và tiêu chí hoàn thành:** có kết luận giữ/loại cho hướng đã thử, kèm chất lượng và lý do về dung lượng hoặc độ đơn giản. Dừng mở nhánh khi đã có cấu hình nền và 1–2 phương án thay thế đạt; nếu hướng giảm bit đều không đạt, có thể chuyển cấu hình nền sang thử chặng 3–4 và ghi rõ chưa có phương án thay thế đạt.

### Bước 7 — Kiểm tra shortlist trên prefill và decode

**Đầu vào:** cấu hình nền và các ứng viên còn lại; tập chọn và lượt cache của bước 1.

**Việc cần làm:**

1. Tổng hợp PPL và PIQA toàn tập chọn từ bước 5–6; chỉ chạy phần còn thiếu hoặc cấu hình đã thay đổi. Các phép đo phải dùng tham số tĩnh từ calibration. Chạy lại một cấu hình sau khi nạp cấu hình/tham số đã lưu để xác nhận khả năng tái lập.
2. Trên 8 cửa sổ cache, dùng cùng token đầu vào cho FP32 và fake-quant; đo NLL/PPL riêng các vị trí decode, gồm dự đoán token đầu tiên ngay sau prompt. Kiểm tra cả prompt ngắn và gần L; áp dụng ngưỡng tăng PPL ở bước 2 cho phần decode so với FP32 tương ứng.
3. Ghi top-1 agreement và KL theo hướng FP32 so với fake-quant trên các vị trí chẩn đoán cố định, dùng toàn vocabulary. Các số này giúp tìm sai khác; không thay thế PPL/accuracy. Ghi sai khác full-forward/cache của candidate để điều tra lỗi vị trí, mask, scale hoặc cache; ngưỡng FP32 không tự là ngưỡng cho hai đường đã có làm tròn lượng tử hóa.
4. Sinh greedy với một số prompt cố định từ tập chọn, tối đa 64 token mới và không vượt tổng context L. Lưu văn bản để kiểm tra biểu hiện bất thường; khi hai model sinh khác token thì không so logits ở các prefix đã khác nhau như một phép đo sai số số học.
5. Nếu kết quả sát ngưỡng hoặc thứ hạng phụ thuộc vài mẫu, mở rộng dữ liệu từ phần validation chưa dùng rồi cố định lại tập chọn cho các ứng viên còn lại; không dùng tập để dành để phân xử.

**Đầu ra và tiêu chí hoàn thành:** mỗi ứng viên được giữ đạt ngưỡng đã chốt trên tập chọn và phần decode; không có NaN/Inf hay lỗi cache đã biết; ghi đủ số mẫu/token, cấu hình và kết quả. Nếu bỏ một candidate ở bước này, cập nhật shortlist thay vì chỉ giữ kết quả chạy nhanh tốt hơn.

### Bước 8 — Tính dung lượng và bàn giao sang chặng 3–4

**Đầu vào:** shortlist đã kiểm tra và cấu hình đầy đủ.

**Việc cần làm:**

1. Tính dung lượng trọng số theo số phần tử và số bit từng tensor, cộng scale/zero-point cần lưu. Tính embedding/LM head dùng chung một lần; nếu một phương án đòi hai bản biểu diễn thì tính cả hai và ghi lý do.
2. Tính KV theo số KV head gốc, số layer và chiều dài L, cộng metadata theo chính sách scale. Không nhân dung lượng lưu cache lên số query head. Với mixed precision/grouping, tính theo từng phần thay vì dùng một số bit trung bình thiếu metadata.
3. Ghi số bit giả định của metadata khi ước tính; nếu dùng scale FP32 trong thí nghiệm thì tính theo FP32, không mặc định đã chuyển được sang scale 16 bit. Ghi rõ đây là payload lý thuyết, chưa có packing, alignment, buffer hay số đo tài nguyên FPGA.
4. Bàn giao cấu hình từng ứng viên, tham số calibration, định danh dữ liệu/token IDs, cách chạy, kết quả chất lượng và bảng dung lượng. Nêu phần còn FP32 cần xác định ở chặng 3; không gọi fake-quant là golden integer.

**Đầu ra và tiêu chí hoàn thành:** người khác có thể dựng lại ứng viên và lặp phép đánh giá; có cấu hình nền cùng shortlist và lý do lựa chọn. Tập xác nhận cuối chưa được dùng. Việc tìm accumulator, thuật toán phi tuyến số nguyên, ngân sách phần cứng và RTL tiếp tục theo chặng 3–4 của kế hoạch chung.

## 3. Tài liệu cốt lõi và cách đọc

Chỉ cần ba nhóm đầu để bắt đầu hiện thực; đọc theo câu hỏi cần giải quyết, không cần đọc toàn bộ paper.

| Thứ tự | Tài liệu | Phần cần hiểu để làm chặng 2 |
| --- | --- | --- |
| 1 | [Jacob et al. — Quantization and Training of Neural Networks for Efficient Integer-Arithmetic-Only Inference](https://arxiv.org/html/1712.05877) | §2.1 và hình 1: quan hệ số thực, scale, zero-point, dữ liệu lượng tử hóa. Phần đầu §3 giải thích simulated quantization. Paper có QAT; v0 chỉ học mô hình biểu diễn và giả lập, không thực hiện quy trình huấn luyện của paper. |
| 2 | [PyTorch FakeQuantize](https://docs.pytorch.org/docs/2.9/generated/torch.ao.quantization.fake_quantize.FakeQuantize.html), [MinMaxObserver](https://docs.pytorch.org/docs/2.9/generated/torch.ao.quantization.observer.MinMaxObserver.html), [PerChannelMinMaxObserver](https://docs.pytorch.org/docs/2.9/generated/torch.ao.quantization.observer.PerChannelMinMaxObserver.html) | Phân biệt thu thống kê với bật lượng tử hóa; cách xác định scale, miền số nguyên và trục channel. Tài liệu 2.9 dùng để đọc khái niệm; đối chiếu [mã FakeQuantize v2.6.0](https://github.com/pytorch/pytorch/blob/v2.6.0/torch/ao/quantization/fake_quantize.py) khi hiện thực trên môi trường đang có. |
| 3 | [Hugging Face — Perplexity of fixed-length models, Transformers 4.49.0](https://huggingface.co/docs/transformers/v4.49.0/en/perplexity) | PPL, target shifting/masking, tổng NLL và ảnh hưởng của context/cách chia cửa sổ. Hiểu vì sao phải giữ cùng protocol khi so FP32 và candidate. |

**Tra cứu đúng bước:** [định nghĩa PIQA của lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/lm_eval/tasks/piqa/piqa.yaml) cho bước 2; không cần đọc hoặc tích hợp toàn bộ framework.

**Chỉ đọc thêm khi A8 gặp vấn đề do outlier:** [SmoothQuant, ICML 2023](https://proceedings.mlr.press/v202/xiao23c.html), phần phương pháp §3. Học cách cân bằng activation và trọng số trước khi quyết định mở nhánh hiệu chỉnh. Đây chưa phải thuật toán bắt buộc của v0.
