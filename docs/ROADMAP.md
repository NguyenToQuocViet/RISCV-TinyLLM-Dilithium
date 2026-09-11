# Project Roadmap

## Current Stable Release

Project chưa có stable release.

Không có trạng thái nào được xem là stable release cho đến khi hoàn thành release process và tạo Git tag tương ứng.

## Current Development Target

Repository đang ở giai đoạn bootstrap trước development milestone đầu tiên.

Mục tiêu hiện tại là thiết lập repository structure, development workflow và shared branch baseline để các subsystem có thể bắt đầu phát triển độc lập.

## Bootstrap Scope

Giai đoạn bootstrap bao gồm:

- Chấp nhận project management workflow.
- Khởi tạo cấu trúc source cơ bản.
- Bảo vệ `main` và `develop` bằng repository ruleset.
- Tạo `develop` từ trạng thái bootstrap đã được chấp nhận trên `main`.
- Xác định development target và acceptance criteria cho version đầu tiên trước khi bắt đầu feature development.

## Bootstrap Acceptance Criteria

Giai đoạn bootstrap hoàn thành khi:

- `PROJECT_MANAGEMENT.md` đã được team chấp nhận.
- Cấu trúc repository cơ bản đã được commit lên `main`.
- `main` và `develop` không cho phép development trực tiếp.
- `develop` đã được tạo từ commit bootstrap mới nhất trên `main`.
- Team đã xác định phạm vi và acceptance criteria của development milestone đầu tiên.

## Future Milestones

Development milestone đầu tiên chưa được xác định.

Version, target scope và acceptance criteria tương ứng phải được team chấp nhận và cập nhật tại đây trước khi các feature branch của milestone đó được phát triển.
