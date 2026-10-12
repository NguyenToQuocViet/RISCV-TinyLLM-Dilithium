# Kế hoạch sơ bộ TinyLLM: từ reference FP32 đến VCU118

## Mục tiêu và ranh giới

Mục tiêu đầu tiên là chạy **đầy đủ luồng suy luận SmolLM2-135M**, gồm prefill, decode và sinh token, bằng TinyLLM accelerator trong SoC trên VCU118. Đây là **kế hoạch kỹ thuật của subsystem**, chưa phải milestone hay cam kết phát hành của toàn dự án. Nghiên cứu model lớn hơn và họ Llama là hướng tiếp theo, sau khi nền tảng SmolLM2-135M đạt yêu cầu.

[PROJECT.md](PROJECT.md) đề xuất phần tính toán model ở RTL, công cụ trên host chuẩn bị trọng số, còn firmware/Rocket xử lý prompt, tokenizer, vòng sinh token và detokenizer. Việc chia trách nhiệm này **chưa phải giao diện SoC đã được chấp nhận**. Memory map, interconnect, clock/reset, interrupt, giao thức điều khiển và trách nhiệm giữa các subsystem phải được project architect và các owner liên quan review trước khi tích hợp. Kế hoạch này không giao việc sửa nội bộ RISC-V hoặc Dilithium cho TinyLLM.

```text
Nguồn model cố định → FP32 chuẩn → fake-quant/PTQ → numerics contract
                                            ↓
                           golden model thuần số nguyên
                                     ↓
                      microarchitecture + RTL + kiểm chứng
                                            ↓
                   TinyLLM subsystem + firmware + SoC
                                            ↓
                             bitstream và demo VCU118
```

## Các chặng thực hiện

### 1. Cố định nguồn model và reference FP32

**Làm gì:** Dùng checkpoint **base**, không dùng bản Instruct, từ [HuggingFaceTB/SmolLM2-135M tại revision `93efa2f097d58c2a74874c7e644dbc9b0cee75a2`](https://huggingface.co/HuggingFaceTB/SmolLM2-135M/tree/93efa2f097d58c2a74874c7e644dbc9b0cee75a2). Lấy `config.json`, `model.safetensors` và tokenizer từ **cùng revision**. Dùng Hugging Face Transformers (`AutoModelForCausalLM`, `AutoTokenizer`) ở chế độ đánh giá, thực hiện phép toán FP32 để làm chuẩn; ghi lại phiên bản thư viện và dữ liệu đầu vào. Checkpoint khai báo trọng số BF16: chuyển chúng sang FP32 để tính toán **không tạo lại độ chính xác đã mất trong trọng số gốc**.

So logits, token kế tiếp và trạng thái KV của forward cục bộ với reference Hugging Face ở cả prefill và decode; thử prompt ngắn/dài, vị trí token và trường hợp biên. Chọn và ghi ngưỡng sai số FP32 trước khi chấp nhận kết quả. Giữ bộ vector kiểm tra cố định cho các bước sau.

**Đạt khi:** Có nguồn model/tokenizer truy vết được bằng revision, reference chạy lặp lại được và regression chứng minh forward cục bộ khớp trong ngưỡng đã công bố. Reference Hugging Face là chuẩn hành vi FP32; forward cục bộ chỉ là công cụ thí nghiệm sau khi được đối chiếu.

### 2. Chốt bài đo và khảo sát lượng tử hóa

**Làm gì:** Duy trì tập calibration và evaluation tách biệt, lưu token IDs, cách chọn cửa sổ, seed và phiên bản dữ liệu. Đo FP32, fake-quant từng tensor và các cấu hình kết hợp với cùng tập test; theo dõi PPL, Top-1, KL và prompt sinh văn bản. Tiếp tục từ kết quả hiện có để kiểm tra decode, KV cache, vị trí token đầu và context dài tới giới hạn model. Thử PTQ/hiệu chỉnh hoặc điều chỉnh chính sách lượng tử khi chất lượng chưa đạt; chỉ cân nhắc phương pháp phức tạp hơn nếu cần. Thống nhất **ngưỡng chất lượng cần đạt** trước khi chọn phương án cuối.

**Đạt khi:** Có policy ứng viên, số liệu tái lập được cho cả prefill/decode và đánh đổi độ chính xác–chi phí được ghi rõ. Kết quả 512 token hiện có là đầu vào của chặng này, **chưa** chứng minh chất lượng ở 8.192 token.

### 3. Khóa numerics contract và golden model số nguyên

**Làm gì:** Từ policy đã chọn, quy định định dạng và scale của trọng số, activation, residual, KV cache, attention probabilities, RoPE, LUT và logits; định nghĩa accumulator, thứ tự phép toán, requantization, rounding, saturation, overflow và xử lý scale của embedding/LM head dùng chung trọng số. Biến Numerics Contract v0 hiện có thành bản được review với các trường hợp còn mở đã giải quyết. Chuẩn bị dữ liệu trọng số/scale/LUT ở định dạng có thể nạp lên hệ thống.

Viết golden model **thuần số nguyên** theo contract, có vector kiểm tra cho số âm, tie khi làm tròn, giá trị cực trị, mask, residual add, KV cache và context dài. So chất lượng của golden model với FP32/fake-quant; nếu sai lệch không đạt ngưỡng, quay lại chặng 2–3.

**Đạt khi:** Contract đủ chi tiết để hai cách hiện thực độc lập cho cùng đầu ra bit-exact; golden model chạy được prefill và decode, có regression và bộ vector chuẩn cho RTL. Fake-quant hiện tại chưa thay thế chặng này.

### 4. Thiết kế microarchitecture và kiểm tra tính khả thi trên VCU118

**Làm gì:** Tách rõ hợp đồng số học ở chặng 3 khỏi lựa chọn triển khai: datapath GEMM/GEMV, tiling, lịch sử dụng khối tính toán qua 30 layer, bộ nhớ trọng số/KV/activation, băng thông, DMA, pipeline và điều khiển. Ước lượng tài nguyên, thời gian chạy và giới hạn bộ nhớ dựa trên cấu hình VCU118 và kết quả công cụ thực tế; thử nghiệm nhỏ nếu cần để kiểm tra giả định. Parameterize các kích thước theo model, nhưng ưu tiên nghiệm thu SmolLM2-135M trước.

Song song, đề xuất register/command interface, luồng nạp trọng số, địa chỉ bộ nhớ, trạng thái hoàn tất và xử lý lỗi. Đưa phần ảnh hưởng SoC cho project architect và owner liên quan review; không coi đề xuất của subsystem là system-level contract.

**Đạt khi:** Có kiến trúc TinyLLM khả thi theo ước lượng được kiểm chứng, kế hoạch verification và giao diện cần thiết đã được chấp nhận ở đúng cấp trước khi khóa top-level RTL.

### 5. Hiện thực RTL theo khối và kiểm chứng từng khối

**Làm gì:** Hiện thực từng khối cần cho đường tính toán: nhân-cộng/requant, embedding, RMSNorm, Q/K/V và RoPE, GQA/attention/softmax, KV cache, FFN/SiLU, residual, final norm, LM head và chọn token theo chính sách demo đã duyệt. Xây testbench trong `tb/`; so kết quả và trạng thái quan sát được với golden model số nguyên, kể cả stall, reset, mask, saturation và ranh giới bộ nhớ. Sau đó ghép một decoder layer và cơ chế thực thi đủ số layer.

**Đạt khi:** Các khối và một layer vượt qua regression bit-exact ở phạm vi contract, không còn lỗi giao tiếp nội bộ đã biết. Giữ các thay đổi RTL trong phạm vi TinyLLM; việc thay đổi shared interface đi qua review cấp dự án.

### 6. Hoàn chỉnh và kiểm chứng TinyLLM subsystem

**Làm gì:** Chạy end-to-end prefill rồi nhiều lượt decode với trọng số thật, KV cache thật và chính sách sinh token đã chọn. So token/logits hoặc mã số nguyên quan sát được với golden model; kiểm tra nạp model, nhiều độ dài prompt, context gần giới hạn, EOS/giới hạn số token, reset và chạy lặp. Đo latency, throughput, băng thông và tài nguyên; sửa contract, microarchitecture hoặc RTL nếu bằng chứng yêu cầu.

**Đạt khi:** Subsystem tái lập được kết quả chuẩn trong ngưỡng đã thống nhất, có báo cáo regression và hiệu năng/tài nguyên đủ để quyết định tích hợp.

### 7. Chuẩn bị phần mềm và tích hợp SoC

**Làm gì:** Hoàn thiện công cụ host đóng gói trọng số, scale và LUT; phối hợp với owner RISC-V về firmware/driver, tokenizer/detokenizer, nạp dữ liệu, yêu cầu prefill/decode và vòng sinh token. Tích hợp TinyLLM qua giao diện **đã được chấp nhận** với bộ nhớ, interconnect, clock/reset và interrupt của SoC. Kiểm tra tương tác với các subsystem khác ở mức system; mọi thay đổi vùng dùng chung hoặc nội bộ RISC-V/Dilithium do đúng owner và project architect xử lý theo quy trình review.

**Đạt khi:** Có bài test SoC từ prompt/token IDs đến token đầu ra, dữ liệu truyền và điều khiển đúng contract, không còn lỗi tích hợp chặn demo. Công việc đa subsystem dùng quy trình `integration/*` và review của dự án.

### 8. Triển khai, đo và demo trên VCU118

**Làm gì:** Chạy synthesis, place-and-route, kiểm tra timing/tài nguyên/bộ nhớ, tạo bitstream và nạp board. Chạy lại các vector chuẩn và demo sinh văn bản với model/trọng số/tokenizer đã cố định; so đầu ra board với golden model và đo latency, throughput, mức sử dụng tài nguyên, điện năng nếu có cách đo đáng tin cậy. Lưu phiên bản tool, constraint, bitstream, log và kết quả để tái lập.

**Đạt khi:** SoC tích hợp chạy được prefill và decode trên VCU118, cho kết quả đúng theo tiêu chí đã thống nhất, đạt timing và có demo cùng bằng chứng đo lường. Việc coi đây là milestone/release của toàn dự án vẫn theo [PROJECT_MANAGEMENT.md](../../../docs/PROJECT_MANAGEMENT.md) và ROADMAP cấp dự án.

## Các điểm cần quyết định trước khi khóa thiết kế

1. Ngưỡng chất lượng, độ dài context và mức hiệu năng chấp nhận cho demo/nghiên cứu; không tự suy ra từ kết quả fake-quant hiện có.
2. Numerics contract cuối cùng, đặc biệt biểu diễn scale, accumulator, softmax, LUT và hành vi decode/KV ở context dài.
3. Ngân sách tài nguyên/băng thông và phương án lưu trọng số/KV trên VCU118 sau khi đo, không đặt số liệu FPGA giả định trong kế hoạch.
4. Giao diện TinyLLM–SoC và phân công host/firmware/RTL được review theo quyền sở hữu; `docs/DECISIONS.md` hoặc tài liệu quyết định tương ứng cần ghi lại các lựa chọn đã được chấp nhận.
