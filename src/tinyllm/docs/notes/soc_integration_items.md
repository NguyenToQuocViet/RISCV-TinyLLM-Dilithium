# Các nội dung TinyLLM cần thống nhất với SoC

Ngày: 25-11-2026. Trạng thái: đầu vào của TinyLLM cho system-level contract. Đây chưa phải contract đã chấp nhận.

Theo [PROJECT_MANAGEMENT §3.5 và §4](../../../../docs/PROJECT_MANAGEMENT.md), memory map, interconnect, giao diện dùng chung, ngắt, clock/reset và integration contract do project architect quyết, có review ở cấp dự án. Kết quả được ghi vào `docs/architecture/` và `docs/decisions/` ở gốc repo. TinyLLM bám theo kết quả đó trong mục 9 của [sườn đặc tả](accelerator_spec_outline.md).

Mỗi mục dưới đây gồm: cần chốt gì, ảnh hưởng tới TinyLLM thế nào, đề xuất của TinyLLM, ai quyết, và mục nào của đặc tả TinyLLM bị chặn cho tới khi chốt.

## 1. Hiện trạng đã biết

| Nội dung | Hiện trạng | Nguồn |
| --- | --- | --- |
| CPU | Core RISC-V 5 tầng của dự án, RV32I 37 lệnh, chưa có cache và branch predictor | [5-stage-baseline-core.md](../../../riscv/docs/designs/5-stage-baseline-core.md) |
| Bus của CPU | Hai cổng OBI 1.6.0 (lệnh, dữ liệu), địa chỉ 32 bit, dữ liệu 32 bit, tối đa 1 giao dịch chờ, không có tín hiệu lỗi bus | như trên |
| Ngắt, trap | `FENCE`, `ECALL`, `EBREAK`, lệnh đặc quyền, trap và mở rộng ISA nằm ngoài phạm vi baseline | như trên |
| Reset của CPU | `rst_n` mức thấp, đồng bộ. Tạo và phân phối reset hệ thống thuộc system-level contract, chưa viết | như trên |
| Tích hợp SoC, AXI, FPGA | Nằm ngoài phạm vi hoàn thành của baseline core | như trên |
| System-level contract | `docs/architecture/`, `docs/designs/`, `docs/decisions/` ở gốc repo còn trống | repo |
| Dilithium, interconnect, SoC | Thư mục `src/` của các phần này chưa có nội dung | repo |
| Board | VCU118 có hai giao diện DDR4 độc lập. Thông số (độ rộng, tốc độ, dung lượng, bank) cần tra UG1224 | kiến thức chung |
| Nhu cầu của TinyLLM (ước tính) | Trọng số 128,25 MiB; decode đọc tuần tự ~134 MB mỗi token; ~16 GB/s dùng hết một kênh; mảng 24×64 dùng 1.536 DSP (48×64: 3.072); KV cache ~5,625 MiB trên URAM | [contract §13](../design/numerical_contract_v1.md), [os_g_matmul_engine.md](os_g_matmul_engine.md) |

[PROJECT.md §5](../PROJECT.md) vẫn ghi "Firmware/Rocket", trong khi README và nhánh `riscv` là core RISC-V tự thiết kế. Cần xác nhận ở mục S1 rồi sửa PROJECT.md.

## 2. Kiến trúc SoC và kịch bản sử dụng

### S1. CPU dùng trong SoC

- **Cần chốt:** core nào chạy firmware trong bản tích hợp (baseline 5 tầng, cấu hình 7 tầng, hay core khác); khi nào có cache, ngắt, `FENCE`, mở rộng M.
- **Ảnh hưởng tới TinyLLM:**
  - Không có ngắt thì firmware phải polling.
  - Không có cache thì không cần xử lý coherence; có cache thì phải có quy tắc riêng.
  - Không có `FENCE` thì thứ tự ghi phải được bảo đảm bằng bus (mục C3).
- **Đề xuất của TinyLLM:** thiết kế cho baseline (polling, không cache), đồng thời vẫn có đường ngắt để dùng về sau.
- **Người quyết:** project architect, owner RISC-V.
- **Chặn:** đặc tả 9.3, 9.4, 9.5.

### S2. Kịch bản demo và tính đồng thời

- **Cần chốt:** luồng demo đầu-cuối (prompt → token → văn bản, có ký Dilithium hay không); TinyLLM và Dilithium chạy đồng thời hay tuần tự.
- **Ảnh hưởng tới TinyLLM:** nếu tuần tự thì TinyLLM có thể dùng toàn bộ DDR trong lúc chạy. Nếu đồng thời thì cần phân xử và QoS (mục M3).
- **Đề xuất của TinyLLM:** chốt luồng demo trước. Nếu chạy tuần tự, cách chia DDR ở mục M1 đơn giản hơn nhiều.
- **Người quyết:** project architect cùng ba owner.
- **Chặn:** đặc tả 6.5 (khoảng dừng DDR phải chịu), 9.1.

### S3. Phân chia việc của phần mềm

- **Cần chốt:**
  - Tokenizer và detokenizer chạy trên CPU hay trên host.
  - Dữ liệu tokenizer (vocab 49.152 mục, bảng merge BPE) nằm ở đâu.
  - Ai viết driver TinyLLM trong firmware.
- **Ảnh hưởng tới TinyLLM:** không đổi RTL, vì TinyLLM chỉ nhận token ID. Nhưng nó quyết định demo có chạy được hay không. BPE trên RV32I không có lệnh nhân sẽ chậm, và bảng dữ liệu cần vài MB bộ nhớ CPU truy cập được.
- **Đề xuất của TinyLLM:** bản demo đầu cho phép host tokenize rồi gửi token ID qua cổng gỡ lỗi; tokenizer trên CPU làm sau. TinyLLM cung cấp driver mẫu theo mô hình lập trình ở đặc tả 9.4.
- **Người quyết:** project architect, owner RISC-V.
- **Chặn:** không chặn RTL TinyLLM; chặn kế hoạch demo ở chặng 7.

## 3. Bộ nhớ DDR4 và interconnect

### M1. Gán kênh DDR4

- **Cần chốt:** mỗi kênh DDR4 phục vụ những master nào.
- **Ảnh hưởng tới TinyLLM:** decode bị giới hạn bởi băng thông DDR. Một kênh riêng cho ~8,2 ms/token, hai kênh cho ~4,1 ms/token (ước tính). Ngoài ra còn ảnh hưởng số cổng DMA và cách chia trọng số trong định dạng đóng gói.
- **Các phương án:**

  | Phương án | TinyLLM nhận | Đánh đổi |
  | --- | --- | --- |
  | A. TinyLLM độc quyền một kênh; CPU và Dilithium dùng kênh còn lại | 1 kênh, không bị nhiễu | Đơn giản nhất; bỏ phí phần còn trống của kênh kia |
  | B. Hai kênh dùng chung, phân xử qua interconnect | Gần 2 kênh | Phức tạp nhất; truy cập ngẫu nhiên của CPU xen vào làm giảm hiệu suất đọc tuần tự |
  | C. TinyLLM độc quyền kênh 2, dùng chung kênh 1 với ưu tiên thấp nhất và giới hạn burst | Gần 2 kênh nếu CPU và Dilithium dùng ít | CPU vẫn có độ trễ bị chặn; TinyLLM phải chịu khoảng dừng trên kênh 1 |

- **Đề xuất của TinyLLM:** tích hợp lần đầu theo A. TinyLLM được thiết kế để chạy được cả C: số cổng DMA là parameter, tỷ lệ chia trọng số giữa hai kênh cấu hình được trong công cụ đóng gói.
- **Người quyết:** project architect, owner interconnect.
- **Chặn:** đặc tả 2.2, 5.1, 5.2, 7.1, 9.1.

### M2. Topology và giao thức cổng DDR của TinyLLM

- **Cần chốt:**
  - TinyLLM nối thẳng vào bộ điều khiển DDR4 (MIG) hay đi qua interconnect chung.
  - Giao thức (AXI4 hay khác), độ rộng dữ liệu, ai sở hữu và cấu hình MIG.
  - CPU (OBI 32 bit) tới DDR qua cầu nối nào.
- **Ảnh hưởng tới TinyLLM:** độ rộng beat quyết định cấu trúc bộ đệm nạp trước và layout trọng số. Đi qua interconnect chung thì có thêm độ trễ và khả năng bị nghẽn.
- **Đề xuất của TinyLLM:** TinyLLM có cổng AXI4 master đọc riêng tới mỗi MIG được gán, độ rộng bằng cổng gốc của MIG. CPU đi qua cầu nối OBI–AXI vào một cổng khác của interconnect.
- **Người quyết:** project architect, owner interconnect.
- **Chặn:** đặc tả 7.1, 9.1, 3.3.

### M3. Phân xử và QoS trên kênh dùng chung

- **Cần chốt:** thứ tự ưu tiên giữa các master; giới hạn độ dài burst của từng master; có bảo đảm băng thông tối thiểu hay không.
- **Ảnh hưởng tới TinyLLM:** bộ đệm nạp trước phải đủ lớn để che khoảng bị chặn dài nhất.
- **Đề xuất của TinyLLM:** CPU ưu tiên cao nhất, rồi Dilithium, TinyLLM thấp nhất. TinyLLM tự giới hạn độ dài burst (ví dụ 4 KB, chiếm kênh khoảng 250 ns). Đặc tả TinyLLM công bố khoảng dừng tối đa nó chịu được mà decode không chậm lại. SoC dùng con số đó làm ràng buộc khi cấu hình phân xử.
- **Người quyết:** project architect, owner interconnect.
- **Chặn:** đặc tả 6.5, 7.1. Chỉ cần nếu chọn B hoặc C ở M1, hoặc nếu S2 là chạy đồng thời.

### M4. Đo băng thông DDR4

- **Cần chốt:** ai dựng thiết kế đo, đo những kịch bản nào.
- **Ảnh hưởng tới TinyLLM:** con số 85% hiệu suất đọc tuần tự hiện chỉ là giả định. Số đo thật quyết định G, dung lượng bộ đệm nạp trước và mục tiêu tốc độ.
- **Đề xuất của TinyLLM:** TinyLLM dựng thiết kế đo gồm MIG, một AXI master đọc tuần tự và bộ đếm byte/chu kỳ. Các kịch bản: đọc tuần tự với vài độ dài burst; đọc tuần tự xen truy cập ngẫu nhiên nhỏ (mô phỏng CPU); hai kênh cùng lúc.
- **Người quyết:** owner TinyLLM, phối hợp với owner interconnect.
- **Chặn:** đặc tả 2.2, 2.3, 6.7.

## 4. Address space và memory map

### A1. Bản đồ địa chỉ

- **Cần chốt:**
  - Base address của thanh ghi TinyLLM trong không gian 32 bit của CPU.
  - Cửa sổ DDR mà CPU nhìn thấy.
  - Vùng DDR dành cho TinyLLM: base, kích thước, căn lề.
  - Độ rộng địa chỉ DMA của TinyLLM, có được khác 32 bit hay không.
  - Vùng của Dilithium và vùng chương trình, dữ liệu của CPU.
- **Ảnh hưởng tới TinyLLM:** vùng của TinyLLM cần khoảng 128,25 MiB trọng số, cộng ~2,3 MB hệ số/LUT, vùng vào/ra và vùng dump gỡ lỗi. Không gian 32 bit của CPU có thể không chứa được toàn bộ DDR.
- **Đề xuất của TinyLLM:** một vùng liên tục 256 MiB, căn lề 4 KiB, trên kênh DDR được gán cho TinyLLM. Địa chỉ DMA của TinyLLM tính theo offset trong vùng này. CPU chỉ cần thấy vùng này khi nạp trọng số và đọc dump.
- **Người quyết:** project architect.
- **Chặn:** đặc tả 5.1, 9.1, 9.2.

### A2. Quyền truy cập vùng nhớ

- **Cần chốt:** ai được ghi vùng nào, vào lúc nào. Hệ thống không có MMU nên đây là quy ước của firmware.
- **Ảnh hưởng tới TinyLLM:** nếu CPU ghi vào vùng trọng số trong lúc TinyLLM đang đọc, kết quả sẽ sai mà không có báo lỗi.
- **Đề xuất của TinyLLM:** chỉ ghi vùng TinyLLM khi trạng thái là rảnh. Header gói dữ liệu có checksum để firmware kiểm tra sau khi nạp.
- **Người quyết:** project architect, owner RISC-V (firmware).
- **Chặn:** đặc tả 5.2, 9.4.

### A3. Nạp trọng số lên board

- **Cần chốt:** đường nạp khoảng 130 MB vào DDR (JTAG-to-AXI, UART, thẻ SD, PCIe…), ai thực hiện, mất bao lâu.
- **Ảnh hưởng tới TinyLLM:** ảnh hưởng thời gian chuẩn bị demo và cách lặp thử nghiệm trên board. Qua UART 115200 baud mất khoảng 3 giờ (ước tính), quá chậm cho việc thử đi thử lại.
- **Đề xuất của TinyLLM:** dùng một đường nạp nhanh ghi thẳng vào DDR, không qua CPU. Chọn cụ thể sau khi biết công cụ và phần cứng sẵn có.
- **Người quyết:** project architect.
- **Chặn:** chặng 7–8 của PLAN; không chặn RTL.

## 5. Giao tiếp CPU ↔ TinyLLM

### C1. Giao thức cổng điều khiển

- **Cần chốt:** cổng thanh ghi của TinyLLM dùng giao thức nào (OBI subordinate cùng chuẩn với CPU, hay AXI4-Lite qua cầu nối), độ rộng, độ trễ phản hồi, có phản hồi lỗi hay không.
- **Ảnh hưởng tới TinyLLM:** quyết định giao diện của khối thanh ghi điều khiển.
- **Đề xuất của TinyLLM:** OBI 1.6.0 subordinate 32 bit, cùng cấu hình với cổng dữ liệu của CPU, không dùng tín hiệu lỗi. Thanh ghi nằm trong miền clock của TinyLLM, có CDC ở ranh giới (mục K1).
- **Người quyết:** project architect, owner interconnect.
- **Chặn:** đặc tả 7.15, 9.2.

### C2. Lệnh và dữ liệu vào/ra

- **Cần chốt:** cách CPU giao một lượt prefill hoặc decode; token ID vào và token kết quả ra đi qua đâu; ai giữ độ dài cache `L`.
- **Ảnh hưởng tới TinyLLM:** quyết định bản đồ thanh ghi và bộ đệm vào/ra.
- **Đề xuất của TinyLLM:**
  - Mỗi lệnh ghi rõ loại (prefill T token, hoặc decode 1 token) và `L_prev`. TinyLLM kiểm tra `L_prev + T ≤ 512`.
  - Token ID vào qua một FIFO thanh ghi (prompt tối đa 512 × 16 bit = 1 KiB). Token ra qua thanh ghi kết quả.
  - Vòng sinh token và kiểm tra EOS do firmware làm, theo PROJECT.md §5.
- **Người quyết:** owner TinyLLM đề xuất; project architect duyệt phần communication contract.
- **Chặn:** đặc tả 8.2, 9.2, 9.4.

### C3. Thứ tự và nhất quán bộ nhớ

- **Cần chốt:**
  - Interconnect có trả phản hồi ghi sớm (posted write) hay không.
  - Có bảo đảm thứ tự giữa một lần ghi DDR của CPU và một lần ghi thanh ghi TinyLLM ngay sau đó hay không.
  - Quy tắc coherence khi CPU có cache.
- **Ảnh hưởng tới TinyLLM:** baseline không có `FENCE`. Nếu CPU ghi dữ liệu vào DDR rồi ghi thanh ghi start, TinyLLM có thể đọc DDR trước khi dữ liệu tới, vì hai lần ghi đi theo hai đường khác nhau.
- **Đề xuất của TinyLLM:** dữ liệu vào/ra của mỗi lượt chỉ đi qua thanh ghi (mục C2), nên không phụ thuộc thứ tự trên DDR. DDR chỉ được ghi khi nạp trọng số, xảy ra trước lần chạy đầu và có kiểm tra checksum. Khi CPU có cache: vùng TinyLLM không được cache, hoặc firmware flush theo quy trình được ghi lại.
- **Người quyết:** project architect, owner interconnect, owner RISC-V.
- **Chặn:** đặc tả 9.5.

### C4. Báo hoàn tất và lỗi

- **Cần chốt:** có bộ điều khiển ngắt hay không; đường ngắt của TinyLLM nối vào đâu; quy ước timeout của firmware.
- **Ảnh hưởng tới TinyLLM:** baseline core không xử lý ngắt nên firmware phải polling thanh ghi trạng thái.
- **Đề xuất của TinyLLM:** thanh ghi trạng thái có bit xong, bit lỗi và mã lỗi; firmware polling. Thêm đường ngắt mức (level), xóa bằng cách ghi thanh ghi, để dùng khi CPU hỗ trợ ngắt. Mỗi token mất vài ms nên chi phí polling không đáng kể.
- **Người quyết:** project architect.
- **Chặn:** đặc tả 9.3.

## 6. Clock và reset

### K1. Clock

- **Cần chốt:** tần số và nguồn clock của TinyLLM, CPU, interconnect và MIG; ai tạo clock (MMCM); ai sở hữu CDC ở từng ranh giới.
- **Ảnh hưởng tới TinyLLM:** mục tiêu hiện là 250 MHz cho lõi TinyLLM. Clock giao diện người dùng của MIG có thể khác, nên có CDC giữa DMA và lõi.
- **Đề xuất của TinyLLM:** TinyLLM có miền clock riêng. CDC tới MIG nằm trong TinyLLM, ở khối DMA. CDC tới cổng điều khiển nằm trong khối thanh ghi của TinyLLM.
- **Người quyết:** project architect.
- **Chặn:** đặc tả 2.2, 3.3.

### K2. Reset

- **Cần chốt:**
  - Nguồn reset hệ thống, cực tính, đồng bộ hay bất đồng bộ, ai đồng bộ vào từng miền clock.
  - Thứ tự nhả reset so với lúc MIG hiệu chỉnh xong.
  - Có reset mềm riêng cho từng khối hay không.
- **Ảnh hưởng tới TinyLLM:** DMA không được phát yêu cầu trước khi MIG hiệu chỉnh xong.
- **Đề xuất của TinyLLM:**
  - Reset đồng bộ mức thấp, theo cùng quy ước với CPU.
  - Trạng thái MIG đã hiệu chỉnh xong được đưa tới TinyLLM; firmware đọc được qua thanh ghi.
  - TinyLLM có reset mềm qua thanh ghi.
- **Người quyết:** project architect.
- **Chặn:** đặc tả 3.3, 4.4, 9.4.

## 7. Tài nguyên FPGA và triển khai vật lý

### R1. Ngân sách tài nguyên

- **Cần chốt:** phần DSP, URAM, BRAM, LUT, FF cho từng phần (TinyLLM, Dilithium, CPU, interconnect) trên XCVU9P.
- **Ảnh hưởng tới TinyLLM:** quyết định M (24 hay 48), dung lượng bộ đệm, có giữ một phần LM head trên chip hay không.
- **Đề xuất của TinyLLM (ước tính, cần cập nhật theo đặc tả):** DSP 1.536 với M = 24 (khoảng 22% của 6.840), mở rộng 3.072 với M = 48. URAM khoảng 160 khối cho KV cache, cộng phần cho các bộ đệm. Cần biết nhu cầu của Dilithium (mục D1) trước khi chốt.
- **Người quyết:** project architect cùng ba owner.
- **Chặn:** đặc tả 2.2, 2.3, 5.3.

### R2. Vị trí trên các SLR

- **Cần chốt:** TinyLLM đặt ở SLR nào; bank của từng DDR4 nằm ở SLR nào; ranh giới SLR nào được phép cắt qua giao diện nào.
- **Ảnh hưởng tới TinyLLM:** mảng PE lớn nên đặt gần bank DDR mà nó dùng. Tín hiệu qua ranh giới SLR chậm hơn, ảnh hưởng trực tiếp tới việc có đạt 250 MHz hay không.
- **Đề xuất của TinyLLM:** đặt mảng và DMA trong cùng SLR với bank DDR được gán ở mục M1. Giao diện điều khiển được phép qua SLR, có thanh ghi pipeline.
- **Người quyết:** project architect.
- **Chặn:** đặc tả 2.2, 3.3; đo timing ở chặng 4.

### R3. Công cụ và ràng buộc

- **Cần chốt:** phiên bản Vivado dùng chung, part `xcvu9p-flga2104-2L-e` cùng board file, license, ai sở hữu file ràng buộc (XDC) của top-level.
- **Ảnh hưởng tới TinyLLM:** số đo timing của RTL đại diện chỉ so sánh được khi dùng cùng công cụ và part. VU9P cần license đầy đủ.
- **Đề xuất của TinyLLM:** chốt phiên bản công cụ trước khi bắt đầu đo ở chặng 4.
- **Người quyết:** project architect.
- **Chặn:** đo RTL đại diện ở chặng 4.

## 8. Dilithium

### D1. Quan hệ giữa TinyLLM và Dilithium

- **Cần chốt:**
  - Có đường dữ liệu trực tiếp giữa hai khối không.
  - Dilithium có dùng DDR không: băng thông, độ trễ, dung lượng.
  - Dilithium cần những tài nguyên FPGA nào.
  - Dilithium có chạy đồng thời với TinyLLM không (mục S2).
- **Ảnh hưởng tới TinyLLM:** quyết định mục M1, M3 và R1.
- **Đề xuất của TinyLLM:** không có đường dữ liệu trực tiếp; mọi trao đổi đi qua CPU. Cần owner Dilithium ước tính nhu cầu DDR và tài nguyên.
- **Người quyết:** owner Dilithium cung cấp số liệu; project architect quyết.
- **Chặn:** M1, M3, R1.

## 9. Kiểm thử tích hợp và gỡ lỗi

### V1. Kiểm thử ở mức SoC

- **Cần chốt:**
  - Ai sở hữu testbench SoC.
  - Mô hình DDR dùng trong mô phỏng: mô hình của MIG hay mô hình bộ nhớ AXI đơn giản.
  - Bài kiểm tra nghiệm thu: từ token đầu vào tới token đầu ra.
- **Ảnh hưởng tới TinyLLM:** TinyLLM cung cấp vector từ golden số học và bài kiểm tra độc lập của khối.
- **Đề xuất của TinyLLM:** dùng mô hình bộ nhớ AXI đơn giản cho kiểm thử chức năng, và mô hình MIG cho một số bài kiểm tra timing của giao diện.
- **Người quyết:** project architect, owner SoC.
- **Chặn:** chặng 7 của PLAN.

### V2. Gỡ lỗi trên board

- **Cần chốt:** console của firmware (UART), truy cập JTAG, cách đọc vùng dump của TinyLLM về host.
- **Ảnh hưởng tới TinyLLM:** khi kết quả trên board không khớp golden, cần đọc được bộ đệm trung gian để khoanh lỗi.
- **Đề xuất của TinyLLM:** dùng chung đường nạp nhanh ở mục A3 để đọc vùng dump.
- **Người quyết:** project architect.
- **Chặn:** đặc tả 10; chặng 8 của PLAN.

## 10. Thứ tự ưu tiên chốt

| Ưu tiên | Mục | Lý do |
| --- | --- | --- |
| Ngay | S1, S2, D1, M1, M2, A1, K1, R1, R2 | Quyết định thông số nền, số cổng DMA, layout DDR và các miền clock của đặc tả |
| Trước khi viết mục 9 của đặc tả | C1, C2, C3, C4, K2, A2, M3 | Quyết định giao diện điều khiển và mô hình lập trình |
| Trước chặng 4 đo đạc | M4, R3 | Cần để số đo có giá trị |
| Trước chặng 7 | S3, A3, V1, V2 | Ảnh hưởng tích hợp và demo, không đổi RTL TinyLLM |
