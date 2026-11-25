# Sườn đặc tả chi tiết TinyLLM accelerator

Ngày: 25-11-2026. Trạng thái: sườn để viết đặc tả theo [D04](../DECISIONS.md#d04-hoàn-thành-đặc-tả-thiết-kế-trước-khi-viết-rtl-đầy-đủ); chưa chứa quyết định thiết kế. Mỗi mục liệt kê những gì đặc tả phải nêu để golden số học và RTL được hiện thực mà không phải suy đoán. Các nội dung cần thống nhất với phần còn lại của SoC nằm trong [soc_integration_items.md](soc_integration_items.md).

## Nguyên tắc viết đặc tả

- **Chỉ ghi nội dung đã quyết.** Câu hỏi còn mở và phương án đang cân nhắc để ở ghi chú riêng. Người đọc được coi mọi thứ trong đặc tả là đã chốt.
- **Số học chỉ được tham chiếu, không chép lại.** Rounding, saturation, độ rộng logic và scale lấy từ numerical contract theo số mục (ví dụ "contract §4.2"). Đặc tả chỉ thêm những gì contract không quy định: độ rộng thanh ghi, container, thứ tự, thời điểm.
- **Mỗi thông số có đúng một nơi định nghĩa**, trong bảng thông số ở mục 2. Các mục khác gọi theo tên.
- **Hành vi được nêu theo chu kỳ khi nó ảnh hưởng giao diện:** độ trễ, throughput, thứ tự dữ liệu, điều kiện dừng, giá trị khi reset.
- **Mọi trường hợp biên được nêu rõ**, kể cả hành vi khi đầu vào sai.
- **Có ví dụ số** cho mỗi công thức địa chỉ và mỗi lịch thực thi.

## Đối chiếu các vấn đề thiết kế với mục

| Vấn đề | Mục |
| --- | --- |
| Chuyển vị ma trận, cách lưu dữ liệu, sinh địa chỉ | 5.4, 5.5 |
| Bộ nhớ đệm, bộ nhớ nội bộ, DDR và cách vận chuyển | 5.1–5.3, 7.1 |
| Hạn chế đọc ghi bộ nhớ, tính on-the-fly | 6.3, 6.5 |
| Thứ tự tính ma trận và hàm phi tuyến | 6.1–6.3 |
| Phối hợp nhân ma trận và phi tuyến | 6.3, 6.4, 7.5–7.11 |
| Bộ điều phối trung tâm | 8 |
| DMA | 7.1, 7.2, 9.1 |
| Kích thước bộ nhớ nội bộ | 5.3 |
| Phối hợp với CPU, Dilithium, chia DDR4 | 9, [soc_integration_items.md](soc_integration_items.md) |

---

## 1. Phạm vi và căn cứ

### 1.1. Phạm vi

- Model, revision, batch, context tối đa, prefill và decode, cách chọn token.
- Những gì nằm ngoài phạm vi: tokenizer, vòng sinh token, sampling khác greedy, nhiều chuỗi đồng thời.
- Phiên bản numerical contract mà đặc tả bám theo.

### 1.2. Tài liệu căn cứ và thứ tự ưu tiên

- Danh sách tài liệu: numerical contract, PLAN, DECISIONS, system-level contract trong `docs/architecture/`.
- Quy tắc khi mâu thuẫn: số học theo contract, giao diện hệ thống theo system-level contract, còn lại theo đặc tả này.

### 1.3. Thuật ngữ và ký hiệu

- Ký hiệu chỉ số: `T`, `L`, `L_prev`, `t`, `h`, `g`, `d`, `k`, `o`, `l`, layer.
- Các thuật ngữ phần cứng: tile, nhóm, drain, beat, burst, descriptor, bank.
- Quy ước bit/byte: thứ tự bit, endianness, cách đánh số lane, cách viết hằng số.
- Quy ước đặt tên tín hiệu, module, tham số.

## 2. Thông số hệ thống

### 2.1. Thông số model

Bảng gồm tên, giá trị SmolLM2-135M, miền hợp lệ, và loại thông số: tham số synthesis hay dữ liệu cấu hình lúc chạy. Các thông số: số layer, hidden size, FFN size, số query head, số KV head, head dim, vocabulary, context tối đa.

### 2.2. Thông số phần cứng

Bảng gồm tên, giá trị mặc định, miền hợp lệ, ràng buộc giữa các thông số. Các thông số:

- Mảng: `M`, `N`, `G`; độ rộng cổng trọng số và cổng activation; độ rộng accumulator.
- Clock: tần số mục tiêu của từng miền clock.
- DMA: số cổng, độ rộng dữ liệu, độ dài burst tối đa, số yêu cầu chờ tối đa.
- Bộ nhớ: dung lượng của từng bộ nhớ ở mục 5.3.

### 2.3. Mục tiêu và ngân sách

- Mục tiêu: thời gian prefill theo T, thời gian mỗi token decode theo L.
- Ngân sách DSP, URAM, BRAM, LUT, FF; ngân sách băng thông DDR.
- Căn cứ của từng con số: số đo (kèm đường dẫn kết quả) hay ước tính (kèm công thức).

## 3. Kiến trúc tổng thể

### 3.1. Sơ đồ khối

- Sơ đồ top-level với mọi khối ở mục 7 và mọi kết nối.
- Mỗi kết nối ghi độ rộng và loại giao diện theo mục 4.

### 3.2. Ánh xạ phép toán vào khối

Bảng từng phép của luồng suy luận (embedding → 30 layer → final norm → LM head → argmax) với khối thực hiện, nguồn dữ liệu và đích dữ liệu. Có bảng riêng cho prefill và decode.

### 3.3. Miền clock và reset

- Danh sách miền clock, nguồn clock, tần số.
- Mọi điểm CDC: vị trí, cơ chế (FIFO bất đồng bộ, đồng bộ hai tầng), độ sâu.
- Cây reset: nguồn, cực tính, đồng bộ hay bất đồng bộ, thứ tự nhả reset; reset mềm qua thanh ghi.

### 3.4. Data plane và control plane

Tách rõ đường dữ liệu tính toán và đường lệnh, trạng thái, cấu hình.

## 4. Quy ước giao diện chung

Áp dụng cho mọi giao diện giữa các khối, trừ khi khối nêu ngoại lệ.

### 4.1. Giao diện stream

- Tín hiệu: `valid`, `ready`, payload, các cờ khung như `first`/`last` và đánh dấu biên tile.
- Quy tắc handshake: điều kiện truyền, payload phải giữ ổn định khi chờ, `valid` không được phụ thuộc `ready`, có hay không đường tổ hợp từ `ready` sang `ready`.
- Cách đóng gói phần tử vào payload: thứ tự lane, sign extension, container so với độ rộng logic.

### 4.2. Giao diện lệnh và cấu hình của khối

- Tín hiệu `start`, `busy`, `done`; thời điểm chốt cấu hình.
- Cấu hình nào được đổi giữa hai lệnh, cấu hình nào cố định trong một lượt suy luận.

### 4.3. Báo lỗi

- Danh sách mã lỗi, khối phát hiện, cách truyền về bộ điều phối.
- Lỗi nào dừng toàn bộ, lỗi nào chỉ ghi nhận.
- Assertion cho các cận overflow mà contract coi là lỗi hiện thực (contract §2.2): vị trí, chỉ dùng khi mô phỏng hay giữ cả trong phần cứng.

### 4.4. Reset và clock gating

- Chính sách reset: những thanh ghi nào được reset, payload có được reset hay không.
- Clock gating: điều kiện, cách hiện thực trên FPGA.

## 5. Bộ nhớ và dữ liệu

### 5.1. Vùng nhớ của TinyLLM trong DDR

Bảng từng vùng với tên, offset so với base, kích thước, căn lề, ai ghi, ai đọc, khi nào. Gồm: trọng số, hệ số, LUT/ROM, vùng vào/ra (token, kết quả), vùng scratch nếu có, vùng dump gỡ lỗi. Base address lấy từ memory map của SoC.

### 5.2. Định dạng đóng gói phần cứng

- Header: magic, version định dạng, version contract, kích thước model, offset từng vùng, checksum.
- Layout trọng số theo đúng thứ tự mảng tiêu thụ: thứ tự tile, thứ tự byte trong một beat, cách chia cho nhiều cổng DMA hoặc nhiều kênh DDR, padding.
- Cách đọc một hàng embedding từ layout của LM head (dùng chung một bộ trọng số, contract §3, §11).
- Layout hệ số đi kèm tile: M/shift theo hàng ra, hệ số theo kênh vào; xen kẽ với trọng số hay để vùng riêng.
- Quy tắc ánh xạ từ định dạng trao đổi của contract §12 sang định dạng này. Đặc tả công cụ đóng gói trên host: đầu vào, đầu ra, kiểm tra.

### 5.3. Danh sách bộ nhớ trên chip

Bảng mỗi bộ nhớ gồm: tên, nội dung, loại tài nguyên (URAM/BRAM/LUTRAM/FF), dung lượng, độ rộng word, số bank, số cổng, ai ghi và ai đọc, số phần tử đọc/ghi mỗi chu kỳ. Dòng cuối là tổng so với ngân sách ở mục 2.3. Gồm ít nhất:

- Bộ đệm nạp trước trọng số.
- Bộ đệm activation và residual; bộ đệm FFN hidden.
- Bộ đệm Q cho attention; bộ đệm score.
- KV cache.
- Bộ nhớ hệ số, LUT, ROM RoPE.
- Bộ đệm vào/ra và bộ đệm dump.

### 5.4. Layout của từng bộ nhớ

Với mỗi bộ nhớ ở 5.3: công thức địa chỉ từ chỉ số logic (layer, head, token, kênh) sang (bank, word, lane), kèm ví dụ số. Các điểm phải có:

- Bộ đệm activation: cách chia bank để mỗi chu kỳ đọc được cùng một kênh của nhiều token.
- K cache (chuyển vị theo khối key) và V cache (theo token); cách chia bank để các nhóm của mảng đọc đồng thời trong decode.
- Bộ đệm Q: đọc theo hàng (token, head) cho attention prefill.
- Bộ đệm score: kích thước cho trường hợp xấu nhất (L = 512, prefill).

### 5.5. Chuyển vị và sinh địa chỉ

- Liệt kê mọi điểm dữ liệu được ghi theo một thứ tự rồi đọc theo thứ tự khác: drain → activation, drain K → K cache, drain Q → bộ đệm Q, và các điểm khác nếu có.
- Với mỗi điểm: cơ chế (chia bank, bộ đệm chuyển vị, ghi theo byte), dung lượng, throughput và độ trễ thêm vào.
- Bộ sinh địa chỉ của từng khối: các vòng lặp, bước nhảy, điều kiện kết thúc.

### 5.6. Xung đột cổng và bank

Với mỗi bộ nhớ có nhiều bên truy cập: chứng minh không xung đột theo lịch ở mục 6, hoặc nêu cơ chế phân xử và chi phí chu kỳ.

## 6. Lịch thực thi

### 6.1. Prefill

- Thứ tự vòng lặp: layer, phép, tile token, tile đầu ra.
- Lưu lượng DDR và dung lượng bộ nhớ trên chip tương ứng với thứ tự đã chọn.

### 6.2. Decode

- Thứ tự vòng lặp; cách chia việc cho các nhóm của mảng theo từng loại phép.

### 6.3. Gộp phép và điểm chắn

Bảng mỗi cặp phép liên tiếp (nhà sản xuất → nơi tiêu thụ) gồm:

- Cách nối: gộp ngay khi drain, gộp ở cạnh vào của mảng, qua bộ đệm trên chip, hay qua DDR.
- Có phải chờ đủ dữ liệu không (barrier), và chờ dữ liệu gì.
- Bộ đệm cần dùng.

Gồm ít nhất: RMSNorm (cần đủ tổng bình phương), RoPE trên Q/K, ghi KV cache, QK → max → softmax → PV, chuẩn hóa sau PV, ghép head → O, cộng residual, gate/up → SiLU·up → down, final norm → LM head → argmax.

### 6.4. Phụ thuộc dữ liệu và đồng bộ

- Mọi phụ thuộc giữa các bước. Ví dụ: K/V của token hiện tại đã ghi vào cache trước khi QK đọc; max của hàng đã có trước khi tính mũ.
- Cơ chế bảo đảm từng phụ thuộc (theo lịch tĩnh hay theo tín hiệu báo).

### 6.5. Chồng lấp tính toán và truyền dữ liệu

- Nạp trước, double buffering.
- Timeline một layer trong prefill và trong decode, ghi rõ khối nào bận ở chu kỳ nào.
- Khoảng dừng DDR tối đa mà thiết kế chịu được mà không làm chậm decode.

### 6.6. Trường hợp biên

T = 1; T không chia hết cho kích thước tile; `L_prev = 0`; `L_prev + T = 512`; L quanh bội số kích thước khối key; khối causal nằm trên đường chéo; decode ngay sau prefill. Ghi hành vi của từng trường hợp.

### 6.7. Mô hình hiệu năng

Công thức số chu kỳ và lưu lượng DDR theo T, L và các thông số phần cứng. Kết quả cho các điểm tham chiếu đã chọn.

## 7. Đặc tả từng khối

### 7.0. Mẫu cho mỗi khối

Mỗi khối dùng đủ các mục sau:

1. **Chức năng:** khối làm gì, nằm ở đâu trong lịch.
2. **Tham số:** tham số synthesis và cấu hình lúc chạy.
3. **Port:** bảng gồm tên, hướng, độ rộng, miền clock, giao diện theo mục 4, ý nghĩa.
4. **Thứ tự dữ liệu vào/ra:** phần tử nào đến ở beat nào; biên tile và biên hàng được đánh dấu thế nào.
5. **Timing:** độ trễ, throughput, khả năng nhận backpressure, số chu kỳ cho mỗi lệnh.
6. **Hành vi:** các bước tính, FSM với trạng thái và điều kiện chuyển.
7. **Số học:** tham chiếu mục contract; độ rộng mọi thanh ghi trung gian.
8. **Trường hợp biên và lỗi.**
9. **Tài nguyên ước tính.**
10. **Điểm so với golden:** tên boundary trong `config.formats` tương ứng với từng đầu ra.
11. **Kiểm tra bắt buộc:** danh sách tình huống test của khối.

### 7.1. DMA đọc và bộ đệm nạp trước trọng số

### 7.2. DMA khác: vào/ra, nạp hệ số/LUT, dump gỡ lỗi

### 7.3. Matmul engine

Gồm PE, mảng, bộ chọn nhóm, skew ở cạnh vào, thanh ghi drain, mask tile lẻ.

### 7.4. Khối nạp cạnh trái của mảng

Đọc activation, Q hoặc E theo thứ tự mảng cần; nhân hệ số theo kênh nếu lịch yêu cầu.

### 7.5. Drain và requantization

### 7.6. Cộng residual

### 7.7. RMSNorm

### 7.8. RoPE

### 7.9. Bộ điều khiển KV cache

### 7.10. Attention: score, max, softmax, chuẩn hóa sau PV

### 7.11. SiLU và tích gate·up

### 7.12. Embedding

### 7.13. LM head và argmax

### 7.14. Bộ nhớ hệ số, LUT và ROM

### 7.15. Khối thanh ghi điều khiển

### 7.16. Bộ đếm hiệu năng và gỡ lỗi

## 8. Bộ điều phối

### 8.1. Mô hình điều khiển

FSM cứng hay chương trình lệnh; phần nào cố định trong phần cứng, phần nào là dữ liệu.

### 8.2. Định dạng lệnh hoặc descriptor

Bảng trường gồm tên, vị trí bit, độ rộng, ý nghĩa, giá trị hợp lệ. Nguồn lệnh: ROM, bộ nhớ nạp từ DDR, hay sinh từ thanh ghi.

### 8.3. Chuỗi lệnh

Chuỗi lệnh cho một layer, cho prefill T token và cho một lượt decode, kèm ví dụ đầy đủ cho một layer.

### 8.4. Đồng bộ giữa các khối

Scoreboard, semaphore hoặc lịch tĩnh; cách bộ điều phối biết khối đã xong.

### 8.5. Lỗi, hủy, timeout

Hành vi khi gặp lỗi; trạng thái sau khi hủy; điều kiện để chạy lại.

### 8.6. Thông số model dưới dạng dữ liệu

Cách nạp và kiểm tra thông số model; chỗ nào trong RTL còn giả định cố định (ví dụ head dim = 64).

## 9. Giao diện ngoài và mô hình lập trình

Phần TinyLLM tự quyết của các giao diện với SoC. Phần thống nhất với SoC nằm trong `docs/architecture/`, đầu vào lấy từ [soc_integration_items.md](soc_integration_items.md).

### 9.1. Cổng DDR master

Giao thức, độ rộng, độ dài burst, số yêu cầu chờ, thuộc tính QoS/cache/prot, hành vi khi nhận lỗi bus.

### 9.2. Cổng điều khiển

- Giao thức, độ rộng, độ trễ phản hồi.
- Bản đồ thanh ghi: offset, tên, quyền truy cập, giá trị reset, các trường, tác dụng phụ khi đọc/ghi.

### 9.3. Báo hoàn tất

Bit trạng thái để polling, đường ngắt, cách xóa trạng thái.

### 9.4. Mô hình lập trình

Chuỗi thao tác của firmware: khởi tạo sau reset, chờ DDR sẵn sàng, kiểm tra header gói dữ liệu, chạy prompt, vòng decode, đọc lỗi, khôi phục. Mỗi chuỗi có ví dụ giá trị thanh ghi.

### 9.5. Quy tắc thứ tự và nhất quán bộ nhớ

Những gì firmware phải bảo đảm trước khi ra lệnh; những gì TinyLLM bảo đảm khi báo xong.

## 10. Gỡ lỗi và quan sát

- Điểm dump và cách kích hoạt; định dạng dữ liệu dump để so với golden.
- Bộ đếm hiệu năng: tên, ý nghĩa, điều kiện đếm.
- Tín hiệu để đưa ra ILA khi chạy trên board.

## 11. Kiểm chứng

### 11.1. Ánh xạ điểm quan sát

Bảng mỗi điểm quan sát trong RTL với tên boundary trong `config.formats` và thứ tự phần tử khi so.

### 11.2. Mức kiểm tra

Khối, layer, model, SoC. Với mỗi mức: công cụ, định dạng vector, cách tạo vector từ golden số học (D05).

### 11.3. Tình huống bắt buộc

Các trường hợp biên ở 6.6; backpressure và stall; reset giữa chừng; saturation; địa chỉ ở biên vùng nhớ; nhiều lượt chạy liên tiếp.

### 11.4. Tiêu chí đạt

Khớp từng bit tại mọi điểm quan sát; không có assertion nào bị vi phạm.

## 12. Tham số hóa cho model lớn hơn

Bảng các thông số model thay đổi khi lên model lớn hơn, với khối và bộ nhớ chịu ảnh hưởng. Các giả định sẽ bị phá vỡ (ví dụ head dim, tỷ lệ GQA, chiều chia hết cho 64, context) và cách mở rộng.

## 13. Phụ lục

- Bảng tổng hợp thông số.
- Bảng tổng hợp bộ nhớ và tài nguyên.
- Bản đồ thanh ghi đầy đủ.
- Bảng mã lệnh và mã lỗi.
- Lịch sử phiên bản đặc tả và phiên bản contract tương ứng.

## Kiểm tra trước khi giao một khối cho RTL

Một khối sẵn sàng hiện thực khi trả lời được hết các câu sau chỉ bằng đặc tả và contract:

- Mỗi port có độ rộng, ý nghĩa và giao thức chưa?
- Thứ tự dữ liệu vào và ra theo từng beat đã rõ chưa?
- Độ trễ, throughput và hành vi khi bị backpressure đã nêu chưa?
- Mỗi phép tính đã tham chiếu đúng mục contract và có đủ độ rộng trung gian chưa?
- Cấu hình nào được nạp, khi nào, từ đâu?
- Trường hợp biên và lỗi đã có hành vi chưa?
- Khối lân cận và bộ điều phối có cùng giả định về các điểm trên chưa?
- Đầu ra so với boundary nào của golden?
