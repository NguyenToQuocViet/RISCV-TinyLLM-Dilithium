# Các quyết định kỹ thuật TinyLLM

## D01. Dùng FP32 làm chuẩn và nền tính toán cho fake-quant

**Chặng áp dụng:** [Chặng 1 — Cố định nguồn model và tạo bản chạy chuẩn FP32](PLAN.md#1-cố-định-nguồn-model-và-tạo-bản-chạy-chuẩn-fp32) và [chặng 2 — Thống nhất cách đánh giá và thử lượng tử hóa](PLAN.md#2-thống-nhất-cách-đánh-giá-và-thử-lượng-tử-hóa).

**Quyết định:** Nạp trọng số BF16 của checkpoint đã chọn, chuyển sang FP32 để chạy bản chuẩn và làm nền tính toán cho các thí nghiệm fake-quant. Trên nền này, thêm các bước lượng tử hóa hoặc tính xấp xỉ theo phương án cần khảo sát.

**Lý do:** FP32 giảm ảnh hưởng của sai số tính toán nền so với BF16, giúp đánh giá rõ hơn sai số do phương án lượng tử hóa hoặc xấp xỉ. Chấp nhận dùng nhiều bộ nhớ hơn BF16 để thí nghiệm dễ kiểm soát hơn.

**Giới hạn:**

- Chuyển trọng số BF16 sang FP32 giữ nguyên giá trị đã lưu, không khôi phục độ chính xác đã mất trong trọng số nguồn.
- Fake-quant vẫn có thể thực hiện trên BF16; FP32 là lựa chọn cho quy trình này, không phải điều kiện bắt buộc của fake-quant.
