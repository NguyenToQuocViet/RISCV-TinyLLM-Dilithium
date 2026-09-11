# Cấu trúc thư mục đề xuất

```text
project/
├── README.md
├── LICENSE
├── docs/
│   ├── architecture/
│   ├── designs/
│
├── src/
│   ├── riscv/
│   │   ├── rtl/
│   │   ├── tb/
│   │   ├── docs/
│   │   ├── filelist/
│   │   ├── scripts/
│   │   └── Makefile
│   │
│   ├── tinyllm/
│   │   ├── rtl/
│   │   ├── tb/
│   │   ├── docs/
│   │   ├── model/
│   │   ├── quantization/
│   │   ├── scripts/
│   │   ├── filelist/
│   │   ├── data/
│   │   └── Makefile
│   │
│   ├── pqc/
│   │   ├── rtl/
│   │   ├── tb/
│   │   ├── docs/
│   │   ├── filelist/
│   │   ├── scripts/
│   │   └── Makefile
│   │
│   ├── interconnect/
│   │   ├── rtl/
│   │   └── tb/
│   │
│   └── soc/
│       ├── rtl/
│       │   └── soc_top.sv
│       └── tb/
│
├── common/
│   ├── soc_pkg.sv
│   ├── axi_if.sv
│   └── defines.svh
│
├── fpga/
│   ├── constraints/
│   ├── scripts/
│   └── boards/
│
└── .gitignore
```

## Quy ước tổ chức module

Ba thư mục `riscv/`, `tinyllm/` và `pqc/` do từng thành viên phụ trách tự tạo và tự quản lý. Tên thư mục có thể thay đổi tùy theo cách đặt tên của mỗi người.

Thư mục `docs/` ở cấp repository chứa tài liệu chung của toàn dự án, chẳng hạn như kiến trúc SoC, memory map, contract giao tiếp giữa các IP và quy trình phát triển. Thư mục `docs/` bên trong `src/<ip>/` chứa tài liệu riêng của IP đó, chẳng hạn như microarchitecture, thiết kế các khối nội bộ và ghi chú verification của IP. Contract dùng chung không nên lặp lại trong tài liệu riêng của từng IP.

Cấu trúc bên trong mỗi module cũng có thể linh hoạt theo nhu cầu phát triển. Tuy nhiên, mỗi module nên có:

- `docs/` để lưu tài liệu thiết kế và verification thuộc riêng module.
- `Makefile` để đơn giản hóa quá trình build và simulation bằng Verilator.
- `filelist/` để quản lý danh sách source file và dependency.
- Filelist cần khai báo đường dẫn tới các file dùng chung trong `common/` khi module có sử dụng chúng, ví dụ `soc_pkg.sv`, `axi_if.sv` hoặc `defines.svh`.

Ví dụ:

```text
src/tinyllm/filelist/tinyllm.f
```

có thể chứa:

```text
../../../common/soc_pkg.sv
../../../common/axi_if.sv

rtl/mac.sv
rtl/mac_array.sv
rtl/tinyllm_top.sv
```

Nhờ đó, mỗi module có thể được simulation độc lập mà vẫn sử dụng được các package/interface chung của toàn SoC.

---

# Git Workflow Đề Xuất

Dự án sử dụng **1 repository chung** cho toàn bộ SoC.
Mỗi thành viên phát triển module của mình bằng các **feature branch ngắn hạn**, sau đó merge về `develop` thông qua Pull Request.

## 1. Các branch chính

```text
main
└── develop
    ├── feature/riscv-...
    ├── feature/llm-...
    ├── feature/pqc-...
    └── integration/soc-...
```

### `main`

Chứa các phiên bản ổn định của dự án, ví dụ:

```text
v0.1-module-ready
v0.5-soc-integrated
v1.0-fpga-demo
```

Không phát triển trực tiếp trên `main`.

### `develop`

Là baseline phát triển chung mới nhất.

Các feature đã hoàn thành, test pass và được review sẽ được merge vào `develop`.

### `feature/*`

Mỗi branch tương ứng với **một chức năng hoặc thay đổi cụ thể**, không tương ứng với một thành viên.

Ví dụ:

```text
feature/llm-mac
feature/llm-controller
feature/llm-axi

feature/pqc-ntt
feature/riscv-axi
```

Không nên dùng các branch dài hạn như:

```text
riscv_branch
llm_branch
pqc_branch
```

## 2. Workflow phát triển

Khi bắt đầu một chức năng mới:

```bash
git checkout develop
git pull
git checkout -b feature/llm-mac
```

Sau khi hoàn thành:

```bash
git add .
git commit -m "feat(llm): implement INT8 MAC"
git push origin feature/llm-mac
```

Sau đó tạo Pull Request:

```text
feature/llm-mac
      ↓
   develop
```

Chỉ merge khi:

- Code đã hoàn thành.
- Test liên quan đã pass.
- Không làm hỏng các phần đã có.
- Đã được ít nhất một thành viên khác review nếu có thể.

Sau khi merge, feature branch có thể xóa.

## 3. Giai đoạn tích hợp SoC

Khi các subsystem đã đủ ổn định, tạo branch tích hợp từ `develop`:

```text
develop
   │
   └── integration/soc-v1
```

Branch này dùng để:

- Kết nối RISC-V, tinyLLM và PQC.
- Tích hợp AXI/interconnect.
- Kiểm tra memory map.
- Kiểm tra interrupt, clock và reset.
- Chạy simulation toàn SoC.

Khi tích hợp ổn định:

```text
integration/soc-v1
        ↓
      develop
        ↓
       main
```

## 4. Quy tắc commit

Một commit nên chứa **một thay đổi logic chính**.

Format đề xuất:

```text
<type>(<scope>): <description>
```

Ví dụ:

```text
feat(llm): implement MAC array
test(llm): add MAC unit tests
fix(llm): correct signed multiplication
feat(pqc): add NTT butterfly
feat(riscv): add AXI master interface
docs(soc): add memory map
```

Các `type` thường dùng:

| Type | Ý nghĩa |
|---|---|
| `feat` | Thêm chức năng |
| `fix` | Sửa lỗi |
| `test` | Thêm hoặc sửa test |
| `refactor` | Cải tổ code nhưng không đổi chức năng |
| `docs` | Thay đổi tài liệu |
| `chore` | Script, build, config, filelist... |

Tránh các commit message không rõ nghĩa như:

```text
update
fix bug
new version
final
final2
```

## 5. Nguyên tắc chung

```text
1 feature = 1 branch ngắn hạn
1 commit = 1 thay đổi logic chính
feature/* → Pull Request → develop
develop → integration → main
```

`develop` luôn là phiên bản phát triển chung tương đối ổn định, còn `main` chỉ chứa các milestone đã được kiểm tra.
