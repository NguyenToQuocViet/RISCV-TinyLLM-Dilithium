# Các quyết định kỹ thuật TinyLLM

## D01. Dùng FP32 làm chuẩn và nền tính toán cho fake-quant

**Chặng áp dụng:** [Chặng 1 — Cố định nguồn model và tạo bản chạy chuẩn FP32](PLAN.md#1-cố-định-nguồn-model-và-tạo-bản-chạy-chuẩn-fp32) và [chặng 2 — Thống nhất cách đánh giá và thử lượng tử hóa](PLAN.md#2-thống-nhất-cách-đánh-giá-và-thử-lượng-tử-hóa).

**Quyết định:** Nạp trọng số BF16 của checkpoint đã chọn, chuyển sang FP32 để chạy bản chuẩn và làm nền tính toán cho các thí nghiệm fake-quant. Trên nền này, thêm các bước lượng tử hóa hoặc tính xấp xỉ theo phương án cần khảo sát.

**Lý do:** FP32 giảm ảnh hưởng của sai số tính toán nền so với BF16, giúp đánh giá rõ hơn sai số do phương án lượng tử hóa hoặc xấp xỉ. Chấp nhận dùng nhiều bộ nhớ hơn BF16 để thí nghiệm dễ kiểm soát hơn.

**Giới hạn:**

- Chuyển trọng số BF16 sang FP32 giữ nguyên giá trị đã lưu, không khôi phục độ chính xác đã mất trong trọng số nguồn.
- Fake-quant vẫn có thể thực hiện trên BF16; FP32 là lựa chọn cho quy trình này, không phải điều kiện bắt buộc của fake-quant.

## D02. Phát triển datapath số nguyên theo SmoothQuant

**Chặng áp dụng:** chặng 3–4 của [kế hoạch TinyLLM](PLAN.md).

**Quyết định:**

- Chọn W8A12KV8 SmoothQuant làm cấu hình chính để xây numerical contract hiện tại, dựa trên candidate alpha 0.5 đã qua quality gate. Giữ A8 làm hướng tối ưu sau; W8A16 per-tensor là đối chứng phần mềm. Chưa đưa A10 vào phạm vi ban đầu.
- Host lựa chọn `alpha` và tính vector `s`, trọng số đã biến đổi `W'[o,i] = W[o,i] * s[i]` cùng các tham số lượng tử hóa tương ứng. RTL nhận bộ trọng số và hệ số đã xuất đồng bộ; `alpha` là tham số hiệu chỉnh trên host. Đổi `s` phải xuất lại bộ tham số tương ứng, đồng thời bảo toàn quan hệ dùng chung trọng số embedding/LM head.
- Hiện thực smoothing bằng số nguyên/fixed-point: ưu tiên gộp phép chia activation cho `s` với quantization thành phép nhân hệ số, dịch, làm tròn và saturation. Giữ đủ độ chính xác trước smoothing. Chỉ thay bộ hệ số mà giữ nguyên RTL khi các giá trị nằm trong miền biểu diễn đã quy định.
- Parameterize độ rộng A8/A12 lúc synthesis, ưu tiên hoàn thiện cấu hình A12 trước. Khả năng đổi độ rộng lúc chạy chỉ được bổ sung sau khi đánh giá chi phí; datapath rộng 12 bit không tự giảm diện tích khi chạy chế độ A8.
- Nếu PTQ A8 chưa đủ chất lượng, xem xét QAT theo numerical contract của datapath, gồm các điểm quantize, quy tắc làm tròn/giới hạn và sai số hệ số nhân/dịch. QAT là phương án cần đánh giá, chưa phải bảo đảm chất lượng A8 hay công việc huấn luyện đã được triển khai.

**Lý do:** Tách hiệu chỉnh model trên host khỏi datapath để tái sử dụng RTL với các bộ tham số và model khác nhau. Sau smoothing, scale A per-tensor thuận lợi cho dot-product số nguyên. A12 đã có bằng chứng chất lượng để bắt đầu bản số nguyên, trong khi A8 SmoothQuant chưa qua gate; giảm bit tiếp tục được xét theo chất lượng và chi phí phần cứng.

**Giới hạn:** Numerical contract v1 cho candidate giảm bit `combined_min_1pct_residual16_m16` đã qua các gate software selection; quy tắc và bằng chứng nằm trong [numerical contract v1](design/numerical_contract_v1.md#144-kết-quả-lựa-chọn-trên-selection). Đây là đầu vào cho công việc hiện thực số nguyên và khảo sát chi phí RTL, chưa phải chốt số học phần cứng vì chưa đánh giá heldout hoặc tài nguyên phần cứng. Ngưỡng và thời điểm dùng heldout vẫn theo [PTQ plan](../quantize/plans/ptq_plan.md).  
  
## D03. Chốt contract theo từng phần; hàm phi tuyến chọn trong lúc thiết kế

**Chặng áp dụng:** chặng 3–4 của [kế hoạch TinyLLM](PLAN.md).

**Quyết định:**

- [Numerical contract v1](design/numerical_contract_v1.md) chốt biểu diễn, độ rộng bit, scale và các phép tính nền: MAC, requantization, smoothing, residual và các bước thu hẹp.
- Thuật toán phi tuyến trong v1 (RMSNorm, RoPE, Softmax, SiLU) chỉ là tạm thời, dùng để đánh giá contract hoàn chỉnh.
- Thuật toán và kiến trúc của các hàm phi tuyến được chọn ở chặng 4, sau khi đã thiết kế các thành phần xung quanh, để phù hợp với thiết kế đó. Sàng lọc có thể dùng fake-quant. Phương án được chọn được cập nhật vào contract và chấm bằng runtime contract.
- Độ rộng vào/ra của khối phi tuyến có thể thay đổi theo kiến trúc được chọn. Mỗi thay đổi tạo một phiên bản contract mới.

**Lý do:** Tìm kiến trúc tối ưu cho từng hàm phi tuyến tốn nhiều thời gian. Chọn sau khi đã có thiết kế xung quanh giúp không chặn các phần việc khác, đồng thời bảo đảm kiến trúc được chọn phù hợp với dataflow.

**Giới hạn:**

- Fake-quant không mô phỏng đúng rounding, saturation và cách gộp hệ số, nên không thay được việc chấm trên runtime contract.
- Khi thiết kế phần xung quanh, cần dành chỗ cho khối phi tuyến: vị trí trong pipeline, throughput, độ trễ và dung lượng bảng. Nếu không, phạm vi thuật toán có thể chọn sẽ bị thu hẹp.

## D04. Hoàn thành đặc tả thiết kế trước khi viết RTL đầy đủ

**Chặng áp dụng:** chặng 4–5 của [kế hoạch TinyLLM](PLAN.md).

**Quyết định:**

- Viết đặc tả thiết kế chi tiết cho toàn accelerator trước khi viết RTL đầy đủ. Đặc tả được xây dần; nội dung có trong đặc tả là nội dung đã quyết.
- Ngoại lệ: một khối được viết RTL trước khi đặc tả hoàn thành khi cả thuật toán lẫn giao diện (port, thứ tự dữ liệu, handshake, throughput) đã cố định và không phụ thuộc vào khối lân cận hoặc bộ điều phối còn chưa quyết. Ví dụ: phần tử RNE và requant nhân–dịch, PE/DSP, cộng residual, bộ so sánh argmax.
- RTL đại diện để đo băng thông DDR, timing của nhóm PE và đối chứng baseline được viết trong chặng 4. Nó không bắt buộc được giữ lại.

**Lý do:** Tránh xung đột giao diện và phải sửa giữa chừng khi ghép các khối. Ngoại lệ giúp không lãng phí thời gian với các khối đã cố định.

**Giới hạn:** Trước khi áp dụng ngoại lệ cho một khối, phải xét giao diện của khối đó, không chỉ phần bên trong. Khối đã viết theo ngoại lệ vẫn phải sửa nếu đặc tả sau đó đổi giao diện của nó.

## D05. Golden model ở mức số học

**Chặng áp dụng:** chặng 4–6 của [kế hoạch TinyLLM](PLAN.md).

**Quyết định:**

- Golden model kiểm tra đúng đắn số học theo contract. Nó không mô phỏng từng bước phần cứng (tile, lịch, bộ đệm, địa chỉ). Không xây mô hình kiến trúc riêng.
- Khi một khối đã chốt thuật toán, viết golden cho khối đó dựa trên primitive và runtime contract hiện có, rồi kiểm tra với oracle độc lập. Khi đủ các khối, ghép golden toàn model và kiểm tra nó cho cùng mã với runtime contract.
- Golden xuất các tensor boundary theo tên trong `config.formats` của contract. RTL so khớp từng bit tại đầu ra từng khối và đầu ra model.

**Lý do:** Golden độc lập với cách tổ chức phần cứng nên không sai cùng kiểu với RTL. Phép cộng số nguyên đủ rộng không phụ thuộc thứ tự, nên phần cứng được tự do chọn dataflow.

**Giới hạn:**

- Mọi chỗ phần cứng làm thay đổi kết quả số, như thứ tự rounding hay vị trí chuẩn hóa, phải được ghi vào contract trước khi hiện thực.
- Golden không biết tile, nên dữ liệu kiểm tra phải được chọn theo phần cứng: tile lẻ, độ dài quanh bội số kích thước tile, L = 512, khối causal trên đường chéo, decode ngay sau prefill.
- Khi có sai lệch, golden chỉ khoanh được tới đầu ra của khối. Lỗi địa chỉ hoặc lịch bên trong khối được tìm bằng cách so sánh tensor.

## D06. Dùng selection và heldout trong giai đoạn thiết kế

**Chặng áp dụng:** chặng 3–6 của [kế hoạch TinyLLM](PLAN.md).

**Quyết định:**

- Mỗi lần cập nhật contract, ví dụ khi chốt thuật toán của một khối phi tuyến, chạy lại quality gate trên selection bằng runtime contract.
- Heldout chỉ chạy một lần, sau khi contract phiên bản cuối đã chốt. Không dùng kết quả heldout để chọn hoặc chỉnh contract.
- Theo dõi khoảng dư giữa kết quả selection và ngưỡng gate qua các phiên bản contract, để giảm rủi ro trượt heldout ở cuối.

**Lý do:** Candidate được chọn từ nhiều phương án trên selection nên điểm selection lạc quan hơn thực tế. Heldout chưa được dùng cho ước lượng không bị lệch. Chạy heldout nhiều lần rồi sửa theo kết quả sẽ biến nó thành một tập selection thứ hai.

**Giới hạn:** Nếu heldout trượt, ghi lại kết quả. Nếu sau đó sửa contract, lần xác nhận tiếp theo không còn hoàn toàn độc lập và phải nêu rõ điều này khi báo cáo. Ngưỡng và protocol theo [PTQ plan](../quantize/plans/ptq_plan.md).
