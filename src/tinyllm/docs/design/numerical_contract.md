# Numerical contract — SmolLM2-135M / W8A12KV8 SmoothQuant

**Trạng thái:** bản nháp. Cấu hình nền đã chọn theo [D02](../DECISIONS.md#d02-phát-triển-datapath-số-nguyên-theo-smoothquant); tài liệu quy định giá trị số nguyên mà golden model và RTL phải tạo ra; chưa có contract số nguyên hoàn chỉnh hoặc bằng chứng chất lượng của golden integer. Ô trống và đầu mục chưa có nội dung là phần **chưa chốt**, không phải giá trị mặc định.

## 1. Phạm vi, cấu hình model và nguồn tham số

| Mục | Nội dung đã xác định |
| --- | --- |
| Model/tokenizer | SmolLM2-135M base, nguồn đã pin trong [README FP32/PTQ](../../quantize/README.md). |
| Candidate tham chiếu | [Config A12 SmoothQuant](../../quantize/candidates/w8a12kv8_smoothquant/config.json), [qparams và vector s](../../quantize/candidates/w8a12kv8_smoothquant/qparams.safetensors). |
| Bằng chứng fake-quant tham chiếu | [Báo cáo](../../quantize/reports/ptq_a_extensions.md), [kết quả qualify](../../quantize/results/ptq/extra/w8a12kv8_smoothquant.final.json); phạm vi áp dụng ở §6.2. |
| Thống kê trung gian | [Miền quan sát và scale ứng viên](../../quantize/results/numerical/intermediate_calibration.json), [scale accumulator và hệ số V → cache tham chiếu](../../quantize/results/numerical/intermediate_qparams.safetensors). |
| Phạm vi ban đầu | Batch 1, không padding, tổng context tối đa 512 token; prefill và decode có KV cache. |
| Kích thước | 30 layer; hidden 576; FFN 1536; vocabulary 49152. |
| Attention | 9 query head, 3 KV head, head dimension 64; mỗi KV head phục vụ 3 query head liên tiếp. |
| RMSNorm | Epsilon nguồn `1e-5`; định dạng epsilon số nguyên chưa chốt ở §4.2. |
| RoPE | Theta `100000`, không RoPE scaling; ghép hai nửa head theo model nguồn. |
| SmoothQuant | Alpha `0.5`; vector `s` theo input feature của từng Linear decoder, lấy từ bundle đã chọn. |
| Ngoại lệ smoothing | Không áp dụng cho `lm_head` và shared embedding/head weight. |

Host chuẩn bị trọng số, scale, hệ số và bảng tra. Đường suy luận model của golden integer dùng phép toán số nguyên; phép đo chất lượng có thể chuyển logits sang số thực ở biên scorer.

## 2. Quy ước số học và biểu diễn dữ liệu

### 2.1. Mã số nguyên, scale và rounding

`v` là giá trị thực trước lượng tử hóa, `q` là mã số nguyên, còn `v_hat = delta * (q - z)` là giá trị thực tái dựng, với scale `delta > 0` và zero-point `z`. Các điểm W/A/K/V đã chọn đều có `z = 0`. Scale W/A/K/V và vector SmoothQuant `s` giữ nguyên từ bundle ở §1; không thay scale khi mở thêm mã âm. Scale FP32 trong bundle là tham số tham chiếu, chưa phải định dạng hệ số dùng trong RTL.

Miền signed bù hai đầy đủ `b` bit là `[-2^(b-1), 2^(b-1)-1]`: W8/KV8 dùng `[-128,127]`, A12 dùng `[-2048,2047]`. Các mã `-128` và `-2048` là giá trị hợp lệ tương ứng.

Quy tắc quantize: `q = clip(RNE(v / delta), qmin, qmax)`, dùng miền đầy đủ nêu trên và giữ rounding nearest, ties-to-even (`RNE`) của candidate tham chiếu. Ví dụ: `RNE(0.5)=0`, `RNE(1.5)=2`, `RNE(-0.5)=0`, `RNE(-1.5)=-2`. Đây là quan hệ tham chiếu; cách hiện thực bằng số nguyên ở §3.

Độ rộng ghi trong tài liệu là độ rộng logic, độc lập với container Python/PyTorch hoặc định dạng lưu/nạp ở §5. Để chứa mọi số nguyên trong `[-M,M]`, độ rộng signed tối thiểu là `1 + ceil(log2(M + 1))`. A12 ở input Linear không xác định độ rộng của các trung gian còn lại; định dạng trung gian được đặt tại mục phép toán hoặc khối sử dụng nó.

### 2.2. Trọng số và activation đầu vào Linear

| Dữ liệu | Số bit / miền số nguyên | Scale và vị trí áp dụng |
| --- | --- | --- |
| W của 7 Linear decoder mỗi layer | Signed 8, `[-128,127]` | Per-output-row, trục 0 của `W[output,input]`, sau biến đổi SmoothQuant. |
| W embedding/LM head | Signed 8, `[-128,127]` | Một bộ W và scale per-vocabulary-row dùng chung; không smoothing. |
| Input A của Linear | Signed 12, `[-2048,2047]` | Per-tensor tại từng điểm: Q/K/V/O, gate/up/down và LM head. Decoder áp dụng sau smoothing; LM head áp dụng trực tiếp. |

### 2.3. Token ID, vị trí và chiều dài context

| Đại lượng | Miền hợp lệ | Độ rộng unsigned tối thiểu |
| --- | --- | --- |
| Token ID | `0..49151` | 16 bit |
| Vị trí tuyệt đối của token | `0..511` | 9 bit |
| Số token đã lưu trong cache | `0..512` | 10 bit |

Độ dài chuỗi đang xử lý nằm trong `1..512`. Các độ rộng trên biểu diễn giá trị logic; container và cách mã hóa giao diện ở §5.

### 2.4. Miền tham chiếu và scale ứng viên của trung gian

Kết quả thống kê ở §1 đo đường fake-quant FP32 với scale W/A/K/V và `s` cố định, dùng miền signed đầy đủ. Miền quan sát trên train không phải cận bảo đảm cho mọi đầu vào. Các thống kê exp/sum/reciprocal Softmax là phép tính tham chiếu từ score sau trừ max, chưa chọn thuật toán số nguyên tương ứng.

Với miền quan sát `[vmin,vmax]`, đặt `Rneg = max(0,-vmin)`, `Rpos = max(0,vmax)`. Scale MinMax ứng viên cho signed `b` bit, zero-point 0, là `max(Rneg / 2^(b-1), Rpos / (2^(b-1)-1))`. Với dữ liệu không âm, ứng viên unsigned là `Rpos / (2^b-1)`, zero-point 0. Tensor chỉ có 0 dùng scale tham chiếu 1. Báo cáo cung cấp các scale theo độ rộng, cùng min/max theo channel/head để áp dụng công thức cho từng nhóm.

Các scale này phủ miền đã quan sát; chúng chưa chốt số bit, trục scale hoặc giới hạn sai số cho các biên mới. Scale của các Q-format và hệ số multiplier–shift chỉ được chốt cùng thuật toán số nguyên sử dụng chúng.

Tại output Linear, scale MinMax ứng viên mô tả một phép requantization bổ sung; không thay thế scale accumulator `delta_A * delta_W[o]` đã xác định ở §3.1.

## 3. Các phép tính nền

Mỗi bước số nguyên phải nêu độ rộng trước/sau phép toán, scale, thời điểm làm tròn/giới hạn và cách xử lý tràn. Kiểu dữ liệu của Python/PyTorch không thay thế cho độ rộng logic đã quy định.

### 3.1. Nhân ma trận / tích vô hướng

Với Linear có zero-point 0: `acc[m,o] = sum_i(qA[m,i] * qW[o,i])`; scale của tổng chưa requantize là `delta_A * delta_W[o]`. Linear không có bias trong model đã chọn. GEMM prefill và GEMV decode cùng tuân theo các quy tắc dưới đây

Shape logic của trọng số là `[output,input]`. Số phần tử reduction `N` là chiều input, không phải số output:

| Linear | Shape W | N |
| --- | --- | --- |
| `q_proj`, `o_proj` | `[576,576]` | 576 |
| `k_proj`, `v_proj` | `[192,576]`, với `192 = 3 * 64` | 576 |
| `gate_proj`, `up_proj` | `[1536,576]` | 576 |
| `down_proj` | `[576,1536]` | 1536 |
| `lm_head` | `[49152,576]` | 576 |

Với miền A/W ở §2, tích nhỏ nhất là `2047 * (-128) = -262016`, tích lớn nhất là `(-2048) * (-128) = 262144`. Vì vậy `-N * 262016 <= acc <= N * 262144`; đặt `Pmax = 262144` để có cận tuyệt đối `abs(acc) <= N * Pmax`:

| Đại lượng | Miền số nguyên được bảo đảm | Độ rộng signed tối thiểu | Scale |
| --- | --- | --- | --- |
| Tích A12 × W8 | `[-262016,262144]` | 20 bit | `delta_A * delta_W[o]` |
| Accumulator, `N=576` | `[-150921216,150994944]` | 29 bit | `delta_A * delta_W[o]` |
| Accumulator, `N=1536` | `[-402456576,402653184]` | 30 bit | `delta_A * delta_W[o]` |

Accumulator Linear dùng **signed INT32**, miền `[-2147483648,2147483647]`, cho cả prefill và decode. Các độ rộng trong bảng là cận tối thiểu để chứng minh biên; độ rộng accumulator được chọn là 32 bit. Tích phải được giữ chính xác ít nhất 20 bit và sign-extend khi đưa vào accumulator. Một partial sum gồm `n` tích có biên tuyệt đối `n * Pmax`, do đó cần ít nhất `1 + ceil(log2(n * Pmax + 1))` bit signed. Với `n <= 1536`, INT32 chứa được mọi partial sum và tổng cuối nêu trên.

| Quy tắc | Nội dung |
| --- | --- |
| Reduction và partial sum | Với các tích/tổng chính xác và đủ rộng theo biên trên, đổi thứ tự cộng hoặc ghép partial sum không đổi kết quả số nguyên. Cách chia tile và lịch reduction cụ thể chưa chốt. |
| Rounding và saturation trung gian | Tích và tổng số nguyên chính xác không cần rounding hoặc saturation. Quy tắc thu hẹp trung gian nếu có chưa chốt. |
| Điều kiện tránh overflow | Toán hạng nằm trong miền ở §2; mỗi tích, partial sum và tổng cuối được giữ đủ rộng theo số tích của nó. Hành vi khi vi phạm điều kiện này chưa chốt. |
| Chuyển accumulator về định dạng output và scale đích | |

| Dữ liệu / điểm quan sát | Signed, bit, miền hợp lệ | Scale / Q-format / zero-point | Điểm chuyển biểu diễn |
| --- | --- | --- | --- |
| Output Linear trước requantization: Q/K/V/O, gate/up/down | Signed INT32; miền theo chiều reduction ở §3.1 | Per-output-row, `delta_A * delta_W[o]`, zero-point 0; giá trị tham chiếu trong bundle trung gian ở §1. | Sau MAC, trước chuyển sang định dạng đầu vào của khối nhận. |

Định dạng sau requantization được xác định tại giao diện của từng khối nhận; không mặc định bằng A12. Bundle trung gian xuất thêm tỷ lệ `delta_A_v * delta_W_v[o] / delta_V[head(o)]` cho V projection → cache, với scale cache đã biết. Đây là hệ số tham chiếu, chưa phải multiplier/shift RTL.

### 3.2. Smoothing và requantization

Quan hệ đã chọn: `x'[i] = x[i] / s[i]`, `W'[o,i] = W[o,i] * s[i]`. Host xuất W đã lượng tử hóa cùng các hệ số tương ứng. Ưu tiên gộp smoothing với quantization bằng multiplier–shift theo D02.

Với đầu vào `x[i] = delta_in * (q_in[i] - z_in)`, hệ số tham chiếu trước quantize A là `c[i] = delta_in / (s[i] * delta_A)`. `delta_in`, `z_in` và cách biểu diễn `c[i]` phải được xác định trước khi dùng công thức này trong golden integer.

Requantization không smoothing có hệ số tham chiếu `c = delta_in / delta_out`. Riêng accumulator Linear sang output có zero-point 0, `q_out[o] = clip(RNE(acc[o] * delta_A * delta_W[o] / delta_out[o]), qmin_out, qmax_out)`. Các công thức này xác định tỷ lệ scale; định dạng output và cách xấp xỉ hệ số bằng multiplier–shift vẫn chưa chốt.

| Quy tắc | Nội dung |
| --- | --- |
| Biểu diễn `c[i]` bằng multiplier/shift; miền và độ rộng từng trường | |
| Độ rộng phép nhân hệ số, vị trí lấy bit và dịch trái/phải | |
| Rounding | RNE theo §2.1 tại biên quantize A; số lần và vị trí rounding nội bộ của multiplier–shift chưa chốt. |
| Saturation về A12 | `clip(q,-2048,2047)` sau rounding; zero-point 0. |
| Xử lý hệ số ngoài miền biểu diễn | |

### 3.3. Residual và phép nhân từng phần tử

| Dữ liệu / điểm quan sát | Signed, bit, miền hợp lệ | Scale / Q-format / zero-point | Điểm chuyển biểu diễn |
| --- | --- | --- | --- |
| Residual stream: đầu layer, sau attention, sau FFN | | | |

- Quy tắc đưa hai toán hạng về scale tương thích:
- Độ rộng cộng/nhân trung gian:
- Thứ tự rescale, cộng/nhân, rounding và saturation:
- Định dạng đầu ra và cách xử lý overflow:

## 4. Thuật toán theo khối

Mỗi khối gồm biểu diễn dữ liệu, chuỗi phép toán số nguyên, hệ số/LUT và các quy tắc xử lý biên. Golden integer và RTL dùng cùng định dạng và cùng phép xấp xỉ tại từng bước.

### 4.1. Embedding và LM head dùng chung trọng số

**Đã xác định:** dùng một bộ `qW[vocab,hidden]` cùng scale per-row cho cả lookup và LM head. LM head có input A12, không SmoothQuant. Scale hàng embedding được chọn theo token ID; scale output LM head được chọn theo vocabulary row.

| Dữ liệu / điểm quan sát | Signed, bit, miền hợp lệ | Scale / Q-format / zero-point | Điểm chuyển biểu diễn |
| --- | --- | --- | --- |
| Hàng embedding sau lookup, trước chuyển về residual | Signed 8, `[-128,127]` | `delta_W[token_id]`, zero-point 0 | Đọc `qW[token_id,0:576]`; dùng mã W chung ở §2.2. |
| Logits | | | Sau MAC LM head và chuyển scale. |

- Chuyển hàng embedding sang định dạng residual:
- MAC LM head: reduction 576 phần tử theo §3.1; chuyển output sang logits:
- Đơn vị/scale dùng để so logits, chính sách hòa khi chọn token:
- Biểu diễn logits trả về scorer:

### 4.2. RMSNorm trước attention, trước FFN và final norm

Quan hệ model: `y = gamma * x / sqrt(mean(x*x) + epsilon)`, với epsilon nguồn ở §1.

Với hidden size 576 và epsilon dương, cận thực tham chiếu là `abs(y[i]) <= 24 * abs(gamma[i])`; square/sum/mean không âm, `mean(x*x) + epsilon >= 1e-5` và `0 < reciprocal_sqrt <= 1/sqrt(1e-5) ≈ 316.227766`. Miền mã và scale của các bước này phụ thuộc định dạng x và thuật toán normalization số nguyên.

| Dữ liệu / điểm quan sát | Signed, bit, miền hợp lệ | Scale / Q-format / zero-point | Điểm chuyển biểu diễn |
| --- | --- | --- | --- |
| RMSNorm gamma | | | |
| RMSNorm square/sum/mean, epsilon, reciprocal sqrt | | | |
| RMSNorm output trước smoothing, gồm final norm | | | |

- Thuật toán số nguyên: square, reduction/mean, epsilon, reciprocal sqrt và nhân gamma:
- Hệ số/LUT, miền xấp xỉ và xử lý vector 0:
- Rounding/overflow ở từng bước và chuyển scale đầu ra:

### 4.3. RoPE

**Đã xác định:** quay Q/K theo vị trí token; `rotate_half(x) = concat(-x[32:64], x[0:32])` cho head 64 chiều. K được lượng tử hóa để lưu cache sau phép quay.

Sin/cos tham chiếu thuộc `[-1,1]`; phép quay thực chính xác bảo toàn tổng bình phương của mỗi cặp. Miền Q/K quan sát trước/sau RoPE được lưu trong thống kê trung gian; độ rộng tích và quy tắc rounding vẫn phải xác định cùng cách biểu diễn sin/cos.

| Dữ liệu / điểm quan sát | Signed, bit, miền hợp lệ | Scale / Q-format / zero-point | Điểm chuyển biểu diễn |
| --- | --- | --- | --- |
| Q/K trước và sau RoPE, trước quantize K cache | | | |
| RoPE sin/cos | | | |

- Cách sinh, chỉ số và độ chính xác sin/cos cho vị trí 0–511:
- Chuỗi phép nhân/cộng số nguyên và định dạng Q/K sau quay:
- Rounding/saturation trước quantize K cache:

### 4.4. KV cache và GQA

**Đã xác định:** cache logic `[B,Hkv,L,D]`, `Hkv=3`, `D=64`. Với query head `h`, dùng KV head `h // 3`. Mỗi token mới được quantize K/V một lần tại các điểm sau RoPE/projection dưới đây; append giữ nguyên mã số nguyên của prefix cũ và không tính lại scale từ lịch sử.

| Dữ liệu | Số bit / miền số nguyên | Scale và vị trí áp dụng |
| --- | --- | --- |
| K lưu cache | Signed 8, `[-128,127]` | Per-native-KV-head tại mỗi layer, zero-point 0; sau RoPE, trước cache/GQA. |
| V lưu cache | Signed 8, `[-128,127]` | Per-native-KV-head tại mỗi layer, zero-point 0; sau projection, trước cache/GQA. |

Ánh xạ GQA: query head `0,1,2` dùng KV head 0; `3,4,5` dùng KV head 1; `6,7,8` dùng KV head 2. Cache lưu 3 native KV head, không nhân bản thành 9 query head.

Với cache cũ dài `L_prev` và block mới có `T` token, token mới thứ `j` có vị trí tuyệt đối `p = L_prev + j`, `0 <= j < T`; độ dài sau append là `L_prev + T <= 512`. Prefill từ cache rỗng có `L_prev=0`; decode một token có `T=1`, vị trí `p=L_prev` và yêu cầu `L_prev <= 511`. Shape mỗi tensor K/V ở giới hạn context là `[1,3,512,64]`.

- Chuyển K/V từ output projection/RoPE sang định dạng cache:
- Thứ tự append/read trong hiện thực:
- Các bước chuyển scale khi đọc cache cho QK/PV:

### 4.5. Attention score và causal mask

Quan hệ model: `score = Q*K^T / sqrt(64)`, tức hệ số thực `1/8`. Chỉ cho phép key có vị trí không lớn hơn vị trí query. Cách biểu diễn mask bằng số nguyên chưa chốt.

Mỗi dot-product QK có 64 tích. Với query ở vị trí tuyệt đối `p`, các key hợp lệ có vị trí `0..p`, tổng cộng `p+1` key; tại `p=511` có tối đa 512 key.

| Dữ liệu / điểm quan sát | Signed, bit, miền hợp lệ | Scale / Q-format / zero-point | Điểm chuyển biểu diễn |
| --- | --- | --- | --- |
| Attention QK accumulator | | | |
| Score sau scaling/mask | | | |

- Biểu diễn Q và accumulator QK:
- Cách kết hợp scale Q/K, hệ số `1/8` và scale score:
- Thời điểm áp mask và cách loại phần tử bị che:

### 4.6. Softmax

Quan hệ model: chuẩn hóa `exp(score)` trên các key được phép; xác suất tại key bị che bằng 0.

Với `N` key hợp lệ, `1 <= N <= 512`, score sau trừ max không dương và có ít nhất một phần tử 0. Các cận thực tham chiếu là `exp ∈ [0,1]`, `sum_exp ∈ [1,N]`, `reciprocal ∈ [1/N,1]`, `P ∈ [0,1]`. Các cận này không tự xác định số bit hoặc scale của exp, reciprocal hay xác suất trong thuật toán số nguyên.

| Dữ liệu / điểm quan sát | Signed, bit, miền hợp lệ | Scale / Q-format / zero-point | Điểm chuyển biểu diễn |
| --- | --- | --- | --- |
| Softmax: max, hiệu, exp, tổng, reciprocal | | | |
| Xác suất attention | | | |

- Thuật toán số nguyên và thứ tự reduction:
- Trừ max, miền exp, cắt miền và LUT/đa thức/hệ số:
- Độ rộng tổng exp; thuật toán chia/reciprocal và rounding:
- Định dạng xác suất, sai lệch tổng xác suất được phép:
- Hành vi với hàng bị che toàn bộ và các trường hợp biên:

### 4.7. Nhân xác suất với V và output projection

Quan hệ model: `context = P*V`, ghép các query head rồi qua `o_proj` và cộng residual.

Mỗi thành phần context cộng trên các vị trí key hợp lệ, tối đa 512 tích. Ghép 9 query head có chiều 64 tạo vector `9 * 64 = 576` phần tử cho `o_proj`.

| Dữ liệu / điểm quan sát | Signed, bit, miền hợp lệ | Scale / Q-format / zero-point | Điểm chuyển biểu diễn |
| --- | --- | --- | --- |
| Attention PV accumulator và context output | | | |

- Độ rộng tích/accumulator PV, scale và thứ tự reduction:
- Chuyển context sang input smoothing/A12 của `o_proj`:
- Chuyển output projection về scale của nhánh residual:

### 4.8. FFN: SiLU, gate multiply và down projection

Quan hệ model: `down_proj(SiLU(gate_proj(norm(x))) * up_proj(norm(x)))`. Gate/up/down có input smoothing/A12 riêng.

| Dữ liệu / điểm quan sát | Signed, bit, miền hợp lệ | Scale / Q-format / zero-point | Điểm chuyển biểu diễn |
| --- | --- | --- | --- |
| SiLU và tích nhánh gate/up trước down projection | | | |

- Thuật toán SiLU số nguyên, miền xấp xỉ, LUT/hệ số:
- Phép nhân hai nhánh: scale, độ rộng tích và chuyển biểu diễn:
- Smoothing/quantize input down projection:
- Chuyển output FFN về residual và cộng residual:

### 4.9. Nhất quán prefill/decode

- Thứ tự phép toán theo token/head/layer và các trạng thái số học lưu qua lượt decode:
- Quan hệ kết quả full-forward với prefill/decode cho cùng token đầu vào, kể cả ảnh hưởng của chia block/reduction:
- Các điểm quan sát và kết quả số nguyên phải đối chiếu:

## 5. Định dạng weights, hệ số, LUT và dữ liệu trao đổi

### 5.1. Biểu diễn và quy tắc lưu/nạp

Bundle fake-quant ở §1 cung cấp tham số tham chiếu; chưa phải gói dữ liệu số nguyên có thể nạp thẳng cho RTL. Định dạng lưu/nạp gồm biểu diễn nhị phân, thứ tự phần tử, endianness, sign extension, padding/alignment và cách giải mã cho từng loại dưới đây.

Khi xuất W số nguyên, dùng miền đầy đủ ở §2.2 với scale đã giữ từ bundle; áp dụng cùng một bộ qW cho embedding và LM head.

Bundle trung gian ở §1 lưu scale accumulator Linear và tỷ lệ chuyển V → cache bằng FP64 để tham chiếu trên host. File thống kê lưu scale MinMax ứng viên, zero-point 0, min/max và phân bố từng điểm; chưa phải gói hệ số fixed-point nạp RTL. Lệnh tạo dữ liệu và kiểm tra được ghi trong [README quantize](../../quantize/README.md#thống-kê-trung-gian-cho-numerical-contract).

| Loại dữ liệu | Định dạng lưu/nạp |
| --- | --- |
| W8 decoder và shared embedding/head; thứ tự hàng/cột | |
| Gamma RMSNorm và các hằng số model | |
| Scale tương đương, multiplier/shift của từng điểm | |
| Sin/cos và LUT/hệ số của các phép xấp xỉ | |
| Activation A12: container/packing, giá trị padding | |
| KV cache và các tensor trung gian cần trao đổi | |
| Token IDs, position/length và logits đầu ra | |
| Gắn phiên bản contract và ánh xạ dữ liệu tới layer/module | |

Các LUT/hệ số xấp xỉ ngoài những mục đã nêu phải có signed/unsigned, số bit, miền hợp lệ, scale/Q-format và vị trí sử dụng tương ứng.

### 5.2. Dung lượng payload trọng số và KV cache

Các số dưới đây chỉ tính mã W8/KV8, mỗi mã 8 bit; không gồm gamma, scale, multiplier/shift, LUT, alignment hoặc buffer. Shared embedding/LM head chỉ tính một lần. Đây là dung lượng logic, không phải dung lượng bộ nhớ FPGA đã triển khai.

| Dữ liệu | Số mã 8 bit / dung lượng byte |
| --- | --- |
| W decoder, 30 layer | `30 * (2*576*576 + 2*192*576 + 3*1536*576) = 106168320` |
| W embedding/LM head dùng chung | `49152 * 576 = 28311552` |
| Tổng W8 | `134479872` byte = `128.25 MiB` |
| K và V, mỗi layer tại context 512 | `2 * 3 * 512 * 64 = 196608` byte |
| K và V, 30 layer tại context 512 | `30 * 196608 = 5898240` byte = `5.625 MiB` |

## 6. Hợp đồng kiểm chứng

### 6.1. Đối chiếu số học

- RTL và oracle độc lập thực hiện cùng contract phải khớp từng bit với golden integer tại các điểm đã quy định. Không yêu cầu bitwise với FP32 hoặc fake-quant vì đường số nguyên có thêm phép xấp xỉ.
- Kiểm tra các primitive và khối với số âm, 0, half-step, cực trị, overflow, mask, residual khác scale, cache append và chuỗi sát giới hạn context.

| Hạng mục kiểm chứng | Nội dung |
| --- | --- |
| Oracle độc lập và vector biên cho từng primitive/khối | |
| Điểm quan sát, shape, scale và mã số nguyên expected | |
| Giới hạn sai số xấp xỉ của từng hàm trước đánh giá toàn model | |
| Vector chuẩn prefill/decode, bao gồm token đầu sau prompt | |
| Phép kiểm lưu/nạp weights/hệ số/LUT không đổi kết quả | |

### 6.2. Đánh giá chất lượng và tiêu chí chấp nhận

Candidate fake-quant tham chiếu ở §1 đã được qualify với miền đối xứng W8/KV8 `[-127,127]` và A12 `[-2047,2047]`. Contract dùng miền signed đầy đủ với cùng scale; không đánh giá lại fake-quant cho thay đổi miền mã này. Chất lượng tương ứng với miền đầy đủ chưa được xác nhận bằng phép đo.

Chất lượng dùng lại [protocol và ngưỡng PTQ](../../quantize/plans/ptq_plan.md#bước-2--có-bộ-chấm-chất-lượng-chạy-được-trên-fp32), so golden integer với FP32 và candidate fake-quant ở §1 trên cùng selection và token đầu vào. Heldout chỉ dùng xác nhận sau khi chốt theo PLAN.md.

Contract đủ để làm chuẩn RTL khi mọi mục ảnh hưởng kết quả đã được xác định, có golden integer prefill/decode và vector chuẩn, chất lượng toàn model đạt yêu cầu, đồng thời chi phí kernel đại diện đã được kiểm tra ở chặng 4. Kết quả chạy và số đo được lưu ở báo cáo thí nghiệm; tài liệu này duy trì các quy tắc số học đã chọn.
