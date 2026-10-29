# Đề xuất cơ chế xấp xỉ Softmax, RMSNorm, SiLU và RoPE

Tài liệu tổng hợp thuật toán đề xuất cho bốn nhóm phép toán của TinyLLM.
Các cơ chế dưới đây là ứng viên để hiện thực, chưa phải numerical contract
đã chốt. Ký hiệu `round` chỉ phép làm tròn tới số nguyên gần nhất.

| Nhóm | Cơ chế đề xuất | Phần cần tính lúc suy luận |
| --- | --- | --- |
| Softmax | IndexSoftmax: trừ max, cắt, tra LUT exponential và chuẩn hóa số nguyên | Max, trừ, so sánh, tạo chỉ số, tra bảng, cộng tổng, nhân và chia số nguyên |
| RMSNorm | LOD giảm miền, LUT khởi tạo và một bước Newton–Raphson cho reciprocal square root | Bình phương, cộng tổng, nhân hằng số, LOD, dịch, tra bảng và nhân–cộng |
| SiLU | PWL không đều, tính trực tiếp SiLU bằng hệ số đã lượng tử hóa | Tìm đoạn, tra hệ số và nhân–cộng |
| RoPE | Sin/cos tính trước và lưu ROM; quay Q/K bằng nhân–cộng | Tra bảng theo position và nhân–cộng |

## 1. Softmax — IndexSoftmax

**Nguồn:** [IntAttention, MLSys 2026, §3.1–3.2](https://arxiv.org/html/2511.21513v2#S3).
Kế thừa cơ chế IndexSoftmax của paper.

Với các score hợp lệ $s_i$, Softmax gốc là:

$$
p_i=\frac{e^{s_i-m}}{\sum_j e^{s_j-m}},
\qquad m=\max_j s_j.
$$

Gọi $c$ là ngưỡng cắt dùng để tạo chỉ số và bảng tra.

### Các bước tính

1. **Trừ max và cắt:**

   $$
   d_i=m-s_i,\qquad d'_i=\min(d_i,c).
   $$

2. **Đổi thành chỉ số LUT**, với $N=32$:

   $$
   j_i=\operatorname{round}\left(\frac{N-1}{c}d'_i\right).
   $$

3. **Tra exponential đã lượng tử hóa.** Chuẩn bị bảng offline:

   $$
   L[j]=
   \begin{cases}
   \operatorname{round}\left(255e^{-cj/(N-1)}\right),&0\le j<N-1,\\
   0,&j=N-1.
   \end{cases}
   $$

   Lúc suy luận chỉ tính $E_i=L[j_i]$.

4. **Cộng tổng và chuẩn hóa bằng phép chia số nguyên có làm tròn:**

   $$
   S=\sum_j E_j,\qquad
   P_i=\operatorname{round}\left(\frac{255E_i}{S}\right).
   $$

$P_i$ là mã xác suất; xác suất tương ứng là $\widehat p_i=P_i/255$.
Phần tử bị causal mask có $E_i=P_i=0$ và không tham gia tìm max.

**Phần xấp xỉ:** rời rạc hóa exponential bằng LUT, đặt phần tử cuối bằng 0
và làm tròn kết quả chuẩn hóa. Không nội suy giữa các phần tử LUT.

## 2. RMSNorm — LOD + LUT seed + Newton–Raphson

**Nguồn kế thừa:** giảm miền theo số mũ/mantissa từ
[Kang–Wang, 2026](https://www.mdpi.com/2072-666X/17/1/84);
LUT khởi tạo kết hợp Newton fixed-point có tiền lệ trong
[triển khai LLM trên Loihi 2, Appendix A.2](https://arxiv.org/html/2503.18002v2).
Tổ hợp dưới đây là đề xuất điều chỉnh cho TinyLLM, không phải bản sao nguyên
thuật toán hay số vòng lặp của hai công trình.

RMSNorm gốc:

$$
t=\frac{1}{D}\sum_{j=0}^{D-1}x_j^2+\epsilon,
\qquad r=\frac{1}{\sqrt t},
\qquad y_i=\gamma_i x_i r.
$$

$D$ là chiều vector, $\gamma_i$ là trọng số normalization và
$\epsilon$ là hằng số của model.

### Các bước tính

1. **Tính $t$** bằng bình phương, cộng tổng, nhân với hằng số $1/D$
   và cộng $\epsilon$.

2. **Tách số mũ bằng leading-one detection (LOD):**

   $$
   \ell=\lfloor\log_2 t\rfloor,\qquad
   k=\left\lfloor\frac{\ell}{2}\right\rfloor,\qquad
   m=t\,2^{-2k}.
   $$

   Khi đó $t=2^{2k}m$, $1\le m<4$, và:

   $$
   \frac{1}{\sqrt t}=2^{-k}\frac{1}{\sqrt m}.
   $$

   LOD xác định $\ell$; không tính hàm logarithm ở runtime.

3. **Tra LUT lấy giá trị khởi tạo.** Với bảng $B$ phần tử:

   $$
   j=\left\lfloor\frac{B(m-1)}{3}\right\rfloor,
   \qquad m_j=1+\frac{3(j+1/2)}{B},
   \qquad U[j]\approx\frac{1}{\sqrt{m_j}}.
   $$

   Bảng $U$ được tính và lượng tử hóa offline; lúc suy luận lấy
   $u_0=U[j]$. Cấu hình khởi đầu đề xuất là $B=64$.

4. **Thực hiện một bước Newton–Raphson:**

   $$
   u_1=\frac{u_0(3-mu_0^2)}{2}.
   $$

   Chuỗi phép tính tương ứng:

   $$
   a=u_0u_0,\qquad b=ma,\qquad
   u_1=\frac{u_0(3-b)}{2}.
   $$

5. **Khôi phục số mũ và áp normalization:**

   $$
   \widehat r=2^{-k}u_1,\qquad
   \widehat y_i=\gamma_i x_i\widehat r.
   $$

**Phần xấp xỉ:** giá trị khởi tạo từ LUT, số bước Newton hữu hạn và làm tròn
các phép tính trung gian.
Chỉ tính một $\widehat r$ cho cả vector, rồi dùng chung cho mọi phần tử.

## 3. SiLU — PWL không đều, tối ưu hệ số đã lượng tử hóa

**Nguồn kế thừa:** kiến trúc nội suy tuyến tính từng đoạn từ
[Flex-SFU](https://arxiv.org/html/2305.04546v1), kết hợp nguyên tắc tối ưu
breakpoint/hệ số có xét lượng tử hóa từ
[GQA-LUT, DAC 2024](https://arxiv.org/html/2403.19591v2).
Đây là đề xuất kết hợp; không mặc định sử dụng nguyên bộ hệ số hoặc pipeline
huấn luyện model của các paper.

SiLU gốc:

$$
f(x)=\operatorname{SiLU}(x)=\frac{x}{1+e^{-x}}.
$$

### Chuẩn bị hệ số offline

Chọn các breakpoint không đều:

$$
-T=b_0<b_1<\cdots<b_M=T.
$$

Trong mỗi đoạn, dùng một hàm bậc nhất:

$$
\widehat f_j(x)=a_jx+\beta_j,
\qquad b_j\le x<b_{j+1}.
$$

Tối ưu breakpoint, slope $a_j$ và intercept $\beta_j$ theo sai số của
**phép tính dùng hệ số đã lượng tử hóa**. Một hàm mục tiêu có thể dùng là:

$$
\min_{\{b_j,a_j,\beta_j\}}
\sum_{x\in\mathcal X}
\left[f(x)-\widehat f_{\mathrm{integer}}(x)\right]^2,
$$

trong đó $\mathcal X$ là tập điểm dùng để fit, còn
$\widehat f_{\mathrm{integer}}$ đánh giá cả việc làm tròn hệ số và kết quả
nhân–cộng. Chưa cố định số đoạn $M$.

### Các bước tính lúc suy luận

$$
\widehat{\operatorname{SiLU}}(x)=
\begin{cases}
0,&x<-T,\\
a_jx+\beta_j,&b_j\le x<b_{j+1},\\
x,&x\ge T.
\end{cases}
$$

Ở nhánh giữa, tìm đoạn bằng cây so sánh breakpoint, tra cặp hệ số
$(a_j,\beta_j)$, rồi thực hiện một phép nhân–cộng. Hai nhánh ngoài dùng
tiệm cận của SiLU. Không tính sigmoid hoặc exponential ở runtime.

Trong SwiGLU, sau SiLU vẫn thực hiện phép nhân hai nhánh:

$$
g=\operatorname{gate\_proj}(h),\qquad
u=\operatorname{up\_proj}(h),\qquad
z=\widehat{\operatorname{SiLU}}(g)\odot u.
$$

**Phần xấp xỉ:** PWL của SiLU, hệ số hữu hạn và hai nhánh tiệm cận.
Phép nhân với nhánh up không phải một hàm cần xấp xỉ riêng.

## 4. RoPE — ROM sin/cos và phép quay nhân–cộng

**Nguồn:** phép quay của [RoFormer/RoPE](https://arxiv.org/abs/2104.09864).
ROM hệ số tính trước là lựa chọn triển khai cho TinyLLM.

Với chiều head $d$, vị trí token $p$ và tham số $\theta$:

$$
\omega_j=\theta^{-2j/d},\qquad
\phi_{p,j}=p\omega_j,\qquad 0\le j<d/2.
$$

### Chuẩn bị ROM offline

Tính và lượng tử hóa các hệ số:

$$
\widehat C[p,j]\approx\cos(\phi_{p,j}),\qquad
\widehat S[p,j]\approx\sin(\phi_{p,j}).
$$

Lưu hai bảng vào ROM. Với SmolLM2-135M đang xét, $d=64$ và
$\theta=100000$. Các head và layer dùng chung bảng hệ số.

### Các bước tính lúc suy luận

Ghép cặp theo **split-half**:

$$
a=x_j,\qquad b=x_{j+d/2}.
$$

Đọc $\widehat c=\widehat C[p,j]$,
$\widehat s=\widehat S[p,j]$, rồi tính:

$$
\widehat y_j=a\widehat c-b\widehat s,\qquad
\widehat y_{j+d/2}=b\widehat c+a\widehat s.
$$

Áp dụng cùng phép quay cho Q và K. Mỗi cặp cần bốn phép nhân và hai phép
cộng/trừ; không cần tính sin/cos, CORDIC hoặc cập nhật truy hồi ở runtime.

**Phần xấp xỉ:** lượng tử hóa hệ số sin/cos và làm tròn phép nhân–cộng;
không thay công thức quay RoPE.
