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
