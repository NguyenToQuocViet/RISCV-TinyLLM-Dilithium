# TinyLLM — Định hướng và phạm vi dự án

**Người phụ trách chính:** @HoangHungLN.

TinyLLM là subsystem accelerator mô hình ngôn ngữ trong dự án RISCV-TinyLLM-Dilithium. Người phụ trách TinyLLM đồng thời tham gia công việc tích hợp với RISC-V và Dilithium.

## 1. Mục tiêu nghiên cứu

- Phát triển TinyLLM để có kết quả nghiên cứu phục vụ việc viết paper về subsystem này.
- Đóng góp vào kết quả nghiên cứu và paper về toàn bộ dự án RISCV-TinyLLM-Dilithium.

## 2. Nền tảng ban đầu: suy luận đầy đủ SmolLM2-135M

Mục tiêu ban đầu là hiện thực RTL cho đầy đủ phần tính toán của luồng suy luận SmolLM2-135M, làm nền tảng cho quá trình phát triển tiếp theo.

Hệ thống cần thực hiện được cả prefill và decode để sinh văn bản. Phần tính toán model do accelerator RTL thực hiện; phần xử lý văn bản và điều khiển ở mức ứng dụng được phân chia với firmware/Rocket như đề xuất tại mục 5.

## 3. Parameterize và mở rộng model

Trong quá trình hiện thực SmolLM2-135M, thiết kế cần được parameterize để có thể mở rộng sang model lớn hơn.

Các thông số theo cấu hình model cần được xem xét khi parameterize gồm số layer, hidden size, kích thước FFN, số query/KV head, chiều mỗi head, vocabulary size và context length. Cách tổ chức các khối tính toán, bộ nhớ và điều khiển cần hỗ trợ việc thay đổi các thông số này.

Thứ tự ưu tiên:

1. Hoàn thành nền tảng SmolLM2-135M.
2. Nâng lên model SmolLM lớn hơn; đây là định hướng cần thực hiện.
3. Mở rộng sang các model thuộc họ Llama nếu còn đủ thời gian.

## 4. Ứng dụng, trọng số và dữ liệu demo

Trước mắt sử dụng model và ứng dụng có sẵn, ưu tiên những lựa chọn dễ lấy trọng số, dữ liệu kiểm tra và dễ trình diễn. Phạm vi hiện tại không bao gồm tự xây dựng ứng dụng đặc thù rồi huấn luyện lại model cho ứng dụng đó.

**Đề xuất demo khởi đầu:** sinh văn bản hoặc tiếp tục một đoạn văn từ prompt với checkpoint có sẵn của SmolLM2-135M. [Model card chính thức](https://huggingface.co/HuggingFaceTB/SmolLM2-135M) có ví dụ nạp trọng số, tokenize prompt, sinh token và chuyển token thành văn bản; đây là căn cứ để xem xét demo này trước.

## 5. Phân chia firmware/Rocket và RTL

Bảng dưới đây là **đề xuất phân chia ở mức chức năng**, dựa trên [luồng dữ liệu SmolLM2 hiện có](design/SmolLM2.drawio).

| Bước trong luồng xử lý                           | Nơi thực hiện đề xuất                               | Phạm vi công việc                                                                                                         |
| ----------------------------------------------------- | --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Chuẩn bị model và trọng số trước khi chạy     | Công cụ trên host, ngoài luồng suy luận trên board | Lấy checkpoint có sẵn và chuẩn bị dữ liệu để nạp vào hệ thống.                                                 |
| Tiếp nhận prompt                                    | Firmware/Rocket                                           | Nhận văn bản đầu vào của ứng dụng demo.                                                                             |
| Tokenizer                                             | Firmware/Rocket                                           | Chuyển văn bản thành token IDs bằng tokenizer tương ứng với checkpoint.                                             |
| Khởi tạo tác vụ suy luận                         | Firmware/Rocket                                           | Cấu hình tác vụ và cung cấp dữ liệu, địa chỉ bộ nhớ, độ dài và vị trí token cần xử lý cho accelerator. |
| Embedding lookup                                      | RTL TinyLLM                                               | Tra trọng số embedding để tạo vector đầu vào cho model.                                                              |
| RMSNorm trước attention                             | RTL TinyLLM                                               | Thực hiện normalization đầu vào nhánh attention.                                                                       |
| Q/K/V projection                                      | RTL TinyLLM                                               | Thực hiện các phép nhân ma trận tạo query, key và value.                                                             |
| Tổ chức head, RoPE và GQA                          | RTL TinyLLM                                               | Sắp xếp tensor, áp dụng RoPE cho Q/K và ánh xạ query head tới KV head.                                               |
| Đọc/ghi KV cache                                    | RTL TinyLLM                                               | Lưu K/V và sử dụng dữ liệu cache trong prefill/decode.                                                                 |
| Attention                                             | RTL TinyLLM                                               | Tính QK, scale, causal mask, softmax và nhân với V.                                                                      |
| Output projection và residual                        | RTL TinyLLM                                               | Thực hiện projection đầu ra attention và cộng residual.                                                                |
| RMSNorm và FFN                                       | RTL TinyLLM                                               | Thực hiện normalization, gate/up projection, SiLU, phép nhân hai nhánh, down projection và cộng residual.             |
| Thực thi các decoder layer                          | RTL TinyLLM                                               | Điều phối chuỗi tính toán qua các layer của model.                                                                   |
| Final RMSNorm và LM head                             | RTL TinyLLM                                               | Tạo logits từ trạng thái đầu ra decoder.                                                                               |
| Chọn token kế tiếp                                 | Đề xuất RTL cho greedy argmax                          | Chọn token từ logits; chính sách chọn token cụ thể sẽ được xác định theo ứng dụng demo.                      |
| Điều khiển vòng sinh token và điều kiện dừng | Firmware/Rocket                                           | Yêu cầu lượt decode tiếp theo, kiểm tra EOS hoặc giới hạn số token sinh và kết thúc tác vụ.                   |
| Detokenizer và trình diễn kết quả                | Firmware/Rocket                                           | Chuyển token IDs thành văn bản và trả kết quả cho ứng dụng demo.                                                   |

Theo phân chia đề xuất này, RTL đảm nhiệm đường tính toán suy luận của model; firmware/Rocket đảm nhiệm xử lý văn bản và điều khiển ứng dụng. Công cụ trên host phục vụ chuẩn bị model và dữ liệu trước khi chạy.

## 6. Triển khai và demo trên VCU118

Đích triển khai của toàn bộ dự án là board **VCU118**. Mục tiêu là tạo bitstream, nạp lên board và demo hệ thống SoC tích hợp.

TinyLLM cần được phát triển và tích hợp theo hướng chạy được luồng suy luận đã nêu trên VCU118, sử dụng ứng dụng demo và trọng số có sẵn. Định hướng nền tảng cấp dự án được ghi trong [README](../../../README.md).
