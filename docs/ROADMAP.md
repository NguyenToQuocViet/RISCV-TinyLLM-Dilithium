# Project Roadmap

## Current Stable Release

Project chưa có stable release.

Không có trạng thái nào được xem là stable release cho đến khi hoàn thành release process và tạo Git tag tương ứng.

## Current Development Target

Giai đoạn bootstrap đã hoàn thành. Project đang hướng tới development milestone đầu tiên.

Mục tiêu hiện tại là phát triển milestone đầu tiên theo phạm vi và acceptance criteria đã được team xác định, sử dụng `develop` làm shared development baseline.

## Bootstrap Scope

Giai đoạn bootstrap đã bao gồm:

- Chấp nhận project management workflow.
- Khởi tạo cấu trúc source cơ bản.
- Bảo vệ `main` và `develop` bằng repository ruleset.
- Tạo `develop` từ trạng thái bootstrap đã được chấp nhận trên `main`.
- Tạo ba nhánh subsystem `riscv`, `tinyllm` và `dilithium` từ `develop`, với owner tương ứng quản lý feature nội bộ và đưa thay đổi vào `develop` qua Pull Request.
- Xác định development target và acceptance criteria cho version đầu tiên trước khi bắt đầu feature development.

## Bootstrap Acceptance Criteria

Các acceptance criteria của giai đoạn bootstrap đã được đáp ứng:

- `PROJECT_MANAGEMENT.md` đã được team chấp nhận.
- Cấu trúc repository cơ bản đã được commit lên `main`.
- `main` và `develop` không cho phép development trực tiếp.
- `develop` đã được tạo từ commit bootstrap mới nhất trên `main`.
- Các nhánh `riscv`, `tinyllm` và `dilithium` đã được tạo từ `develop` và có owner phụ trách.
- Team đã xác định phạm vi và acceptance criteria của development milestone đầu tiên.

## First Development Milestone

Team đã xác định phạm vi và acceptance criteria của development milestone đầu tiên.

Chi tiết version, target scope và acceptance criteria của milestone này chưa được ghi trong tài liệu hiện tại. Các nội dung đã được team chấp nhận cần được cập nhật tại đây để theo dõi tiến độ và làm căn cứ cho verification và release.

## Future Milestones

Các milestone tiếp theo được cập nhật khi team thống nhất version, target scope và acceptance criteria tương ứng.
