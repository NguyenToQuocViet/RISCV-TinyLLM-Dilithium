# Numerical contract đề xuất — SmolLM2-135M / W8A12KV8 SmoothQuant

**Trạng thái:** đề xuất cấu hình `combined_high`, cấu hình duy nhất trong ba tổ hợp đo được vượt toàn bộ quality gate trên selection. Đây là kết quả của mô phỏng mã trên host; chưa phải golden integer kernel hoặc bằng chứng RTL. [Contract tham chiếu](numerical_contract.md) được giữ nguyên.

## 1. Model và bộ tham số

| Thuộc tính | Quy định |
| --- | --- |
| Model | SmolLM2-135M base, revision `93efa2f097d58c2a74874c7e644dbc9b0cee75a2`; nguồn và môi trường trong [README quantize](../../quantize/README.md). |
| Cấu hình nền | [W8A12KV8 SmoothQuant alpha 0.5](../../quantize/candidates/w8a12kv8_smoothquant/config.json), theo [D02](../DECISIONS.md#d02-phát-triển-datapath-số-nguyên-theo-smoothquant). |
| Tham số nguồn | [Qparams và vector SmoothQuant](../../quantize/candidates/w8a12kv8_smoothquant/qparams.safetensors). Giữ nguyên scale W/A/K/V và vector `s`. |
| Calibration trung gian | [Số đo train](../../quantize/results/numerical/intermediate_calibration.json); scale khởi đầu chỉ được tính từ train. |
| Batch / context | Batch 1, không padding, tổng context `1..512`; hỗ trợ prefill và decode dùng KV cache. |
| Decoder | 30 layer, hidden 576, FFN 1536, vocabulary 49152; Linear không bias. |
| Attention | 9 query head, 3 KV head, head dimension 64. |
| RMSNorm / RoPE | Epsilon nguồn `1e-5`; theta `100000`, split-half, không RoPE scaling. |

Host chuẩn bị mã W, hệ số và LUT. Đường tính model được đặc tả bằng số nguyên; chuyển logits sang số thực chỉ diễn ra tại scorer. Dung lượng và độ rộng logic trong tài liệu không phải số liệu diện tích, timing hoặc số DSP đã đo bằng RTL.

## 2. Quy ước biểu diễn và số học

### 2.1. Giá trị, mã và miền hợp lệ

`v` là giá trị thực, `q` là mã số nguyên, `delta > 0` là scale. Giá trị tái dựng là `v_hat = delta * (q - z)`. Miền mã hợp lệ do định dạng quy định; min/max trên calibration là miền quan sát, không thay thế miền hợp lệ.

Signed bù hai `b` bit có miền `[-2^(b-1),2^(b-1)-1]`; unsigned `b` bit có miền `[0,2^b-1]`. W8/KV8 dùng đủ `[-128,127]`, A12 dùng đủ `[-2048,2047]`. Độ rộng logic độc lập với container lưu/nạp.

### 2.2. Rounding, saturation và phép toán mở rộng

`RNE` là làm tròn tới số nguyên gần nhất, trường hợp đúng nửa chọn số chẵn. Ví dụ `RNE(0.5)=0`, `RNE(1.5)=2`, `RNE(-0.5)=0`, `RNE(-1.5)=-2`.

Với tử signed `n` và mẫu nguyên dương `d`, phép chia RNE được định nghĩa độc lập với ngôn ngữ lập trình:

1. Đặt `a=abs(n)`, `u=a//d`, `r=a-u*d`.
2. Tăng `u` thêm 1 nếu `2*r>d`, hoặc nếu `2*r=d` và `u` lẻ.
3. Trả `u` khi `n>=0`, ngược lại trả `-u`.

`rshift_RNE(n,s)` với `s>=0` là phép chia trên với `d=2^s`. Dịch trái là nhân chính xác với `2^s`, không làm tròn. Không dùng phép dịch phải số âm của ngôn ngữ để thay RNE.

Saturation `sat_b` được áp dụng sau rounding về miền đích. Tích và tổng trước bước thu hẹp phải giữ đủ độ rộng; không wrap-around. Một phép toán vượt miền đã chứng minh là lỗi hiện thực, không phải một kết quả suy luận hợp lệ.

**Lý do:** cùng một quy tắc cho số âm và trường hợp đúng nửa giúp bản phần mềm và RTL tạo cùng mã.

### 2.3. Boundary format và biến nội bộ

**Boundary** là tensor mã hóa được một phép toán xuất ra và phép toán kế tiếp nhận vào. Định dạng của từng boundary được quy định theo tên tensor trong `config.formats` của candidate xuất; §14.4 chỉ tổng hợp số lượng theo độ rộng, không thay thế danh sách này. Các trường trong entry có ý nghĩa:

| Trường | Ý nghĩa |
| --- | --- |
| `bits`, `signed`, `code_range` | Độ rộng logic, signedness và miền mã hợp lệ. |
| `scale`, `zero_point`, `axis` | Quy tắc giải mã `v = scale * (q-zero_point)`. `scale` là scalar khi `axis=null`, hoặc là vector được đánh chỉ mục theo `axis`. |
| `container_bits` | Độ rộng lưu/nạp; có thể lớn hơn `bits` và không làm thay đổi miền logic. |
| `real_range` | Min/max quan sát được trong dữ liệu calibration, không phải miền mã được bảo đảm. |

Ví dụ các entry thật của `combined_high`:

| Boundary | Format |
| --- | --- |
| `model.layers.0.self_attn.query_post_rope` | Signed16, `axis=1` với scale theo query head; miền mã `[-32768,32767]`, container16. |
| `model.layers.0.self_attn.probability_unmasked` | Unsigned P12, `axis=null`, scale `1/4095`; miền mã `[0,4095]`, container16. |
| `model.layers.0.residual_after_attention` | Signed24, `axis=null`; miền mã `[-8388608,8388607]`, container32. |

Danh sách đầy đủ 483 boundary format, gồm scale, axis và miền mã của từng tensor, nằm trong [`combined_high/config.json`](../../quantize/results/numerical/contract_search/combined_high/config.json), khóa `formats`. Các intermediate như `u0`, `a`, `b`, `u1` trong §6.2 là biến số học bên trong RMSNorm; bảng của chúng cho biết cận/độ rộng cần thiết trong thuật toán, không phải boundary format độc lập. Các hàm nonlinear khác cũng có biến nội bộ riêng, được đặc tả trong các mục tương ứng; chỉ tensor vào/ra của chúng có entry `formats` khi nó là boundary giữa các phép toán.

## 3. Trọng số và input Linear

| Dữ liệu | Biểu diễn | Scale / zero-point |
| --- | --- | --- |
| W decoder | Signed 8, `[-128,127]`; shape `[out,in]` | Per-output-row sau SmoothQuant; scale nguồn; `z=0`. |
| W embedding/LM head | Signed 8, `[-128,127]`; dùng chung một bộ mã | Per-vocabulary-row; không smoothing; `z=0`. |
| Input Q/K/V/O, gate/up/down | Signed 12, `[-2048,2047]` | Per-tensor tại từng Linear, sau smoothing; scale nguồn; `z=0`. |
| Input LM head | Signed 12, `[-2048,2047]` | Per-tensor, không smoothing; scale nguồn; `z=0`. |

Host chuẩn bị `W'[o,i]=W[o,i]*s[i]`; đầu vào decoder tương ứng là `x'[i]=x[i]/s[i]`. Shared embedding/head không áp dụng phép biến đổi này. [Bộ mã W nguyên](../../quantize/results/numerical/contract_search/weights.safetensors) là dữ liệu dùng chung cho các cấu hình; lookup và LM head đọc cùng một tensor trong bộ này.

Bộ mã được xuất từ frozen fake-quant FP32 của candidate với miền signed đầy đủ, rồi khôi phục mã theo scale hàng đã biết. Không tính lại W bằng phép chia FP64 khác với phép chuẩn bị đã dùng khi đánh giá; các trường hợp sát half-step có thể khác mã. Việc chuẩn bị này chỉ chạy trên host; suy luận đọc trực tiếp W8 đã xuất.

**Lý do:** giữ bộ W/A/K/V và smoothing đã chọn giúp khảo sát riêng ảnh hưởng của các giao diện mới và xấp xỉ phi tuyến.

## 4. Linear và chuyển scale

### 4.1. Tích và accumulator

`acc[m,o]=sum_i(qA[m,i]*qW[o,i])`, với scale `delta_acc[o]=delta_A*delta_W[o]`, zero-point 0. Mỗi tích được tính chính xác và sign-extend trước khi cộng. Accumulator Linear là signed INT32.

| Linear | Shape W | Reduction |
| --- | --- | --- |
| Q, O | `[576,576]` | 576 |
| K, V | `[192,576]` | 576 |
| Gate, up | `[1536,576]` | 576 |
| Down | `[576,1536]` | 1536 |
| LM head | `[49152,576]` | 576 |

| Đại lượng | Cận mã chính xác | Số bit signed tối thiểu |
| --- | --- | --- |
| Một tích A12 × W8 | `[-262016,262144]` | 20 |
| Tổng 576 tích | `[-150921216,150994944]` | 29 |
| Tổng 1536 tích | `[-402456576,402653184]` | 30 |

Với mọi partial sum có `n<=1536` tích, cận tuyệt đối `n*262144` nằm trong INT32. Không rounding hoặc saturation trong reduction. Đổi thứ tự cộng không đổi kết quả khi mỗi partial sum được giữ đủ rộng.

**Lý do:** INT32 chứa được cả trường hợp hai mã âm nhỏ nhất nhân nhau; không cần bỏ mã `-128` hoặc `-2048`.

### 4.2. Hệ số nhân–dịch và requantization

Host compile hệ số thực `c` bằng FP64; runtime chỉ nhận mã `M` và shift nguyên `s`. Với precision mantissa `p`:

```text
c = f*2^e, 0.5<=abs(f)<1 khi c!=0
M = RNE(f*2^p)
s = p-e
nếu abs(M)==2^p: M=M/2; s=s-1
nếu c==0: M=0; s=0
requant(q,c) = RNE(q*M/2^s)
```

Nếu `s<0`, dịch trái tích chính xác. Nếu `s>=0`, giữ toàn bộ tích rồi chia RNE. Không làm tròn tích trước khi dịch và không saturation trước bước đã chỉ định tại consumer.

`p` giới hạn trị tuyệt đối mantissa, không bao gồm bit dấu: `abs(M)<2^p`. Hệ số có dấu cần signed `p+1` bit; trường luôn không âm có thể dùng unsigned `p` bit. Giá trị shift được lưu có dấu. Độ rộng tích phải bao gồm độ rộng của cả mã input và M, cùng phần dịch trái nếu có.

Sau Linear, hệ số per-output-row là `delta_A*delta_W[o]/delta_target[o]`. Trước Linear decoder, smoothing được gộp vào hệ số per-input-feature `delta_source[i]/(s[i]*delta_A)`. LM head bỏ thành phần `s[i]`. Những hệ số này được compile trên host cùng độ chính xác của cấu hình, không chia activation cho số thực ở runtime.

**Lý do:** nhân–dịch dùng lại được cho mọi bước chuyển scale. Gộp smoothing tránh một phép chia riêng cho từng activation.

## 5. KV cache, GQA và vị trí

K sau RoPE và V sau projection được quantize một lần về signed 8, zero-point 0, scale nguồn per-native-KV-head ở mỗi layer. Cache lưu mã `[B,Hkv,L,D]`, không lưu thêm bản nhân rộng theo query head.

Query head `h` dùng KV head `h//3`. Với cache cũ dài `L_prev` và block mới `T`, token mới thứ `j` có vị trí `p=L_prev+j`, `0<=j<T`; yêu cầu `L_prev+T<=512`. Decode một token dùng `p=L_prev`, với `L_prev<=511`. Append giữ nguyên mã và scale của prefix cũ.

Key hợp lệ khi `key_position<=query_position`. Mask là điều kiện hợp lệ riêng; phần tử bị che không tham gia tìm max hoặc tổng Softmax và có mã xác suất 0. Với batch 1, không padding và causal self-attention hợp lệ, mỗi hàng có ít nhất một key. Hàng không có key hợp lệ là lỗi đầu vào.

| Đại lượng | Miền | Biểu diễn tối thiểu |
| --- | --- | --- |
| Token ID | `0..49151` | Unsigned 16 |
| Position | `0..511` | Unsigned 9 |
| Cache length | `0..512` | Unsigned 10 |

**Lý do:** mask riêng tránh phải dành một mã score làm âm vô cùng; giữ cache cũ nguyên trạng tránh sai số tăng theo số lượt decode.

## 6. RMSNorm

Input được biểu diễn bằng mã `qX` và một scale chung `delta_X` cho vector 576 phần tử. Nếu residual dùng scale per-channel, chuyển một lần về định dạng input RMSNorm scalar 24 bit trước reduction; định dạng và hệ số của bước này là một phần của bộ tham số, không dùng lại các mã khác scale như thể chúng cùng đơn vị.

### 6.1. Square, reduction và epsilon

Đặt `Q=sum_i(qX[i]^2)`. Cộng chính xác, không rounding trong reduction. Với input tối đa signed 24, `Q<=576*2^46`, cần unsigned 56 bit. Các input hẹp hơn được zero/sign-extend đúng trước phép bình phương.

Biểu diễn `t = mean(x*x)+epsilon` bằng mã unsigned, scale `2^-F_t`. `F_t` là số fractional bit của cấu hình norm:

```text
c_t = delta_X^2 * 2^F_t / 576
(M_t, s_t) = compile(c_t)
epsilon_code = max(1,RNE(1e-5*2^F_t))
t_code = RNE(Q*M_t / 2^s_t) + epsilon_code
```

Nếu `s_t<0`, dịch trái tử thay cho dịch phải. `epsilon_code` lần lượt là `168`, `42950`, `10995116` cho `F_t=24,32,40`; nó dương và không mất epsilon tại vector 0. Độ rộng tích `Q*M_t` và mã `t` được tính từ định dạng input và hệ số từng norm; không ép các scalar rộng này về INT32/INT64 trước khi rounding.

### 6.2. LOD, LUT và một bước Newton

```text
ell = bit_length(t_code) - 1 - F_t
k = floor(ell/2)
m = clip(RNE(t_code / 2^(F_t+2*k-16)), 65536, 262143)
j = floor((m-65536)*B_seed / 196608)
u0 = seed_lut[j]
a = u0*u0
b = RNE(m*a / 2^28)
u1 = RNE(u0*(196608-b) / 2^17)
```

`k` dùng phép chia lấy floor, kể cả khi âm; các phép chia có ký hiệu RNE dùng quy tắc §2. `m` có scale `2^-16`, miền mã `[65536,262143]`; `j` unsigned 5 bit với LUT32 hoặc 6 bit với LUT64. Giá trị seed được chuẩn bị trên host:

```text
seed_lut[j] = RNE(2^14 / sqrt(1 + 3*(j+0.5)/B_seed)), j=0..B_seed-1
```

Seed và `u1` có scale `2^-14`. Với các bước trên, cận mã là:

| Trung gian | Miền mã LUT32 | Miền mã LUT64 | Số bit unsigned đủ chứa |
| --- | --- | --- | --- |
| `u0` | `[8240,16013]` | `[8216,16195]` | 14 |
| `a` | `[67897600,256416169]` | `[67502656,262278025]` | 28 |
| `b` | `[62602,68470]` | `[64033,67033]` | 17 |
| `196608-b` | `[128138,134006]` | `[129575,132575]` | 18 |
| `u0*(196608-b)` | `[1073688480,2145838078]` | `[1073732608,2147052125]` | 31 |
| `u1` | `[8192,16371]` | `[8192,16381]` | 14 |

Các cận này xét toàn miền mantissa, không lấy min/max từ calibration. Payload logic LUT32/LUT64 tương ứng 56/112 byte; container unsigned 16 dùng 64/128 byte. Cấu hình quy định một giá trị `B_seed` cụ thể, không tự đổi bảng giữa các lượt chạy.

### 6.3. Nhân gamma và output

Với scale output `delta_Y`, host compile per-feature `c_gamma[i]=gamma[i]*delta_X/delta_Y` thành `(M_gamma[i],s_gamma[i])`. Gamma được gộp vào hệ số này, không cần một tensor gamma số thực trong đường suy luận.

```text
qY[i] = sat_Y(RNE(qX[i]*u1*M_gamma[i] / 2^(s_gamma[i]+14+k)))
```

Giữ tích đủ rộng trước bước RNE duy nhất của biểu thức output. Mỗi vector tính một `u1,k`, dùng chung cho mọi feature. Vector input toàn 0 tạo output toàn 0. Output được chuyển qua smoothing/quantize A12 bằng hệ số tương ứng của Linear nhận.

**Lý do:** LUT nhỏ đưa reciprocal square root về miền hẹp; một bước Newton cải thiện seed mà không cần sqrt hoặc phép chia số thực lúc suy luận. Định dạng `t` giữ epsilon ngay cả khi input bằng 0.

## 7. RoPE

ROM dùng position `p=0..511`, pair index `j=0..31`:

```text
omega[j] = 100000^(-2*j/64)
C[p,j] = RNE(D_C*cos(p*omega[j]))
S[p,j] = RNE(D_C*sin(p*omega[j]))
D_C = 2^(b_C-1)-1
```

ROM có 32768 hệ số; `b_C` là độ rộng được khảo sát/chọn trong cấu hình. Scale hệ số là `1/D_C`, zero-point 0; mã sinh được nằm trong `[-D_C,D_C]`. Head và layer dùng chung ROM. Position 0 có `C=D_C,S=0`, nên quay là phép đồng nhất chính xác trước requant output.

Q/K trước quay dùng scale chung trong mỗi head. Với cặp split-half `a=qX[j]`, `b=qX[j+32]`:

```text
n0 = a*C - b*S
n1 = b*C + a*S
qRot[j]    = RNE(n0/D_C)
qRot[j+32] = RNE(n1/D_C)
```

Tích và tổng được giữ chính xác; chỉ rounding sau cộng/trừ. Mã `qRot` giữ scale input, có thể vượt miền mã input; không clip nó trước bước requant sang Q sau RoPE hoặc K cache. Với input signed `b_X`, cận bảo thủ của mỗi tử là `abs(n)<=2*2^(b_X-1)*D_C`; dùng độ rộng signed chứa cả hai đầu cận này.

K đi trực tiếp tới KV8 sau quay; Q chuyển sang định dạng input QK. Chia cho `D_C` là phép chia nguyên có RNE với hằng số ROM đã biết, không thay bằng phép chia xấp xỉ không được đặc tả.

**Lý do:** ROM loại bỏ việc tính sin/cos lúc suy luận. Scale này biểu diễn chính xác hệ số 1 tại position 0; chi phí phép chia hằng số được xét riêng với phép chia biến thiên của Softmax.

## 8. Attention

### 8.1. QK và score

Mỗi head có một scale Q chung cho 64 feature, K dùng scale cache của KV head `h//3`:

```text
A_QK = sum_d(qQ[d]*qK[d])
c_score[h] = delta_Q[h]*delta_K[h//3] / (8*delta_score[h])
qScore = sat_score(requant(A_QK,c_score[h]))
```

Dot-product có 64 tích. Ở cấu hình `combined_high`, Q signed16 có mã `[-32768,32767]`, K signed8 có mã `[-128,127]`. Một tích nằm trong `[-4194176,4194304]`; tổng 64 tích nằm trong `[-268427264,268435456]`. Cần signed30 bit tối thiểu: signed29 chỉ chứa tối đa `268435455`, thiếu đúng mã dương `+2^28`. Export ghi cận này và độ rộng vào `resources.arithmetic_widths`; container accumulator là 32 bit. Scaling thực `1/sqrt(64)=1/8` đã gộp vào hệ số. Áp mask bằng tập key hợp lệ ở §5; không quantize một sentinel số thực.

### 8.2. IndexSoftmax

Với score cùng scale trên một hàng và các key hợp lệ:

```text
m = max(qScore[i]) trên key hợp lệ
d[i] = m-qScore[i]
j[i] = clip(requant(d[i],delta_score*(N_LUT-1)/c),0,N_LUT-1)
E[i] = exp_lut[j[i]] nếu key hợp lệ; ngược lại 0
S = sum(E[i])
```

`c>0` và `N_LUT` là các hằng số cụ thể trong cấu hình. Bảng được sinh offline:

```text
exp_lut[j] = RNE(255*exp(-c*j/(N_LUT-1))), j=0..N_LUT-2
exp_lut[N_LUT-1] = 0
```

Không nội suy LUT. Với LUT32, chỉ số unsigned 5; `E` unsigned 8. Có ít nhất một key ở max và `E=255`, nên `255<=S<=512*255=130560`; tổng cần unsigned 17. Mọi phép cộng tổng chính xác. Không có denominator 0 trên hàng hợp lệ.

### 8.3. Giao diện xác suất rời rạc và PV

Phương án chuẩn hóa từng xác suất của proposal dùng:

```text
qP[i] = RNE((2^b_P-1)*E[i]/S)
delta_P = 1/(2^b_P-1), zero-point = 0
A_PV[d] = sum_i(qP[i]*qV[i,d])
delta_A_PV[h] = delta_P*delta_V[h//3]
qContext = sat_context(requant(A_PV,delta_A_PV/delta_context))
```

`qP` unsigned `b_P`; mã key bị che bằng 0. Mỗi phép chia xác suất có RNE độc lập; không ép tổng mã bằng `2^b_P-1`. Phương án P8 nguyên bản có trường hợp 512 score bằng nhau tạo toàn bộ `qP=0`; P12/P16 là các phương án thay đổi độ chính xác của giao diện này, không phải kết quả mặc định suy ra từ calibration.

Một cận an toàn cho tổng mã là `sum(qP)<=2^b_P-1+256`. Do mã P không âm, mỗi partial sum PV có trị tuyệt đối không quá `128*sum(qP)`. Cận này bao gồm sai số tổng xác suất do rounding.

### 8.4. Giao diện E/S và PV ghép

Phương án ghép giữ nguyên index và LUT ở §8.2, nhưng giao diện Softmax→PV là `E` unsigned 8 cùng denominator chung `S` unsigned 17 cho mỗi query/head. Xác suất tham chiếu là phân số `E[i]/S`; không lưu hoặc làm tròn một tensor P riêng.

```text
A[d] = sum_i(E[i]*qV[i,d])
(M_C,s_C) = compile(delta_V[h//3]/delta_context[h])
qContext[d] = sat_context(RNE(A[d]*M_C/(S*2^s_C)))
```

Nếu `s_C<0`, dịch trái tử `-s_C` bit và dùng mẫu `S`. Không rounding tử hoặc phân số trước phép chia cuối. Mã E bị che bằng 0, không góp vào cả hai tổng.

| Đại lượng | Miền mã được bảo đảm | Độ rộng tối thiểu |
| --- | --- | --- |
| `E*qV` | `[-32640,32385]` | Signed 16 |
| `A`, tối đa 512 tích | `[-16711680,16581120]` | Signed 25 |
| `S` | `[255,130560]` | Unsigned 17 |

Trước xấp xỉ hệ số/output requant, `A/S` nằm trong `[-128,127]`: đây là trung bình có trọng số của các mã V. Giữ đủ độ rộng cho `A*M_C` và `S*2^s_C`; container INT64 không cho phép tự động wrap nếu mẫu hoặc tử rộng hơn 64 bit.

**Lý do của phương án ghép:** bỏ một bước rounding và dùng tích E8×V8. Nó cũng tránh trường hợp P8 toàn 0. Số phép chia là 64 trên mỗi query/head, so với `N` phép chia xác suất của phương án rời rạc; lợi ích về số phép chia xuất hiện khi `N>64`.

Sau PV, ghép 9 head theo thứ tự head rồi feature thành 576 phần tử. Context đi qua smoothing/quantize A12 của O projection; output O được chuyển về scale residual trước khi cộng.

## 9. FFN và SiLU

Gate/up projection có input A12 riêng sau smoothing; output chuyển sang định dạng của từng nhánh. SiLU dùng PWL không đều với hai nhánh ngoài miền:

```text
qGate < B[0]       : qSiLU = 0
B[j]<=qGate<B[j+1] : qSiLU = sat_SiLU(RNE((qGate*A[j]+Beta[j])/2^s[j]))
qGate >= B[M]      : qSiLU = sat_SiLU(requant(qGate,delta_gate/delta_SiLU))
```

Breakpoint là mã nguyên; tại breakpoint nội bộ chọn đoạn bên phải. Các bảng `B,A,Beta,s` được compile theo scale input/output của từng layer. Hai số hạng affine dùng cùng shift trong một đoạn và được cộng chính xác trước RNE; không làm tròn riêng slope term và intercept term.

Hệ số tham chiếu được fit offline trên lưới có dấu `4097` điểm trong `[-T,T]`. Phân đoạn không đều được chọn bằng cải thiện sai số sau lượng tử hóa hệ số; không dùng selection để fit hệ số. `T`, số đoạn và độ chính xác hệ số lấy từ cấu hình cụ thể. LUT/hệ số runtime là các bảng nguyên đã compile; không tính sigmoid/exp hoặc fit lại khi suy luận.

Sau SiLU:

```text
qProduct_raw = qSiLU*qUp
delta_Product_raw = delta_SiLU*delta_Up
qProduct = sat_product(requant(qProduct_raw,delta_Product_raw/delta_product))
```

Tích hai nhánh là phép nhân số nguyên chính xác trước requant, không phải một hàm xấp xỉ riêng. Output product đi qua smoothing/quantize A12 của down projection. Output down được chuyển về scale residual rồi cộng.

**Lý do:** PWL tính trực tiếp SiLU bằng một nhân–cộng và tìm đoạn; các đoạn không đều dành độ phân giải cho vùng cong thay vì tăng bảng trên toàn miền.

## 10. Residual

Định dạng residual có thể khác định dạng nhánh O/down. Để cộng về target scale `delta_R`, dùng 20 guard fractional bit:

```text
qL_guard = requant(qL,delta_L/delta_R * 2^20)
qR_guard = requant(qR,delta_right/delta_R * 2^20)
qResidual = sat_residual(RNE((qL_guard+qR_guard)/2^20))
```

Mỗi bước align có RNE tại độ chính xác guard; cộng hai mã guard chính xác, rồi RNE và saturation một lần về output. Độ rộng guard được tính theo hệ số và miền nguồn của từng nhánh; không mặc định 48 bit khi dùng scale per-channel. Bản mô phỏng dùng container INT64 cho mã guard và tổng, với cận đã kiểm tra để không clipping trung gian hoặc overflow. Scale per-channel được broadcast theo feature; hai nhánh phải được đưa về cùng target scale tại mỗi feature trước phép cộng.

Các scale tĩnh giữ nguyên giữa prefill/decode. Nếu residual dùng per-channel, bảng scale có 576 phần tử ở mỗi biên; chi phí metadata và bước align input RMSNorm phải được tính cùng với lợi ích giảm bit.

**Lý do:** scale riêng theo channel có thể giữ chi tiết của các feature nhỏ khi một feature có outlier lớn. Guard bit giảm sai số khi hai nhánh gần triệt tiêu nhau.

## 11. Embedding, logits và chọn token

Embedding đọc `qW[token_id,:]`, scale hàng `delta_W[token_id]`. Chuyển về định dạng residual đầu tiên bằng hệ số `delta_W[token_id]/delta_embedding`; không coi scale của các hàng khác nhau là cùng scale.

LM head dùng chính bộ mã W đó, input A12 không smoothing, INT32 accumulator như §4. Raw logits có scale per-vocabulary-row `delta_A_lm_head*delta_W[o]`. Chuyển tất cả về scale logits chung trước khi so mã hoặc trả scorer.

Greedy argmax chọn mã logits lớn nhất; khi hòa chọn token ID nhỏ nhất. Scorer nhận giá trị tái dựng theo scale logits chung. Không so trực tiếp các raw accumulator đang có scale khác nhau.

**Lý do:** dùng chung mã W giữ quan hệ embedding/head; scale logits chung làm phép so token có cùng đơn vị.

## 12. Định dạng lưu/nạp

Tất cả giá trị nhiều byte dùng little-endian. Ma trận W row-major `[out,in]`; vector hệ số theo thứ tự output hoặc input feature được ghi trong mapping; cache theo `[B,Hkv,L,D]` native head. Padding bằng 0, không chèn phần tử padding vào reduction logic.

| Dữ liệu | Container phần mềm/trao đổi |
| --- | --- |
| W8, K8, V8 | Signed int8 |
| Mã signed ≤16, gồm A12 | Signed int16, sign-extend đúng từ độ rộng logic |
| Mã unsigned ≤16 | Unsigned int16 |
| Mã signed/unsigned 17–32 | Container 32 bit tương ứng |
| Trung gian 33–64 bit | Container 64 bit tương ứng |
| Trung gian rộng hơn 64 | Số nguyên đủ rộng; không cắt bớt trước bước rounding/thu hẹp đã quy định |
| Token ID | Unsigned int16 |
| Position/cache length | Unsigned int16; miền logic theo §5 |
| Multiplier `M` | Signed INT32; `p` là số bit giới hạn trị tuyệt đối, thêm một bit dấu |
| Shift `s` | Signed INT8 nếu toàn bộ giá trị trong `[-128,127]`, nếu không Signed INT16 |
| RoPE ROM | Signed int8 cho `b_C=8`, nếu không Signed int16; shape `[512,32]` cho mỗi bảng |
| RMS seed LUT | UQ0.14, lưu trong Signed INT16; epsilon code Signed INT32 |
| Softmax exponential LUT | Unsigned INT8; tổng `S` là unsigned 17 bit, không cần ROM riêng |
| SiLU PWL | Breakpoint, slope và intercept Signed INT32; shift Signed INT8 nếu vừa miền, ngược lại Signed INT16; một bộ compile cho mỗi layer |

Packing này không quy định bus hoặc thanh ghi SoC. Độ rộng logic dùng để thiết kế datapath vẫn là số bit trong contract, kể cả khi container rộng hơn. Các bảng hệ số/LUT phải được nạp nguyên vẹn; không lượng tử hóa lần nữa lúc load.

Bundle được ánh xạ qua [`config.json`](../../quantize/results/numerical/contract_search/combined_high/config.json), [`coefficients.safetensors`](../../quantize/results/numerical/contract_search/combined_high/coefficients.safetensors) và [`weights.safetensors`](../../quantize/results/numerical/contract_search/weights.safetensors). Trong `config.formats`, mỗi tên điểm ánh xạ tới `bits`, signedness, miền mã, scale, zero-point, axis và miền thực. Tensor `.M`/`.shift` cùng tiền tố là một cặp cho phép chuyển biểu diễn; thứ tự phần tử theo axis trong `formats`. Bundle hệ số chứa các cặp multiplier–shift, ROM RoPE, LUT Softmax/RMS và bảng PWL theo layer. Qparams frozen được tham chiếu từ candidate nguồn, không chép lại vào bundle. Export đã so toàn bộ tensor hệ số đã serialize với trình biên dịch runtime; cấu hình được chọn cũng đã reload và khớp bitwise ở logits full/cached. Adapter kiểm tra chỉ nạp `config.json`, không nạp bundle hệ số.

`config.json` giữ scale dạng số thực làm metadata và chứa bảng SiLU tham chiếu để tái tạo offline. Datapath dự kiến chỉ dùng mã, hệ số nguyên và bảng đã xuất. Campaign hiện dùng `ContractAdapter` như bộ chuẩn bị/mô phỏng trên host: nó đọc format trong config và biên dịch lại M/shift khi chạy; nó **không nạp** `coefficients.safetensors` vào suy luận. Bước export đọc lại bundle và so từng M/shift, ROM, LUT, epsilon và bảng PWL với trình biên dịch runtime tương ứng. Kiểm tra config reload chỉ chứng minh phép mô phỏng tái lập theo config; chưa phải kiểm tra nạp bundle vào một integer kernel.

## 13. Dung lượng dữ liệu cố định

| Payload | Dung lượng logic |
| --- | --- |
| W8 decoder | `30*(2*576*576+2*192*576+3*1536*576)=106168320` byte |
| W8 embedding/head dùng chung | `49152*576=28311552` byte |
| Tổng W8 | `134479872` byte = `128.25 MiB` |
| K/V một layer, context 512 | `2*3*512*64=196608` byte |
| K/V 30 layer, context 512 | `5898240` byte = `5.625 MiB` |

Các số này không gồm hệ số, gamma, LUT, padding/alignment hoặc buffer. Bộ W dùng chung gồm 211 ma trận INT8; `weights.safetensors` có payload mã 134479872 byte và file serialize 134502896 byte. Thay độ rộng trung gian không làm giảm payload W/KV đã cố định.

## 14. Điều kiện kiểm chứng

### 14.1. Đối chiếu số nguyên

- Golden integer và RTL thực hiện cùng bộ mã W, hệ số, LUT và quy tắc trong cấu hình được chọn phải khớp từng mã tại các biên quan sát.
- Full forward và prefill/decode cho cùng token/vị trí phải tạo cùng mã logits. Không dùng scale chung cho cả prompt hoặc dữ liệu tương lai để chọn định dạng của token hiện tại.
- Cache append giữ nguyên prefix K/V; mỗi token mới được quantize đúng một lần. Masked key không góp vào max hoặc tổng normalization.
- Oracle số học dùng số nguyên đủ rộng hoặc phân số độc lập, gồm số âm, half-step, saturation, cực trị, cancellation, vị trí 0/511, PWL breakpoint, vector norm 0, attention uniform/peaked và độ dài 512.
- Load/save không thay mã W/hệ số/LUT hoặc thứ tự feature/head. Greedy dùng cùng quy tắc hòa điểm ở §11.

### 14.2. Bằng chứng từ backend khảo sát

Phép đo riêng từng biên và từng hàm dùng frozen fake-quant làm nền. Campaign lưu 483 biên, 151 phép thử phi tuyến và 32 lượt family; các phép đo này dùng để xếp hạng độ nhạy. Một cửa sổ, lượt family hoặc quick8 không chứng minh cấu hình đạt quality gate. Kết quả đầy đủ và cấu hình của từng phép đo nằm trong [campaign.json](../../quantize/results/numerical/contract_search/campaign.json).

Các cấu hình kết hợp dùng phép toán nguyên cho requant, residual, nonlinear và các bước thu hẹp. MAC lớn được mô phỏng bằng GEMM FP64 trên mã nguyên. Cận **tổng trị tuyệt đối các tích**, không chỉ cận tổng sau triệt tiêu, nằm dưới `2^53`:

| Reduction | Cận đủ dùng |
| --- | --- |
| Linear A12×W8, tối đa 1536 tích | `1536*2048*128=402653184` |
| QK, Q tối đa 24 bit, 64 tích | `64*2^23*128=2^36` |
| PV rời rạc, P tối đa unsigned 16, 512 tích | `512*65535*128<2^32` |
| PV ghép E8×V8 | `512*255*128=16711680<2^24` |

Vì từng tích và mọi partial sum đều là số nguyên biểu diễn chính xác, FP64 GEMM cho cùng accumulator như reduction số nguyên trong các miền này. Riêng E8×V8 có thể dùng FP32 code GEMM theo cận trong bảng. Square/reduction RMSNorm tối đa 56 bit dùng phép toán nguyên, không dựa vào FP64 để cộng chính xác.

Đây là backend mô phỏng mã, chưa phải phần mềm golden integer thuần kernel số nguyên hoặc bằng chứng RTL/synthesis. Bản phần mềm số nguyên được hiện thực từ contract vẫn cần regression với bộ mã đã xuất.

### 14.3. Quality gate trên selection

Dùng [protocol PTQ hiện có](../../quantize/plans/ptq_plan.md#bước-2--có-bộ-chấm-chất-lượng-chạy-được-trên-fp32):

| Phép đo | Dữ liệu | Điều kiện |
| --- | --- | --- |
| PPL full | 64 cửa sổ selection × 512 token, 32704 target | Không quá `1.05*22.574714201210707 = 23.703449911271242`. |
| PIQA | 919 câu selection; chấm tổng LL phần đáp án | Giảm không quá 0.02 accuracy so `625/919`; tương đương ít nhất 607 câu đúng. |
| Decode, prefill 32 | 8 cửa sổ × 64 target | PPL không quá `1.05*26.676072498453824 = 28.009876123376517`. |
| Decode, prefill 448 | 8 cửa sổ × 64 target | PPL không quá `1.05*12.019438254052904 = 12.62041016675555`. |

64 target decode bao gồm token đầu ngay sau prompt. Gate áp dụng PPL tổng hợp riêng từng regime, không áp một ngưỡng mới cho từng cửa sổ lẻ. KL và top-1 agreement là phép đo chẩn đoán, không thay thế các gate này. Heldout chỉ dùng xác nhận sau khi lựa chọn được chốt theo PLAN/D02.

### 14.4. Kết quả lựa chọn trên selection

Cấu hình được đề xuất là `combined_high`. Trong 483 điểm format, nó dùng 393 điểm signed 16 bit, 30 điểm xác suất unsigned P12 và 60 điểm residual signed 24 bit; scale từng điểm và axis chính xác nằm trong `config.formats`. Tham số chung là coefficient precision `p=24`, RMS seed LUT64 với `F_t=40`, RoPE coefficient 16 bit, Softmax LUT32 với `c=8` và P12 rời rạc, SiLU PWL32 đoạn với ngưỡng 8. Mỗi dịch xuất được chứa trong INT8. Scale W/A/KV và SmoothQuant vẫn là frozen source.

| Candidate | Full PPL / gate 23.7034499113 | PIQA / gate ≥607 | Cache32 / gate 28.0098761234 | Cache448 / gate 12.6204101668 | Kết quả |
| --- | ---: | ---: | ---: | ---: | --- |
| `combined_high` | 22.8212126292 (+1.0919% so FP32) | 612/919; giảm 0.014146 | 26.8071147129 | 12.1201981256 | Đạt mọi gate |
| `combined_mixed` | 26.4760330739 (+17.2818%) | Không chạy sau khi trượt PPL | Không chạy sau khi trượt PPL | Không chạy sau khi trượt PPL | Loại: trượt PPL |
| `combined_guarded_fused` | 25.6511196453 (+13.6277%) | Không chạy sau khi trượt PPL | Không chạy sau khi trượt PPL | Không chạy sau khi trượt PPL | Loại: trượt PPL |

PPL full dùng 64 cửa sổ selection, 32704 target; PIQA dùng 919 câu. Cache mỗi regime tổng hợp 8 lượt, 512 target; gate áp trên PPL tổng hợp. Vì chỉ `combined_high` đạt gate, cấu hình này là lựa chọn duy nhất trong các ứng viên đã đo, không phải tối ưu toàn cục. Campaign không dùng heldout để lựa chọn.

### 14.5. So sánh tài nguyên

| Candidate | Trạng thái gate | Boundary payload / container ở context 512 (byte) | Coefficient tensor / file serialize (byte) | ROM/LUT/RMS/PWL (byte) | Phép normalize Softmax trong dense shape 512 |
| --- | --- | ---: | ---: | ---: | ---: |
| `combined_high` | Đạt | 670826496 / 723910656 | 2279050 / 2479970 | 78540 | 2359296, P12 rời rạc |
| `combined_mixed` | Trượt PPL | 451215360 / 533299200 | 2668348 / 2881060 | 36348 | 2359296, P12 rời rạc |
| `combined_guarded_fused` | Trượt PPL | 432733056 / 485683200 | 2679858 / 2893066 | 36348 | 294912, E8+S17 ghép |

Boundary payload cộng tất cả tensor tại context512, container bytes phản ánh kiểu lưu/nạp đo được; hai số này không phải peak SRAM. Phép normalize là số đếm theo dense software shape; causal mask có thể giảm công việc đã schedule. Bundle coefficient tensor của `combined_high` gồm 2200510 byte multiplier/shift và 78540 byte bảng (65536 RoPE, 32 Softmax, 372 RMS/epsilon, 12600 SiLU). Bundle chung không gồm 134479872 byte W và 5898240 byte KV ở context512.

`combined_mixed` và `combined_guarded_fused` có payload boundary nhỏ hơn, nhưng không vượt PPL gate nên không phải lựa chọn hợp lệ. Chỉ `combined_high` đạt gate, do đó chưa có so sánh tài nguyên giữa nhiều cấu hình đạt gate. Payload cộng qua các biên là proxy dung lượng/traffic của graph, không phải peak SRAM hoặc diện tích FPGA. Kết quả còn phụ thuộc lịch streaming và cách dùng lại datapath. Không có số liệu synthesis area, timing hoặc power; các phép đo này chỉ xếp hạng ba ứng viên đã khảo sát.
