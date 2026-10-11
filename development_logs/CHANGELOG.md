# Changelog

## 0.1.0 - 2026-09-26

- Khởi tạo backend FastAPI và frontend React/TypeScript.
- Thiết kế PostgreSQL schema, SQLAlchemy models và Alembic migration.
- Thêm CRUD project và quản lý thư mục dữ liệu theo project.
- Thêm upload video/audio, FFprobe metadata, thumbnail và media streaming.
- Thêm adapter VieNeu-TTS, preset voice, CUDA/CPU và lưu WAV theo project.
- Thêm sequence thủ công, permutation và product có lặp với giới hạn 100.
- Thêm pipeline FFmpeg chuẩn hóa resolution/FPS, concat và lồng/trộn audio.
- Thêm ba chính sách thời lượng và hai encoder libx264/NVENC.
- Thêm job queue tuần tự, progress, cancel, retry và log riêng từng job.
- Thêm giao diện Media, Voice Studio, Sequence Builder, Render và Jobs.
- Thêm kiểm tra PostgreSQL, FFmpeg, NVENC, CUDA và dung lượng đĩa.
- Thêm script chạy local, phát triển và kiểm tra môi trường.
- Thêm script thiết lập database/user PostgreSQL và tạo `.env` an toàn qua prompt.
- Thêm kiểm tra dung lượng tối thiểu trước render, cleanup output tạm khi lỗi và mở thư mục project.
- Loại bỏ font CDN để giao diện hoạt động hoàn toàn offline.
- Xác minh VieNeu CUDA bằng WAV thật 3,76 giây.
- Thêm integration test FFmpeg thực tế cho keep-original, replace và mix.
- Hoàn tất PostgreSQL 17 native, migration và smoke test end-to-end trên database thật.
- Chạy production local tại `127.0.0.1:8765` với PostgreSQL/FFmpeg/NVENC/CUDA hoạt động.
- Thêm script dừng server an toàn; chỉ dừng process uvicorn đang giữ đúng cổng 8765.

## 0.2.0 - 2026-09-26

- Tự động hiển thị 25 preset voice trong khoảng 100 ms, không cần nút tải và không khởi tạo model chỉ để lấy tên giọng.
- Buộc VieNeu dùng model cache offline đã có, loại bỏ retry mạng Hugging Face khi khởi tạo.
- TTS xuất MP3/WAV và giữ các tham số gốc: batch, batch size, temperature, max chars, top-k, top-p, repetition penalty, silence.
- Thêm thanh tiến độ ước tính cho TTS và lưu thời gian tạo trên audio.
- Thêm lọc audio theo ngày, tăng/giảm tốc độ bước 0,1 và cắt đầu/cuối bằng FFmpeg.
- Thêm nhiều video batch độc lập, dự báo số tổ hợp theo K và timeline riêng cho mỗi batch.
- Tách thao tác phát video khỏi checkbox chọn video; cho phép import video ngay tại Sequence Builder.
- Cho phép tối đa 3 media job chạy song song; TTS model vẫn được khóa tuần tự để an toàn.
- Thêm kéo-thả audio riêng lên từng sequence, tùy chọn tắt/trộn/giữ tiếng gốc riêng từng output.
- Thêm preset video 9:16/16:9, preview source/output và tên output tùy chỉnh.
- Gom output vào thư mục riêng theo project, tên lần chạy và timestamp.
- Thêm Alembic migration `0002_sequence_batches`.
- Smoke test thật: TTS CUDA MP3, 25 progress samples, audio speed/trim và PostgreSQL render đều qua.
