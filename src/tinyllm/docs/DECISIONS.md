# Các quyết định kỹ thuật TinyLLM

## D01. Dùng FP32 làm chuẩn và nền tính toán cho fake-quant

**Chặng áp dụng:** [Chặng 1 — Cố định nguồn model và tạo bản chạy chuẩn FP32](PLAN.md#1-cố-định-nguồn-model-và-tạo-bản-chạy-chuẩn-fp32) và [chặng 2 — Thống nhất cách đánh giá và thử lượng tử hóa](PLAN.md#2-thống-nhất-cách-đánh-giá-và-thử-lượng-tử-hóa).

**Quyết định:** Nạp trọng số BF16 của checkpoint đã chọn, chuyển sang FP32 để chạy bản chuẩn và làm nền tính toán cho các thí nghiệm fake-quant. Trên nền này, thêm các bước lượng tử hóa hoặc tính xấp xỉ theo phương án cần khảo sát.

**Lý do:** FP32 giảm ảnh hưởng của sai số tính toán nền so với BF16, giúp đánh giá rõ hơn sai số do phương án lượng tử hóa hoặc xấp xỉ. Chấp nhận dùng nhiều bộ nhớ hơn BF16 để thí nghiệm dễ kiểm soát hơn.

**Giới hạn:**

- Chuyển trọng số BF16 sang FP32 giữ nguyên giá trị đã lưu, không khôi phục độ chính xác đã mất trong trọng số nguồn.
- Fake-quant vẫn có thể thực hiện trên BF16; FP32 là lựa chọn cho quy trình này, không phải điều kiện bắt buộc của fake-quant.

## D02. Phát triển datapath số nguyên theo SmoothQuant, ưu tiên W8A8

**Chặng áp dụng:** chặng 3–4 của [kế hoạch TinyLLM](PLAN.md).

**Quyết định:**

- Chọn SmoothQuant làm hướng RTL chính, với W8/KV8 và mục tiêu A8; dùng A12 SmoothQuant làm phương án dự phòng chất lượng. Giữ W8A16 per-tensor làm đối chứng phần mềm, không yêu cầu hiện thực riêng một accelerator A16 trước. Chưa đưa A10 vào phạm vi ban đầu.
- Host lựa chọn `alpha` và tính vector `s`, trọng số đã biến đổi `W'[o,i] = W[o,i] * s[i]` cùng các tham số lượng tử hóa tương ứng. RTL nhận bộ trọng số và hệ số đã xuất đồng bộ; `alpha` là tham số hiệu chỉnh trên host. Đổi `s` phải xuất lại bộ tham số tương ứng, đồng thời bảo toàn quan hệ dùng chung trọng số embedding/LM head.
- Hiện thực smoothing bằng số nguyên/fixed-point: ưu tiên gộp phép chia activation cho `s` với quantization thành phép nhân hệ số, dịch, làm tròn và saturation. Giữ đủ độ chính xác trước smoothing. Chỉ thay bộ hệ số mà giữ nguyên RTL khi các giá trị nằm trong miền biểu diễn đã quy định.
- Ban đầu parameterize độ rộng A8/A12 lúc synthesis để so chất lượng và chi phí trên cùng thiết kế. Khả năng đổi độ rộng lúc chạy chỉ được bổ sung sau khi đánh giá chi phí; datapath rộng 12 bit không tự giảm diện tích khi chạy chế độ A8.
- Nếu PTQ A8 chưa đủ chất lượng, xem xét QAT theo numerical contract của datapath, gồm các điểm quantize, quy tắc làm tròn/giới hạn và sai số hệ số nhân/dịch. QAT là phương án cần đánh giá, chưa phải bảo đảm chất lượng A8 hay công việc huấn luyện đã được triển khai.

**Lý do:** Tách hiệu chỉnh model trên host khỏi datapath để tái sử dụng RTL với các bộ tham số và model khác nhau. Sau smoothing, scale A per-tensor thuận lợi cho dot-product số nguyên; A8 là mục tiêu giảm chi phí, còn A12 cung cấp phương án đối chứng đã có bằng chứng chất lượng.

**Giới hạn:** Đây là quyết định về hướng phát triển, chưa chốt numerical contract. Định dạng và miền hệ số nhân/dịch, độ rộng các trung gian và accumulator, quy tắc requantization, thuật toán phi tuyến và định dạng nạp dữ liệu tiếp tục được xác định và kiểm chứng ở chặng 3–4. Chỉ chốt contract sau khi bản số nguyên đạt chất lượng và đã kiểm tra chi phí phần cứng; ngưỡng đánh giá và thời điểm dùng heldout vẫn theo [PTQ plan](../quantize/plans/ptq_plan.md).
