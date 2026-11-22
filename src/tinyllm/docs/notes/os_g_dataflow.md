---
title: "Dòng dữ liệu trên OS-G: prefill, decode và attention qua hình vẽ"
date: 2026-11-21
---

```{=latex}
\usetikzlibrary{decorations.pathreplacing,patterns}
\tikzset{
  pe/.style={draw=hcmutdark!55, fill=hcmutblue!10, line width=0.4pt},
  peoff/.style={draw=neutralgray!70, fill=white, dashed, line width=0.4pt},
  peact/.style={draw=accentamber!85!black, fill=white, line width=0.9pt},
  pedone/.style={draw=accentamber!85!black, fill=accentamber!25, line width=0.9pt},
  warr/.style={-{Stealth[length=1.7mm,width=1.4mm]}, draw=hcmutblue, line width=0.8pt},
  aarr/.style={-{Stealth[length=1.7mm,width=1.4mm]}, draw=accentteal!85!black, line width=0.8pt},
  oarr/.style={-{Stealth[length=1.7mm,width=1.4mm]}, draw=accentamber!85!black, line width=0.8pt},
  karr/.style={-{Stealth[length=1.7mm,width=1.4mm]}, draw=hcmutdark, line width=0.6pt},
  mat/.style={draw=hcmutdark, line width=0.5pt},
  thin/.style={draw=neutralgray!40, line width=0.2pt},
  lbl/.style={font=\footnotesize, text=hcmutdark, align=center, inner sep=1pt},
  sub/.style={font=\footnotesize, text=neutralgray, align=center, inner sep=1pt},
  wtxt/.style={font=\footnotesize, text=hcmutblue!75!black, align=center, inner sep=1pt},
  atxt/.style={font=\footnotesize, text=accentteal!65!black, align=center, inner sep=1pt},
  otxt/.style={font=\footnotesize, text=accentamber!65!black, align=center, inner sep=1pt},
  ttl/.style={font=\footnotesize\bfseries, text=hcmutdark, align=center},
  blk/.style={draw=hcmutdark, fill=hcmutblue!10, rounded corners=2pt, font=\footnotesize, text=hcmutdark, align=center, inner sep=3pt},
  eng/.style={draw=hcmutdark, fill=hcmutblue!30, rounded corners=2pt, font=\footnotesize, text=hcmutdark, align=center, inner sep=3pt, line width=0.7pt},
  post/.style={draw=neutralgray, fill=white, rounded corners=2pt, font=\footnotesize, text=hcmutdark, align=center, inner sep=3pt},
  brc/.style={decorate, decoration={brace, amplitude=3pt}, draw=hcmutdark, line width=0.5pt},
}
```

# Ý chính

- Mọi phép trên OS-G có dạng $Y = X \cdot B$: ma trận trái $X$ (activation, $Q$ hoặc $E$, phía 12 bit) vào **cạnh trái**, mỗi hàng của $X$ vào một hàng của mảng; ma trận trên $B$ ($W^{\mathsf T}$, $K^{\mathsf T}$ hoặc $V$, phía 8 bit) vào **cạnh trên**, mỗi cột của $B$ vào một cột của mảng; chiều chung của hai ma trận chạy theo **thời gian**, mỗi chu kỳ một bước. Kết quả nằm yên trong ô, xong thì xả ra.
- **Prefill**: 24 hàng dùng chung một luồng 64 byte mỗi chu kỳ. **Decode**: 4 nhóm nhận 4 luồng khác nhau: 4 tile đầu ra (Linear, LM head), 4 khối key (QK) hoặc 4 phần key (PV).
- Ghi chú này vẽ lại đề xuất trong [os_g_matmul_engine.pdf](os_g_matmul_engine.pdf) (gọi tắt là *ghi chú chính*); chưa có RTL. Chi tiết tự suy ra thêm được ghi *suy ra*.

# Cách đọc hình

Màu trong mọi hình của ghi chú này:

| Màu | Nghĩa |
|------|-----------------------------|
| Xanh dương | Phía 8 bit, vào cạnh trên: trọng số $W$, $K$ và $V$ từ KV cache |
| Xanh ngọc | Phía 12 bit, vào cạnh trái: activation $X$, $Q$, giá trị mũ $E$ |
| Vàng cam | Kết quả: ô đang cộng dồn, tile đầu ra, dữ liệu xả ra |
| Xám nét đứt | Ô tắt xung nhịp (clock gating) hoặc phần bỏ qua |

: Quy ước màu.

Trọng số theo contract lưu dạng $W[o, k]$: hàng $o$ là một đầu ra, $k$ là kênh vào, và $y[o] = \sum_k W[o,k]\,x[k]$. Viết theo ma trận là $Y = X W^{\mathsf T}$, nên **cột $o$ của $W^{\mathsf T}$ (tức hàng $o$ của $W$) vào cột của mảng**. Mảng $24 \times 64$ được vẽ thu nhỏ, thường 8 cột thay cho 64.

Hình \ref{fig:flow} là chuỗi phép của một decoder layer. Ô xanh đậm chạy trên mảng OS-G; ô viền xám chạy ở khối hậu xử lý. Kết quả của phép trước, sau khi requant (đổi sang cách biểu diễn của phép sau), là đầu vào cạnh trái của phép sau.

```{=latex}
\begin{figure}[htbp]\centering\everymath{}
\begin{tikzpicture}[x=1cm,y=1cm, bx/.style={minimum width=13mm, minimum height=8.5mm}]
\def\dx{1.85}
\node[lbl] (in) at (0,0) {vào\\layer};
\node[post,bx] (n1) at (\dx,0) {RMSNorm};
\node[eng,bx] (qkv) at (2*\dx,0) {Linear\\Q, K, V};
\node[post,bx] (rope) at (3*\dx,0) {RoPE\\(Q, K)};
\node[eng,bx] (qk) at (4*\dx,0) {QK};
\node[post,bx] (sm) at (5*\dx,0) {max,\\bảng mũ};
\node[eng,bx] (pv) at (6*\dx,0) {PV};
\node[post,bx] (dv) at (7*\dx,0) {nhân\\$1/S$};
\node[eng,bx] (o) at (8*\dx,0) {Linear\\O};
\node[blk,bx] (kv) at (5*\dx,1.5) {KV cache};
\foreach \a/\b in {in/n1,n1/qkv,qkv/rope,qk/sm,pv/dv,dv/o} \draw[karr] (\a)--(\b);
\draw[karr] (rope)--node[above,sub]{$Q$}(qk);
\draw[karr] (sm)--node[above,sub]{$E$}(pv);
\draw[karr] (rope.north) |- node[pos=0.75,above,sub]{$K$, $V$ mới} (kv.west);
\draw[karr] (kv.south west) -- node[left,sub,pos=0.35]{$K$} (qk.north east);
\draw[karr] (kv.south east) -- node[right,sub,pos=0.35]{$V$} (pv.north west);
\node[post,bx] (r1) at (8*\dx,-2.0) {cộng\\residual};
\node[post,bx] (n2) at (7*\dx,-2.0) {RMSNorm};
\node[eng,bx] (gu) at (6*\dx,-2.0) {Linear\\gate, up};
\node[post,bx] (si) at (5*\dx,-2.0) {SiLU,\\nhân};
\node[eng,bx] (dn) at (4*\dx,-2.0) {Linear\\down};
\node[post,bx] (r2) at (3*\dx,-2.0) {cộng\\residual};
\node[lbl] (out) at (2*\dx,-2.0) {sang\\layer sau};
\draw[karr] (o.east) -- ++(0.25,0) |- (r1.east);
\foreach \a/\b in {r1/n2,n2/gu,gu/si,si/dn,dn/r2,r2/out} \draw[karr] (\a)--(\b);
\node[lbl] (l30) at (0,-3.9) {sau\\layer 30};
\node[post,bx] (n3) at (\dx,-3.9) {RMSNorm};
\node[eng,bx] (lm) at (2*\dx,-3.9) {LM head};
\node[post,bx] (am) at (3*\dx,-3.9) {argmax};
\node[lbl] (tok) at (4*\dx,-3.9) {token\\kế tiếp};
\foreach \a/\b in {l30/n3,n3/lm,lm/am,am/tok} \draw[karr] (\a)--(\b);
\foreach \n/\t in {qkv/{\ref{fig:linpre}, \ref{fig:lindec}}, qk/{\ref{fig:qkdec}, \ref{fig:attpre}}, pv/{\ref{fig:pvdec}, \ref{fig:attpre}}, o/{\ref{fig:linpre}, \ref{fig:lindec}}}
  \node[sub, below=0.4mm of \n] {Hình \t};
\foreach \n/\t in {gu/{\ref{fig:linpre}, \ref{fig:lindec}}, dn/{\ref{fig:linpre}, \ref{fig:lindec}}, lm/{\ref{fig:lindec}}}
  \node[sub, below=0.4mm of \n] {Hình \t};
\node[eng, minimum width=7mm, minimum height=4mm] (lg1) at (9.6,-3.6) {};
\node[lbl, anchor=west] at (lg1.east) {chạy trên mảng OS-G};
\node[post, minimum width=7mm, minimum height=4mm] (lg2) at (9.6,-4.2) {};
\node[lbl, anchor=west] at (lg2.east) {chạy ở khối hậu xử lý};
\end{tikzpicture}
\caption{Một decoder layer đi qua engine. Dòng trên: nhánh attention; dòng giữa (đọc từ phải sang trái): nhánh FFN; dòng dưới: phần cuối model. Số hình dưới mỗi ô xanh trỏ tới hình vẽ dòng dữ liệu của phép đó.}\label{fig:flow}
\end{figure}
```

# Ví dụ $2 \times 2$ theo từng chu kỳ

Mảng output-stationary nhỏ nhất đủ thấy mọi chuyển động: 2 token, 2 kênh vào, 2 đầu ra. Mỗi chu kỳ, một ô nhận $x$ từ trái và $w$ từ trên, cộng $x \cdot w$ vào tổng $S$ của mình, rồi chuyển $x$ sang phải và $w$ xuống dưới. Vì dữ liệu đi qua từng ô một, ô $(m, n)$ nhận cặp thứ $k$ ở chu kỳ $k + m + n + 1$: hàng dưới vào trễ hơn hàng trên một chu kỳ, cột phải trễ hơn cột trái một chu kỳ. Đó là hình bậc thang ở mép trái và mép trên (kiến thức chung về mảng systolic).

```{=latex}
\begin{figure}[htbp]\centering\everymath{}
\newcommand{\cA}[1]{\textcolor{accentteal!65!black}{#1}}
\newcommand{\cW}[1]{\textcolor{hcmutblue!75!black}{#1}}
\newcommand{\cS}[1]{\textcolor{accentamber!65!black}{#1}}
\newcommand{\tbase}{%
  \foreach \ri in {0,1}{\foreach \ci in {0,1}{\draw[pe] (\ci*2.0,-\ri*1.4) rectangle ++(1.6,-0.95);}}%
  \foreach \ri in {0,1}{\draw[aarr] (-0.6,-\ri*1.4-0.475) -- (0,-\ri*1.4-0.475);
                        \draw[aarr] (1.6,-\ri*1.4-0.475) -- (2.0,-\ri*1.4-0.475);}%
  \foreach \ci in {0,1}{\draw[warr] (\ci*2.0+0.8,0.6) -- (\ci*2.0+0.8,0);
                        \draw[warr] (\ci*2.0+0.8,-0.95) -- (\ci*2.0+0.8,-1.4);}}
\newcommand{\ai}[3]{\node[circle, fill=accentteal!80!black, text=white, font=\footnotesize\bfseries, inner sep=0pt, minimum size=4.4mm] at (#1,#2) {#3};}
\newcommand{\aq}[3]{\node[circle, draw=accentteal!80!black, fill=accentteal!12, text=accentteal!65!black, font=\footnotesize\bfseries, inner sep=0pt, minimum size=4.4mm] at (#1,#2) {#3};}
\newcommand{\wi}[3]{\node[circle, fill=hcmutblue, text=white, font=\footnotesize\bfseries, inner sep=0pt, minimum size=4.4mm] at (#1,#2) {#3};}
\newcommand{\wq}[3]{\node[circle, draw=hcmutblue, fill=hcmutblue!12, text=hcmutdark, font=\footnotesize\bfseries, inner sep=0pt, minimum size=4.4mm] at (#1,#2) {#3};}
\newcommand{\pa}[6]{\draw[peact] (#2*2.0,-#1*1.4) rectangle ++(1.6,-0.95);
  \node[font=\footnotesize, align=center, inner sep=0pt] at (#2*2.0+0.8,-#1*1.4-0.475)
    {\cS{#3}${}+{}$\cA{#4}${}\times{}$\cW{#5}\\\cS{${}={}$\textbf{#6}}};}
\newcommand{\pd}[3]{\draw[pedone] (#2*2.0,-#1*1.4) rectangle ++(1.6,-0.95);
  \node[font=\small\bfseries, text=accentamber!65!black] at (#2*2.0+0.8,-#1*1.4-0.475) {#3};}
\begin{tikzpicture}[x=1cm,y=1cm]
% ---- bài toán
\begin{scope}
\node[ttl] at (0.9,1.95) {Bài toán};
\node[font=\footnotesize] at (0.9,0.95) {$\cA{X}\!\begin{bmatrix}\cA{1}&\cA{2}\\\cA{3}&\cA{4}\end{bmatrix}
  \!\times\! \cW{W^{\mathsf T}}\!\begin{bmatrix}\cW{5}&\cW{6}\\\cW{7}&\cW{8}\end{bmatrix}
  \!=\! \cS{Y}\!\begin{bmatrix}\cS{19}&\cS{22}\\\cS{43}&\cS{50}\end{bmatrix}$};
\node[lbl, align=left, anchor=north west] at (-1.5,0.15) {%
  \textbullet\ hàng $m$ của $\cA{X}$ (một token) $\rightarrow$\\\quad hàng $m$ của mảng, từ trái\\
  \textbullet\ cột $n$ của $\cW{W^{\mathsf T}}$ (một đầu ra) $\rightarrow$\\\quad cột $n$ của mảng, từ trên\\
  \textbullet\ kênh $k$ chạy theo thời gian\\
  \textbullet\ $\cS{Y[m,n]}$ ở yên trong ô $(m,n)$};
\end{scope}
% ---- chu kỳ 1
\begin{scope}[shift={(5.6,0)}]
\node[ttl] at (1.8,1.95) {Chu kỳ 1};
\tbase
\ai{-0.3}{-0.475}{1}\aq{-0.8}{-0.475}{2}\aq{-0.8}{-1.875}{3}\aq{-1.3}{-1.875}{4}
\wi{0.8}{0.3}{5}\wq{0.8}{0.85}{7}\wq{2.8}{0.85}{6}\wq{2.8}{1.4}{8}
\pa{0}{0}{0}{1}{5}{5}
\end{scope}
% ---- chu kỳ 2
\begin{scope}[shift={(11.2,0)}]
\node[ttl] at (1.8,1.95) {Chu kỳ 2};
\tbase
\ai{-0.3}{-0.475}{2}\ai{-0.3}{-1.875}{3}\aq{-0.8}{-1.875}{4}
\wi{0.8}{0.3}{7}\wi{2.8}{0.3}{6}\wq{2.8}{0.85}{8}
\pa{0}{0}{5}{2}{7}{19}\pa{0}{1}{0}{1}{6}{6}\pa{1}{0}{0}{3}{5}{15}
\ai{1.8}{-0.475}{1}\wi{0.8}{-1.175}{5}
\end{scope}
% ---- chu kỳ 3
\begin{scope}[shift={(0,-5.0)}]
\node[ttl] at (1.8,1.95) {Chu kỳ 3};
\tbase
\ai{-0.3}{-1.875}{4}\wi{2.8}{0.3}{8}
\pd{0}{0}{19}\pa{0}{1}{6}{2}{8}{22}\pa{1}{0}{15}{4}{7}{43}\pa{1}{1}{0}{3}{6}{18}
\ai{1.8}{-0.475}{2}\ai{1.8}{-1.875}{3}\wi{0.8}{-1.175}{7}\wi{2.8}{-1.175}{6}
\end{scope}
% ---- chu kỳ 4
\begin{scope}[shift={(5.6,-5.0)}]
\node[ttl] at (1.8,1.95) {Chu kỳ 4};
\tbase
\pd{0}{0}{19}\pd{0}{1}{22}\pd{1}{0}{43}\pa{1}{1}{18}{4}{8}{50}
\ai{1.8}{-1.875}{4}\wi{2.8}{-1.175}{8}
\end{scope}
% ---- xả
\begin{scope}[shift={(11.2,-5.0)}]
\node[ttl] at (1.8,1.95) {Sau chu kỳ 4: xả};
\tbase
\pd{0}{0}{19}\pd{0}{1}{22}\pd{1}{0}{43}\pd{1}{1}{50}
\foreach \ci in {0,1} \draw[oarr] (\ci*2.0+0.8,-2.4) -- (\ci*2.0+0.8,-2.85);
\node[otxt, anchor=north] at (1.8,-2.9) {$Y$ ra khối hậu xử lý};
\end{scope}
\end{tikzpicture}
\caption{Mảng OS $2 \times 2$ tính $Y = X W^{\mathsf T}$. Chấm đặc: giá trị đang vào ô trong chu kỳ đó (trên mép hoặc đang chuyển giữa hai ô); chấm nhạt: giá trị còn chờ, xếp bậc thang. Ô viền vàng cam: đang cộng trong chu kỳ đó; ô tô vàng cam: đã xong. Mỗi ô xong thì chép $S$ sang thanh ghi đệm và nhận ngay tile mới; thanh ghi đệm xả kết quả ra ngoài.}\label{fig:toy}
\end{figure}
```

Mảng thật làm y hệt với 24 hàng, 64 cột và $k$ chạy tới 576 hoặc 1536. Khi xả, mỗi chu kỳ ra 64 giá trị (một giá trị mỗi cột), nên một tile 24 hàng xả hết trong 24 chu kỳ. Đây chính là cách ghi chú chính tính con số mảng phải dừng 27% nếu bỏ thanh ghi đệm: $24 / (64 + 24)$ (*suy ra*).

# Linear và LM head

| Lớp | Kênh vào $K$ (số chu kỳ mỗi tile) | Đầu ra $N$ | Số tile 64 cột | Prefill $T = 512$: số tile |
|------------|----------|----------|----------|-------------|
| Q, O | 576 | 576 | 9 | 22 × 9 |
| K, V | 576 | 192 | 3 | 22 × 3 |
| gate, up | 576 | 1536 | 24 | 22 × 24 |
| down | 1536 | 576 | 9 | 22 × 9 |
| LM head | 576 | 49.152 | 768 | chỉ token cuối, như decode |

: Kích thước các phép Linear của SmolLM2-135M (contract §1). 22 tile hàng = 21 tile đủ 24 token và 1 tile lẻ 8 token.

## Prefill: 24 token dùng chung một luồng trọng số

```{=latex}
\begin{figure}[htbp]\centering\everymath{}
\begin{tikzpicture}[x=1cm,y=1cm]
% ---- (a) chia ma trận
\foreach \ri in {1,...,21} \draw[thin] (0,-\ri*0.2) -- (2.0,-\ri*0.2);
\fill[accentteal!40] (0,-0.6) rectangle (2.0,-0.8);
\draw[mat] (0,0) rectangle (2.0,-4.4);
\foreach \ci in {1,...,8} \draw[thin] (2.4+\ci*0.4,0.4) -- (2.4+\ci*0.4,2.4);
\fill[hcmutblue!45] (3.2,0.4) rectangle (3.6,2.4);
\draw[mat] (2.4,0.4) rectangle (6.0,2.4);
\foreach \ri in {1,...,21} \draw[thin] (2.4,-\ri*0.2) -- (6.0,-\ri*0.2);
\foreach \ci in {1,...,8} \draw[thin] (2.4+\ci*0.4,0) -- (2.4+\ci*0.4,-4.4);
\fill[accentamber!75] (3.2,-0.6) rectangle (3.6,-0.8);
\draw[mat] (2.4,0) rectangle (6.0,-4.4);
\draw[densely dashed, neutralgray] (2.0,-0.7) -- (3.2,-0.7);
\draw[densely dashed, neutralgray] (3.4,0.4) -- (3.4,-0.6);
\draw[brc] (-0.08,-0.8) -- node[left=3pt, atxt]{24 token\\(tile hàng $i$)} (-0.08,-0.6);
\draw[brc] (3.2,2.48) -- node[above=3pt, wtxt]{64 đầu ra (tile cột $j$)} (3.6,2.48);
\node[wtxt] at (0.95,1.75) {$W^{\mathsf T}$: $576 \times N$\\trọng số};
\node[sub] at (2.12,1.05) {$k$\\$\downarrow$};
\node[sub, anchor=south] at (1.0,0.02) {$k$: $0 \rightarrow 575$};
\node[atxt, anchor=north] at (1.0,-4.5) {$X$: $T \times 576$\\activation};
\node[otxt, anchor=north] at (4.2,-4.5) {$Y = X W^{\mathsf T}$: $T \times N$};
\node[otxt, anchor=west] (tl) at (4.2,-1.9) {tile $(i,j)$:\\$24 \times 64$};
\draw[oarr, line width=0.5pt] (tl.north west) -- (3.62,-0.82);
\node[ttl] at (2.6,-5.55) {(a) Chia ma trận thành tile};
% ---- (b) một tile trên mảng
\begin{scope}[shift={(8.3,0)}]
\def\cw{0.34}
\node[blk] (ddr) at (0.35,1.75) {DDR};
\node[blk, minimum width=2.72cm] (buf) at (3.36,1.75) {bộ đệm nạp trước};
\draw[warr] (ddr) -- (buf);
\foreach \gi in {0,...,3}{\foreach \ri in {0,1}{\foreach \ci in {0,...,7}{
  \draw[pe] (2.0+\ci*\cw+0.02,-\gi*0.86-\ri*\cw-0.02) rectangle ++(\cw-0.04,-\cw+0.04);}}}
\foreach \ci in {0,...,7}{
  \draw[warr] (2.0+\ci*\cw+\cw/2,1.38) -- (2.0+\ci*\cw+\cw/2,0.02);
  \draw[hcmutblue, line width=0.5pt] (2.0+\ci*\cw+\cw/2,0) -- (2.0+\ci*\cw+\cw/2,-3.26);
  \draw[oarr] (2.0+\ci*\cw+\cw/2,-3.3) -- (2.0+\ci*\cw+\cw/2,-3.72);}
\foreach \gi in {0,...,3}{\foreach \ri in {0,1}{
  \draw[aarr] (1.6,-\gi*0.86-\ri*\cw-\cw/2) -- (1.98,-\gi*0.86-\ri*\cw-\cw/2);}}
\node[atxt, anchor=east] at (1.55,-\cw/2) {$X[24i,\,k]$};
\node[atxt, anchor=east] at (1.55,-3.26+\cw/2) {$X[24i{+}23,\,k]$};
\node[atxt] at (1.1,-1.63) {$\vdots$};
\node[wtxt, anchor=west] at (4.85,0.75) {cột $n$ nhận\\$W[64j{+}n,\,k]$};
\draw[brc] (4.8,-0.0) -- (4.8,-3.26);
\node[sub, anchor=west] at (5.0,-1.0) {4 nhóm nối nhau:\\một luồng\\64 byte/chu kỳ\\cho 24 hàng};
\node[sub, anchor=west] at (5.0,-2.65) {$k = 0 \ldots 575$:\\576 chu kỳ};
\node[otxt, anchor=north] at (3.36,-3.75) {xả $Y[24i{+}m,\,64j{+}n]$};
\node[ttl] at (3.36,-5.55) {(b) Một tile trên mảng $24 \times 64$};
\end{scope}
\end{tikzpicture}
\caption{Linear khi prefill (ví dụ $N = 576$: 9 tile cột). (a) Đầu ra $Y$ chia thành tile $24 \times 64$; tile $(i, j)$ cần dải 24 hàng của $X$ và dải 64 cột của $W^{\mathsf T}$. (b) Ở chu kỳ $k$, hàng $m$ nhận $X[24i{+}m,\,k]$, cột $n$ nhận $W[64j{+}n,\,k]$; cả 24 hàng dùng chung 64 byte trọng số đó. Vẽ 2 hàng mỗi nhóm thay cho 6, 8 cột thay cho 64.}\label{fig:linpre}
\end{figure}
```

Hình \ref{fig:linpre} đọc như sau. Mỗi hàng của mảng là một token, mỗi cột là một đầu ra. Trong $K$ chu kỳ, cạnh trái nhận lần lượt các kênh của 24 token, cạnh trên nhận lần lượt 64 byte trọng số của 64 đầu ra. Mỗi byte trọng số được dùng cho 24 token nên prefill dùng lại trọng số 24 lần. Xong tile, kết quả $24 \times 64$ được xả, requant rồi ghi vào bộ đệm activation làm đầu vào cho phép sau. Mảng tính tiếp tile kế ngay. Tile lẻ 8 token chỉ dùng 8 hàng; các hàng còn lại được che bằng mặt nạ.

## Decode: 4 nhóm tính 4 tile đầu ra cùng lúc

Khi decode chỉ có một token nên mỗi nhóm chỉ cần một hàng. Bốn nhóm nhận cùng vector $x$ nhưng bốn luồng trọng số khác nhau, nên một lượt $K$ chu kỳ cho 256 đầu ra (hình \ref{fig:lindec}). Trọng số mỗi lượt là $4 \times 64 \times K$ byte và mỗi byte chỉ dùng một lần. DDR chỉ cấp khoảng 64 byte mỗi chu kỳ nên bình thường mảng chờ dữ liệu; khi bộ đệm đã đầy lên trong lúc mảng làm attention, mảng chạy hết tốc độ để rút bộ đệm xuống.

```{=latex}
\begin{figure}[!hbp]\centering\everymath{}
\begin{tikzpicture}[x=1cm,y=1cm]
% ---- (a) chia ma trận
\fill[accentteal!40] (0,0) rectangle (2.0,-0.3);
\draw[mat] (0,0) rectangle (2.0,-0.3);
\foreach \ci in {1,...,8} \draw[thin] (2.4+\ci*0.4,0.4) -- (2.4+\ci*0.4,2.4);
\foreach \ci in {0,...,3}{
  \fill[hcmutblue!45] (2.4+\ci*0.4,0.4) rectangle (2.8+\ci*0.4,2.4);
  \fill[accentamber!60] (2.4+\ci*0.4,0) rectangle (2.8+\ci*0.4,-0.3);
  \pgfmathtruncatemacro{\gn}{\ci+1}
  \node[lbl] at (2.6+\ci*0.4,1.4) {\gn};
  \node[lbl] at (2.6+\ci*0.4,-0.15) {\gn};}
\foreach \ci in {1,...,8} \draw[thin] (2.4+\ci*0.4,0) -- (2.4+\ci*0.4,-0.3);
\draw[mat] (2.4,0.4) rectangle (6.0,2.4);
\draw[mat] (2.4,0) rectangle (6.0,-0.3);
\draw[brc] (2.4,2.48) -- node[above=3pt, wtxt]{lượt này: tile 1--4 $\rightarrow$ nhóm 1--4} (4.0,2.48);
\node[wtxt] at (0.95,1.75) {$W^{\mathsf T}$: $576 \times N$\\trọng số};
\node[sub] at (2.12,1.05) {$k$\\$\downarrow$};
\node[sub, anchor=south] at (1.0,0.02) {$k$: $0 \rightarrow 575$};
\node[atxt, anchor=north] at (1.0,-0.4) {$x$: $1 \times 576$\\(1 token)};
\node[otxt, anchor=north] at (4.2,-0.4) {$y$: $1 \times N$\\mỗi lượt 256 đầu ra};
\node[sub, anchor=north] at (3.0,-1.5) {lượt sau: 4 tile kế tiếp (5--8, \ldots)};
\node[ttl] at (2.6,-4.65) {(a) Chia ma trận};
% ---- (b) mảng
\begin{scope}[shift={(7.6,0.6)}]
\def\cw{0.34}
\foreach \gi in {0,...,3}{
  \foreach \ci in {0,...,7}{
    \draw[pe] (1.6+\ci*\cw+0.02,-\gi*1.12-0.02) rectangle ++(\cw-0.04,-\cw+0.04);
    \draw[peoff] (1.6+\ci*\cw+0.02,-\gi*1.12-\cw-0.02) rectangle ++(\cw-0.04,-\cw+0.04);
    \draw[warr, line width=0.6pt] (1.6+\ci*\cw+\cw/2,-\gi*1.12+0.2) -- (1.6+\ci*\cw+\cw/2,-\gi*1.12+0.01);}
  \draw[hcmutblue, line width=1.2pt] (1.6,-\gi*1.12+0.2) -- (5.45,-\gi*1.12+0.2);
  \pgfmathtruncatemacro{\gn}{\gi+1}
  \node[wtxt, fill=white] at (4.85,-\gi*1.12+0.2) {tile \gn};
  \draw[aarr] (1.15,-\gi*1.12-\cw/2) -- (1.58,-\gi*1.12-\cw/2);
  \node[lbl, anchor=east] at (0.55,-\gi*1.12-\cw/2) {nhóm \gn};}
\draw[accentteal!85!black, line width=1.2pt] (1.15,0.75) -- (1.15,-3*1.12-\cw/2);
\node[atxt, anchor=south] at (1.15,0.75) {$x[k]$, chung cho 4 nhóm};
\node[blk, minimum width=0.8cm, minimum height=4.1cm] (buf) at (5.85,-1.55) {};
\node[lbl, rotate=90] at (buf.center) {bộ đệm nạp trước};
\node[blk] (ddr) at (5.85,1.35) {DDR};
\draw[warr] (ddr) -- node[right, sub]{$\approx$ 64 B/chu kỳ} (buf.north);
\node[wtxt, anchor=north] at (5.85,-3.68) {tới $4 \times 64$\\$= 256$ B/chu kỳ};
\foreach \ci in {0,...,7} \draw[oarr] (1.6+\ci*\cw+\cw/2,-3*1.12-2*\cw-0.04) -- ++(0,-0.38);
\node[otxt, anchor=north] at (2.96,-4.5) {xả $4 \times 64$ kết quả};
\draw[peoff] (-0.15,-4.2) rectangle ++(0.3,-0.3);
\node[sub, anchor=west, align=left] at (0.2,-4.35) {tắt clock\\(5 hàng)};
\node[ttl] at (3.3,-5.25) {(b) Mảng ở chế độ decode};
\end{scope}
\end{tikzpicture}
\caption{Linear và LM head khi decode. (a) Một token $x$ nhân với 4 tile 64 cột của $W^{\mathsf T}$ cùng lúc. (b) Cùng $x[k]$ vào hàng đầu của 4 nhóm; nhóm $g$ nhận luồng trọng số riêng gồm 64 hàng của $W$ thuộc tile $g$. Các hàng khác tắt clock. Mảng ăn được tới 256 byte mỗi chu kỳ, gấp 4 lần DDR, nên đuổi kịp sau lúc phải chờ (hình 3 ghi chú chính).}\label{fig:lindec}
\end{figure}
```

**LM head** dùng chính bộ mã $W$ của embedding (contract §11), $N = 49.152$ đầu ra nên có 768 tile. Kết quả xả ra là logits, đi thẳng vào argmax. Khi prefill, LM head chỉ tính cho token cuối nên cũng là phép nhân vector như hình \ref{fig:lindec}.

# Attention

Attention chạy riêng cho từng head K/V (3 head). Mỗi head K/V phục vụ 3 head câu hỏi (GQA), nên $Q$ của 3 head đó dùng chung một bộ $K$, $V$. $Q$ ra từ Linear Q sau RoPE; $K$, $V$ của token mới được ghi vào KV cache, và QK, PV đọc cache gồm cả token hiện tại (key hợp lệ khi vị trí key không lớn hơn vị trí query, contract §5). Với $L$ là số key trong cache:

- QK: $s[h, l] = \sum_{d} Q[h, d]\,K[l, d]$, tức $Q \cdot K^{\mathsf T}$; chiều chung là 64 chiều $d$.
- PV: $\text{out}[h, d] = \frac{1}{S_h}\sum_{l} E[h, l]\,V[l, d]$, tức $E \cdot V$; chiều chung là $L$ key.

## Decode: QK chia khối key cho 4 nhóm

Khi decode chỉ có một token, nhưng 3 head câu hỏi dùng chung một head K/V, nên mỗi nhóm dùng 3 hàng: hàng $h$ là head câu hỏi $h$. Cột là key: nhóm $g$ nhận khối 64 key thứ $g$, nên 4 nhóm cùng lúc tính điểm cho 256 key. Một vòng mất 64 chu kỳ ($d = 0 \ldots 63$); $L = 512$ cần 2 vòng. Mỗi nhóm cho ra điểm của những key riêng nên không cần cộng gì thêm (hình \ref{fig:qkdec}).

```{=latex}
\begin{figure}[htbp]\centering\everymath{}
\begin{tikzpicture}[x=1cm,y=1cm]
\def\cw{0.3}
% Q
\fill[accentteal!40] (0,-0.5) rectangle (0.9,-1.4);
\draw[mat] (0,-0.5) rectangle (0.9,-1.4);
\foreach \ri in {1,2} \draw[thin] (0,-0.5-\ri*0.3) -- (0.9,-0.5-\ri*0.3);
\node[atxt, anchor=south] at (0.45,-0.45) {$Q$: $3 \times 64$};
\node[atxt, anchor=north] at (0.45,-1.45) {3 head\\câu hỏi};
\foreach \gi in {0,...,3}{
  \pgfmathsetmacro{\gx}{1.75+\gi*2.95}
  \pgfmathtruncatemacro{\gn}{\gi+1}
  \pgfmathtruncatemacro{\klo}{\gi*64}
  \pgfmathtruncatemacro{\khi}{\gi*64+63}
  % K block
  \fill[hcmutblue!22] (\gx,0.15) rectangle (\gx+2.4,1.05);
  \fill[hcmutblue!55] (\gx,0.62) rectangle (\gx+2.4,0.72);
  \draw[mat] (\gx,0.15) rectangle (\gx+2.4,1.05);
  \node[wtxt, anchor=south] at (\gx+1.2,1.08) {khối \gn: key \klo--\khi};
  % PE rows
  \foreach \ri in {0,1,2}{\foreach \ci in {0,...,7}{
    \draw[pe] (\gx+\ci*\cw+0.02,-0.5-\ri*\cw-0.02) rectangle ++(\cw-0.04,-\cw+0.04);}
    \draw[aarr] (\gx-0.4,-0.5-\ri*\cw-\cw/2) -- (\gx-0.02,-0.5-\ri*\cw-\cw/2);}
  \foreach \ci in {0,...,7}{
    \draw[peoff] (\gx+\ci*\cw+0.02,-0.5-3*\cw-0.02) rectangle ++(\cw-0.04,-\cw+0.04);
    \draw[warr, line width=0.6pt] (\gx+\ci*\cw+\cw/2,0.13) -- (\gx+\ci*\cw+\cw/2,-0.48);
    \draw[oarr, line width=0.6pt] (\gx+\ci*\cw+\cw/2,-1.74) -- (\gx+\ci*\cw+\cw/2,-2.02);}
  \fill[accentamber!55] (\gx,-2.08) rectangle (\gx+2.4,-2.43);
  \draw[mat] (\gx,-2.08) rectangle (\gx+2.4,-2.43);
  \node[lbl] at (\gx+1.2,-2.255) {điểm $3 \times 64$};
  \node[lbl, anchor=north] at (\gx+1.2,-2.48) {nhóm \gn};}
\node[sub, anchor=east] at (1.7,0.67) {$d$};
\draw[karr, neutralgray] (1.62,0.98) -- (1.62,0.2);
\node[wtxt, anchor=west] at (13.5,0.6) {vòng 2:\\khối 5--8\\(key 256--511)\\lại chia\\cho 4 nhóm};
\node[sub, anchor=west] at (13.5,-1.3) {64 chu kỳ\\mỗi vòng};
\node[otxt, anchor=north] at (7.2,-2.95) {$\rightarrow$ bộ đệm điểm: tìm max của hàng trong lúc xả};
\end{tikzpicture}
\caption{QK khi decode, một head K/V, $L = 512$. Nhóm $g$ nhận khối 64 key thứ $g$ từ KV cache; cả 4 nhóm nhận cùng $Q$. Ở chu kỳ $d$, hàng $h$ nhận $Q[h, d]$, cột $n$ nhận $K[64b{+}n,\,d]$ (dải đậm trong khối). K cache lưu theo từng chiều trong mỗi khối 64 key nên dải đó là một lần đọc 64 byte. Mỗi nhóm dùng 3 trong 6 hàng; 3 hàng còn lại tắt clock (vẽ 1 hàng nét đứt).}\label{fig:qkdec}
\end{figure}
```

## Decode: PV chia key cho 4 nhóm rồi cộng 4 tổng

PV đổi vai: cột là 64 chiều của $V$, còn key trở thành chiều cộng dồn chạy theo thời gian. Nhóm $g$ nhận một phần tư số key; mỗi chu kỳ một key $l$: hàng $h$ nhận $E[h, l]$, cột $n$ nhận $V[l, n]$. Mỗi nhóm vì vậy chỉ có một phần của tổng, nên 4 phần được cộng khi xả rồi mới nhân $1/S$ (hình \ref{fig:pvdec}).

```{=latex}
\begin{figure}[htbp]\centering\everymath{}
\begin{tikzpicture}[x=1cm,y=1cm]
\def\cw{0.3}
% E
\fill[accentteal!40] (0,-0.5) rectangle (1.2,-1.4);
\foreach \ci in {1,2,3} \draw[thin, draw=hcmutdark!60] (\ci*0.3,-0.5) -- (\ci*0.3,-1.4);
\foreach \ci in {0,...,3}{\pgfmathtruncatemacro{\gn}{\ci+1}\node[lbl] at (0.15+\ci*0.3,-0.95) {\gn};}
\draw[mat] (0,-0.5) rectangle (1.2,-1.4);
\node[atxt, anchor=south] at (0.6,-0.45) {$E$: $3 \times L$};
\node[atxt, anchor=north] at (0.6,-1.45) {4 phần key};
\foreach \gi in {0,...,3}{
  \pgfmathsetmacro{\gx}{2.05+\gi*2.95}
  \pgfmathtruncatemacro{\gn}{\gi+1}
  \pgfmathtruncatemacro{\klo}{\gi*128}
  \pgfmathtruncatemacro{\khi}{\gi*128+127}
  % V slice
  \fill[hcmutblue!22] (\gx,0.15) rectangle (\gx+2.4,1.05);
  \fill[hcmutblue!55] (\gx,0.62) rectangle (\gx+2.4,0.72);
  \draw[mat] (\gx,0.15) rectangle (\gx+2.4,1.05);
  \node[wtxt, anchor=south] at (\gx+1.2,1.08) {$V$: key \klo--\khi};
  \foreach \ri in {0,1,2}{\foreach \ci in {0,...,7}{
    \draw[pe] (\gx+\ci*\cw+0.02,-0.5-\ri*\cw-0.02) rectangle ++(\cw-0.04,-\cw+0.04);}
    \draw[aarr] (\gx-0.4,-0.5-\ri*\cw-\cw/2) -- (\gx-0.02,-0.5-\ri*\cw-\cw/2);}
  \node[atxt, anchor=south east] at (\gx-0.02,-0.48) {$E_{\gn}$};
  \foreach \ci in {0,...,7}{
    \draw[peoff] (\gx+\ci*\cw+0.02,-0.5-3*\cw-0.02) rectangle ++(\cw-0.04,-\cw+0.04);
    \draw[warr, line width=0.6pt] (\gx+\ci*\cw+\cw/2,0.13) -- (\gx+\ci*\cw+\cw/2,-0.48);}
  \node[lbl, anchor=north] at (\gx+1.2,-1.72) {nhóm \gn};
  \draw[oarr] (\gx+1.2,-2.1) -- (7.98,-2.95);}
\node[otxt, anchor=east] at (7.7,-3.15) {4 tổng dở dang $3 \times 64$};
\node[sub, anchor=east] at (1.78,0.67) {$l$};
\draw[karr, neutralgray] (1.85,0.98) -- (1.85,0.2);
\node[circle, draw=accentamber!85!black, fill=accentamber!25, font=\small\bfseries, inner sep=1pt, minimum size=5mm] (sum) at (8.15,-3.1) {$+$};
\node[post] (div) at (10.4,-3.1) {nhân $1/S$\\theo hàng};
\node[post] (ssum) at (10.4,-4.25) {$S = \sum E$};
\node[lbl, anchor=west] (ctx) at (12.2,-3.1) {context $3 \times 64$\\$\rightarrow$ Linear O};
\draw[oarr] (sum) -- (div);
\draw[karr] (ssum) -- (div);
\draw[oarr] (div) -- (ctx);
\node[sub, anchor=west] at (13.5,-0.6) {$L/4$ chu kỳ\\mỗi nhóm\\(128 khi\\$L = 512$)};
\end{tikzpicture}
\caption{PV khi decode, một head K/V, $L = 512$. Nhóm $g$ nhận một phần tư số key: hàng $h$ nhận $E[h, l]$, cột $n$ nhận $V[l, n]$ (dải đậm: một key). V cache lưu theo từng token nên dải đó là một lần đọc 64 byte. Mỗi nhóm chỉ có tổng dở dang trên phần key của mình; 4 tổng được cộng khi xả, rồi nhân $1/S$. Chia key thành 4 đoạn liền nhau là cách chia minh họa.}\label{fig:pvdec}
\end{figure}
```

Giữa hai phép, điểm QK nằm trong bộ đệm để tìm max của hàng, rồi tra bảng mũ ra $E$ (mục 3.5 ghi chú chính). Làm xong 3 head K/V thì ghép 9 head thành vector 576 phần tử cho Linear O.

## Prefill: hàng là cặp (token, head) và causal mask

Khi prefill, cả mảng chỉ có một luồng ở cạnh trên, nên mọi hàng phải dùng cùng một khối $K$ hoặc cùng một key $V$. Vì vậy 24 hàng là 8 token × 3 head câu hỏi của cùng một head K/V (*suy ra* từ ghi chú chính: hàng = cặp (token, head câu hỏi)).

```{=latex}
\begin{figure}[htbp]\centering\everymath{}
\begin{tikzpicture}[x=1cm,y=1cm]
\def\cw{0.3}\def\rh{0.22}
% ---- (a) mảng
\foreach \gi in {0,...,3}{
  \foreach \ri in {0,...,5}{
    \foreach \ci in {0,...,7}{
      \draw[pe] (2.6+\ci*\cw+0.02,-\gi*1.48-\ri*\rh-0.015) rectangle ++(\cw-0.04,-\rh+0.03);}
    \draw[aarr, line width=0.5pt] (2.25,-\gi*1.48-\ri*\rh-\rh/2) -- (2.58,-\gi*1.48-\ri*\rh-\rh/2);}
  \foreach \ti in {0,1}{
    \pgfmathtruncatemacro{\tn}{2*\gi+\ti}
    \ifnum\tn=0 \def\tl{$t_0$}\else \def\tl{$t_0{+}\tn$}\fi
    \draw[brc] (2.18,-\gi*1.48-\ti*3*\rh-3*\rh+0.01) -- node[left=3pt, atxt]{token \tl} (2.18,-\gi*1.48-\ti*3*\rh-0.01);}}
\foreach \ci in {0,...,7}{
  \draw[warr] (2.6+\ci*\cw+\cw/2,0.55) -- (2.6+\ci*\cw+\cw/2,0.0);
  \draw[hcmutblue, line width=0.5pt] (2.6+\ci*\cw+\cw/2,0) -- (2.6+\ci*\cw+\cw/2,-5.76);
  \draw[oarr] (2.6+\ci*\cw+\cw/2,-5.8) -- (2.6+\ci*\cw+\cw/2,-6.2);}
\node[wtxt, anchor=south] at (3.8,0.58) {QK: $K[64b{+}n,\,d]$, chu kỳ $d$\\PV: $V[l,\,n]$, chu kỳ $l$};
\node[otxt, anchor=north] at (3.8,-6.25) {QK: điểm $24 \times 64$\\PV: $24 \times 64$, nhân $1/S$ theo hàng};
\node[ttl] at (2.9,-7.4) {(a) 24 hàng = 8 token $\times$ 3 head};
% ---- (b) causal map
\begin{scope}[shift={(7.9,-1.0)}]
\def\bw{0.9}
\fill[hcmutblue!30] (0,0) -- (\bw,0) -- (\bw,-\bw) -- (2*\bw,-\bw) -- (2*\bw,-2*\bw) -- (3*\bw,-2*\bw) -- (3*\bw,-3*\bw) -- (4*\bw,-3*\bw) -- (4*\bw,-4*\bw) -- (0,-4*\bw) -- cycle;
\begin{scope}
\clip (0,0) -- (\bw,0) -- (\bw,-\bw) -- (2*\bw,-\bw) -- (2*\bw,-2*\bw) -- (3*\bw,-2*\bw) -- (3*\bw,-3*\bw) -- (4*\bw,-3*\bw) -- (4*\bw,-4*\bw) -- cycle;
\fill[white] (0,0) -- (4*\bw,0) -- (4*\bw,-4*\bw) -- cycle;
\fill[pattern=north east lines, pattern color=neutralgray] (0,0) -- (4*\bw,0) -- (4*\bw,-4*\bw) -- cycle;
\end{scope}
\foreach \ri in {1,...,31} \draw[draw=hcmutdark!40, line width=0.25pt] (0,-\ri*\bw/8) -- ({(floor(\ri/8)+1)*\bw},-\ri*\bw/8);
\foreach \bi in {1,2,3}{
  \draw[peoff] (\bi*\bw,0) rectangle (4*\bw,-\bi*\bw);}
\foreach \bi in {1,2,3} \draw[mat] (\bi*\bw,-\bi*\bw) -- (\bi*\bw,-4*\bw);
\foreach \bi in {1,2,3} \draw[mat] (0,-\bi*\bw) -- (\bi*\bw,-\bi*\bw);
\draw[mat] (0,0) -- (\bw,0) -- (\bw,-\bw) -- (2*\bw,-\bw) -- (2*\bw,-2*\bw) -- (3*\bw,-2*\bw) -- (3*\bw,-3*\bw) -- (4*\bw,-3*\bw) -- (4*\bw,-4*\bw) -- (0,-4*\bw) -- cycle;
\draw[hcmutdark, line width=1.0pt] (0,0) -- (4*\bw,-4*\bw);
\node[lbl, anchor=south] at (2*\bw,0.05) {key 0 $\rightarrow$ 255};
\node[lbl, anchor=south, rotate=90] at (-0.05,-2*\bw) {token 0 $\rightarrow$ 255};
\draw[karr] (0,-2.3) -- (2.33,-2.3);
\node[lbl, anchor=west, fill=white, inner sep=1pt] at (2.75,-2.3) {PV: key 0 $\rightarrow$ $t_0{+}7$};
% legend
\fill[hcmutblue!30] (0,-4.05) rectangle ++(0.35,-0.3);
\draw[mat] (0,-4.05) rectangle ++(0.35,-0.3);
\node[lbl, anchor=west] at (0.4,-4.2) {tính đủ};
\fill[white] (0,-4.5) rectangle ++(0.35,-0.3);
\fill[pattern=north east lines, pattern color=neutralgray] (0,-4.5) rectangle ++(0.35,-0.3);
\draw[mat] (0,-4.5) rectangle ++(0.35,-0.3);
\node[lbl, anchor=west] at (0.4,-4.65) {vẫn tính, che ở softmax ($E = 0$)};
\draw[peoff] (0,-4.95) rectangle ++(0.35,-0.3);
\node[lbl, anchor=west] at (0.4,-5.1) {bỏ qua hẳn};
\draw[hcmutdark, line width=1.0pt] (0,-5.55) -- ++(0.35,0);
\node[lbl, anchor=west] at (0.4,-5.55) {key = token};
\node[ttl] at (1.8,-6.4) {(b) Causal mask, prompt 256 token};
\end{scope}
\end{tikzpicture}
\caption{Attention khi prefill, một head K/V. (a) Mỗi token chiếm 3 hàng liền nhau, một hàng cho một head câu hỏi; cả mảng nhận chung một khối $K$ (QK) hoặc một key $V$ mỗi chu kỳ (PV). (b) Điểm QK của một head: mỗi dòng mảnh là một tile hàng 8 token, mỗi cột là một khối 64 key. Khối nằm hoàn toàn bên phải đường chéo bị bỏ qua; khối chứa đường chéo vẫn tính đủ, phần key sau token được che khi tính softmax. PV của một tile hàng quét key từ 0 tới token cuối của tile.}\label{fig:attpre}
\end{figure}
```

Với một tile hàng gồm token $t_0 \ldots t_0{+}7$: QK chạy 64 chu kỳ cho mỗi khối key từ khối 0 tới khối chứa $t_0{+}7$; PV chạy $t_0 + 8$ chu kỳ, mỗi chu kỳ một key. Ở PV, hàng của token $t$ nhận $E = 0$ cho các key sau $t$, nên mặt nạ không làm sai tổng.

# Tổng hợp cổng vào và ra

| Phép | Chế độ | Cạnh trái (12 bit): hàng là | Cạnh trên (8 bit): cột là | Chạy theo thời gian | Ra |
|---------|------|---------------|---------------|---------|------------|
| Linear | prefill | $X[t, k]$; 24 token | $W[o, k]$; 64 đầu ra; một luồng chung | $k$: 576 (down 1536) | tile $24 \times 64$ $\rightarrow$ requant |
| Linear, LM head | decode | $x[k]$ vào hàng đầu của 4 nhóm | nhóm $g$: tile đầu ra thứ $g$ | $k$ | $4 \times 64$ đầu ra; LM head $\rightarrow$ argmax |
| QK | prefill | $Q[(t, h), d]$; 8 token × 3 head | $K[64b{+}n, d]$; 64 key; luồng chung | $d$: 64 | $24 \times 64$ điểm $\rightarrow$ max, mask |
| QK | decode | $Q[h, d]$; 3 head, mỗi nhóm một bản | nhóm $g$: khối key riêng | $d$: 64 mỗi vòng | $4 \times 3 \times 64$ điểm |
| PV | prefill | $E[(t, h), l]$; như QK | $V[l, n]$; 64 chiều; luồng chung | $l$: $0 \ldots t_0{+}7$ | $24 \times 64$ $\rightarrow$ nhân $1/S$ |
| PV | decode | $E[h, l]$, $l$ thuộc phần của nhóm | $V[l, n]$ của phần đó | $l$: $L/4$ | cộng 4 tổng $\rightarrow$ nhân $1/S$ |

: Dữ liệu vào và ra mảng cho từng phép. $t$: token; $h$: head câu hỏi; $k$: kênh vào; $o$: đầu ra; $d$: chiều trong head; $l$: key; $b$: khối 64 key; $n = 0 \ldots 63$: cột của mảng.

# Bẫy thường gặp

- **"Cột của mảng ứng với cột của $W$."** Contract lưu $W[o, k]$ theo hàng đầu ra, nên mỗi cột của mảng nhận **một hàng** của $W$. Để mỗi chu kỳ chỉ cần một lần đọc liền, DDR xếp sẵn 64 byte $W[64j \ldots 64j{+}63,\,k]$ cạnh nhau (*suy ra* từ mẹo xếp trọng số ở mục 3.3 ghi chú chính).
- **"K và V lưu cùng kiểu."** $K$ vào cột theo key, $V$ vào cột theo chiều. Vì vậy K cache lưu theo từng chiều trong khối 64 key, còn V cache lưu theo từng token; mỗi chu kỳ đều chỉ đọc 64 byte liền nhau.
- **"Decode chia việc cho 4 nhóm theo cùng một cách."** Linear và QK chia theo đầu ra (tile đầu ra, khối key) nên mỗi nhóm cho kết quả riêng. PV chia theo chiều cộng dồn nên phải cộng 4 tổng dở dang khi xả.
- **"Khi prefill, mỗi hàng attention là một token."** Hàng là cặp (token, head câu hỏi); 24 hàng gồm 8 token, vì 3 head dùng chung luồng $K$, $V$.
- **"Khối key bị che một phần thì bỏ qua."** Chỉ khối bị che hết mới bỏ qua. Khối chứa đường chéo vẫn tính đủ; phần bị che bị loại ở softmax ($E = 0$).
