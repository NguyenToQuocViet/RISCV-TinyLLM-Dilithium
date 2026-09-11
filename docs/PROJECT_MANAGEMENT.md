# Project Management and Development Workflow

## 1. Mục đích tài liệu

Tài liệu này quy định cách project được tổ chức, phát triển, review, tích hợp và phát hành.

Mọi contributor tham gia project phải đọc và tuân thủ tài liệu này trước khi thực hiện thay đổi trên repository.

Tài liệu là nguồn quy định chính thức cho:

- Cấu trúc repository.
- Phạm vi quản lý của từng subsystem.
- Quy tắc sử dụng Git branch.
- Quy trình phát triển feature.
- Pull Request và code review.
- Tích hợp các subsystem.
- Commit convention.
- Quản lý version.
- Release từ `develop` sang `main`.
- Hotfix trên version đã phát hành.
- Quản lý roadmap và changelog.

Các quyết định kỹ thuật riêng của từng subsystem thuộc trách nhiệm của subsystem owner, miễn là không vi phạm các system-level contract và quy định chung của project.

---

## 2. Repository Structure

```text
project/
├── README.md
├── LICENSE
│
├── docs/
│   ├── PROJECT_MANAGEMENT.md
│   ├── CHANGELOG.md
│   ├── ROADMAP.md
│   ├── architecture/
│   ├── designs/
│   └── decisions/
│
└── src/
    ├── riscv/
    │   ├── rtl/
    │   ├── tb/
    │   └── .../
    │
    ├── tinyllm/
    │   ├── rtl/
    │   ├── tb/
    │   └── .../
    │
    ├── dilithium/
    │   ├── rtl/
    │   ├── tb/
    │   └── .../
    │
    ├── interconnect/
    │   ├── rtl/
    │   ├── tb/
    │   └── .../
    │
    ├── common/
    │   ├── rtl/
    │   ├── tb/
    │   └── .../
    │
    └── soc/
        ├── rtl/
        ├── tb/
        └── .../
```

Ký hiệu `.../` trong sơ đồ không đại diện cho một thư mục có tên `...`.

Nó biểu thị rằng owner của subsystem được phép bổ sung các thư mục hoặc file cần thiết cho quá trình phát triển subsystem đó.

Mỗi subsystem bắt buộc duy trì:

- `rtl/`: synthesizable RTL của subsystem.
- `tb/`: verification environment, testbench và test liên quan.

Các thành phần khác như documentation, scripts, model, data, build files, file lists hoặc tool configuration được subsystem owner tổ chức theo nhu cầu thực tế.

`src/common/` chỉ chứa source thực sự được nhiều subsystem sử dụng chung. Nội dung tại đây phải tuân theo system-level contract và không được dùng làm nơi chứa các file chưa xác định được ownership.

---

## 3. Documentation Structure

### 3.1 `README.md`

`README.md` cung cấp góc nhìn cấp cao về project.

README phải thể hiện tối thiểu:

- Mục tiêu project.
- Kiến trúc tổng quát.
- Các subsystem chính.
- Trạng thái phát triển hiện tại.
- Stable release hiện tại.
- Milestone tiếp theo.
- Liên kết đến các tài liệu quan trọng trong `docs/`.

README không thay thế cho tài liệu kỹ thuật chi tiết.

### 3.2 `docs/PROJECT_MANAGEMENT.md`

Đây là tài liệu hiện tại.

File này là nguồn quy định chính thức cho development workflow, branch policy, Pull Request, versioning và release process.

### 3.3 `docs/CHANGELOG.md`

Ghi lại các thay đổi đã được project chấp nhận.

Changelog phải phân biệt:

- Các thay đổi chưa phát hành.
- Các stable release đã tồn tại.
- Nội dung thay đổi của từng release.

Các thay đổi đang nằm trên `develop` nhưng chưa được release phải thuộc phần `Unreleased`.

Khi một release mới được tạo, các thay đổi tương ứng được chuyển từ `Unreleased` sang version vừa phát hành.

Changelog mô tả thay đổi ở mức project hoặc user-visible engineering state; không thay thế Git commit history.

### 3.4 `docs/ROADMAP.md`

ROADMAP là nguồn xác định project đang hướng tới đâu.

File này phải ghi rõ:

- Stable release hiện tại.
- Version đang được phát triển.
- Mục tiêu của version tiếp theo.
- Phạm vi dự kiến.
- Acceptance criteria.
- Các milestone tiếp theo đã được định hướng.

Một version chỉ được promote từ `develop` sang `main` khi acceptance criteria tương ứng trong ROADMAP đã được đáp ứng.

### 3.5 `docs/architecture/`

Chứa system-level architecture của project.

Các nội dung ảnh hưởng nhiều subsystem phải được định nghĩa tại đây, bao gồm khi áp dụng:

- SoC architecture.
- Interconnect architecture.
- Address space và memory map.
- Communication contract.
- Interrupt architecture.
- Clock và reset architecture.
- Shared protocol.
- System-level data flow.

System-level contract thuộc quyền quản lý của project architect.

Subsystem không được tự thay đổi system-level contract mà không có review ở cấp project.

### 3.6 `docs/designs/`

Chứa các tài liệu thiết kế có phạm vi rộng hơn một implementation file và cần được chia sẻ giữa các contributor.

Design document phải mô tả đủ để reviewer hiểu:

- Vấn đề cần giải quyết.
- Requirements.
- Kiến trúc được chọn.
- Interface liên quan.
- Trade-off quan trọng.
- Verification expectation.

### 3.7 `docs/decisions/`

Chứa các quyết định kỹ thuật quan trọng đã được project chấp nhận.

Các quyết định ảnh hưởng lâu dài đến architecture, interface hoặc development direction phải được ghi lại để tránh việc rationale bị mất theo thời gian.

---

## 4. Ownership và Development Boundary

Các subsystem chính gồm:

```text
riscv
tinyllm
dilithium
interconnect
soc
```

Mỗi subsystem có owner chịu trách nhiệm chính về:

- Internal architecture.
- RTL implementation.
- Verification.
- Internal documentation.
- Feature decomposition.
- Maintenance.

Subsystem owner có quyền tổ chức nội bộ subsystem của mình miễn là không vi phạm:

- Shared interface.
- System architecture.
- Coding hoặc development policy chung.
- Contract với subsystem khác.

`common` là khu vực source dùng chung, không thuộc quyền thay đổi độc lập của một subsystem owner.

Project architect chịu trách nhiệm đối với các quyết định vượt qua boundary của một subsystem, bao gồm:

- SoC architecture.
- Shared interface.
- Memory map.
- Interconnect.
- Interrupt topology.
- Clock/reset relationship.
- Integration contract.
- Các thay đổi ảnh hưởng nhiều subsystem.

---

## 5. Branch Model

Repository duy trì hai long-lived branch:

```text
main
develop
```

Các branch phát triển còn lại là short-lived branch.

Branch model:

```text
main
├── develop
│   ├── feature/*
│   └── integration/*
│
└── hotfix/*
```

Không tạo long-lived branch riêng cho từng contributor hoặc từng subsystem.

---

## 6. `main`

`main` đại diện cho lịch sử các **stable project milestone**.

Code trên `main` phải ở trạng thái:

- Đã được review.
- Đã vượt qua verification yêu cầu của milestone.
- Không có blocking issue đã biết.
- Documentation tương ứng đã được cập nhật.
- Có trạng thái project rõ ràng trong CHANGELOG và ROADMAP.

Không phát triển trực tiếp trên `main`.

Không push trực tiếp lên `main`.

Thay đổi chỉ được đưa vào `main` thông qua:

- Release từ `develop`.
- Hotfix từ `hotfix/*`.

Một stable release được xác định bằng Git tag theo version format của project.

Trước stable release đầu tiên, `main` có thể chứa repository scaffold, governance và tài liệu khởi tạo. Trạng thái bootstrap này không được xem là stable release nếu chưa hoàn thành release process và chưa có Git tag tương ứng.

---

## 7. `develop`

`develop` là **shared development baseline** mới nhất của toàn project.

Đây là branch mà các contributor sử dụng làm nền để phát triển feature mới.

`develop` phải chứa các thay đổi đã:

- Hoàn thành phạm vi được định nghĩa.
- Qua review.
- Pass các test liên quan.
- Không phá vỡ baseline hiện tại ở phạm vi đã được kiểm tra.

`develop` không phải stable release.

Không gắn stable version tag trực tiếp lên `develop`.

Không push trực tiếp lên `develop`.

Mọi thay đổi thông thường phải đi qua Pull Request.

`develop` luôn hướng tới version tiếp theo được định nghĩa trong `ROADMAP.md`.

---

## 8. `feature/*`

`feature/*` là short-lived branch dùng cho một thay đổi logic cụ thể.

Naming format:

```text
feature/<scope>-<description>
```

Một feature branch phải:

- Được tạo từ `develop`.
- Có phạm vi rõ ràng.
- Không trở thành branch phát triển dài hạn của một subsystem.
- Không chứa các thay đổi không liên quan đến mục tiêu của branch.
- Được merge trở lại `develop` thông qua Pull Request.
- Được xóa sau khi merge khi không còn cần thiết.

Migration code từ project cũ cũng được xử lý như một feature.

Code cũ không được đưa trực tiếp vào `develop` hoặc `main`.

Migration phải đi qua quá trình:

```text
existing implementation
        ↓
review
        ↓
understanding
        ↓
required modification
        ↓
documentation
        ↓
verification
        ↓
Pull Request
        ↓
develop
```

Việc code đã tồn tại trước project không miễn trừ yêu cầu review và verification.

---

## 9. `integration/*`

`integration/*` là short-lived branch dành cho công việc cần thay đổi hoặc kiểm tra đồng thời nhiều subsystem.

Naming format:

```text
integration/<scope>
```

Integration branch phải được tạo từ `develop`.

Branch này được sử dụng khi công việc không thể được xử lý hợp lý trong phạm vi một subsystem riêng lẻ.

Integration work có thể bao gồm:

- Kết nối nhiều subsystem.
- Interconnect integration.
- Memory map validation.
- Interrupt integration.
- Shared protocol validation.
- Clock/reset integration.
- System-level simulation.

`integration/*` không merge trực tiếp vào `main`.

Sau khi integration hoàn tất và đạt acceptance criteria, branch phải được Pull Request trở lại `develop`.

Sau khi merge thành công, integration branch được xóa khi không còn cần thiết.

---

## 10. `hotfix/*`

`hotfix/*` chỉ được sử dụng để sửa lỗi nghiêm trọng trên stable release hiện tại của `main`.

Naming format:

```text
hotfix/<description>
```

Hotfix branch phải được tạo từ commit hiện tại của `main`.

Hotfix không được sử dụng để:

- Thêm feature mới.
- Thay đổi architecture không liên quan đến lỗi.
- Mở rộng milestone.
- Thực hiện refactor không cần thiết.

Hotfix phải:

1. Sửa đúng lỗi cần xử lý.
2. Có verification chứng minh lỗi đã được khắc phục.
3. Không tạo regression đã biết.
4. Được review qua Pull Request.
5. Merge vào `main`.
6. Tạo PATCH release mới.
7. Được đồng bộ trở lại `develop`.

Việc đồng bộ hotfix về `develop` là bắt buộc để lỗi không xuất hiện trở lại trong version đang phát triển.

---

## 11. Pull Request Policy

Pull Request là đơn vị chính thức để project review và chấp nhận thay đổi.

Không merge feature vào shared branch nếu không có Pull Request.

### 11.1 Feature Pull Request

Luồng:

```text
feature/*
    ↓
Pull Request
    ↓
develop
```

Pull Request phải mô tả rõ:

- Mục tiêu thay đổi.
- Phạm vi thay đổi.
- Các file hoặc subsystem bị ảnh hưởng.
- Design decision liên quan.
- Interface bị thay đổi nếu có.
- Verification đã thực hiện.
- Kết quả verification.
- Known limitation nếu tồn tại.
- Documentation đã được cập nhật khi cần thiết.

Trước khi merge:

- Scope của branch phải hoàn thành.
- Required tests phải pass.
- Conflict với target branch phải được xử lý.
- Không có regression đã biết trong phạm vi kiểm tra.
- Documentation liên quan phải nhất quán với implementation.
- Phải có ít nhất một reviewer khác author.

Thay đổi ảnh hưởng system-level architecture hoặc shared contract phải có approval của project architect.

Author không được xem việc code chạy được là điều kiện duy nhất để merge.

Review phải kiểm tra cả:

- Correctness.
- Architecture consistency.
- Interface consistency.
- Verification sufficiency.
- Maintainability.
- Documentation consistency.

### 11.2 Merge Method

Pull Request mặc định được merge bằng merge commit để bảo toàn lịch sử phát triển của branch.

Squash merge chỉ được sử dụng ngoại lệ khi lịch sử commit quá nhiễu nhưng final diff đã được review, đúng phạm vi và đủ điều kiện merge.

Squash không được dùng để che giấu thay đổi ngoài scope, conflict chưa được xử lý hoặc verification chưa đầy đủ.

---

## 12. Release Pull Request

Release là quá trình promote project từ development state sang stable milestone.

Luồng:

```text
develop
   ↓
Release Pull Request
   ↓
main
   ↓
Git tag
```

Release Pull Request chỉ được tạo khi version target trong `ROADMAP.md` đã đạt toàn bộ acceptance criteria.

Trước khi merge `develop` vào `main`, phải xác nhận:

- Tất cả feature thuộc milestone đã được merge vào `develop`.
- Required verification của milestone đã pass.
- Không còn blocking issue thuộc release scope.
- System-level contract nhất quán.
- `CHANGELOG.md` đã được cập nhật.
- `ROADMAP.md` đã được cập nhật.
- Documentation phản ánh đúng trạng thái implementation.
- Release đã được team review.
- Project architect xác nhận milestone đủ điều kiện phát hành.

Sau khi Release Pull Request được merge:

1. Commit trên `main` đại diện cho release được gắn Git tag.
2. CHANGELOG ghi nhận version vừa phát hành.
3. ROADMAP chuyển development target sang version tiếp theo.
4. Development tiếp tục trên `develop`.

Không merge `develop` vào `main` chỉ vì `develop` đang hoạt động ổn định.

`main` chỉ thay đổi khi một project milestone được chính thức chấp nhận.

---

## 13. Versioning

Project sử dụng version format:

```text
v<MAJOR>.<MINOR>.<PATCH>
```

Trong đó:

```text
MAJOR.MINOR.PATCH
```

### 13.1 `MAJOR`

`MAJOR` biểu thị thế hệ ổn định chính của project.

Trong giai đoạn project chưa đạt first complete stable release:

```text
MAJOR = 0
```

`v1.0.0` chỉ được tạo khi project đạt milestone hoàn chỉnh được team định nghĩa và chấp nhận trong ROADMAP.

Sau `v1.0.0`, tăng `MAJOR` khi có thay đổi không tương thích với public architecture, interface hoặc contract đã được coi là stable.

### 13.2 `MINOR`

`MINOR` biểu thị một project milestone mới trong cùng một major development line.

Tăng `MINOR` khi project đạt một capability hoặc development milestone mới đã được định nghĩa trước.

Khi tăng `MINOR`, `PATCH` trở về `0`.

Trong giai đoạn trước `v1.0.0`, `MINOR` là thành phần chính dùng để biểu diễn tiến trình qua các milestone của đồ án.

### 13.3 `PATCH`

`PATCH` biểu thị correction release trên cùng một milestone.

Tăng `PATCH` khi sửa:

- Defect.
- Regression.
- Documentation error ảnh hưởng release.
- Integration issue không làm thay đổi phạm vi milestone.
- Stable release issue cần hotfix.

PATCH release không được dùng để đưa một feature hoặc milestone mới vào stable release.

---

## 14. Stable Version

Stable version là version đã:

- Merge vào `main`.
- Được chấp nhận theo release process.
- Có Git tag tương ứng.

Git tag trỏ đến đúng commit đại diện cho snapshot chính thức của release.

Format tag:

```text
v<MAJOR>.<MINOR>.<PATCH>
```

`main` có thể tiếp tục có các commit release mới hơn, nhưng mỗi tag vẫn giữ nguyên tham chiếu tới trạng thái chính xác của release mà nó đại diện.

Tag đã phát hành không được di chuyển sang commit khác.

---

## 15. Development Version

`develop` không phải một stable version.

Không tạo stable release tag cho trạng thái đang phát triển.

Version mà `develop` đang hướng tới phải được ghi trong:

```text
docs/ROADMAP.md
```

Các thay đổi đã merge vào `develop` nhưng chưa release phải được ghi trong phần:

```text
Unreleased
```

của:

```text
docs/CHANGELOG.md
```

Do đó project luôn phân biệt rõ:

```text
main
→ stable released state

develop
→ accepted development state toward next release

feature/*
→ work in progress
```

---

## 16. Hotfix Version

Hotfix tạo một PATCH release mới từ stable version hiện tại.

Version hotfix phải giữ nguyên:

```text
MAJOR
MINOR
```

và tăng:

```text
PATCH
```

Hotfix chỉ sửa stable release hiện tại.

Sau khi hotfix được chấp nhận:

```text
hotfix/*
    ↓
main
    ↓
PATCH version tag
```

Sau đó cùng correction phải được đưa trở lại development line:

```text
main / hotfix change
        ↓
develop
```

Stable release và development branch không được phép duy trì hai cách sửa khác nhau cho cùng một defect nếu không có technical justification được ghi lại.

---

## 17. CHANGELOG Policy

`CHANGELOG.md` phải có một khu vực dành cho thay đổi chưa release.

Mọi thay đổi đáng kể được merge vào `develop` phải được phản ánh tại đây nếu thay đổi đó ảnh hưởng:

- Project capability.
- Architecture.
- Interface.
- Behavior.
- Verification baseline.
- Development workflow.
- Release-visible documentation.

Khi tạo release:

- Nội dung thuộc release được chuyển khỏi `Unreleased`.
- Một section version mới được tạo.
- Release date được ghi lại.
- `Unreleased` được giữ lại cho development tiếp theo.

Changelog không cần liệt kê từng commit.

---

## 18. ROADMAP Policy

`ROADMAP.md` phải thể hiện ít nhất:

```text
Current stable release
Current development target
Target scope
Acceptance criteria
Future milestones
```

Acceptance criteria phải đủ cụ thể để team có thể xác định một cách khách quan liệu version đã đủ điều kiện release hay chưa.

Không được quyết định release chỉ dựa trên cảm giác rằng project "đã đủ ổn".

Nếu phạm vi milestone thay đổi, ROADMAP phải được cập nhật trước khi release.

---

## 19. Commit Policy

Một commit phải đại diện cho một logical change có thể hiểu được độc lập.

Commit message sử dụng format:

```text
<type>(<scope>): <description>
```

Các type được sử dụng:

| Type       | Ý nghĩa                                                              |
| ---------- | -------------------------------------------------------------------- |
| `feat`     | Thêm hoặc thay đổi functionality                                     |
| `fix`      | Sửa defect                                                           |
| `test`     | Thêm hoặc sửa verification                                           |
| `refactor` | Thay đổi cấu trúc implementation nhưng không chủ ý thay đổi behavior |
| `docs`     | Thay đổi documentation                                               |
| `chore`    | Build, script, configuration, dependency hoặc maintenance task       |

`scope` phải xác định subsystem hoặc khu vực bị tác động.

Commit message phải mô tả cụ thể thay đổi.

Không sử dụng commit message mơ hồ không thể hiện nội dung kỹ thuật của commit.

---

## 20. Development Lifecycle

Development lifecycle chuẩn của project:

```text
ROADMAP defines target
        ↓
develop
        ↓
feature/*
        ↓
implementation + verification + documentation
        ↓
Pull Request
        ↓
review
        ↓
develop
        ↓
integration when required
        ↓
milestone verification
        ↓
Release Pull Request
        ↓
main
        ↓
version tag
        ↓
next ROADMAP target
```

Feature acceptance và project release là hai cấp độ khác nhau.

```text
feature/* → develop
```

có nghĩa thay đổi đã được chấp nhận để trở thành một phần của development baseline.

```text
develop → main
```

có nghĩa toàn project đã đạt một milestone được định nghĩa và kiểm chứng.

---

## 21. Core Project Rules

Các quy tắc sau là bắt buộc:

1. Một repository chung cho toàn project.
2. Chỉ duy trì một `main`.
3. Chỉ duy trì một `develop`.
4. Không phát triển trực tiếp trên `main`.
5. Không phát triển trực tiếp trên `develop`.
6. Feature phải được phát triển trên short-lived branch.
7. Feature branch phải xuất phát từ `develop`.
8. Feature phải merge về `develop` thông qua Pull Request.
9. Integration branch phải xuất phát từ và quay trở lại `develop`.
10. `main` chỉ chứa các stable milestone đã được chấp nhận, ngoại trừ bootstrap trước release đầu tiên.
11. `develop` chỉ được promote lên `main` khi release acceptance criteria đã hoàn thành.
12. Mỗi stable release phải có version tag.
13. Development state không được gắn stable version tag.
14. Hotfix phải xuất phát từ `main`.
15. Hotfix phải tạo PATCH release.
16. Hotfix phải được đồng bộ trở lại `develop`.
17. Thay đổi system-level contract phải có project architect review.
18. Code cũ phải được review, document và verify trước khi trở thành development baseline.
19. Implementation và documentation không được cố ý duy trì hai trạng thái mâu thuẫn.
20. `ROADMAP.md` xác định project đang đi tới đâu; `CHANGELOG.md` ghi lại project đã thay đổi như thế nào; Git tag xác định chính xác stable snapshot đã được phát hành.
