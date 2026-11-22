---
title: "Matmul engine OS-G: một mảng cho cả prefill và decode"
date: 2026-11-19
---

# Ý chính

- **OS-G** là mảng nhân–cộng *output-stationary* (mỗi ô giữ cố định một kết quả) gồm $M \times 64$ ô, mỗi ô là một khối DSP48E2, chia thành $G = 4$ nhóm hàng có thể nhận trọng số riêng.
- Khi sinh văn bản, **decode chiếm khoảng 93% thời gian** và bị giới hạn bởi tốc độ đọc trọng số từ DDR. OS-G cho prefill dùng chung trọng số trên cả mảng, còn decode biến 4 nhóm thành 4 engine nhân ma trận–vector ăn trọng số nhanh gấp 4 lần DDR, che được mọi lúc phải chờ.
- Đây là **đề xuất**: số học bám numerical contract v1; số thời gian và tài nguyên là ước tính, chưa có RTL.

Ký hiệu nguồn trong ghi chú: *contract §x* là mục của [numerical_contract_v1.md](../design/numerical_contract_v1.md) (đã kiểm chứng bằng phần mềm); *ước tính* là tính từ công thức ở mục 4; *kiến thức chung* là tài liệu FPGA hoặc bài báo.

# Trực giác: trọng số đi trên băng chuyền

## Engine tính gì

SmolLM2-135M xử lý văn bản theo từng **token** (mẩu chữ, khoảng một từ hoặc một phần từ). Gần như toàn bộ phép tính của model là nhân ma trận, tức rất nhiều phép **MAC** (nhân rồi cộng dồn). Matmul engine là khối phần cứng làm các phép này:

| Phép | Làm gì | Phía trọng số (8 bit) | Phía activation (12 bit) |
|------|------------------------|--------|------|
| Linear | Nhân vector token với ma trận trọng số; mỗi layer có Q/K/V/O và gate/up/down | W | A12 |
| LM head | Lớp cuối, biến trạng thái thành điểm cho 49.152 từ | W dùng chung với embedding | A12 |
| QK | Điểm liên quan giữa token hiện tại và các token trước, trong từng *head* (nhánh attention 64 chiều) | K cache | Q |
| PV | Cộng các vector V theo điểm liên quan vừa tính | V cache | $E$ (mục 3.5) |

: Bốn loại phép chạy trên engine. Cổng trọng số nhận số nguyên có dấu 8 bit (s8); cổng activation nhận số nguyên có dấu 12 bit (s12).

**KV cache** là nơi lưu K và V của các token trước để không phải tính lại. SmolLM2 có 9 head câu hỏi nhưng chỉ 3 head K/V: cứ 3 head câu hỏi dùng chung 1 head K/V, gọi là **GQA**.

## Hai giai đoạn: prefill và decode

**Prefill** là đọc toàn bộ câu hỏi (prompt) một lần; **decode** là sinh từng token tiếp theo. Hình dung **DDR** (bộ nhớ ngoài chip, lớn nhưng băng thông giới hạn) là một băng chuyền chở trọng số tới các bộ nhân:

|  | Prefill (prompt $T$ token) | Decode (sinh 1 token) |
|-----------|-------------|-------------|
| Mỗi trọng số được dùng | $T$ lần | 1 lần |
| Thứ thiếu | bộ nhân | tốc độ băng chuyền (DDR) |
| Dạng phép tính | GEMM: ma trận × ma trận | GEMV: ma trận × vector |
| Ví dụ (prompt 512, sinh 256) | $\approx$ 160 ms | $\approx$ 2.109 ms |

: Prefill và decode. Thời gian là ước tính, mảng 24 × 64, một kênh DDR4.

Vì decode quyết định thời gian, engine phải **giữ băng chuyền chạy liên tục**. Prefill chỉ cần đủ nhanh trong số DSP được phép dùng. Điều này đúng với LLM nói chung khi chạy một người dùng (batch 1). Bài HSA (ISLPED 2025) đo trên Jetson Orin Nano cũng thấy decode chiếm hơn 80% thời gian (kiến thức chung).

# Định nghĩa

## Bức tranh tổng thể

![Đường đi của dữ liệu. Xanh dương: trọng số và K/V (phía 8 bit); cam: activation (phía 12 bit); xanh lục: kết quả.](figures/os_g_overview.pdf)

- **Bộ đệm nạp trước** nhận trọng số từ DDR qua **DMA** (khối tự chép dữ liệu, không cần CPU điều khiển từng byte).
- **KV cache** đủ nhỏ để nằm trong **URAM** (bộ nhớ trên chip của FPGA, nhanh nhưng dung lượng có hạn): 5,625 MiB khi đủ 512 token (contract §13).
- **Khối hậu xử lý** làm các việc không phải nhân ma trận: *requant* (đổi kết quả sang cách biểu diễn của phép tiếp theo), softmax, RMSNorm (chuẩn hóa vector), SiLU (hàm kích hoạt), argmax (chọn token điểm cao nhất).

## Một ô (PE) và mảng output-stationary

Mảng ghép từ nhiều **PE** (phần tử xử lý). Mỗi PE dùng một khối **DSP48E2**: khối nhân–cộng cứng có sẵn trên FPGA UltraScale+, có bộ nhân 27 × 18 bit và thanh ghi cộng dồn 48 bit (kiến thức chung, AMD UG579). Mỗi chu kỳ, PE nhận trọng số $w$ từ trên, activation $a$ từ trái và cộng dồn tại chỗ:
$$S \leftarrow S + a \cdot w$$
Trọng số đi tiếp xuống ô dưới, activation đi tiếp sang ô phải. Bài toán được chia thành từng mảnh vừa với mảng, gọi là **tile**. Tính xong một tile, $S$ được chép sang **thanh ghi đệm** để xả ra ngoài, còn PE tính tile mới ngay.

Ghép PE thành lưới $M$ hàng × 64 cột: mỗi cột lo một đầu ra, mỗi hàng lo một token. Kiểu tổ chức này gọi là **output-stationary (OS)**: kết quả đứng yên trong ô, dữ liệu chảy qua. Vì vậy không cần bộ nhớ riêng để cất các tổng dở dang.

![(a) Một PE. (b) Prefill: 4 nhóm dùng chung một luồng trọng số, mọi ô làm việc. (c) Decode: mỗi nhóm nhận luồng trọng số riêng và tính một nhóm đầu ra riêng; chỉ hàng đầu của nhóm làm việc, các hàng khác được tắt xung nhịp (clock gating) để tiết kiệm điện. Hình thu nhỏ: 6 cột đại diện 64 cột, 8 hàng đại diện 24 hàng.](figures/os_g_array.pdf)

Chọn **64 cột** vì ba lý do. Một kênh DDR4 cấp khoảng 64 byte trọng số mỗi chu kỳ (mục 4). Mỗi head có 64 chiều. Mọi lớp Linear của SmolLM2 đều có số đầu ra là bội của 64 (576, 192, 1536, 49.152).

## Chữ G và cơ chế đuổi kịp

Nếu chỉ có lưới trên, decode chỉ có một token nên chỉ một hàng làm việc. Hàng đó ăn đúng 64 byte trọng số mỗi chu kỳ, bằng đúng tốc độ DDR. Chữ **G** giải quyết điều này: chia $M$ hàng thành $G = 4$ nhóm, mỗi nhóm có một **công tắc** (bộ chọn 2 đường) ở đầu.

- Khi prefill, công tắc nối nhóm với nhóm phía trên, nên cả mảng dùng chung trọng số.
- Khi decode, công tắc lấy luồng trọng số riêng từ bộ đệm. Mảng ăn được tới $G \times 64 = 256$ byte mỗi chu kỳ.

Trọng số không phụ thuộc kết quả tính, nên DMA **đọc trước** vào bộ đệm cả khi mảng đang bận việc khác (attention, chờ RMSNorm). Gọi $B$ là số byte DDR cấp mỗi chu kỳ và $t_w$ là số chu kỳ mảng phải chờ. DDR không bao giờ phải dừng nếu:
$$\text{dung lượng bộ đệm} \ge B \cdot t_w \quad\text{và}\quad G \cdot 64 > B$$
Khi đó thời gian một token decode $\approx W/B$, với $W$ là số byte trọng số. Với hai kênh DDR ($B \approx 130$), $G = 4$ vẫn cho dư gấp 2 lần.

![Một layer khi decode. (a) Mảng không nhanh hơn DDR: thời gian chờ attention cộng thẳng vào token. (b) Với G = 4: bộ đệm đầy lên lúc mảng chờ, sau đó mảng chạy 4× để đuổi kịp; DDR không ngừng.](figures/os_g_catchup.pdf){width=78%}

Thêm một mẹo đơn giản: trọng số được xếp sẵn trong DDR **đúng theo thứ tự mảng sẽ dùng**. Mỗi token decode khi đó chỉ là một lượt đọc tuần tự dài, kiểu truy cập DDR đạt tốc độ cao nhất.

## Attention trên OS-G

Khi decode, mỗi phép QK chỉ có 3 hàng câu hỏi (3 head dùng chung một head K/V). Một nhóm chỉ cần 3 hàng, nên 4 nhóm cùng lúc xử lý 4 khối key khác nhau. PV làm tương tự: 4 nhóm chia nhau các key, cuối cùng cộng 4 tổng lúc xả.

![QK khi decode: 4 nhóm cùng lúc xử lý 4 khối 64 key khác nhau, rồi chuyển sang 4 khối tiếp theo. Trong mỗi nhóm, 3 hàng là 3 head câu hỏi dùng chung key.](figures/os_g_attention.pdf)

Khi prefill, hàng là các cặp (token, head câu hỏi), cột là 64 key (QK) hoặc 64 chiều (PV). **Causal mask** quy định mỗi token chỉ được nhìn các token trước nó. Vì vậy khối key nằm hoàn toàn sau mọi token trong tile được bỏ qua hẳn.

Để mảng đọc nhanh, K được lưu theo từng chiều trong mỗi khối 64 key, còn V lưu theo từng token. Thêm một token mới vào K cache là 64 lần ghi một byte. URAM cho phép ghi từng byte, nên việc này không tốn đáng kể.

## Softmax ghép vào PV

**Softmax** biến các điểm QK của một hàng thành xác suất có tổng bằng 1. Contract v1 chuẩn hóa từng xác suất thành mã 12 bit (P12, contract §8.3) rồi mới tính PV. Đề xuất thay bằng:

1. Đưa thẳng giá trị mũ $E_l \in [0, 255]$ (tra từ bảng 32 mục có sẵn, contract §8.2) vào hàng của mảng.
2. Cộng $S = \sum_l E_l$ song song.
3. Chỉ chia một lần cho mỗi hàng:
$$\text{out}_d = \frac{1}{S}\sum_l E_l \, V_{l,d}$$

![Softmax nằm ở đầu vào hàng của mảng khi tính PV. Không còn bước chia riêng cho từng key.](figures/os_g_softmax.pdf)

Max của hàng vẫn phải biết trước khi tra bảng mũ. Vì vậy điểm QK của một khối hàng được giữ trong bộ đệm, max tính trong lúc xả QK, rồi mới chạy PV.

# Ví dụ số tự kiểm tra

Giả định: xung nhịp 250 MHz; một kênh DDR4-2400 64 bit (19,2 GB/s đỉnh) đạt 85% khi đọc tuần tự. Board VCU118 có hai kênh như vậy (kiến thức chung). Các số dưới đây là **ước tính từ công thức**, không phải số đo.

| Đại lượng | Phép tính | Kết quả |
|---------|---------------|-------------|
| Byte trọng số mỗi token | $30(2 \cdot 576^2 + 2 \cdot 192 \cdot 576 + 3 \cdot 1536 \cdot 576) + 49152 \cdot 576$ | 134.479.872 (khớp contract §13) |
| Byte DDR mỗi chu kỳ $B$ | $19{,}2 \cdot 10^9 \cdot 0{,}85 \,/\, 250 \cdot 10^6$ | $\approx$ 65 với 1 kênh, $\approx$ 130 với 2 kênh |
| Một token decode | $134{,}48 \cdot 10^6 \,/\, 16{,}32 \cdot 10^9$ | $\approx$ 8,24 ms ($\approx$ 121 token/s); 2 kênh: $\approx$ 4,12 ms |
| Prefill 512 token | $\big(512 \cdot 106{,}17\text{M} + 28{,}3\text{M} + 4{,}54\text{G}\big) / (1536 \cdot 250\text{M})$ | 58,9 G MAC; $M = 24$: $\approx$ 153 ms lý tưởng, $\approx$ 160 ms khi tính tile lẻ; $M = 48$: $\approx$ 81 ms |
| Tổng lớn nhất của Linear | $1536 \cdot 2048 \cdot 128$ | $402.653.184 < 2^{31}$, 32 bit đủ (contract §4.1) |
| Chờ attention mỗi layer, $L = 512$ | QK $3 \cdot 2 \cdot 64$ + PV $3 \cdot 128$ + $\approx$ 300 (phi tuyến, giả định) | $\approx$ 1.068 chu kỳ; bộ đệm $\approx$ 68 KiB (1 kênh), $\approx$ 136 KiB (2 kênh) |
| Phần LM head trong decode | $28.311.552 \,/\, 134.479.872$ | 21% byte đọc mỗi token |

: Các số định cỡ. 4,54 G là MAC attention: $30 \cdot 9 \cdot 64 \cdot 2 \cdot \tfrac{512 \cdot 513}{2}$; LM head chỉ tính cho token cuối của prompt.

# Áp dụng trong dự án

## Ánh xạ từng phép

| Phép | Prefill | Decode |
|--------|------------------|------------------|
| Linear, LM head | Hàng = token; cột = 64 đầu ra; trọng số dùng lại qua $M$ token | 4 nhóm × 1 hàng tính 4 tile đầu ra cùng lúc |
| QK ($K = 64$) | Hàng = cặp (token, head câu hỏi); cột = 64 key; bỏ khối key bị causal mask che hết | 3 hàng = 3 head câu hỏi; 4 nhóm lấy 4 khối 64 key |
| PV ($K = L$) | Hàng như QK; cột = 64 chiều; $E$ vào ở đầu hàng | 4 nhóm chia key, cộng 4 tổng lúc xả |

: Ánh xạ phép tính lên mảng OS-G. $K$ là số phép cộng dồn cho mỗi kết quả; $L$ là số token đã có trong KV cache.

Hình vẽ dữ liệu vào/ra mảng cho từng phép, cả prefill và decode, nằm ở ghi chú đi kèm [os_g_dataflow.pdf](os_g_dataflow.pdf).

## Số học và scale

**Scale** là hệ số đổi mã số nguyên về giá trị thật: giá trị $\approx$ scale × mã. Số học của engine bám contract v1. Phần mềm tham chiếu là `quantize/ptq_contract_runtime.py`; RTL phải khớp nó từng bit.

| Thành phần | Quy định | Nguồn |
|--------|--------------------|----------|
| Cổng trọng số | s8: W, K, V | contract §3, §5 |
| Cổng activation | s12: A12; Q 8 bit mở rộng dấu; $E$ 8 bit mở rộng số 0 | contract §3, §8; $E$ là đề xuất |
| Tổng cộng dồn | 32 bit bên ngoài, 48 bit trong DSP | contract §4.1 |
| Scale trọng số | mỗi hàng W một scale | contract §3 |
| Scale activation | một scale cho cả tensor, sau SmoothQuant | contract §3, §4.2 |
| Scale Q, K, V | mỗi head một scale | contract §5, §8 |
| Chuẩn hóa softmax | $1/S$ theo hàng, sau PV | đề xuất |

: Số học dùng trong engine. SmoothQuant: chuyển bớt độ lớn bất thường của activation sang trọng số bằng hệ số theo từng kênh, làm trên host trước khi lượng tử hóa.

Mọi scale ở bảng trên đều nhân vào **sau khi đã cộng xong**: theo cột (W) hoặc theo hàng (head, $1/S$) khi xả kết quả. Vì vậy trong mảng không cần mạch scale nào. Scale thay đổi *trong lúc đang cộng* (ví dụ mỗi nhóm 64 kênh activation một scale) mới cần thêm mạch.

## Kích thước khởi đầu

| Thông số | Giá trị | Ghi chú |
|------------|--------------|--------------------|
| Số cột $N$ | 64 | Bằng byte DDR mỗi chu kỳ (1 kênh); bằng số chiều mỗi head |
| Số nhóm $G$ | 4 | Decode ăn tới 256 B/chu kỳ: gấp 4 lần 1 kênh, gấp 2 lần 2 kênh |
| Số hàng $M$ | 24, mở rộng 48 | 1.536 DSP ($\approx$ 22% của 6.840 DSP trên XCVU9P) hoặc 3.072 ($\approx$ 45%) |
| Xung nhịp | 250 MHz (mục tiêu) | Cần tổng hợp mạch để xác nhận |
| Bộ đệm nạp trước | 256 KiB | Tối thiểu $\approx$ 68 KiB (1 kênh), $\approx$ 136 KiB (2 kênh) |
| Thanh ghi đệm | $\approx$ 50K FF, $\approx$ 25K LUT ($M = 24$) | 32 FF và bộ chọn cho mỗi PE; FF, LUT là tài nguyên logic của FPGA |
| KV cache | 5,625 MiB, $\approx$ 160 khối URAM | Dung lượng KV: contract §13; mỗi khối URAM 36 KiB (kiến thức chung) |

: Kích thước đề xuất (ước tính).

## Hai đòn bẩy cấp SoC

Hai lựa chọn sau ảnh hưởng tốc độ decode nhiều hơn mọi chi tiết bên trong engine. Chúng cần thống nhất với kiến trúc sư SoC vì liên quan bộ nhớ dùng chung với RISC-V và Dilithium.

- **Dùng cả hai kênh DDR4** của VCU118: decode nhanh gấp đôi ($\approx$ 4,12 ms/token). Với $G = 4$, engine vẫn đủ nhanh để đuổi kịp.
- **Giữ LM head trên chip:** LM head chiếm 21% byte đọc mỗi token. Giữ toàn bộ cần $\approx$ 27 MiB, khoảng 80% URAM của XCVU9P (33,75 MiB). Cộng với KV cache thì gần hết URAM, nên khó làm trọn vẹn. Giữ một phần thì lợi tương ứng; giữ toàn bộ thì decode còn $\approx$ 6,5 ms/token.

# Bẫy thường gặp

- **"Decode bị DDR giới hạn nên một hàng là đủ."** Một hàng chỉ ăn đúng bằng tốc độ DDR nên không bù được lúc chờ. Theo ước tính, ở $L = 512$ attention cộng thêm $\approx$ 4,5% thời gian mỗi token; với $G = 4$ còn $\approx$ 1,1% và được che.
- **"Prefill luôn bị giới hạn bởi tính toán."** Prompt không dài hơn $M$ token (24 với $M = 24$) chỉ chiếm một tile hàng, nên vẫn bị DDR giới hạn. Nó tốn xấp xỉ thời gian một token decode. LM head trong prefill chỉ tính cho token cuối nên cũng là GEMV.
- **"Mọi chiều ra là bội của 64."** Đúng với Linear và PV; sai với QK (số key $L$ từ 1 đến 512) và với số token. Cần mặt nạ cho tile lẻ.
- **"Bỏ thanh ghi đệm cho đỡ tốn."** QK chỉ cộng 64 số mỗi tile. Nếu xả trực tiếp, mảng phải dừng khoảng 27% ($M = 24$) đến 43% ($M = 48$) thời gian QK.
- **"Softmax online kiểu FlashAttention cũng tương đương."** Cách đó cập nhật max dần qua từng khối key, làm đổi thứ tự làm tròn so với contract. Ở đây giữ max của cả hàng.
- **"Ghép 2 MAC INT8 vào một DSP như FlightLLM sẽ tăng tốc decode."** FlightLLM dùng chung trọng số cho 2 token (FlightLLM §3.2.1), nên chỉ có lợi ở prefill.
- **"Đổi P12 sang $E$ hay P11 chỉ là việc phần cứng."** Đó là thay đổi contract; phải đo lại chất lượng.

# Lý do chọn kiến trúc này

## Bốn yêu cầu từ bài toán

1. Decode quyết định thời gian và bị DDR giới hạn: engine phải giữ DDR đọc liên tục, kể cả trong lúc làm attention và các khối phi tuyến.
2. Prefill cần dùng lại trọng số qua nhiều token với ít bộ nhớ trung gian, để đỡ tốn điện và bộ nhớ trên chip.
3. Attention có hình dạng lạ: QK chỉ cộng 64 số; decode chỉ có 3 hàng câu hỏi; số key bất kỳ từ 1 đến 512.
4. Phải làm được trên VU9P với rủi ro thấp và khớp từng bit với contract số nguyên.

## So sánh với các phương án khác

|  | OS thuần | WS R×64 | SPECTRA | **OS-G** |
|----------|--------|----------|--------|--------|
| GEMV khi decode | bằng DDR, không đuổi kịp | nhanh nếu bộ đệm đủ | cả mảng | 4 lần DDR |
| Attention decode, $L = 512$ | +4,5%, không che | nhanh | nhanh | $\approx$ 1,1%, che được |
| Bộ nhớ tổng dở dang khi prefill | không cần | đọc–ghi mỗi chu kỳ ($\approx$ 3× lưu lượng SRAM) | như OS | như OS |
| Scale theo nhóm 64 kênh | chỉ lũy thừa 2 | tự nhiên | — | chỉ lũy thừa 2 |
| Chi phí cho tính linh hoạt | không | không | +82% LUT, +79% FF | 3 bộ chọn, cổng đọc rộng hơn |

: So sánh. Số của OS thuần, WS và OS-G là ước tính; số của SPECTRA lấy từ Bảng 2 của bài (`docs/papers/SPECTRA ... .pdf`).

- **OS thuần** chỉ thiếu khả năng đuổi kịp. OS-G giữ mọi ưu điểm của nó (không cần bộ nhớ tổng dở dang, dùng DSP tự nhiên, dễ khớp bit) và thêm đúng khả năng đó bằng 3 bộ chọn.
- **WS R×64** (*weight-stationary*: mỗi hàng giữ cố định 64 trọng số và tính một tích vô hướng 64 làn) mạnh ở QK và ở scale theo nhóm. Nhưng nó phải đọc–ghi tổng dở dang liên tục khi prefill và cần lưu V theo dạng chuyển vị. Với cách chia scale đã chọn, ưu điểm scale theo nhóm không được dùng tới.
- **SPECTRA** (ICCAD 2026) cho cả mảng làm GEMV, điều thừa khi DDR chỉ cấp khoảng 64 byte mỗi chu kỳ. OS-G lấy đúng mức linh hoạt cần thiết với chi phí nhỏ hơn nhiều.
- Tiền lệ gần nhất là **HSA** (ISLPED 2025, `docs/papers/Hybrid Systolic Array ... .pdf`): mảng OS cho prefill, tách cụm cho decode, thêm 0,4% diện tích. Điều này cho thấy hướng đi khả thi. Nó cũng có nghĩa OS-G chỉ mới ở mức vừa phải: đóng góp phải đến từ cơ chế đuổi kịp, ánh xạ attention GQA và số đo thật trên DDR4.

## Vì sao giữ A12 và một scale cho cả tensor

**Lượng tử hóa** là biểu diễn số thực bằng số nguyên ít bit; A12 và A8 nghĩa là activation 12 hoặc 8 bit. Bảng dưới là mức tăng **PPL** (perplexity: độ "bối rối" của model khi đoán token, thấp hơn là tốt hơn) so với FP32. Số đo bằng **fake-quant** (mô phỏng lượng tử hóa bằng số thực), trên 64 cửa sổ của tập *selection*, tập dùng để chọn phương án. Tập *heldout* dành cho kiểm tra cuối chưa được dùng. Ngưỡng của dự án là tăng không quá 5%.

| Cách lượng tử activation ở đầu vào Linear | PPL tăng | Áp scale trong mảng OS | Nguồn |
|------------------|-----|----------------|----|
| A12, một scale + SmoothQuant (v1) | +0,82% | miễn phí | [a] |
| A8, nhóm 64 kênh động + SmoothQuant | +0,60% | cần tổng riêng mỗi nhóm nhân scale | (\*) |
| A8, nhóm 64 động, scale lũy thừa 2 + SmoothQuant (kiểu MX) | +1,16% | dịch toán hạng ở đầu hàng; toán hạng rộng nên không ghép DSP | (\*) |
| A8, mỗi token động + SmoothQuant | +2,11% | hệ số theo hàng khi xả; ghép 2 MAC/DSP được | (\*) |
| A8, mỗi kênh tĩnh | +2,40% | không tách khỏi tổng | [a] |
| A8, mỗi kênh lũy thừa 2, tối đa 8 mức (kiểu Tender) | +3,75% | dịch toán hạng ở đầu hàng | (\*) |
| A8, một scale + SmoothQuant ($\alpha = 0{,}9$) | +6,13% | miễn phí; ghép được | [a] |
| A8, mỗi token động, không SmoothQuant | +7,44% | hệ số theo hàng khi xả | [b] |

: Lựa chọn activation. [a] `quantize/reports/ptq_a_extensions.md`; [b] `quantize/reports/ptq_stage3.md`; (\*) sàng lọc bổ sung ngày 17-11-2026 bằng adapter fake-quant của repo, script và kết quả chưa lưu trong repo. Kiểu MX: một nhóm phần tử dùng chung một số mũ lũy thừa 2. Kiểu Tender (ISCA 2024): chia kênh thành nhóm có scale cách nhau lũy thừa 2.

- **12 bit không phải do chất lượng bắt buộc**: A8 theo nhóm 64 kênh, scale động, cộng SmoothQuant còn nhỉnh hơn A12.
- **Trên DSP48E2, A8 không làm giảm số DSP**: nhân 8 × 8 hay 12 × 8 đều tốn đúng một khối DSP. A8 chỉ có lợi khi ghép được 2 phép nhân vào một DSP. Cách ghép là đặt hai số 8 bit vào cổng 27 bit, cách nhau 18–19 bit, nhân với một toán hạng chung. Phần thấp chỉ cộng được khoảng 7–15 tích trước khi tràn, nên phải tách tổng ra ngoài định kỳ (kiến thức chung; FlightLLM gọi khối này là Overflow Adjust Unit).
- **Các kiểu A8 ghép được trong mảng OS** là một scale hoặc theo token. Kiểu tốt nhất trong số đó là theo token (+2,11%), quá sát ngưỡng 5% khi contract số nguyên v1 đã dùng khoảng 3,9% (contract §14.4).
- **Dịch bit trong DSP không miễn phí về chất lượng**: hai kiểu dùng scale lũy thừa 2 (MX, Tender) đều kém hơn kiểu scale tự do tương ứng.
- **Kết luận**: A12 một scale là điểm rẻ nhất trên FPGA (không mạch scale, không đổi số DSP, chất lượng tốt). Cặp "A8 nhóm 64 + WS" để dành nếu sau này chuyển sang ASIC hoặc nếu DSP trở thành giới hạn.

## Vì sao không giảm softmax xuống P11

- **Không cần**: cổng A của DSP rộng 27 bit, nên giữ 12 bit cho xác suất cũng không tốn thêm DSP.
- **Có cách tốt hơn**: đưa $E$ (8 bit) thẳng vào PV và chia $S$ một lần mỗi hàng (mục 3.5). Số phép chuẩn hóa giảm 8 lần: từ $9 \cdot 512 \cdot 512 = 2.359.296$ xuống $9 \cdot 512 \cdot 64 = 294.912$ mỗi layer (contract §14.5). Ngoài ra bớt được một lần làm tròn.
- **Cần kiểm chứng riêng**: phương án `combined_guarded_fused` từng có softmax ghép nhưng trượt PPL, vì đổi đồng thời RMSNorm, RoPE, SiLU và nhiều độ rộng khác. Phần softmax ghép chưa từng được đo riêng.

## Chưa được chứng minh và việc tiếp theo

Chưa được chứng minh:

- Chưa có RTL và tổng hợp mạch: chưa biết đạt 250 MHz không, chưa có số FF/LUT thật. Khi $M = 48$, mảng phải trải qua 2 **SLR** (XCVU9P gồm 3 lát silicon ghép lại; tín hiệu qua ranh giới lát chậm hơn).
- Băng thông DDR4 thực trên VCU118 chưa đo.
- Ngân sách DSP/URAM của TinyLLM trong SoC chưa thống nhất.
- Các số chất lượng là fake-quant; contract số nguyên sẽ cộng thêm sai số.

Việc tiếp theo:

1. Đo băng thông DDR4 duy trì trên VCU118 (đọc tuần tự khối lớn qua MIG, bộ điều khiển DDR của AMD).
2. Thử contract chỉ đổi softmax sang $E$ ghép, trên ứng viên `combined_min_1pct_residual16_m16`.
3. Viết RTL một nhóm (6 × 64 PE, có xả kết quả và requant), tổng hợp ở 250 MHz, so với một kernel WS-64 cùng số DSP làm đối chứng.
4. Thống nhất ngân sách DSP/URAM và số kênh DDR với kiến trúc sư SoC.
