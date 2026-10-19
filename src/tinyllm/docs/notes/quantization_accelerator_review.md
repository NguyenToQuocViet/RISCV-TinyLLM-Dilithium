**Tổng hợp nghiên cứu: lượng tử hóa và accelerator cho SmolLM2-135M**

Ngày đối chiếu nguồn: 12–13-10-2026. Trạng thái: đề xuất nghiên cứu của TinyLLM; chưa phải quyết định đã chấp nhận, numerical contract đã khóa hoặc system-level contract.

Cập nhật lộ trình: 13-10-2026. Đọc kèm [đề xuất một paper chính](paper_research_strategy.md). Danh sách 20 paper dưới đây là nguồn để chọn cách làm; không phải 20 phương pháp phải hiện thực hay kế hoạch tạo nhiều bài.

Phạm vi: giữ checkpoint SmolLM2-135M base đang pin; hướng tới đầy đủ prefill/decode trên VCU118. Không thay đổi code thí nghiệm, tài liệu quyết định, hoặc các subsystem khác trong lần khảo sát này.

Tài liệu dùng trang tác giả, bản thảo gốc và proceedings. Với I-LLM, FlightLLM, KIVI, QuaRot, InTAR, LUT-LLM, SLMQuant và TATAA, đã đối chiếu thêm các phần phương pháp/thực nghiệm/giới hạn trong bản HTML. DSP-Packing được đối chiếu thêm phần sửa lỗi trong PDF. Các tài liệu còn lại dùng abstract/proceedings để xác định vai trò, không xem là đã thẩm định toàn bộ hiện thực. Đây là khảo sát có chọn lọc, không phải tổng quan hệ thống bao phủ mọi công trình.

**Một số từ dùng trong note**

| Từ                   | Nghĩa đơn giản                                                                                                                                                                                                          |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Numerical contract    | Quy tắc số học mà phần mềm và RTL cùng tuân theo: số bit, scale, cách làm tròn, xử lý tràn và các bước tính.                                                                                           |
| Policy / precision    | Policy là bộ lựa chọn lượng tử hóa; precision là độ chính xác của cách biểu diễn, chẳng hạn INT8 hay INT16.                                                                                              |
| Fake-quant            | Giả lập việc làm tròn về ít mức giá trị, nhưng nhiều phép tính vẫn dùng floating-point. Chưa mô phỏng đầy đủ số học RTL.                                                                           |
| Golden integer        | Bản phần mềm làm kết quả chuẩn theo đúng quy tắc số nguyên dự kiến cho phần cứng.                                                                                                                           |
| PTQ / calibration     | PTQ là lượng tử hóa model đã huấn luyện; calibration dùng một tập dữ liệu để chọn/thống kê tham số lượng tử hóa. Một số PTQ còn học tham số hiệu chỉnh.                                      |
| PPL / Top-1 agreement | PPL đo khả năng dự đoán văn bản, thấp hơn thường tốt hơn khi đo cùng điều kiện. Top-1 agreement đo tỷ lệ lựa chọn giống reference; không phải điểm đúng/sai trên bài kiểm tra ứng dụng. |
| Profile / bottleneck  | Đo từng phần tốn bao nhiêu thời gian/tài nguyên; bottleneck là phần giới hạn mục tiêu hiệu năng.                                                                                                            |
| Kernel / end-to-end   | Kernel là một khối tính nhỏ; end-to-end là đánh giá cả luồng suy luận thay vì chỉ khối đó.                                                                                                                 |
| Baseline / ablation   | Baseline là cách đối chứng; ablation là bỏ hoặc đổi riêng một thành phần để biết nó đóng góp gì.                                                                                                      |

**1. Kết luận đề xuất cho project**

Mục tiêu là accelerator đạt hiệu năng/chi phí tài nguyên tốt trong ngân sách phần cứng và giữ chất lượng model trong ngưỡng đã định. Chọn numerical contract và cách hiện thực phần cứng bằng một vòng lặp chung. Bắt đầu với một phương án giữ chất lượng tốt, khảo sát kernel/dataflow, rồi điều chỉnh số học hoặc phần cứng theo chỗ thật sự tốn chi phí. So các cặp contract + cách hiện thực, thay vì chỉ chọn policy có PPL hoặc số bit tốt nhất.

Có hai cách cải thiện cần phân biệt khi đo: đổi contract có thể thay chất lượng và cost; giữ contract nhưng tổ chức bộ nhớ/pipeline tốt hơn có thể giảm cost mà giữ nguyên kết quả số học. Nếu tối ưu RTL làm đổi accumulator, cách làm tròn hoặc phép tính, phải cập nhật contract và kiểm tra lại chất lượng. Golden integer và kernel RTL đại diện giúp đánh giá hai phần trước khi triển khai đầy đủ.

Không có bằng chứng từ các nguồn đã đọc rằng một thuật toán duy nhất, hay một bộ số bit cố định, tối ưu cho đúng checkpoint này trên đúng ngân sách VCU118 của SoC. Các khuyến nghị dưới đây là suy luận cho project, cần thí nghiệm kiểm chứng.

Không nên chốt toàn bộ số học chỉ từ PPL fake-quant rồi mới bắt đầu tìm hiểu cost RTL. Khóa sớm cách đo, ngưỡng chất lượng và phạm vi; giữ một vài contract ứng viên để kiểm tra bằng golden integer và kernel RTL nhỏ. Cách này giảm rủi ro hơn việc cố tìm contract “tối ưu nhất” hoàn toàn trên Python.

Bản model tự viết không phải điều kiện bắt buộc để nghiên cứu PTQ và cũng không tự là đóng góp paper. Có thể dùng Hugging Face làm reference, dùng các lớp/hook phù hợp để thử lượng tử hóa. Cần một golden model mô tả đúng số học dự kiến cho RTL; có thể xây từng phép toán và từng layer, thay vì viết lại toàn model ngay chỉ để thay số bit. Nếu dùng bản tự viết hiện tại, phải đối chiếu nó trước khi tin các kết quả.

Integer-only không có nghĩa mọi dữ liệu và phép tính đều phải dùng INT8. Đầu vào 8 bit có thể cần accumulator và trung gian rộng hơn. Trọng số/bảng tra có thể được chuẩn bị bằng floating-point trên host; yêu cầu integer-only, nếu được chọn, áp dụng cho đường suy luận.

**2. Những gì đang có trong workspace**

| Bằng chứng hiện có                                                                                                                                                | Ý nghĩa đối với nghiên cứu tiếp theo                                                                                                                       |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [Báo cáo fake-quant](../../quant/results/fake_quant_report.md), dòng 7–12: model pin theo SHA, 16 cửa sổ calibration và 48 cửa sổ evaluation, dài 512 token. | Giữ làm thí nghiệm khảo sát. Cần reference Hugging Face đã đối chiếu và tập đánh giá cuối độc lập với quá trình lựa chọn policy.         |
| Báo cáo, dòng 56: residual và`down_in` có giá trị cực lớn; clipping đã thử gây mất chất lượng.                                                     | Có lý do thử hiệu chỉnh phân bố trước khi tăng bit cho mọi vị trí. Chưa chứng minh SmoothQuant/rotation sẽ giải quyết được các outlier này. |
| Báo cáo, dòng 59: tăng một số đường lên INT12 cải thiện chất lượng; chưa có số đo FPGA.                                                            | INT12 là ứng viên. Chưa biết lợi ích tài nguyên/tốc độ so với INT8 hay INT16.                                                                         |
| Báo cáo, dòng 70: K và V đều đề xuất INT8 động theo token.                                                                                                 | Cần thử K/V riêng và các layer nhạy nếu cache là chi phí đáng kể.                                                                                      |
| [Forward](../../quant/smollm2_fq.py), dòng 238–265 chỉ nhận `ids` và trả logits.                                                                               | Chưa có luồng giữ, đọc và cập nhật KV cache qua các lượt decode.                                                                                       |
| `smollm2_fq.py`, dòng 141–143 dùng lưới tuyến tính cho xác suất attention.                                                                                 | Kết luận số bit chỉ áp dụng cho cách biểu diễn này. Không suy ra mọi cách biểu diễn ít bit đều thất bại.                                       |
| Báo cáo, dòng 79–86 còn mở biểu diễn scale, multiplier/shift, accumulator và phép tính số nguyên.                                                        | Fake-quant hiện tại chưa là bằng chứng bit-exact cho RTL.                                                                                                    |

Trường `sec` trong `results.jsonl` là thời gian chạy thí nghiệm Python, không phải latency của accelerator.

`docs/DECISIONS.md` hiện trống. Vì vậy, không coi các lựa chọn trong ghi chú này là quyết định đã được owner/project chấp nhận.

**3. Các paper nên dùng và giới hạn khi áp dụng**

| Paper và nguồn gốc                                                                                                         | Nội dung nên học                                                                                                    | Giới hạn đối với TinyLLM                                                                                                                                                                                                         |
| ----------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [I-LLM](https://arxiv.org/html/2405.17849v2), bản thảo 2024; §3, Table 1, Appendix A.4.                                     | Dynamic integer-only MatMul, RMSNorm, softmax và SwiGLU; hiệu chỉnh theo block.                                     | Không có latency đo trên phần cứng trong bản đã đọc. Các kết quả không bao gồm checkpoint SmolLM2-135M này.                                                                                                          |
| [I-BERT](https://proceedings.mlr.press/v139/kim21d.html), ICML 2021.                                                           | Cách tổ chức phép toán phi tuyến bằng số nguyên.                                                              | BERT/RoBERTa dùng GELU/LayerNorm; không bê nguyên sang SiLU/RMSNorm/RoPE và decode của SmolLM2.                                                                                                                                 |
| [FQ-ViT](https://www.ijcai.org/proceedings/2022/164), IJCAI 2022.                                                              | Log-Int-Softmax: biểu diễn attention không đều theo log2 và tính bằng dịch bit.                               | ViT là model thị giác. Cần kiểm tra causal mask, context dài và sai số toàn model; đây chưa là bằng chứng cho SmolLM2.                                                                                                 |
| [SmoothQuant](https://proceedings.mlr.press/v202/xiao23c.html), ICML 2023.                                                     | Dùng biến đổi tương đương để cân bằng độ lớn activation/trọng số trước lượng tử hóa.           | Ưu tiên thử ở norm→linear; không tự giải quyết residual, KV và mọi phép phi tuyến.                                                                                                                                       |
| [GPTQ](https://arxiv.org/abs/2210.17323), ICLR 2023.                                                                           | Lượng tử hóa trọng số có tối ưu sai số, làm đối chứng cho round-to-nearest hiện tại.                   | Weight-only; không phải contract hoàn chỉnh cho activation/cache/nonlinear.                                                                                                                                                       |
| [QuaRot](https://arxiv.org/html/2404.00456v2), NeurIPS 2024; §4, Appendix A.7.                                                | Rotation phân tán outlier; có biến đổi fuse vào trọng số và biến đổi cần chạy online.                   | Bản đã đọc dùng Hadamard online FP32. Phải đánh giá phần online và các chiều 576/1536/9 head cùng embedding dùng chung. Không xem đây là thiết kế integer-only sẵn.                                            |
| [KIVI](https://proceedings.mlr.press/v235/liu24bz.html), ICML 2024; [§3 bản đầy đủ](https://arxiv.org/html/2402.02750v2). | Tách cách lượng tử hóa K theo channel và V theo token; xử lý tính chất streaming của cache.                | Có cache residual giữ precision cao và metadata. Không lấy số bit thấp rồi bỏ qua các phần đó; không mặc định K/V của model này có cùng phân bố với paper.                                                    |
| [KVTuner](https://proceedings.mlr.press/v267/li25dd.html), ICML 2025.                                                          | Độ nhạy theo layer, tìm cặp precision K/V offline với nhiều mục tiêu.                                         | Số bit trung bình thấp trên LLM khác không phải cam kết cho model 135M. Mixed precision có thể thêm chi phí điều khiển/lưu trữ trên FPGA.                                                                           |
| [HAQ](https://arxiv.org/abs/1811.08886), CVPR 2019.                                                                            | Đưa phản hồi latency/energy của phần cứng vào quá trình chọn precision.                                     | Học nguyên tắc; không cần bắt đầu bằng một hệ thống reinforcement learning phức tạp.                                                                                                                                    |
| [HAWQ-V3](https://proceedings.mlr.press/v139/yao21a.html), ICML 2021.                                                          | Kết hợp integer-only, mixed precision và ràng buộc bộ nhớ/latency.                                              | Thí nghiệm trên mạng thị giác/GPU; cần tự xác định toán tử và cost cho FPGA của project.                                                                                                                               |
| [DSP-Packing](https://arxiv.org/abs/2203.11028), FPL 2022; phần V trong [PDF](https://arxiv.org/pdf/2203.11028).               | Ghép phép toán ít bit vào DSP, sửa lỗi tách kết quả signed và chi phí correction.                          | Có cả phương án chính xác và phương án gần đúng. Chọn exact trước; approximation phải trở thành một phần riêng của contract và được đánh giá chất lượng.                                            |
| [FlightLLM](https://arxiv.org/html/2401.03868v2), FPGA 2024; §3.2, §4.                                                       | Ghép precision với DSP chain, bộ nhớ và dataflow decode; giữ activation trên chip để giảm truyền dữ liệu. | Có softmax/normalization FP16. U280 có HBM; không chuyển số throughput/bandwidth trực tiếp sang VCU118.                                                                                                                        |
| [InTAR](https://arxiv.org/html/2502.08807v2), FCCM 2025.                                                                       | Chọn cách thực thi tuần tự hay pipeline theo lượng dữ liệu và tài nguyên.                                  | Học cách tổ chức dữ liệu; không phải thuật toán chọn số bit. HLS/GPT-2 không tự xác lập toolchain hay kiến trúc cho SmolLM2 RTL.                                                                                    |
| [LUT-LLM](https://arxiv.org/html/2511.06174v2), bản extended FCCM 2026; §III, §V-A.                                         | Đối chứng cho hướng thay phép nhân bằng tra bảng và đồng thiết kế thuật toán/phần cứng.              | Vector quantization, training bổ sung và V80/HBM khác đáng kể với phạm vi hiện tại. Một số so sánh với accelerator khác là simulator-derived. Đây là nhánh nghiên cứu sau, không phải lựa chọn mặc định. |
| [SLMQuant](https://arxiv.org/html/2511.13023v1), bản thảo 2025; §2.1, Table 1, §4–6.                                      | Benchmark lượng tử hóa model nhỏ, có nêu SmolLM2-135M.                                                          | FP16/GPU; tên model/checkpoint và giải thích kiến trúc cần kiểm tra; xem mục 4.                                                                                                                                              |
| [TATAA](https://arxiv.org/html/2411.03697v1), bản thảo 2024; §4–5.                                                         | Accelerator lập trình được, chia sẻ phần cứng giữa MatMul INT8 và vector BF16.                               | Khả năng lập trình/chia sẻ datapath đã có tiền lệ; BF16 nonlinear không phải integer-only.                                                                                                                                |
| [QONNX](https://arxiv.org/abs/2206.07527), 2022.                                                                               | Mô tả lượng tử hóa arbitrary precision trong một biểu diễn chung cho các công cụ.                          | Định nghĩa graph/precision không tự bảo đảm hành vi finite-width của mọi toán tử hoặc luồng cache có trạng thái của LLM.                                                                                           |
| [FINN-R](https://arxiv.org/abs/1809.04570), TRETS 2018.                                                                        | Đồng thiết kế precision, mô hình cost và khám phá thiết kế FPGA.                                            | Tiền lệ cho quy trình; các workload CNN được đánh giá không phải reference cho decode SmolLM2.                                                                                                                            |
| [Massive Activations](https://arxiv.org/abs/2402.17762), COLM 2024.                                                            | Nghiên cứu những activation rất lớn nhưng ít; gợi ý kiểm tra vai trò của chúng trước khi clipping.      | Sự tương đồng với outlier token 0 trong workspace là giả thuyết, chưa phải xác nhận cùng nguyên nhân.                                                                                                                 |
| [PrefixQuant](https://arxiv.org/abs/2410.05265), bản thảo cập nhật 2025.                                                   | Cô lập token outlier bằng prefix KV; nghiên cứu static quantization và hiệu chỉnh theo block.                  | Có thay đổi khởi tạo cache và tùy chọn học tham số. Không giả định toàn bộ pipeline training-free hoặc tương đương việc chỉ đổi bit; phải đo trên checkpoint hiện tại.                                 |

Các nguồn này chứng minh có nhiều lựa chọn về thuật toán, biểu diễn và kiến trúc. Chúng không cung cấp một bộ tham số tối ưu đã kiểm chứng cho TinyLLM.

**4. Những điểm cần phản biện ngay khi đọc paper**

I-LLM Table 1 báo cáo LLaMA2-7B WikiText-2 PPL 5.47 cho FP16 và 10.44 cho W4A4. Vì vậy, câu mô tả chung về mất chất lượng nhỏ không thể áp dụng cho mọi cấu hình. §4 cũng giữ activation phi tuyến ở 8 bit ngay cả trong các cấu hình tuyến tính thấp bit. Appendix A.4 chưa có latency phần cứng. Đây là nguồn học toán tử, không phải lý do chốt W4A4 hoặc tuyên bố tăng tốc FPGA. [Nguồn đầy đủ](https://arxiv.org/html/2405.17849v2).

QuaRot có những biến đổi chạy online bằng FP32 trong thực nghiệm. Muốn dùng fixed-point cho chúng phải kiểm tra lại độ chính xác và chi phí; không suy ra từ cụm từ “4-bit inference” rằng mọi phép toán đều dùng 4 bit. [Appendix A.7](https://arxiv.org/html/2404.00456v2).

KIVI giữ phần cache residual ở precision cao; cache 2 bit là một cấu trúc gồm dữ liệu, scale/zero-point và phần residual. Chỉ lấy tỷ lệ nén theo bit sẽ đánh giá thiếu bộ nhớ và chi phí đọc/ghi. [§3.3 và phần giới thiệu](https://arxiv.org/html/2402.02750v2).

SLMQuant §2.1 nêu SmolLM2-135M, nhưng Table 1 ghi SmolLM-135M. §6 giải thích độ bền lượng tử hóa bằng NoPE/YaRN; checkpoint đang pin có RoPE theta=100000 và `rope_scaling=null`. Không dùng lời giải thích đó cho checkpoint này, không lấy PPL trong bảng làm baseline thay cho lần chạy riêng. Có thể học cách chọn benchmark và phương án đối chứng, nhưng phải xác minh model/tokenizer/prompt/config trong hiện thực. [Paper](https://arxiv.org/html/2511.13023v1), [cấu hình chính thức tại SHA đang pin](https://huggingface.co/HuggingFaceTB/SmolLM2-135M/blob/93efa2f097d58c2a74874c7e644dbc9b0cee75a2/config.json).

FlightLLM là ví dụ accelerator hiệu quả vẫn dùng FP16 cho một số toán tử. Đây là một phương án cần so chi phí nếu integer-only chưa được chấp nhận làm ràng buộc bắt buộc. Nếu chọn integer-only theo kế hoạch hiện tại, giữ FlightLLM làm đối chứng kiến trúc, không sao chép toán tử FP16. [§3.2](https://arxiv.org/html/2401.03868v2).

VCU118 có bộ nhớ DDR4 theo [UG1224](https://docs.amd.com/api/khub/documents/Uoc4S9pQd1uve6kiGiG2kA/content). Những số hiệu năng trên U280/V80 với HBM không phải dự đoán hiệu năng cho board này. Cần phân biệt phép đo board, kết quả synthesis, mô phỏng và tính toán lý thuyết trong bảng paper của project.

**5. Phương pháp thực hiện đề xuất**

| Thứ tự | Công việc cụ thể                                                                                                                              | Bằng chứng cần có trước khi đi tiếp                                                                                                                                                                                                             |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1        | Chọn workload, context, giới hạn giảm chất lượng, mục tiêu chính và ngân sách DSP/LUT/BRAM/URAM/bộ nhớ/băng thông.               | Ví dụ: giảm latency decode trong giới hạn tài nguyên và chất lượng. Tiêu chí được xác định trước khi đánh giá cuối; ngân sách shared hardware theo quyền sở hữu project.                                                  |
| 2        | Nạp reference Hugging Face FP32 tại SHA đã pin; đối chiếu bản tự viết khi policy trống.                                                | Sai số được công bố trên cùng token IDs ở prefill và decode; không quy lỗi implementation thành sai số quantization.                                                                                                                      |
| 3        | Tách calibration, tập chọn policy và tập test cuối.                                                                                         | Lưu model/data revision, token IDs, seed, thư viện, thiết bị/backend và cấu hình chạy.                                                                                                                                                         |
| 4        | Có một ứng viên giữ chất lượng tốt để làm nền.                                                                                       | Chất lượng và các điểm nhạy đã đo; không cần ép activation/residual/nonlinear về INT8 ngay.                                                                                                                                              |
| 5        | Đo độ nhạy theo tensor và vài layer; đồng thời lập mô hình chi phí và synthesis kernel đại diện.                                 | Biết thay đổi nào giảm chi phí đáng kể và thay đổi nào chỉ giảm số bit trên giấy.                                                                                                                                                     |
| 6        | Thử PTQ có hiệu chỉnh tại các chỗ gây sai số hoặc chi phí lớn.                                                                        | So với cùng policy không hiệu chỉnh để thấy đóng góp; không gộp nhiều thay đổi rồi mất khả năng giải thích.                                                                                                                       |
| 7        | Chuyển 2–3 ứng viên sang phép tính số nguyên hữu hạn; thử LUT/polynomial/bit-shift ở các khối cần thiết.                          | Dtype/scale/accumulator/rounding/saturation/thứ tự phép toán được mô tả đầy đủ và kiểm tra.                                                                                                                                              |
| 8        | Kiểm tra decode, context dài, số học biên và chất lượng trên tập chọn policy.                                                         | Đạt tiêu chí chất lượng trong phạm vi hỗ trợ; cache mã/scale/position cập nhật đúng. Chưa dùng tập test cuối để xếp hạng ứng viên.                                                                                             |
| 9        | Chọn theo mục tiêu chính trong các phương án đạt ràng buộc; khóa contract/version rồi đánh giá trên tập test cuối độc lập. | Cost được kiểm tra bằng kernel synthesis, chất lượng bằng bản số nguyên. Sau đó triển khai RTL đầy đủ và đo board. Nếu sửa policy sau khi xem test cuối, phải ghi rõ và dành dữ liệu độc lập cho lần xác nhận mới. |

Không cần thực hiện đầy đủ mọi thuật toán trong danh sách. Thứ tự ưu tiên là giải quyết sai số và chi phí đã quan sát được, thay vì chọn phương pháp chỉ vì paper dùng ít bit hơn.

“Reference FP32” ở đây nói về cách tính: nạp các trọng số của checkpoint đã pin và thực hiện bằng FP32 với backend/cấu hình được ghi nhận. Chuyển trọng số nguồn BF16 sang FP32 không phục hồi các chữ số đã mất trước đó. Cần phân biệt precision của trọng số nguồn với precision của phép tính reference.

Đối với bước 5, ưu tiên MAC + requantization, residual add/align scale, RMSNorm, softmax và đường đọc/ghi KV. Với synthesis, ghi DSP/LUT/FF/BRAM/URAM, clock target/achieved và số chu kỳ; synthesis đơn lẻ chưa chứng minh timing sau place-and-route hoặc latency toàn model.

Mô hình thời gian sơ bộ nên có cả giới hạn tính toán và truyền dữ liệu. Giá trị `max(thời gian tính lý tưởng, thời gian truyền lý tưởng)` chỉ là cận dưới với giả định overlap; phải cộng/đo scheduling, phụ thuộc dữ liệu, chuyển scale và stall thực tế.

**6. Ma trận thí nghiệm nhỏ nên bắt đầu**

Đây là các ứng viên đề xuất, không phải cấu hình đã kiểm chứng hay đã được chấp nhận.

| Nhánh | Phép thử                                                                                                                         | Câu hỏi nó trả lời                                                                                                        |
| ------ | ---------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| A      | Giữ`wide_compute_12_lut` sau khi reference được xác minh; xây bản số nguyên tương ứng.                               | Sai số bổ sung từ biểu diễn integer và scale có làm mất lợi thế fake-quant không?                                  |
| B      | W8 ở projection, thử activation thấp bit có SmoothQuant tại các cặp norm→linear; giữ điểm nhạy ở precision cao hơn.  | Có giảm activation/chi phí so với tăng bit trực tiếp mà vẫn đạt chất lượng không?                               |
| C      | Projection W4 có GPTQ; embedding/LM head được xử lý riêng và bảo toàn trọng số dùng chung.                            | Lượng tử hóa trọng số có hiệu chỉnh có giúp giảm tải bộ nhớ không? Chưa mặc định dùng W4 cho toàn model. |
| D      | Bắt đầu K8/V8; nếu cache là bottleneck, thử K8/V4 rồi mở rộng cách chia scale/channel và một số layer.                | K và V có cần cùng số bit/chia scale không; chi phí metadata và streaming có xóa lợi ích không?                   |
| E      | Khi nonlinear là điểm đáng tối ưu, so LUT hiện tại với integer approximation/bit-shift; Log-Int-Softmax là nhánh phụ. | Có biểu diễn/tính toán tốt hơn lưới xác suất tuyến tính u16 không?                                               |
| F      | Rotation kiểu QuaRot khi outlier vẫn gây chi phí lớn sau các thử nghiệm đơn giản.                                       | Lợi ích precision có bù chi phí biến đổi online và độ phức tạp hiện thực không?                                |

Thử tuyến tính với nonlinear FP32 có thể dùng để tách nguyên nhân sai số trong khảo sát. Một cấu hình như vậy không được báo cáo là integer-only hoàn chỉnh.

Giảm bit theo layer chỉ nên dùng nếu bộ điều khiển, datapath và định dạng bộ nhớ hỗ trợ nó với chi phí hợp lý. Một datapath cố định ở precision cao nhất có thể không tiết kiệm DSP khi các layer khác dùng ít bit hơn, dù vẫn giảm dung lượng dữ liệu nếu packing được thực hiện thật.

**7. Những số liệu cần báo cáo cho paper**

Chất lượng: PPL trên WikiText-2 và một corpus độc lập phù hợp; thêm PIQA/ARC-Easy/HellaSwag hoặc các task phù hợp khả năng model base. Với model nhỏ, cần xem cả baseline và mức giảm tuyệt đối/tương đối, không dùng kết quả gần đoán ngẫu nhiên để kết luận chất lượng được giữ tốt. Top-1 agreement/KL với FP32 dùng làm số chẩn đoán bổ sung.

Tái lập: mã model/tokenizer, input IDs, cách chọn cửa sổ, context, dữ liệu calibration/test, seed, thư viện, dtype/backend và policy đầy đủ. So sai số số học bằng cùng prefix/token IDs; đo sinh tự do là phép đánh giá bổ sung.

Phần cứng: latency prefill và decode tách riêng, thời gian có token đầu tiên, token/s khi batch/context cố định, dung lượng dữ liệu thực gồm metadata và padding, bytes đọc/ghi, tài nguyên sau implementation và clock đạt được. Nếu đo năng lượng, ghi rõ cách đo và phần hệ thống được tính. Giữ cùng precision/chất lượng/workload hoặc trình bày rõ khác biệt khi so các baseline.

Để minh họa chi phí KV hiện tại, ở batch=1 và không lặp 3 KV head thành 9 query head trong bộ nhớ, payload K/V INT8 là:

`30 layer × 2 (K,V) × 3 KV head × context × 64 phần tử × 1 byte`.

| Context | Payload K/V INT8 lý thuyết |
| ------- | ---------------------------: |
| 512     |                    5.625 MiB |
| 2048    |                     22.5 MiB |
| 8192    |                       90 MiB |

Nếu lưu một scale/token/layer cho mỗi K và V, context 8192 có thêm 491,520 scale: 0.9375 MiB nếu scale 16 bit hoặc 1.875 MiB nếu 32 bit. Đây là tính toán dung lượng, chưa gồm zero-point, padding, residual buffer hoặc cache controller; không phải phép đo hiện thực.

Tính đúng của RTL và chất lượng model là hai phép kiểm tra: RTL phải khớp golden model theo contract; golden model phải đạt ngưỡng chất lượng so với reference.

Các ablation hữu ích cho paper: có/không PTQ hiệu chỉnh; cùng precision với scale/zero-point khác; K/V đồng nhất và tách riêng; precision theo layer và đồng nhất; nonlinear FP32/LUT/integer approximation; cost của packing chính xác. Mỗi phép thử cần giải thích được phần thay đổi và phần giữ nguyên.

**8. Thứ tự đọc đề xuất và việc nên hoãn**

Đọc trước: I-LLM §3 và Appendix A.4 → FlightLLM §3–4 → KIVI §3 → KVTuner → DSP-Packing phần correction. Dùng SLMQuant để tham khảo protocol đánh giá nhưng kiểm tra lại checkpoint và lý giải kiến trúc.

Sau khi có baseline và cost ban đầu: SmoothQuant/GPTQ → QuaRot → InTAR nếu dataflow là bottleneck. I-BERT/FQ-ViT là nguồn tham khảo toán tử, cần đánh giá lại trên model decoder của project.

Hoãn chuyển toàn pipeline sang vector quantization, ternary model hoặc training phức tạp khi chưa chứng minh cần thay hướng. LUT-LLM cho thấy một lối thiết kế khác có thật, nhưng tăng đáng kể phạm vi thuật toán và kiến trúc. Không dùng tốc độ của model/phần cứng khác như cam kết cho project.

Chưa thí nghiệm lại các thuật toán này trên SmolLM2-135M, chưa đo synthesis/board trong lần tổng hợp này. Việc tiếp theo có giá trị nhất là hoàn thiện reference, đặt protocol đánh giá và lấy cost kernel ban đầu; sau đó mới chọn nhánh PTQ/precision để thử.
