# Issues và vấn đề theo dõi

## Đang mở

- PostgreSQL chưa được cài trên máy phát triển: máy không có winget/choco/scoop và kết nối tải EDB bị reset. Product vẫn cấu hình PostgreSQL; integration test dùng SQLite cô lập chỉ để xác minh API/pipeline cho tới khi cài native.
- Cần chạy lại migration và API smoke test trên PostgreSQL thật sau khi bộ cài native khả dụng.
- Cần đo mức sử dụng VRAM thực tế khi chạy VieNeu CUDA rồi NVENC tuần tự trên GTX 1650 4 GB.
- Voice cloning chưa có control riêng trong giao diện; preset voice là phạm vi MVP hiện tại.
- Loudness normalization EBU R128, subtitle và transition thuộc giai đoạn sau MVP.

## Đã xử lý

- 2026-09-26: FFmpeg báo output `[basea]` unconnected ở chế độ replace audio. Đã nối nhánh bỏ đi vào `anullsink` và thêm regression test.
- 2026-09-26: PowerShell 5 ParserError do file UTF-8 không BOM chứa tiếng Việt. Đã dùng chuỗi ASCII cho script thiết lập PostgreSQL.
- 2026-09-26: Alembic ConfigParser hiểu `%xx` trong database URL là interpolation. Đã escape dấu `%` khi gọi `set_main_option`.

## Quy tắc ghi issue

Mỗi issue phải có thời gian phát hiện, môi trường, cách tái hiện, ảnh hưởng, hướng xử lý và trạng thái.
