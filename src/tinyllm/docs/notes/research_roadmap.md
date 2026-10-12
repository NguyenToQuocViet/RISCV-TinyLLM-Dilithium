Mục tiêu của lộ trình là xây dựng mức hiểu đủ sâu để hiện thực RTL, tập trung vào SmolLM2-135M và luồng dữ liệu inference thay vì nghiên cứu LLM theo hướng AI tổng quát. Tài liệu này là roadmap tham khảo cho quá trình học và triển khai; các mức độ ưu tiên có thể được điều chỉnh theo phạm vi của từng giai đoạn.

SmolLM2-135M chính thức dùng `LlamaForCausalLM`, với `hidden_size=576`, `intermediate_size=1536`, 30 decoder layers, 9 query heads, 3 KV heads, vocabulary 49,152, context tối đa 8,192, SiLU, RMSNorm và RoPE với `theta=100000`; input/output embedding được tie với nhau. Tokenizer của model là `GPT2Tokenizer`, tức byte-level BPE.

---

# 1. Phạm vi kiến thức cần nắm

```text
TEXT
 │
 ▼
① GPT-2 Byte-level BPE Tokenizer
 │
 ▼
Token IDs [T]
 │
 ▼
② Token Embedding
 │
 ▼
X [T, 576]
 │
 ╔══════════════════════════════════════╗
 ║ ③ Transformer Decoder Layer × 30   ║
 ║                                      ║
 ║   RMSNorm                            ║
 ║      │                               ║
 ║   Q / K / V Linear Projection       ║
 ║      │                               ║
 ║   reshape heads                      ║
 ║      │                               ║
 ║   RoPE(Q,K)                          ║
 ║      │                               ║
 ║   KV Cache                           ║
 ║      │                               ║
 ║   GQA                                ║
 ║      │                               ║
 ║   QKᵀ / √d                           ║
 ║      │                               ║
 ║   Causal Mask                        ║
 ║      │                               ║
 ║   Softmax                            ║
 ║      │                               ║
 ║   Attention × V                      ║
 ║      │                               ║
 ║   Output Projection                  ║
 ║      │                               ║
 ║   Residual Add                       ║
 ║      │                               ║
 ║   RMSNorm                            ║
 ║      │                               ║
 ║   gate_proj ─► SiLU ─┐              ║
 ║                       ×─► down_proj   ║
 ║   up_proj ────────────┘              ║
 ║      │                               ║
 ║   Residual Add                       ║
 ╚══════════════════════════════════════╝
 │
 ▼
④ Final RMSNorm
 │
 ▼
⑤ LM Head
 │
 ▼
Logits [49152]
 │
 ▼
⑥ Greedy / Sampling
 │
 ▼
NEXT_TOKEN
 │
 └────────────► đưa lại vào model
```

---

# 2. Chặng 0 — Hiểu autoregressive inference

Nên bắt đầu bằng việc nắm quy trình autoregressive inference, trước khi đi vào attention.

Các khái niệm nền tảng cần nắm:

```text
"I love"

tokenizer

[ID_I, ID_love]

      ↓ model

logits cho 49152 token

      ↓

next_token = "you"

      ↓

"I love you"

      ↓ model tiếp

next_token = ...
```

Khái niệm quan trọng nhất:

$$
P(x_{t+1}|x_0,x_1,...,x_t)
$$

LLM không trực tiếp sinh một câu. Nó **dự đoán một token kế tiếp**, rồi lặp lại.

### Phạm vi cần nắm

**Mức độ AI: cơ bản; không yêu cầu đọc paper.**

Các nội dung cần hiểu:

* causal/autoregressive model;
* token là gì;
* logits là gì;
* tại sao output trở thành input cho vòng tiếp theo;
* causal attention nghĩa là token hiện tại không nhìn future token.

Phần giải thích causal decoder của Hugging Face cung cấp mức tổng quan phù hợp cho nội dung này. ([Hugging Face][4])

**Kết quả cần đạt:** biểu diễn được chu trình:

```text
tokens → model → logits → next token → tokens → model → ...
```

---

# 3. Chặng 1 — Tokenizer: Text → Token IDs

SmolLM2 dùng:

> `GPT2Tokenizer`

với vocabulary:

$$
V=49152
$$

([Hugging Face][2])

Nó thuộc loại **byte-level BPE**.

Ví dụ khái niệm:

```text
"hardware accelerator"

       ↓

["hard", "ware", " accelerator"]

       ↓

[1234, 8921, 17382]
```

Token thực tế tất nhiên phụ thuộc vocab của SmolLM2.

### Nội dung cần nắm

```text
UTF-8 text
   ↓
byte representation
   ↓
BPE merge rules
   ↓
tokens
   ↓
vocabulary lookup
   ↓
token_id
```

### Tài liệu tham khảo

**Không yêu cầu paper.**

Đây không phải phần quan trọng của accelerator.

Tài liệu Byte-level BPE của Hugging Face là đủ cho phạm vi này; tài liệu giải thích cả BPE và đặc điểm GPT-2 byte-level BPE. ([Hugging Face][5])

### RTL?

Không nên hiện thực tokenizer bằng RTL.

Trong SoC, tokenizer nên được đặt ở phía phần mềm:

```text
RISC-V
   │
 tokenizer()
   ↓
token IDs
   │
   ▼
LLM accelerator
```

Vì tokenizer có string manipulation, lookup, merge rule, control flow khá irregular nhưng workload cực nhỏ so với Transformer.

**Mức học: 2/5.**

---

# 4. Chặng 2 — Embedding: Token ID → vector 576 chiều

Đây là phần có độ phức tạp thấp.

SmolLM2 có:

```text
vocab_size  = 49152
hidden_size = 576
```

nên embedding matrix:

$$
E\in R^{49152\times576}
$$

Token:

```text
token_id = 1234
```

chỉ đơn giản:

$$
x=E[1234]
$$

kết quả:

```text
x = vector [576]
```

### Tài liệu tham khảo

**Không yêu cầu paper.**

Các nội dung cần hiểu:

* tensor;
* vector;
* matrix indexing;
* embedding là lookup table;
* shape.

Không thuộc phạm vi cần thiết của roadmap là lý thuyết embedding trong NLP như Word2Vec.

### Hardware

Về RTL:

```text
token_id
   ↓
address generator
   ↓
memory
   ↓
576 embedding values
```

Đây chủ yếu là **memory access**, không phải computation.

**Mức học: 1/5 AI, 3/5 hardware.**

---

# 5. Chặng 3 — Linear/GEMM: nền móng quan trọng nhất

Trước khi nghiên cứu attention, cần nắm chắc:

$$
y=Wx
$$

và:

$$
Y=XW
$$

Cần sử dụng thành thạo:

```text
vector × matrix
matrix × matrix

dimensions
dot product
MAC
tiling
```

Ví dụ Q projection của SmolLM2:

```text
x             [576]

Wq            [576 × 576]

Q = Wq x      [576]
```

K và V nhỏ hơn do GQA:

```text
Wk            [192 × 576]
Wv            [192 × 576]

K             [192]
V             [192]
```

vì:

$$
3\ KV\ heads\times64=192
$$

### Tài liệu tham khảo

**Không yêu cầu paper.**

Đây là linear algebra + digital design.

Nội dung này nên được tiếp cận theo hướng hardware nhiều hơn AI:

```text
dot product
MAC
accumulator
PE
systolic/MAC array
tiling
data reuse
```

`llama2.c` là tài liệu tham khảo phù hợp: hàm `matmul()` minh họa trực tiếp phép tính cần hiện thực ở RTL, đồng thời cho thấy đây là khu vực chiếm phần lớn computation của model. ([GitHub][6])

**Đây là nền móng số 1 của accelerator.**

---

# 6. Chặng 4 — RMSNorm

Bây giờ mới bước vào decoder layer.

SmolLM2 dùng **pre-RMSNorm**.

Input:

$$
x=[x_0,x_1,...,x_{575}]
$$

RMS:

$$
RMS(x)=
\sqrt{
\frac{1}{576}
\sum_i x_i^2+\epsilon
}
$$

output:

$$
y_i=w_i\frac{x_i}{RMS(x)}
$$

SmolLM2:

$$
\epsilon=10^{-5}
$$

([Hugging Face][1])

### Tài liệu tham khảo

**Có, nhưng chỉ cần đọc phần liên quan trực tiếp.**

Đọc:

**Root Mean Square Layer Normalization — Zhang & Sennrich**

Các nội dung cần hiểu:

* LayerNorm làm gì;
* RMSNorm bỏ mean subtraction;
* công thức RMSNorm.

Không cần đọc phần experiments hoặc training. ([arXiv][7])

Sau đó đọc implementation trong `llama2.c`:

```text
square
 ↓
sum
 ↓
divide N
 ↓
+ epsilon
 ↓
rsqrt
 ↓
multiply x
 ↓
multiply weight
```

([GitHub][6])

### Hardware

Rất quan trọng:

```text
x
│
├─ x²
│
├─ reduction SUM
│
├─ /576
│
├─ + eps
│
├─ rsqrt       ← nonlinear/SFU
│
└─ × x × weight
```

**Mức học: 4/5.**

---

# 7. Chặng 5 — Q, K, V + GQA

Đây là giai đoạn nghiên cứu attention một cách đầy đủ.

SmolLM2:

```text
hidden_size = 576

num_Q_heads  = 9
num_KV_heads = 3

head_dim = 576 / 9
         = 64
```

([Hugging Face][1])

Sau RMSNorm:

```text
x [576]
```

linear projection:

```text
Q = Wq x → [576]
K = Wk x → [192]
V = Wv x → [192]
```

reshape:

```text
Q → [9 heads × 64]

K → [3 heads × 64]
V → [3 heads × 64]
```

### Tại sao?

Vì SmolLM2 dùng **Grouped Query Attention**.

Mapping:

```text
Q0 ─┐
Q1 ─┼──► K0,V0
Q2 ─┘

Q3 ─┐
Q4 ─┼──► K1,V1
Q5 ─┘

Q6 ─┐
Q7 ─┼──► K2,V2
Q8 ─┘
```

Tức là:

$$
9/3=3
$$

query heads dùng chung một KV head.

### Tài liệu paper cần đọc

Đọc:

**GQA: Training Generalized Multi-Query Transformer Models from Multi-Head Checkpoints**

Chỉ cần tập trung vào các phần giải thích:

```text
MHA
↓
MQA
↓
GQA
```

và hiểu tại sao giảm KV heads làm giảm memory/bandwidth. ([arXiv][8])

### Kiến thức attention cơ bản trước GQA

Tham khảo **Attention Is All You Need**, tập trung vào phần:

> 3.2 Attention

để hiểu:

$$
Attention(Q,K,V)
=
softmax
\left(
\frac{QK^T}{\sqrt{d_k}}
\right)V
$$

([arXiv][9])

Không thuộc phạm vi của roadmap:

* encoder-decoder translation;
* training;
* positional encoding sinusoidal của Transformer gốc;
* multi-GPU training.

**Mức học: 5/5.**

---

# 8. Chặng 6 — RoPE

Sau Q/K projection:

```text
Q
K
 │
 ▼
RoPE
```

SmolLM2 không cộng positional embedding vào `x`.

Nó **rotate Q và K** dựa trên vị trí token.

Khái niệm đơn giản với một cặp:

$$
\begin{bmatrix}
x'_0\\
x'_1
\end{bmatrix}
=
\begin{bmatrix}
\cos\theta &-\sin\theta\\
\sin\theta &\cos\theta
\end{bmatrix}
\begin{bmatrix}
x_0\\
x_1
\end{bmatrix}
$$

SmolLM2 dùng:

```text
rope_theta = 100000
```

([Hugging Face][1])

### Tài liệu tham khảo

**Có.**

Đọc:

**RoFormer: Enhanced Transformer with Rotary Position Embedding**

Chỉ cần tập trung vào:

* motivation;
* rotation;
* cách position được đưa vào Q/K;
* relative position xuất hiện trong \(QK^T\).

Không cần đọc phần benchmark của RoFormer. ([arXiv][10])

Sau đó đọc implementation `apply_rotary_pos_emb()` của Transformers để thấy chính xác:

```text
q*cos + rotate_half(q)*sin
k*cos + rotate_half(k)*sin
```

([GitHub][11])

### Hardware

Không nhất thiết phải tính các hàm sau tại runtime:

```text
sin()
cos()
```

runtime.

Có thể:

```text
position
   ↓
sin/cos LUT
   ↓
MUL + ADD/SUB
```

---

# 9. Chặng 7 — Attention + Softmax + Causal Mask

Bây giờ kết nối mọi thứ.

Đối với một Q head:

$$
score_t=
\frac{Q\cdot K_t}{\sqrt{64}}
$$

với tất cả previous tokens:

```text
Qcurrent

     dot
      │
K0 ───┤
K1 ───┤
K2 ───┤
...   │
Kt ───┘

 ↓

scores [t+1]
```

Sau đó:

$$
a_i=
\frac{e^{s_i}}{\sum_j e^{s_j}}
$$

rồi:

$$
output=\sum_i a_iV_i
$$

### Numerical stability của Softmax

Không làm trực tiếp:

$$
e^{x_i}
$$

mà:

$$
softmax(x_i)=
\frac{e^{x_i-\max(x)}}{
\sum_j e^{x_j-\max(x)}
}
$$

`llama2.c` có implementation cực kỳ dễ đọc: max → subtract → exp → reduction sum → division. ([GitHub][6])

### Tài liệu tham khảo cho Softmax

**Không yêu cầu paper riêng.**

Chỉ cần nắm công thức và numerical stability.

### Causal mask?

**Không yêu cầu paper riêng.**

Trong prefill:

```text
token 0 → nhìn token 0
token 1 → nhìn token 0..1
token 2 → nhìn token 0..2
...
```

Phần causal decoder của Hugging Face là đủ cho nội dung này. ([Hugging Face][4])

### Hardware

Đây là block khá lớn:

```text
DOT PRODUCT
     ↓
scale 1/√64
     ↓
MAX reduction
     ↓
EXP
     ↓
SUM reduction
     ↓
RECIPROCAL
     ↓
normalize
     ↓
weighted V accumulation
```

**Mức học: 5/5.**

---

# 10. Chặng 8 — KV Cache

Đây là phần **bắt buộc nếu mục tiêu là accelerator**, dù thường được trình bày khá ít trong các khóa AI.

Giả sử đã generate:

```text
A B C D
```

Trong quá trình tạo `E`, không nên tính lại:

```text
K_A,V_A
K_B,V_B
K_C,V_C
K_D,V_D
```

Ta lưu:

```text
K cache
┌────┬────┬────┬────┐
│ KA │ KB │ KC │ KD │
└────┴────┴────┴────┘

V cache
┌────┬────┬────┬────┐
│ VA │ VB │ VC │ VD │
└────┴────┴────┴────┘
```

Token E chỉ tính:

```text
KE
VE
```

rồi append.

Hugging Face giải thích KV cache khá trực diện: mỗi layer giữ K/V từ token trước và chỉ append K/V mới trong autoregressive decoding. ([GitHub][12])

### Tài liệu tham khảo

**Không.**

Đọc Hugging Face KV-cache documentation + `llama2.c` là tốt hơn paper.

Trong `llama2.c`, các thành phần tương ứng được thể hiện trực tiếp:

```text
key_cache
value_cache
layer offset
position offset
```

([GitHub][6])

### Với SmolLM2

Mỗi layer, mỗi token:

```text
K = 3 × 64 = 192 values
V = 3 × 64 = 192 values
```

30 layers:

$$
30\times2\times192=11520
$$

giá trị KV/token.

Nếu BF16:

$$
11520\times2\ bytes
\approx22.5\ KiB/token
$$

Đây là lý do GQA quan trọng với hardware.

### Phải học cùng lúc Prefill vs Decode

```text
PREFILL

T tokens
    ↓
matrix × matrix
    ↓
populate KV cache
```

sau đó:

```text
DECODE

1 new token
    ↓
matrix × vector
    ↓
read old KV
    ↓
append new KV
```

Đây là một trong những kiến thức **quan trọng nhất của toàn project**.

---

# 11. Chặng 9 — Output projection + Residual

Sau attention:

```text
9 heads × 64
       ↓
concatenate
       ↓
576
       ↓
Wo
       ↓
576
```

rồi:

$$
x=x+AttentionOutput
$$

### Cần paper?

**Không.**

Linear projection đã được trình bày ở các phần trước.

Residual chỉ là elementwise add:

```text
for i = 0..575:
    x[i] = x[i] + attn_out[i]
```

Chỉ cần hiểu vai trò của residual connection trong kiến trúc Transformer; không cần nghiên cứu ResNet.

---

# 12. Chặng 10 — SwiGLU FFN

Đây là nửa còn lại của Transformer layer.

Input:

```text
x [576]
```

sau RMSNorm:

```text
         ┌── gate_proj ──► [1536] ─► SiLU ─┐
x [576] ─┤                                  ×
         └── up_proj ─────► [1536] ─────────┘
                                             │
                                          [1536]
                                             │
                                         down_proj
                                             │
                                           [576]
```

Công thức:

$$
gate=W_gx
$$

$$
up=W_ux
$$

$$
h=SiLU(gate)\odot up
$$

$$
output=W_dh
$$

với:

$$
SiLU(x)=x\sigma(x)
=
\frac{x}{1+e^{-x}}
$$

SmolLM2 dùng `hidden_act = silu` và `intermediate_size=1536`. ([Hugging Face][1])

### Tài liệu tham khảo

**Nên đọc ở phạm vi ngắn.**

**GLU Variants Improve Transformer — Noam Shazeer**

Chỉ cần tập trung vào:

* GLU;
* SwiGLU;
* công thức.

Không cần đọc phần benchmark. ([arXiv][13])

Sau đó đọc `LlamaMLP` của Hugging Face:

```text
down_proj(
    act(gate_proj(x))
    *
    up_proj(x)
)
```

([GitHub][11])

Và `llama2.c` cũng triển khai đúng luồng này rất rõ. ([GitHub][6])

### Hardware

GEMM engine có thể được tái sử dụng ba lần:

```text
GEMM gate
GEMM up
       ↓
SiLU + elementwise multiply
       ↓
GEMM down
```

Do đó, FFN không yêu cầu một compute architecture hoàn toàn khác.

---

# 13. Hoàn thành một layer và lặp lại 30 lần

Một decoder layer hoàn chỉnh:

```text
x
│
RMSNorm
│
QKV projection
│
RoPE
│
GQA Attention
│
O projection
│
+ x
│
▼
x'
│
RMSNorm
│
SwiGLU FFN
│
+ x'
│
▼
x''
```

SmolLM2-135M làm:

```text
Layer 0
 ↓
Layer 1
 ↓
...
 ↓
Layer 29
```

([Hugging Face][1])

### Kiến thức bổ sung

**Không.**

Đây chỉ là cơ chế tái sử dụng.

Ở cấp RTL, thông thường không cần instantiate 30 accelerator physical layers.

Kiến trúc có thể tổ chức theo hướng:

```text
               ┌───────────────┐
               │ Compute Core  │
               └───────┬───────┘
                       │
Layer 0 weights ───────┤
Layer 1 weights ───────┤
...
Layer 29 weights ──────┘
```

reuse hardware theo thời gian.

---

# 14. Final RMSNorm

Sau layer 29:

```text
x [576]
   ↓
Final RMSNorm
   ↓
h [576]
```

### Tài liệu?

**Không cần gì mới.**

Chính RMSNorm đã học ở trên.

---

# 15. LM Head: 576 → 49,152 logits

Đây là linear projection cuối:

$$
logits=W_{LM}h
$$

Shape:

```text
h          [576]

W_LM       [49152 × 576]

logits     [49152]
```

SmolLM2 có:

```text
tie_word_embeddings = true
```

do đó embedding matrix đầu vào và LM head **share cùng weights**. ([Hugging Face][1])

Conceptually:

```text
             Embedding weights
             [49152 × 576]
              ▲          │
              │          │
token_id ─ lookup        │
                         │
                  reuse/transposed
                         │
hidden [576] ────────────┘
                         ↓
                 logits [49152]
```

### Tài liệu tham khảo

**Không.**

Chỉ cần nắm linear layer.

Nhưng về hardware nó **rất quan trọng**, vì 49,152 × 576 là một matrix khá lớn.

---

# 16. Logits → next_token

Output là logits, không phải probability:

```text
logits =
[
 -2.1,
  3.7,
  0.8,
 ...
]
```

Cách đơn giản nhất:

$$
next\_token=\arg\max(logits)
$$

### Khi phát triển RTL

**Dùng greedy decoding trước.**

```text
logits
  ↓
ARGMAX
  ↓
next_token
```

Giai đoạn này không cần softmax.

Điều này có lợi vì:

> `argmax(softmax(logits)) = argmax(logits)`.

Nhờ đó verification deterministic và đơn giản.

Sau này mới:

```text
logits
  ↓
temperature
  ↓
softmax
  ↓
top-k/top-p
  ↓
random sampling
```

Hugging Face có tài liệu chính thức cho greedy, multinomial, top-k và top-p. ([Hugging Face][14])

### Tài liệu tham khảo

**Không cho giai đoạn đầu.**

Sampling có thể được xử lý ở:

```text
RISC-V / software
```

thay vì RTL.

---

# 17. Sau đó vòng lặp bắt đầu lại

Giả sử output:

```text
next_token = 427
```

thì:

```text
427
 ↓
Embedding
 ↓
Layer 0
 ↓
...
 ↓
Layer 29
 ↓
LM Head
 ↓
next_token2
```

nhưng lần này:

> chỉ đưa **1 token mới** vào compute pipeline và reuse KV-cache cũ.

Đây là **decode loop thực sự**.

---

# 18. Thứ tự học được khuyến nghị

| Thứ tự | Chủ đề                    | Độ sâu cần học | Paper?         | RTL quan trọng |
| -------: | ---------------------------- | ------------------- | -------------- | :-------------: |
|        0 | Autoregressive / causal LM   | cơ bản            | ❌             |     ⭐⭐⭐     |
|        1 | Byte-level BPE tokenizer     | biết hoạt động  | ❌             |       ⭐       |
|        2 | Embedding lookup             | rất cơ bản       | ❌             |      ⭐⭐      |
|        3 | Linear / GEMM / tensor shape | **rất sâu** | ❌             |   ⭐⭐⭐⭐⭐   |
|        4 | RMSNorm                      | sâu                | ✅ RMSNorm     |    ⭐⭐⭐⭐    |
|        5 | Q/K/V projection             | sâu                | Transformer    |   ⭐⭐⭐⭐⭐   |
|        6 | MHA → GQA                   | **rất sâu** | ✅ GQA         |   ⭐⭐⭐⭐⭐   |
|        7 | RoPE                         | sâu                | ✅ RoFormer    |    ⭐⭐⭐⭐    |
|        8 | QKᵀ + causal attention      | **rất sâu** | ✅ Transformer |   ⭐⭐⭐⭐⭐   |
|        9 | Softmax                      | sâu về numerical  | ❌             |   ⭐⭐⭐⭐⭐   |
|       10 | KV cache                     | **rất sâu** | ❌ docs/code   |   ⭐⭐⭐⭐⭐   |
|       11 | O projection + residual      | cơ bản            | ❌             |     ⭐⭐⭐     |
|       12 | SwiGLU / SiLU                | sâu                | ✅ GLU paper   |    ⭐⭐⭐⭐    |
|       13 | Final RMSNorm                | đã biết          | ❌             |      ⭐⭐      |
|       14 | LM Head                      | GEMM đã biết     | ❌             |   ⭐⭐⭐⭐⭐   |
|       15 | Greedy / sampling            | cơ bản            | ❌             |      ⭐⭐      |
|       16 | Prefill vs Decode            | **rất sâu** | ❌             |   ⭐⭐⭐⭐⭐   |

---

# 19. Bộ tài liệu tối thiểu — 8 nguồn cốt lõi

Không cần đọc 20 paper. Bộ tài liệu cốt lõi gồm:

1. **SmolLM2 official config + model card** — dùng để xác định chính xác đặc tính của model được hiện thực. Đối với RTL, `config.json` quan trọng hơn paper SmolLM2. ([Hugging Face][1])
2. **Hugging Face BPE tutorial** — tài liệu tham khảo cho tokenizer. ([Hugging Face][15])
3. **Attention Is All You Need** — tập trung `Scaled Dot-Product Attention` và `Multi-Head Attention`. ([arXiv][9])
4. **RMSNorm paper** — chỉ công thức và motivation. ([arXiv][7])
5. **RoFormer paper** — chỉ RoPE. ([arXiv][10])
6. **GQA paper** — MHA/MQA/GQA. ([arXiv][8])
7. **GLU Variants Improve Transformer** — SwiGLU. ([arXiv][13])
8. **`llama2.c/run.c` + Hugging Face Llama implementation** — nên được đọc kỹ sau khi nắm lý thuyết, vì hai tài liệu này nối trực tiếp công thức với computation thực tế. ([GitHub][6])

---

# 20. Cách học tối ưu cho một RTL engineer

Không nên hoàn thành toàn bộ lý thuyết rồi mới bắt đầu hiện thực.

Mỗi block nên được triển khai theo chu trình:

```text
① Hiểu toán
     ↓
② Nhìn tensor shape của SmolLM2
     ↓
③ Đọc implementation Hugging Face
     ↓
④ Viết mô hình tham chiếu bằng NumPy/Python
     ↓
⑤ Compare với Hugging Face
     ↓
⑥ Viết C/simple reference
     ↓
⑦ Thiết kế datapath RTL
     ↓
⑧ So sánh RTL với mô hình golden bằng Python
```

Ví dụ với RMSNorm:

```text
Paper
 ↓
hiểu công thức
 ↓
input [576]
 ↓
viết `rmsnorm.py`
 ↓
so sánh với PyTorch
 ↓
rmsnorm.c
 ↓
RMSNorm RTL
```

Sau đó mới sang RoPE.

---

# 21. Phân chia quá trình học và hiện thực thành 4 phase

```text
PHASE 1 — Hiểu đường đi dữ liệu
──────────────────────────────
Tokenizer
Embedding
Autoregressive generation
Tensor shapes
Linear/GEMM

              ↓

PHASE 2 — Một Transformer Layer
───────────────────────────────
RMSNorm
QKV
GQA
RoPE
Attention
Softmax
Residual
SwiGLU

              ↓

PHASE 3 — Full SmolLM2 inference
────────────────────────────────
30 layers
Final RMSNorm
LM Head
Greedy next_token
KV Cache
Prefill / Decode

              ↓

PHASE 4 — Hardware
──────────────────
GEMM engine
RMSNorm
RoPE
Softmax
SiLU
KV-cache manager
buffers
DMA
scheduler
quantization
```

**Mốc kết thúc phần lý thuyết không phải là “đọc hết paper”.** Mốc đạt yêu cầu là: với một prompt có `T` token, có thể giải thích được **shape của tensor ở mọi điểm từ `input_ids [T]` tới `logits [T,49152]`**, đồng thời giải thích được tại sao ở bước decode chỉ cần xử lý token cuối cùng cùng KV-cache cũ.

Khi đọc `llama2.c`, **không được sao chép nguyên thông số RoPE của nó sang RTL**: code Llama2.c minh họa RoPE với base 10,000, còn SmolLM2-135M chính thức đặt `rope_theta = 100000`. ([GitHub][6]) Đây là ví dụ cho nguyên tắc: **`llama2.c` dùng để hiểu thuật toán; `SmolLM2 config/weights` là source of truth cho RTL.**

[1]: https://huggingface.co/HuggingFaceTB/SmolLM2-135M/blob/main/config.json?utm_source=chatgpt.com
[2]: https://huggingface.co/HuggingFaceTB/SmolLM2-135M/blob/main/tokenizer_config.json?utm_source=chatgpt.com
[3]: https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct/blob/main/tokenizer_config.json?utm_source=chatgpt.com
[4]: https://huggingface.co/docs/course/chapter1/4?utm_source=chatgpt.com
[5]: https://huggingface.co/docs/course/vi/chapter6/5?utm_source=chatgpt.com
[6]: https://github.com/karpathy/llama2.c/blob/master/run.c?utm_source=chatgpt.com
[7]: https://arxiv.org/abs/1910.07467?utm_source=chatgpt.com
[8]: https://arxiv.org/abs/2305.13245?utm_source=chatgpt.com
[9]: https://arxiv.org/abs/1706.03762?utm_source=chatgpt.com
[10]: https://arxiv.org/abs/2104.09864?utm_source=chatgpt.com
[11]: https://github.com/huggingface/transformers/blob/main/src/transformers/models/llama/modeling_llama.py?utm_source=chatgpt.com
[12]: https://github.com/huggingface/transformers/blob/main/docs/source/en/cache_explanation.md?utm_source=chatgpt.com
[13]: https://arxiv.org/abs/2002.05202?utm_source=chatgpt.com
[14]: https://huggingface.co/docs/transformers/main_classes/text_generation?utm_source=chatgpt.com
[15]: https://huggingface.co/docs/course/chapter6/5?utm_source=chatgpt.com
