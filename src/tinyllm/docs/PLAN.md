# Kế hoạch sơ bộ TinyLLM: từ bản chạy chuẩn FP32 đến VCU118

## Mục tiêu và phạm vi

Theo [PROJECT.md](PROJECT.md), mục tiêu đầu tiên là chạy **đầy đủ SmolLM2-135M bằng RTL trên VCU118**, gồm xử lý prompt ban đầu (prefill) và từng lượt sinh token tiếp theo (decode). Sau khi nền tảng này đạt yêu cầu, tiếp tục với model SmolLM lớn hơn và cân nhắc họ Llama nếu còn thời gian.

Cần chọn đồng thời **quy tắc số học (numerical contract)** và cách tổ chức phần cứng. Mục tiêu là chạy nhanh hoặc dùng ít tài nguyên trong giới hạn cho phép, đồng thời giữ chất lượng model trong mức đã thống nhất.

```text
Cố định nguồn model → Chạy bằng FP32 để lấy kết quả chuẩn
                              ↓
   Thử fake-quant → Contract số học: biểu diễn, độ rộng bit, phép tính nền
                              ↓
        Đặc tả thiết kế chi tiết ↔ Chọn thuật toán phi tuyến, cập nhật contract
        Golden số học từng khối  ↔ RTL đại diện để đo DDR, timing và đối chứng
                              ↓
   Chốt đặc tả và contract → Ghép golden toàn model → Xác nhận heldout
                              ↓
               Viết RTL đầy đủ và kiểm tra
                              ↓
               Ghép TinyLLM với phần mềm và SoC
                              ↓
               Tạo bitstream và chạy demo trên VCU118
```

Contract được chốt theo từng phần ([D03](DECISIONS.md#d03-chốt-contract-theo-từng-phần-hàm-phi-tuyến-chọn-trong-lúc-thiết-kế)). Đặc tả hoàn chỉnh đi trước RTL đầy đủ; chỉ những khối thỏa điều kiện ngoại lệ mới được viết RTL sớm hơn ([D04](DECISIONS.md#d04-hoàn-thành-đặc-tả-thiết-kế-trước-khi-viết-rtl-đầy-đủ)). Golden model kiểm tra đúng đắn số học, không mô phỏng phần cứng ([D05](DECISIONS.md#d05-golden-model-ở-mức-số-học)).

## Các chặng thực hiện

### 1. Cố định nguồn model và tạo bản chạy chuẩn FP32

**Công việc:**

- Dùng [SmolLM2-135M tại phiên bản `93efa2f097d58c2a74874c7e644dbc9b0cee75a2`](https://huggingface.co/HuggingFaceTB/SmolLM2-135M/tree/93efa2f097d58c2a74874c7e644dbc9b0cee75a2), bản **base**. Lấy `config.json`, `model.safetensors` và tokenizer từ cùng phiên bản.
- Dùng thư viện Python Transformers của Hugging Face để nạp và chạy chính model đó bằng FP32. Đặt model ở chế độ dùng cho suy luận và giữ bản này nguyên gốc để đối chiếu. Trọng số nguồn là BF16; chuyển sang FP32 để tính toán không làm bộ trọng số gốc chính xác hơn.
- Ghi lại phiên bản thư viện, cách chạy và token đầu vào để có thể chạy lại cùng phép kiểm tra.
- Chọn và ghi mức chênh lệch FP32 được chấp nhận khi so hai cách chạy.
- Kiểm tra cách dùng KV cache trên một chuỗi token cố định: so logits tại cùng vị trí khi đưa cả chuỗi vào model trong một lần với khi đưa đoạn đầu vào trước, rồi đưa từng token còn lại cùng KV cache. Thử các độ dài chuỗi khác nhau trong phạm vi hỗ trợ.
- Lưu bộ đầu vào và kết quả chuẩn cố định để dùng lại sau mỗi lần sửa mã.

**Tiêu chí hoàn thành:**

- Xác định được chính xác phiên bản model, tokenizer và thư viện đã dùng.
- Chạy lại được kết quả FP32 cho xử lý prompt (prefill) và từng lượt decode bằng KV cache.
- Logits tại cùng vị trí của hai cách chạy chuỗi token khớp nhau trong mức chênh lệch đã chọn.

### 2. Thống nhất cách đánh giá và thử lượng tử hóa

**Công việc:**

- Chia dữ liệu thành ba tập riêng: tập để tính tham số lượng tử hóa, tập để so và chọn phương án, tập để kiểm tra phương án cuối cùng. Lưu token đầu vào, cách lấy đoạn văn bản, giá trị khởi tạo bộ sinh số ngẫu nhiên (seed) và phiên bản dữ liệu.
- Thống nhất cách đo chất lượng, **mức giảm chất lượng cho phép** và phạm vi độ dài chuỗi trước khi so các phương án.
- Khảo sát sơ bộ nhu cầu bộ nhớ, tính toán và băng thông; xác định các giả định phần cứng và ngân sách sơ bộ để sàng lọc ứng viên. Mục tiêu tốc độ và ngân sách chi tiết được tinh chỉnh ở chặng 4.
- Chèn fake-quant có sẵn của PyTorch vào bản thí nghiệm dựa trên cùng model Transformers chạy FP32. Giữ nguyên kiến trúc và nguồn trọng số; dùng các phép tính gốc giữa các bước fake-quant.
- Với mỗi phương án, ghi rõ vị trí lượng tử hóa, số bit, miền giá trị, cách chia scale và zero-point. Dùng tập calibration để tính tham số; cố định các tham số lượng tử hóa tĩnh trước khi đánh giá.
- Khảo sát độ nhạy tại các điểm cần thiết để xây dựng và điều chỉnh các cấu hình kết hợp. Đánh giá chất lượng toàn model cho từng cấu hình kết hợp trên cùng tập chọn phương án.
- Đánh giá khả năng dự đoán văn bản bằng PPL (thấp hơn là tốt hơn) và điểm trên các bài kiểm tra đã chọn. Dùng thêm tỷ lệ chọn cùng token với FP32, độ lệch phân bố dự đoán (KL) và văn bản sinh ra để tìm nguyên nhân sai khác.
- Đánh giá cả prefill, decode dùng KV cache, token sinh đầu tiên và các độ dài chuỗi trong phạm vi đã chọn. Khi so sai số với FP32, dùng cùng token đầu vào.
- Nếu chất lượng chưa đạt, điều chỉnh số bit, cách chọn scale hoặc áp dụng hiệu chỉnh lượng tử hóa rồi đánh giá lại cấu hình kết hợp.
- Chọn một cấu hình lượng tử hóa nền (baseline) đạt ngưỡng chất lượng và một số ít ứng viên có lợi ích phần cứng dự kiến, xét cả dung lượng scale và thông tin đi kèm, để kiểm tra ở chặng 3–4.

**Tiêu chí hoàn thành:**

- Đủ điều kiện chuyển sang chặng 3–4 khi có cấu hình nền và danh sách ngắn ứng viên fake-quant kết hợp đạt ngưỡng chất lượng, kèm cấu hình đầy đủ, dung lượng dữ liệu dự kiến và kết quả có thể chạy lại; không yêu cầu tìm phương án tối ưu toàn cục.
- Tắt fake-quant cho kết quả khớp bản Transformers gốc theo mức chênh lệch đã chọn ở chặng 1.
- Đã kiểm tra chất lượng cho prefill và decode trong phạm vi hỗ trợ.
- Tập kiểm tra cuối chưa được dùng để chọn phương án; chỉ dùng để xác nhận sau khi chốt.

### 3. Xác định contract số học: biểu diễn, độ rộng bit và phép tính nền

Chặng này chốt phần contract mà mọi khối phần cứng dựa vào. Thuật toán phi tuyến ở chặng này là tạm thời; thuật toán chính thức được chọn ở chặng 4 theo [D03](DECISIONS.md#d03-chốt-contract-theo-từng-phần-hàm-phi-tuyến-chọn-trong-lúc-thiết-kế). [Numerical contract v1](design/numerical_contract_v1.md) là kết quả của chặng này.

**Công việc:**

1. **Xác định các biên dữ liệu.** Từ cấu hình và qparams chặng 2, điền bảng biểu diễn trọng số, activation, residual, KV, attention, RoPE, norm, LUT và logits trong contract. Xác định đầu vào/đầu ra của các khối phi tuyến ngay từ bước này.
2. **Định nghĩa và kiểm tra các phép tính nền.** Hoàn thiện MAC, smoothing/requantization và chuyển scale: độ rộng tích/accumulator, thứ tự cộng, hệ số nhân/dịch, rounding, saturation và overflow. Chuẩn bị W số nguyên và hệ số cần dùng; viết bản số nguyên cùng oracle độc lập cho các phép này. Đầu ra là primitive đã kiểm tra và quy tắc đủ rõ để tái hiện từng bit.
3. **Chọn thuật toán phi tuyến tạm thời.** Chọn thuật toán số nguyên cho RMSNorm, RoPE, Softmax và SiLU đủ để chạy và đánh giá contract toàn model. Ghi từng bước số nguyên, bảng tra/hệ số, độ rộng và scale; bao gồm số âm, half-step, cực trị, mask, cache và giới hạn độ dài chuỗi.
4. **Hiện thực runtime contract.** Chạy toàn model trên mã nguyên theo contract, gồm embedding và LM head dùng chung một bộ trọng số, prefill, decode và KV cache, từ bộ mã W, hệ số và LUT đã xuất. Runtime này dùng để chấm chất lượng mỗi phiên bản contract.
5. **Hoàn thiện định dạng trao đổi.** Chốt cách biểu diễn/lưu trọng số, scale, hệ số và LUT; kiểm tra lưu/nạp. Không tạo hai bản trọng số embedding/head ngoài quy tắc đã ghi. Định dạng đóng gói cho phần cứng được suy ra từ định dạng này ở chặng 4.
6. **Đánh giá toàn model.** Dùng lại protocol và scorer của chặng 2 để so FP32, fake-quant và runtime contract trên selection, gồm PPL, PIQA, prefill, token đầu tiên và hai regime decode. Ghi chất lượng, các sai khác cần điều tra và kết quả có thể chạy lại; không dùng heldout ([D06](DECISIONS.md#d06-dùng-selection-và-heldout-trong-giai-đoạn-thiết-kế)).

**Tiêu chí hoàn thành:**

- Biểu diễn, độ rộng bit, scale và các phép tính nền đủ rõ để hai cách viết độc lập cho kết quả giống nhau tới từng bit.
- Runtime contract chạy được prefill và decode, đạt quality gate trên selection.
- Thuật toán phi tuyến được ghi rõ là tạm thời, không được coi là kiến trúc phần cứng đã chốt.

### 4. Đặc tả thiết kế chi tiết và golden số học

Đặc tả mô tả toàn bộ accelerator đủ chi tiết để viết golden số học và RTL mà không phải đoán. Đặc tả được xây dần từ đầu; nội dung có trong đặc tả là nội dung đã quyết. Contract được cập nhật trong chặng này khi chốt thuật toán phi tuyến.

**Công việc:**

- **Mục tiêu và ngân sách.** Từ khảo sát sơ bộ ở chặng 2, xác định mục tiêu tốc độ, clock, ngân sách DSP/URAM/BRAM, số kênh DDR, phân bố trên các SLR và các miền clock. Thống nhất ngân sách với kiến trúc sư SoC.
- **Đo thông số nền bằng RTL đại diện.** Đo băng thông DDR4 duy trì trên VCU118 qua bộ điều khiển DDR4 (MIG). Viết một nhóm PE có drain/requant, kiểm tra clock mục tiêu sau place-and-route. RTL đại diện phục vụ đo và đối chứng, không bắt buộc giữ lại.
- **Datapath và matmul engine.** Cách chia phép nhân ma trận/vector thành tile; ánh xạ Linear, QK, PV và LM head cho prefill và decode; tile lẻ, mask và causal skip; lịch dùng lại khối tính toán qua 30 layer.
- **Bộ nhớ và dữ liệu.**
  - Phân cấp DDR → bộ đệm nạp trước → bộ nhớ nội bộ → thanh ghi.
  - Layout của trọng số, activation, KV cache và hệ số trong DDR và trên chip; chuyển vị và sinh địa chỉ.
  - Embedding và LM head dùng chung trọng số.
  - Dung lượng của từng bộ nhớ.
- **Lịch thực thi.**
  - Thứ tự vòng lặp của prefill và decode.
  - Thứ tự tính các ma trận và hàm phi tuyến.
  - Chỗ gộp phép và các điểm chắn (barrier) giữa nhân ma trận và phi tuyến, nhằm giảm đọc/ghi bộ nhớ.
  - Phụ thuộc dữ liệu, ví dụ K/V của token hiện tại vào cache trước khi QK đọc.
- **DMA và giao diện SoC.** AXI (độ rộng, burst, số yêu cầu chờ), thanh ghi điều khiển, ngắt, memory map, coherence với Rocket, chia băng thông với RISC-V/Dilithium, cách nạp trọng số lên board, cách báo hoàn tất và báo lỗi.
- **Bộ điều phối.**
  - Cách điều khiển toàn bộ suy luận và định dạng lệnh/descriptor.
  - Kích thước model là dữ liệu cấu hình, ưu tiên hoàn thành SmolLM2-135M trước.
  - Quy ước giao diện chung giữa các khối: handshake, cấu hình, báo xong, báo lỗi.
- **Hệ số, LUT và đóng gói.** Định dạng đóng gói phần cứng suy ra từ định dạng trao đổi của contract; công cụ đóng gói có version. Quyết định nạp hệ số/LUT sẵn trên chip hay stream theo layer.
- **Khối phi tuyến.** Theo D03, chọn thuật toán và kiến trúc phù hợp với thiết kế xung quanh. Sàng lọc có thể dùng fake-quant. Phương án được chọn được cập nhật vào contract và chấm bằng runtime contract trên selection.
- **Golden số học.** Khi một khối đã chốt thuật toán, viết golden của khối đó theo [D05](DECISIONS.md#d05-golden-model-ở-mức-số-học) và kiểm tra với oracle độc lập.
- **Gỡ lỗi và kiểm chứng.** Dump bộ đệm trung gian, bộ đếm hiệu năng, assertion cho các cận overflow. Ánh xạ điểm quan sát của đặc tả sang boundary của contract. Lập kế hoạch kiểm tra RTL.
- **Cơ chế kiến trúc và đối chứng.** Xác định phần giới hạn hiệu năng hoặc tài nguyên từ số đo và mô hình chi phí. Đề xuất cơ chế kiến trúc, xây dựng baseline và đối chiếu với nghiên cứu trước. Thử cơ chế trên RTL đại diện, so với baseline theo cùng workload và ràng buộc, tính cả chi phí bổ sung.
- **Ước lượng.** Ước lượng tài nguyên, thời gian chạy và bộ nhớ, tính cả phần tốn thêm để tìm/lưu scale, chuyển biểu diễn số và lưu thông tin đi kèm dữ liệu. Nếu chất lượng hoặc chi phí chưa đạt, sửa contract hoặc thiết kế rồi chạy lại các kiểm chứng bị ảnh hưởng.

**Tiêu chí hoàn thành:**

- Đặc tả mô tả đủ các khối, kết nối, bộ nhớ, pipeline, lịch thực thi và điều khiển để viết RTL không phải đoán. Giao diện giữa các khối và với SoC đã thống nhất.
- Ước lượng thời gian chạy và số đo RTL đại diện cho thấy có thể đáp ứng mục tiêu tốc độ và giới hạn tài nguyên.
- Có kết quả đối chứng sơ bộ giữa cơ chế kiến trúc và baseline.
- Mọi khối có golden số học. Golden toàn model ghép từ các khối chạy được prefill và decode, cho cùng mã với runtime contract.
- Contract phiên bản cuối đạt quality gate trên selection, sau đó được xác nhận một lần trên heldout theo D06.
- Kết quả timing của RTL đại diện được ghi đúng mức: vẫn cần kiểm tra sau place-and-route của toàn thiết kế ở chặng 8.

### 5. Viết RTL và kiểm tra từng khối

RTL đầy đủ bắt đầu sau khi chốt đặc tả. Khối thỏa điều kiện ngoại lệ của [D04](DECISIONS.md#d04-hoàn-thành-đặc-tả-thiết-kế-trước-khi-viết-rtl-đầy-đủ) có thể được viết trong chặng 4.

**Công việc:**

- Viết các khối tính toán theo đặc tả: nhân-cộng và chuyển cách biểu diễn số, embedding, RMSNorm, Q/K/V, RoPE, GQA/attention/softmax, KV cache, FFN/SiLU, cộng residual, chuẩn hóa cuối, LM head và chọn token; cùng DMA, bộ nhớ và bộ điều phối.
- Viết mã kiểm tra (testbench) trong `tb/`; so khớp từng bit với golden số học tại đầu ra từng khối.
- Chọn dữ liệu kiểm tra theo phần cứng, vì golden không biết tile: T = 1, T không chia hết cho kích thước tile, L quanh bội số kích thước khối key, L = 512, khối causal nằm trên đường chéo, decode ngay sau prefill.
- Kiểm tra cả lúc luồng dữ liệu phải chờ, lúc reset, phần tử attention bị che, giá trị bị giới hạn và địa chỉ ở biên vùng nhớ.
- Ghép thành một decoder layer, rồi thêm phần điều khiển để chạy đủ số layer.

**Tiêu chí hoàn thành:**

- Các khối và một layer khớp golden số học tới từng bit.
- Bộ kiểm tra chạy lại đạt yêu cầu sau khi ghép hoặc sửa mã.
- Không còn lỗi đã biết trong việc truyền dữ liệu và điều khiển giữa các khối.

### 6. Ghép và kiểm tra toàn bộ TinyLLM

**Công việc:**

- Chạy đầy đủ từ prefill đến nhiều lượt decode, dùng trọng số và KV cache thật cùng cách chọn token đã thống nhất.
- So token, logits và các giá trị số nguyên quan sát được với golden số học toàn model.
- Kiểm tra nạp model, nhiều độ dài prompt, chuỗi gần giới hạn, token kết thúc (EOS), giới hạn số token sinh, reset và chạy lặp.
- Đo thời gian chạy, tốc độ xử lý token, lượng dữ liệu truyền và tài nguyên sử dụng.
- Đánh giá lợi ích của cơ chế kiến trúc trên toàn TinyLLM so với baseline và kiểm tra riêng đóng góp của cơ chế đã chọn.
- Nếu sửa quy tắc số học sau khi chốt, cập nhật phiên bản contract, golden và dữ liệu kiểm tra; đánh giá lại chất lượng trên selection trước khi chốt lại. Không dùng tập kiểm tra cuối để chọn hoặc điều chỉnh phương án.
- Với thay đổi microarchitecture giữ nguyên quy tắc số học, kiểm chứng RTL khớp golden hiện có.

**Tiêu chí hoàn thành:**

- Toàn bộ TinyLLM cho kết quả khớp golden số học theo quy tắc đã chốt.
- Có báo cáo kiểm tra, tốc độ và tài nguyên đủ để quyết định chuyển sang tích hợp SoC.

### 7. Chuẩn bị phần mềm và tích hợp vào SoC

**Công việc:**

- Hoàn thiện công cụ chạy trên máy tính để đóng gói trọng số, scale và bảng tra theo định dạng đóng gói trong đặc tả.
- Phối hợp với phần RISC-V để chuẩn bị phần mềm điều khiển, tokenizer/detokenizer, nạp dữ liệu và điều khiển các lượt prefill/decode.
- Kết nối TinyLLM với bộ nhớ, liên kết truyền dữ liệu (interconnect), clock/reset và ngắt qua giao diện đã thống nhất.
- Kiểm tra TinyLLM khi hoạt động cùng các phần khác của SoC.

**Tiêu chí hoàn thành:**

- Có bài kiểm tra SoC từ prompt hoặc token đầu vào đến token đầu ra.
- Dữ liệu truyền và lệnh điều khiển đúng giao diện, kết quả đúng quy tắc số học.
- Không còn lỗi tích hợp ngăn việc chạy demo.

### 8. Triển khai, đo và chạy demo trên VCU118

**Công việc:**

- Chạy synthesis và place-and-route; kiểm tra mạch đáp ứng clock đã đặt, đủ tài nguyên và đủ bộ nhớ.
- Tạo bitstream và nạp lên board.
- Chạy lại bộ đầu vào chuẩn và demo sinh văn bản với model/tokenizer đã cố định phiên bản.
- So kết quả board với golden số học; đo thời gian chạy, tốc độ xử lý token và tài nguyên sử dụng. Đo điện năng nếu có phương pháp đáng tin cậy.
- Đối chiếu lợi ích kiến trúc trên board với baseline theo cùng workload và các ràng buộc đã chọn; ghi rõ nguồn số liệu đối chứng là đo trên board hay ước lượng.
- Lưu phiên bản công cụ, các ràng buộc thiết kế, bitstream, log và kết quả để có thể chạy lại và đối chiếu.

**Tiêu chí hoàn thành:**

- SoC tích hợp chạy được prefill và decode trên VCU118, cho kết quả đúng theo quy tắc đã chốt.
- Mạch đáp ứng clock và các yêu cầu đã thống nhất.
- Có demo và số liệu đo thực tế.

## Các điểm cần quyết định trước khi chốt thiết kế

1. Mục tiêu tốc độ; mức giảm chất lượng cho phép và độ dài chuỗi hỗ trợ giữ theo quality gate hiện có, trừ khi được thống nhất lại.
2. Thuật toán và kiến trúc của RMSNorm, RoPE, Softmax và SiLU, cùng phần contract tương ứng.
3. Giới hạn tài nguyên, băng thông DDR đo được và cách lưu trọng số/KV trên VCU118.
4. Giao diện TinyLLM–SoC và phần việc của phần mềm/phần cứng, được ghi trong tài liệu quyết định tương ứng.
