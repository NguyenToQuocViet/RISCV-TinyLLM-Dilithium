# Kế hoạch sơ bộ TinyLLM: từ bản chạy chuẩn FP32 đến VCU118

## Mục tiêu và phạm vi

Theo [PROJECT.md](PROJECT.md), mục tiêu đầu tiên là chạy **đầy đủ SmolLM2-135M bằng RTL trên VCU118**, gồm xử lý prompt ban đầu (prefill) và từng lượt sinh token tiếp theo (decode). Sau khi nền tảng này đạt yêu cầu, tiếp tục với model SmolLM lớn hơn và cân nhắc họ Llama nếu còn thời gian.

Cần chọn đồng thời **quy tắc số học (numerical contract)** và cách tổ chức phần cứng. Mục tiêu là chạy nhanh hoặc dùng ít tài nguyên trong giới hạn cho phép, đồng thời giữ chất lượng model trong mức đã thống nhất.

```text
Cố định nguồn model → Chạy bằng FP32 để lấy kết quả chuẩn
                              ↓
         Thử fake-quant ↔ Quy tắc số học + bản chạy số nguyên
                              ↕
               Thiết kế thử các khối RTL và đo chi phí
                              ↓
               Chọn phương án và chốt quy tắc số học
                              ↓
               Viết RTL đầy đủ và kiểm tra
                              ↓
               Ghép TinyLLM với phần mềm và SoC
                              ↓
               Tạo bitstream và chạy demo trên VCU118
```

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

### 3. Xác định quy tắc số học và viết bản phần mềm số nguyên

**Công việc:**

- Với các ứng viên từ chặng 2, hoàn thiện số bit và hệ số biểu diễn giá trị (scale) cho trọng số, các giá trị trung gian, dữ liệu ở nhánh residual, KV cache, xác suất attention, RoPE, bảng tra (LUT) và logits.
- Quy định số bit của tích và bộ cộng dồn, thứ tự tính, cách chuyển kết quả về số bit và scale tiếp theo, cách làm tròn, cách giới hạn giá trị và xử lý tràn số tại từng bước.
- Chọn và hiện thực thuật toán số nguyên cho nhân ma trận, Softmax, RMSNorm và các phép tính còn lại. Ghi rõ các bước tính và cách xấp xỉ để bản số nguyên và RTL thực hiện cùng một cách.
- Quy định cách dùng chung trọng số giữa embedding và LM head, kể cả cách áp dụng scale ở hai nơi.
- Chuẩn bị trọng số, scale và bảng tra theo định dạng có thể nạp lên phần cứng.
- Viết bản phần mềm tính **thuần số nguyên** theo các quy tắc trên để làm kết quả chuẩn cho RTL (golden model).
- Kiểm tra riêng các phép tính số nguyên trước khi đánh giá toàn model; dùng dữ liệu cho số âm, giá trị nằm đúng giữa hai mức làm tròn, giá trị cực trị, phần tử bị che trong attention, phép cộng residual, KV cache và chuỗi dài.
- So chất lượng của bản số nguyên với bản FP32 và fake-quant. Nếu chất lượng hoặc chi phí phần cứng chưa đạt, quay lại điều chỉnh ở chặng 2–4.

**Tiêu chí hoàn thành:**

- Quy tắc đủ rõ để hai cách viết độc lập cho kết quả giống nhau tới từng bit.
- Bản số nguyên chạy được prefill và decode, đạt mức chất lượng yêu cầu.
- Có bộ đầu vào và kết quả chuẩn để kiểm tra lại sau mỗi lần sửa, đồng thời dùng để đối chiếu RTL.
- Chưa chốt quy tắc số học trước khi kiểm tra chi phí phần cứng ở chặng 4.

### 4. Thiết kế microarchitecture và kiểm tra khả năng triển khai trên VCU118

Chặng 2–4 được thực hiện lặp và có thể xen kẽ. Bắt đầu khảo sát các khối RTL đại diện khi có mô tả số học ứng viên cho các khối đó; không cần hoàn thiện bản số nguyên của mọi ứng viên trước.

**Công việc:**

- Từ khảo sát sơ bộ ở chặng 2, xác định và tinh chỉnh mục tiêu tốc độ cùng ngân sách tài nguyên, bộ nhớ và băng thông cho workload đã chọn.
- Thiết kế datapath của các khối tính toán, cách chia phép nhân ma trận/vector thành các phần nhỏ để xử lý và lịch dùng lại khối tính toán qua 30 layer.
- Lập cách lưu và chuyển trọng số, KV cache và dữ liệu trung gian; xác định bộ nhớ cần có, tốc độ truyền dữ liệu, cách chia phép tính thành các tầng (pipeline) và cách điều khiển việc tính/truyền dữ liệu.
- Ước lượng tài nguyên, thời gian chạy và bộ nhớ. Viết một số khối RTL đại diện để kiểm tra các giả định bằng kết quả tổng hợp mạch (synthesis) và kiểm tra thời gian truyền tín hiệu (timing).
- Tính cả phần tốn thêm để tìm/lưu scale, chuyển cách biểu diễn số và lưu thông tin đi kèm dữ liệu.
- Dùng kết quả đo để sửa quy tắc số học ở chặng 2–3 hoặc cách tổ chức phần cứng. So từng cặp **quy tắc số học + cách tổ chức phần cứng** theo chất lượng và chi phí.
- Xác định phần giới hạn hiệu năng hoặc tài nguyên từ số đo và mô hình chi phí; đề xuất cơ chế kiến trúc cần khảo sát, xây dựng thiết kế đối chứng (baseline) và đối chiếu với nghiên cứu trước.
- Thử cơ chế đề xuất trên các khối RTL đại diện, so với baseline theo cùng workload và các ràng buộc chất lượng, phần cứng đã chọn; tính cả chi phí bổ sung của cơ chế trước khi triển khai RTL đầy đủ.
- Đưa các kích thước model thành tham số có thể thay đổi, nhưng ưu tiên hoàn thành SmolLM2-135M trước.
- Đề xuất các thanh ghi/lệnh điều khiển, cách nạp trọng số, địa chỉ bộ nhớ, cách báo hoàn tất và báo lỗi.

**Tiêu chí hoàn thành:**

- Chọn được một cặp đạt yêu cầu chất lượng; ước lượng thời gian chạy và kết quả các khối RTL cho thấy có thể đáp ứng mục tiêu tốc độ và giới hạn tài nguyên.
- Có mô tả microarchitecture đủ rõ để hiện thực RTL: các khối, kết nối, bộ nhớ, pipeline và cơ chế điều khiển.
- Có kết quả thử nghiệm và đối chứng sơ bộ để quyết định tiếp tục hoặc điều chỉnh cơ chế kiến trúc trước khi viết RTL đầy đủ.
- Chốt phiên bản quy tắc số học và xác nhận chất lượng trên tập kiểm tra cuối.
- Có kế hoạch kiểm tra RTL; giao diện cần thiết được thống nhất trước khi chốt RTL cấp cao nhất.
- Kết quả timing sau synthesis được ghi đúng mức: vẫn cần kiểm tra sau bước bố trí và nối dây mạch (place-and-route) ở chặng 8.

### 5. Viết RTL và kiểm tra từng khối

**Công việc:**

- Viết các khối tính toán: nhân-cộng và chuyển cách biểu diễn số, embedding, RMSNorm, Q/K/V, RoPE, GQA/attention/softmax, KV cache, FFN/SiLU, cộng residual, chuẩn hóa cuối, LM head và chọn token.
- Viết mã kiểm tra (testbench) trong `tb/`; so kết quả và trạng thái bên trong với bản phần mềm số nguyên.
- Kiểm tra cả lúc luồng dữ liệu phải chờ, lúc reset, phần tử attention bị che, giá trị bị giới hạn và địa chỉ ở biên vùng nhớ.
- Ghép thành một decoder layer, rồi thêm phần điều khiển để chạy đủ số layer.

**Tiêu chí hoàn thành:**

- Các khối và một layer khớp bản số nguyên tới từng bit.
- Bộ kiểm tra chạy lại đạt yêu cầu sau khi ghép hoặc sửa mã.
- Không còn lỗi đã biết trong việc truyền dữ liệu và điều khiển giữa các khối.

### 6. Ghép và kiểm tra toàn bộ TinyLLM

**Công việc:**

- Chạy đầy đủ từ prefill đến nhiều lượt decode, dùng trọng số và KV cache thật cùng cách chọn token đã thống nhất.
- So token, logits và các giá trị số nguyên quan sát được với bản phần mềm số nguyên.
- Kiểm tra nạp model, nhiều độ dài prompt, chuỗi gần giới hạn, token kết thúc (EOS), giới hạn số token sinh, reset và chạy lặp.
- Đo thời gian chạy, tốc độ xử lý token, lượng dữ liệu truyền và tài nguyên sử dụng.
- Đánh giá lợi ích của cơ chế kiến trúc trên toàn TinyLLM so với baseline và kiểm tra riêng đóng góp của cơ chế đã chọn.
- Nếu sửa quy tắc số học sau khi chốt, cập nhật phiên bản, bản số nguyên và dữ liệu kiểm tra; quay lại đánh giá chất lượng ở chặng 2–4 trước khi chốt lại. Không dùng tập kiểm tra cuối để chọn hoặc điều chỉnh phương án.
- Với thay đổi microarchitecture giữ nguyên quy tắc số học, kiểm chứng RTL khớp bản số nguyên hiện có.

**Tiêu chí hoàn thành:**

- Toàn bộ TinyLLM cho kết quả khớp bản số nguyên theo quy tắc đã chốt.
- Có báo cáo kiểm tra, tốc độ và tài nguyên đủ để quyết định chuyển sang tích hợp SoC.

### 7. Chuẩn bị phần mềm và tích hợp vào SoC

**Công việc:**

- Hoàn thiện công cụ chạy trên máy tính để đóng gói trọng số, scale và bảng tra.
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
- So kết quả board với bản phần mềm số nguyên; đo thời gian chạy, tốc độ xử lý token và tài nguyên sử dụng. Đo điện năng nếu có phương pháp đáng tin cậy.
- Đối chiếu lợi ích kiến trúc trên board với baseline theo cùng workload và các ràng buộc đã chọn; ghi rõ nguồn số liệu đối chứng là đo trên board hay ước lượng.
- Lưu phiên bản công cụ, các ràng buộc thiết kế, bitstream, log và kết quả để có thể chạy lại và đối chiếu.

**Tiêu chí hoàn thành:**

- SoC tích hợp chạy được prefill và decode trên VCU118, cho kết quả đúng theo quy tắc đã chốt.
- Mạch đáp ứng clock và các yêu cầu đã thống nhất.
- Có demo và số liệu đo thực tế.

## Các điểm cần quyết định trước khi chốt thiết kế

1. Mức giảm chất lượng cho phép, độ dài chuỗi hỗ trợ và mục tiêu tốc độ.
2. Quy tắc số học cuối cùng, nhất là scale, số bit bộ cộng dồn, softmax, bảng tra và cách cập nhật KV cache khi chuỗi dài.
3. Giới hạn tài nguyên, tốc độ truyền dữ liệu và cách lưu trọng số/KV trên VCU118.
4. Giao diện TinyLLM–SoC và phần việc của phần mềm/phần cứng, được ghi trong tài liệu quyết định tương ứng.
