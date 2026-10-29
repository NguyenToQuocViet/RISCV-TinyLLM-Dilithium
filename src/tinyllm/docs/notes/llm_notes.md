# Các file nguồn của SmolLM2-135M

`source.lock.json` ghi lại phiên bản model và mã kiểm tra (SHA-256) của từng file để biết bộ nguồn đang dùng có đúng phiên bản đã chọn hay không.

| File                        | Công dụng                                                                      |
| --------------------------- | -------------------------------------------------------------------------------- |
| `config.json`             | Chứa cấu hình và kích thước các thành phần của model.                 |
| `generation_config.json`  | Chứa thiết lập mặc định khi model sinh token.                              |
| `model.safetensors`       | Chứa các trọng số đã huấn luyện mà model dùng để tính toán.        |
| `merges.txt`              | Chứa quy tắc ghép các mảnh chữ khi tách văn bản thành token.           |
| `vocab.json`              | Ánh xạ các token với mã số tương ứng.                                   |
| `tokenizer.json`          | Chứa dữ liệu tokenizer để chuyển văn bản thành token và ngược lại.  |
| `tokenizer_config.json`   | Chứa thiết lập tokenizer, như cách xử lý văn bản và token đặc biệt. |
| `special_tokens_map.json` | Ghi tên và cách nhận diện các token đặc biệt, như token kết thúc.    |

# Các Ghi chú quan trọng

## Smoothing và requantization trong numerical contract

Phần này giải thích các công thức ở [§3.2 — Smoothing và requantization](../design/numerical_contract.md#32-smoothing-và-requantization).

### Hệ số tham chiếu trước quantize A

SmoothQuant biến đổi activation và trọng số theo `x'[i] = x[i] / s[i]`, `W'[o,i] = W[o,i] * s[i]`. Trước lượng tử hóa, hai hệ số `s[i]` triệt tiêu trong từng tích nên kết quả Linear được bảo toàn.

Gọi `q_in[i]` là mã số nguyên đầu vào, `delta_in` là scale và `z_in` là zero-point. Giá trị thực mà mã đầu vào biểu diễn là `x[i]`. Sau smoothing, giá trị này được lượng tử hóa thành A với scale đích `delta_A`:

```text
Giá trị thực được biểu diễn:  x[i]  = delta_in * (q_in[i] - z_in)
Sau smoothing:               x'[i] = x[i] / s[i]
Đổi sang đơn vị mã A:        u[i]  = x'[i] / delta_A
```

Thay hai dòng đầu vào dòng cuối:

```text
u[i] = (q_in[i] - z_in) * delta_in / (s[i] * delta_A)
     = (q_in[i] - z_in) * c[i]

c[i] = delta_in / (s[i] * delta_A)
```

Do đó, `c[i]` là hệ số nhân lý tưởng để đưa mã đầu vào sang đơn vị mã A sau smoothing, trước rounding và clipping:

```text
qA[i] = clip(RNE(c[i] * (q_in[i] - z_in)), -2048, 2047)
```

Trong công thức này, `delta_in` chuyển mã đầu vào thành giá trị thực; chia `s[i]` thực hiện smoothing; chia `delta_A` chuyển giá trị sau smoothing sang đơn vị mã A12. `RNE` là làm tròn về số nguyên gần nhất, trường hợp chính giữa chọn số chẵn. Nếu scale đầu vào thay đổi theo feature thì dùng `delta_in[i]` thay cho `delta_in` trong hệ số tương ứng.

Ví dụ với `q_in=100`, `z_in=0`, `delta_in=0.02`, `s=4`, `delta_A=0.01`:

```text
x  = 100 * 0.02 = 2
x' = 2 / 4 = 0.5
qA = RNE(0.5 / 0.01) = 50

c  = 0.02 / (4 * 0.01) = 0.5
qA = RNE(100 * 0.5) = 50
```

Gọi là **hệ số tham chiếu** vì `c[i]` là tỷ lệ toán học cần thực hiện. Trong datapath số nguyên, hệ số được biểu diễn bằng multiplier–shift, chẳng hạn `c[i] ≈ M[i] / 2^r[i]`. Độ rộng `M`, miền dịch, độ rộng tích và vị trí rounding vẫn cần được xác định theo §3.2; công thức tham chiếu không tự quyết định các thông số đó.

### Requantization và chuyển scale

**Requantization là chuyển một giá trị đã có biểu diễn số nguyên sang một biểu diễn số nguyên khác**, thường có scale hoặc số bit khác. Với zero-point bằng 0 ở cả đầu vào và đầu ra:

```text
q_out = clip(RNE(q_in * delta_in / delta_out), qmin_out, qmax_out)
```

Mục tiêu là giữ gần đúng giá trị thực đã biểu diễn:

```text
delta_out * q_out ≈ delta_in * q_in
```

Vì vậy, requantization không chỉ là ép kiểu hoặc cắt bit; hệ số chuyển đổi phải xét tỷ lệ giữa hai scale. Sai khác có thể phát sinh từ rounding, clipping và việc xấp xỉ hệ số bằng multiplier–shift.

Riêng accumulator Linear có scale `delta_A * delta_W[o]` và zero-point 0, nên hệ số chuyển sang scale output là:

```text
c_out[o] = delta_A * delta_W[o] / delta_out[o]
q_out[o] = clip(RNE(acc[o] * c_out[o]), qmin_out, qmax_out)
```

Smoothing rồi quantize A có thêm phép chia `s[i]` so với chuyển scale thông thường, vì vậy hệ số `c[i]` có thêm `s[i]` ở mẫu số. Gộp các hệ số này giúp hiện thực đường chuyển đổi bằng nhân và dịch số nguyên, thay vì phải tái dựng giá trị thực tại runtime.
