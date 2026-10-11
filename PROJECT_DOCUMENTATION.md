# Tài liệu tổng quan dự án Video TTS Studio

> Tài liệu này mô tả trạng thái hiện tại của mã nguồn trong repository: mục tiêu sản phẩm, kiến trúc, luồng dữ liệu, API, cơ sở dữ liệu, cách cài đặt, vận hành, kiểm thử và các giới hạn đã biết.

## 1. Tổng quan

**Video TTS Studio** là ứng dụng chạy cục bộ trên Windows để tạo giọng đọc tiếng Việt bằng VieNeu-TTS, tổ chức nhiều video nguồn thành các sequence, ghép giọng đọc/nhạc nền bằng FFmpeg và quản lý toàn bộ kết quả theo project.

Ứng dụng hướng tới quy trình sản xuất video hàng loạt:

1. Tạo project.
2. Nhập video và audio nguồn.
3. Tạo audio TTS thủ công hoặc hàng loạt từ Excel.
4. Tạo các tổ hợp video theo batch.
5. Gán voice, nhạc nền và chính sách âm thanh cho từng sequence.
6. Render nhiều video qua hàng đợi nền.
7. Xem, đổi tên và tải kết quả về thư mục người dùng chọn.

Ứng dụng không phụ thuộc dịch vụ web khi chạy bình thường. VieNeu-TTS dùng model đã tải sẵn và được ép sang chế độ offline.

## 2. Công nghệ chính

| Khu vực | Công nghệ | Vai trò |
|---|---|---|
| Backend | Python, FastAPI, Uvicorn | REST API, SSE, phục vụ frontend production |
| ORM và database | SQLAlchemy 2, PostgreSQL, psycopg | Lưu metadata, project, asset, sequence và job |
| Migration | Alembic | Quản lý schema database |
| Frontend | React, TypeScript, Vite | Giao diện quản lý toàn bộ workflow |
| TTS | VieNeu-TTS v3 Turbo | Sinh giọng đọc tiếng Việt bằng CUDA hoặc CPU/ONNX |
| Media | FFmpeg, FFprobe | Đọc metadata, thumbnail, chỉnh audio, concat và render video |
| Icon | lucide-react | Icon giao diện |
| Test | pytest, FastAPI TestClient/httpx | Unit test và integration test |

## 3. Kiến trúc tổng thể

```mermaid
flowchart LR
    U[Trình duyệt] -->|REST /api| F[FastAPI]
    U <-->|SSE /api/events| F
    F --> DB[(PostgreSQL)]
    F --> FS[(data/projects)]
    F --> JM[JobManager]
    JM --> TTS[VieNeu-TTS]
    JM --> FF[FFmpeg / FFprobe]
    TTS --> FS
    FF --> FS
    F -->|Static files khi production| UI[React build]
```

Backend là tiến trình trung tâm. Nó phục vụ API, quản lý database, đọc/ghi media và điều phối job nền. Frontend chỉ lưu lựa chọn project hiện tại trong `localStorage`; dữ liệu nghiệp vụ chính nằm trong PostgreSQL và thư mục `data`.

Khi production, FastAPI phục vụ bản build trong `frontend/dist`. Khi phát triển, Vite chạy ở cổng `5173` và proxy `/api` sang backend ở cổng `8765`.

## 4. Cấu trúc repository

```text
video-tts-studio/
├── backend/
│   ├── app/
│   │   ├── api/              # REST API: project, asset, sequence, job, system
│   │   ├── core/             # Cấu hình và logging
│   │   ├── db/               # Engine, session và Declarative Base
│   │   ├── models/           # SQLAlchemy entities
│   │   ├── schemas/          # Pydantic request/response models
│   │   ├── services/         # TTS, FFmpeg, storage, job queue, sequence engine
│   │   └── main.py           # Khởi tạo FastAPI và lifecycle
│   ├── alembic/              # Migration database
│   ├── tests/                # Unit/integration/smoke tests
│   ├── alembic.ini
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx           # Giao diện và workflow chính
│   │   ├── api.ts            # HTTP client và URL media
│   │   ├── types.ts          # Kiểu dữ liệu frontend
│   │   ├── styles.css
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
├── scripts/                  # Script setup, chạy, dừng và kiểm tra môi trường
├── data/                     # Media thực tế, tách theo project
├── logs/                     # Runtime log chung
├── development_logs/         # Changelog, issue và nhật ký phát triển
├── test-*-data/              # Fixture/kết quả từ các đợt integration test
├── .env.example
├── README.md
└── OLLAMA_INTEGRATION_PLAN.md # Kế hoạch tích hợp, chưa phải luồng runtime hiện tại
```

## 5. Mô hình dữ liệu

### 5.1. Quan hệ chính

```mermaid
erDiagram
    PROJECT ||--o{ ASSET : contains
    PROJECT ||--o{ SEQUENCE : contains
    PROJECT ||--o{ JOB : contains
    SEQUENCE ||--o{ SEQUENCE_ITEM : orders
    ASSET ||--o{ SEQUENCE_ITEM : references
    ASSET o|--o{ JOB : output_of

    PROJECT {
        string id PK
        string name
        json settings
        datetime created_at
        datetime updated_at
    }
    ASSET {
        string id PK
        string project_id FK
        string type
        string display_name
        text relative_path
        text thumbnail_path
        bigint duration_ms
        int width
        int height
        float fps
        string codec
        bool has_audio
        json metadata_json
        string video_batch_name
    }
    SEQUENCE {
        string id PK
        string project_id FK
        string name
        string batch_name
        bool enabled
    }
    SEQUENCE_ITEM {
        string id PK
        string sequence_id FK
        string asset_id FK
        int position
    }
    JOB {
        string id PK
        string project_id FK
        string kind
        string status
        float progress
        json input_json
        string output_asset_id FK
        text error_message
        text log_path
    }
```

### 5.2. Các loại asset

| Giá trị `type` | Ý nghĩa | Vị trí file mặc định |
|---|---|---|
| `video` | Video nguồn do người dùng nhập | `source/videos/` |
| `external_audio` | Audio nguồn do người dùng nhập | `source/audio/` |
| `tts_audio` | Audio sinh bởi TTS hoặc bản chỉnh sửa | `generated/tts/` |
| `output` | Video thành phẩm | `outputs/<run-folder>/` |

Metadata kỹ thuật gồm thời lượng, codec, kích thước, FPS và trạng thái có audio. `metadata_json` giữ dữ liệu mở rộng như tên file gốc, kích thước file, nội dung TTS, voice, tham số sinh, nhóm audio và thông tin lần render.

### 5.3. Migration

- `0001_initial`: tạo năm bảng chính.
- `0002_sequence_batches`: thêm `batch_name` cho sequence.
- `0003_video_batch_ownership`: thêm `video_batch_name` cho asset video để mỗi video nguồn thuộc tối đa một batch tại một thời điểm.

Khi khởi động, ứng dụng vẫn gọi `Base.metadata.create_all()`. Script production đồng thời chạy `alembic upgrade head` trước khi mở server.

## 6. Cấu trúc dữ liệu trên đĩa

Mỗi project dùng UUID và có cây thư mục riêng:

```text
data/projects/<project-id>/
├── source/
│   ├── videos/
│   └── audio/
├── generated/
│   └── tts/
├── work/
│   ├── normalized/
│   └── concat/
├── outputs/
├── logs/
└── thumbnails/
```

Đường dẫn lưu trong database là đường dẫn tương đối tính từ thư mục project. `resolve_asset_path()` kiểm tra đường dẫn sau khi resolve để ngăn truy cập ra ngoài thư mục project. Tên file được chuẩn hóa về ASCII, giữ chữ, số, `_`, `-` và phần mở rộng; tên trùng được thêm hậu tố `-2`, `-3`, ...

Xóa project sẽ xóa cả bản ghi database lẫn toàn bộ cây thư mục tương ứng. Xóa asset sẽ xóa bản ghi, file media và thumbnail nếu có.

## 7. Các phân hệ backend

### 7.1. Khởi động ứng dụng

Trong lifecycle của FastAPI, ứng dụng:

1. Thiết lập logging.
2. Tạo các thư mục dữ liệu/log còn thiếu.
3. Bảo đảm các bảng tồn tại.
4. Đánh dấu job đang `running`, `rendering` hoặc `processing` thành `failed` sau sự cố khởi động lại.
5. Nộp lại các job còn ở trạng thái `queued` vào hàng đợi.

### 7.2. Quản lý job

`JobManager` dùng hai executor:

- Một `ThreadPoolExecutor` có tối đa `MAX_CONCURRENT_JOBS` worker cho render và xử lý audio; mặc định là 3.
- Một executor một worker riêng cho TTS, bảo đảm model dùng chung xử lý đúng thứ tự và không tranh chấp GPU.

Các loại job hiện có:

| Kind | Công việc |
|---|---|
| `tts` | Sinh WAV/MP3 từ văn bản bằng VieNeu-TTS |
| `audio_process` | Cắt và thay đổi tốc độ audio bằng FFmpeg |
| `render` | Ghép sequence video với voice/BGM và xuất MP4 |

Trạng thái thường đi qua `queued` → `running` → `completed`. Job có thể kết thúc ở `failed` hoặc `cancelled`. Người dùng có thể hủy job đang hoạt động và tạo một job mới từ job lỗi/hủy bằng thao tác retry.

Frontend nhận bản tóm tắt job qua SSE mỗi 1,5 giây. Endpoint chỉ phát sự kiện mới khi payload thay đổi; nếu không sẽ gửi heartbeat. Khi thấy output mới, frontend tải lại danh sách asset.

### 7.3. VieNeu-TTS

Adapter TTS:

- Chấp nhận device `auto`, `cuda` hoặc `cpu`.
- Dùng backend ONNX khi chọn CPU.
- Đọc nhanh danh sách preset từ `voices_v3_turbo.json`; chỉ khởi tạo model nếu file preset không tồn tại.
- Đặt `HF_HUB_OFFLINE=1` và `TRANSFORMERS_OFFLINE=1` để dùng cache local.
- Cache một engine theo device.
- Xuất WAV trực tiếp; với MP3, tạo WAV tạm rồi chuyển bằng `libmp3lame` 192 kbps.

Các tham số sinh được đưa xuống VieNeu gồm batch size, temperature, max chars, top-k, top-p, repetition penalty và khoảng lặng. Tốc độ đọc khác `1.0` được áp dụng hậu kỳ bằng filter `atempo`.

VieNeu SDK không cung cấp tổng frame trước khi suy luận, nên progress TTS là ước tính theo độ dài văn bản và thời gian đã chạy; mức 100% chỉ được đặt khi file đã sinh, probe và ghi database thành công.

### 7.4. Sequence engine

Engine hỗ trợ:

- `manual`: người dùng tự chọn thứ tự video.
- `permutation`: hoán vị không lặp, số lượng là `n! / (n-k)!`.
- `product_with_repetition`: tích Descartes có lặp, số lượng là `n^k`.

Engine kiểm tra số lượng trước khi materialize danh sách. API giới hạn theo giá trị nhỏ hơn giữa `payload.limit` và `MAX_SEQUENCE_OUTPUTS`; mặc định tối đa 100 output. ID video trùng trong nguồn bị từ chối.

Mỗi batch có tên riêng. Khi xóa một batch, các sequence bị xóa và video thuộc batch đó được trả về trạng thái chưa gán.

### 7.5. Pipeline render FFmpeg

Pipeline thực hiện các bước sau:

1. Đọc sequence và asset liên quan.
2. Nếu chính sách là `match_audio_loop_video`, lặp cả sequence đủ để phủ thời lượng voice.
3. Scale video theo độ phân giải đích.
4. Với `fit`, giữ tỷ lệ và thêm nền đen; với `fill`, phóng rồi crop.
5. Chuẩn hóa FPS, SAR và audio về stereo 48 kHz.
6. Tạo audio im lặng cho clip không có audio để concat ổn định.
7. Concat các clip.
8. Giữ, tắt hoặc trộn âm thanh gốc; thêm voice và BGM theo volume riêng.
9. Encode H.264 và AAC, thêm `+faststart`.
10. Theo dõi `-progress pipe:1`, xác minh output bằng FFprobe rồi mới đăng ký asset.

Các chính sách thời lượng:

| Giá trị | Hành vi |
|---|---|
| `match_audio_loop_video` | Lặp sequence video và cắt theo thời lượng voice |
| `match_video` | Giữ thời lượng video; audio được pad/cắt theo video |
| `shortest` | Dừng theo nguồn ngắn nhất |

Các chính sách audio nguồn hợp lệ là `replace`, `mix`, `keep_original` và `mute`. Trong implementation hiện tại, `replace` và `mute` đều bỏ audio gốc; `mix` và `keep_original` đều đưa audio gốc vào bộ trộn với `source_volume`.

Encoder hỗ trợ `h264_nvenc` và `libx264`. NVENC dùng preset `p4`, CQ 22; libx264 dùng preset `medium`, CRF 20. Audio output là AAC 192 kbps, 48 kHz, pixel format video là `yuv420p`.

## 8. Giao diện và workflow

### 8.1. Quản lý project

Thanh bên cho phép tạo, chọn, đổi tên, xóa và mở thư mục project. Project đang chọn được lưu trong `localStorage` để giữ qua lần tải trang sau.

### 8.2. Media

Tab Media cho phép nhập nhiều video/audio, xem preview và metadata. Định dạng hỗ trợ:

- Video: `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`, `.m4v`.
- Audio: `.wav`, `.mp3`, `.m4a`, `.aac`, `.flac`, `.ogg`, `.opus`.

Mỗi file được đọc theo chunk 1 MiB và giới hạn bằng `MAX_UPLOAD_MB`. Video được tạo thumbnail tại mốc gần 0,2 giây; lỗi thumbnail không làm hỏng việc import asset.

### 8.3. Tạo giọng

Người dùng có thể:

- Nhập văn bản trực tiếp.
- Chọn preset voice và device.
- Chọn MP3/WAV, tốc độ đọc và tham số nâng cao.
- Nhập Excel `.xlsx` với đúng hai cột `STT` và `text`.
- Gom audio theo tên nhóm, lọc theo nhóm và ngày tạo.
- Chọn nhiều audio để tạo bản đổi tốc độ hàng loạt.
- Cắt đầu/cuối và đổi tốc độ một audio; kết quả là asset mới, không ghi đè nguồn.

Excel tối đa 10 MiB và 1.000 dòng nội dung. STT phải là số nguyên liên tục từ 1 đến n. Tên nhóm audio không được trùng trong project.

### 8.4. Batch video

Người dùng tạo nhiều batch độc lập, chọn video nguồn, chọn thuật toán và K. UI hiển thị trước số sequence dự kiến. Sequence có thể bật/tắt, đổi tên hoặc xóa. Video nguồn được gắn quyền sở hữu batch để tránh dùng nhầm giữa các batch.

### 8.5. Gán audio và xuất video

Mỗi sequence có thể nhận:

- Một voice audio.
- Một BGM.
- Chính sách tắt/giữ audio gốc.
- Volume voice và BGM.
- Tên tùy chỉnh.

Giao diện có modal xem/nghe thử, preset 16:9 và 9:16, lựa chọn fit/fill, encoder và chính sách thời lượng. API mặc định yêu cầu mỗi sequence có voice và không dùng trùng voice; người dùng phải bật cờ ngoại lệ nếu muốn thiếu hoặc dùng lại audio.

Một lần nhấn render tạo một nhóm output chung với timestamp ổn định. Tên mặc định có dạng:

```text
<ngày>-<tháng>-<năm-2-số>-<giờ>-<phút>-<giây>-<tên-output>-<số-thứ-tự>.mp4
```

### 8.6. Công việc và kết quả

Tab cuối hiển thị job, progress, lỗi, hủy và retry. Output được nhóm theo thư mục lần chạy. Người dùng có thể:

- Xem video trực tiếp.
- Đổi tên một nhóm hoặc toàn bộ output.
- Chọn một số video để tải.
- Tải cả nhóm hoặc toàn bộ output.
- Chọn mật độ lưới hiển thị.

Frontend ưu tiên File System Access API để ghi trực tiếp vào thư mục người dùng chọn, tối đa ba lượt tải song song. Backend cũng có endpoint tạo ZIP cho một danh sách output.

## 9. Danh mục API

Tất cả endpoint nghiệp vụ có tiền tố `/api`.

### System

| Method | Endpoint | Chức năng |
|---|---|---|
| GET | `/health` | Health check cơ bản |
| GET | `/system/status` | Kiểm tra database, FFmpeg, FFprobe, NVENC, CUDA, TTS và dung lượng đĩa |
| GET | `/system/tts/voices?device=auto` | Danh sách voice preset |

### Project

| Method | Endpoint | Chức năng |
|---|---|---|
| POST | `/projects` | Tạo project |
| GET | `/projects` | Liệt kê project mới cập nhật trước |
| GET | `/projects/{project_id}` | Xem project |
| PATCH | `/projects/{project_id}` | Đổi tên/cập nhật settings |
| DELETE | `/projects/{project_id}` | Xóa project và media |
| POST | `/projects/{project_id}/open-folder` | Mở thư mục project bằng Explorer |

### Asset và output

| Method | Endpoint | Chức năng |
|---|---|---|
| POST | `/projects/{project_id}/assets/import` | Nhập nhiều video/audio; multipart `files`, tùy chọn `batch_name` |
| GET | `/projects/{project_id}/assets` | Liệt kê asset, có thể lọc query `type` |
| PATCH | `/assets/{asset_id}/video-batch` | Gán hoặc bỏ video khỏi batch |
| GET | `/assets/{asset_id}/stream` | Stream/tải file asset |
| GET | `/assets/{asset_id}/thumbnail` | Lấy thumbnail JPEG |
| DELETE | `/assets/{asset_id}` | Xóa asset và file |
| PATCH | `/projects/{project_id}/outputs/rename` | Đổi tên hàng loạt theo base name và thứ tự |
| POST | `/projects/{project_id}/outputs/download` | Tạo ZIP tạm chứa các output được chọn |

### Sequence

| Method | Endpoint | Chức năng |
|---|---|---|
| GET | `/projects/{project_id}/sequences` | Liệt kê sequence kèm item/asset |
| POST | `/projects/{project_id}/sequences/manual` | Tạo sequence thủ công |
| POST | `/projects/{project_id}/sequences/generate` | Sinh permutation hoặc product có lặp |
| PATCH | `/sequences/{sequence_id}` | Đổi tên hoặc bật/tắt sequence |
| DELETE | `/sequences/{sequence_id}` | Xóa sequence |
| DELETE | `/projects/{project_id}/sequence-batches/{batch_name}` | Xóa toàn bộ batch và trả video về trạng thái tự do |

### Job

| Method | Endpoint | Chức năng |
|---|---|---|
| POST | `/projects/{project_id}/tts/jobs` | Tạo một job TTS |
| POST | `/projects/{project_id}/tts/excel-jobs` | Tạo nhiều job TTS từ Excel |
| POST | `/assets/{asset_id}/audio/jobs` | Tạo bản audio cắt/đổi tốc độ |
| POST | `/projects/{project_id}/audio/batch-jobs` | Đổi tốc độ nhiều audio |
| POST | `/projects/{project_id}/render/jobs` | Tạo một hoặc nhiều render job |
| GET | `/jobs?project_id=...&limit=...` | Liệt kê job |
| GET | `/jobs/{job_id}` | Xem job |
| POST | `/jobs/{job_id}/cancel` | Hủy job |
| POST | `/jobs/{job_id}/retry` | Tạo job mới từ job lỗi/hủy |
| GET | `/events?project_id=...` | SSE cập nhật job |

Swagger UI có tại `http://127.0.0.1:8765/docs` khi backend đang chạy.

## 10. Cấu hình môi trường

Tạo `.env` từ `.env.example`:

```dotenv
DATABASE_URL=postgresql+psycopg://video_tts_app:change_me@127.0.0.1:5432/video_tts_studio
APP_HOST=127.0.0.1
APP_PORT=8765
DATA_DIR=./data
LOG_DIR=./logs
VIENEU_REPO=../VieNeu-TTS
TTS_DEVICE=auto
MAX_SEQUENCE_OUTPUTS=100
MAX_UPLOAD_MB=4096
MAX_CONCURRENT_JOBS=3
VIENEU_OFFLINE=1
```

| Biến | Ý nghĩa |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL tới PostgreSQL |
| `APP_HOST`, `APP_PORT` | Địa chỉ backend; script hiện dùng cố định `127.0.0.1:8765` |
| `DATA_DIR` | Thư mục gốc chứa project media |
| `LOG_DIR` | Thư mục runtime log |
| `VIENEU_REPO` | Đường dẫn tới repository VieNeu-TTS |
| `TTS_DEVICE` | Device mặc định; request vẫn có thể chọn `auto/cuda/cpu` |
| `MAX_SEQUENCE_OUTPUTS` | Trần sequence sinh trong một request |
| `MAX_UPLOAD_MB` | Giới hạn từng file upload |
| `MAX_CONCURRENT_JOBS` | Số media job không phải TTS chạy đồng thời |
| `VIENEU_OFFLINE` | Cờ quy ước cho vận hành offline; adapter cũng đặt biến Hugging Face offline |

Không commit `.env` vì chứa thông tin đăng nhập database.

## 11. Cài đặt trên Windows

### 11.1. Yêu cầu

- Windows và PowerShell.
- Python nằm trong môi trường `../VieNeu-TTS/.venv`.
- PostgreSQL chạy cục bộ.
- FFmpeg và FFprobe có trong `PATH`.
- Node.js/npm để cài và build frontend.
- NVIDIA driver/CUDA nếu muốn dùng VieNeu CUDA và NVENC; CPU/libx264 vẫn là lựa chọn thay thế.

Kiểm tra nhanh môi trường:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-environment.ps1
```

### 11.2. PostgreSQL

Có thể chạy script tương tác:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-postgres.ps1
```

Script tìm `psql`, yêu cầu mật khẩu admin, tạo/cập nhật role `video_tts_app`, tạo database `video_tts_studio` nếu chưa có và ghi `.env` với mật khẩu URL-encoded.

Hoặc tạo thủ công:

```sql
CREATE USER video_tts_app WITH PASSWORD 'mat_khau_manh';
CREATE DATABASE video_tts_studio OWNER video_tts_app;
```

### 11.3. Backend

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv pip install --python ..\VieNeu-TTS\.venv\Scripts\python.exe -r backend\requirements.txt
```

### 11.4. Frontend

```powershell
npm.cmd --prefix frontend install
npm.cmd --prefix frontend run build
```

## 12. Chạy ứng dụng

### Production local

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-local.ps1
```

Script sẽ build frontend nếu thiếu, chạy migration rồi mở Uvicorn. Truy cập `http://127.0.0.1:8765`.

### Development

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1
```

- Frontend Vite: `http://127.0.0.1:5173`.
- Backend/OpenAPI: `http://127.0.0.1:8765/docs`.
- Backend chạy với `--reload` trong process ẩn; frontend chạy ở terminal hiện tại.

### Dừng backend local

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-local.ps1
```

Script chỉ dừng process đang listen cổng 8765 nếu command line cho thấy đó là Uvicorn đúng cổng, tránh dừng nhầm chương trình khác.

## 13. Kiểm thử

Chạy test từ thư mục `backend` bằng Python của VieNeu:

```powershell
cd backend
..\..\VieNeu-TTS\.venv\Scripts\python.exe -m pytest
```

Các nhóm test chính:

| File | Phạm vi |
|---|---|
| `test_sequence_engine.py` | Hoán vị, tích có lặp, giới hạn và ID trùng |
| `test_storage.py` | Chuẩn hóa tên file tiếng Việt và fallback |
| `test_tts_excel.py` | Import Excel, đánh số tên audio |
| `test_workflow_rules.py` | Nhóm Excel và quy tắc audio khi render |
| `test_api_integration.py` | Project → import media → sequence → render FFmpeg thật |
| `postgres_smoke.py` | Smoke test PostgreSQL |
| `tts_smoke.py` | Smoke test VieNeu-TTS thực tế |

Một số test cô lập dùng SQLite và thư mục `test-*-data`. Integration test media cần FFmpeg/FFprobe. Smoke test TTS cần VieNeu model và tùy device có thể cần CUDA.

Build frontend để kiểm tra TypeScript:

```powershell
npm.cmd --prefix frontend run build
```

## 14. Logging và chẩn đoán

- Log ứng dụng chung: `logs/app.log`.
- Log từng job: `data/projects/<id>/logs/tts-*.log`, `audio-*.log`, `render-*.log`.
- Render log ghi cả câu lệnh FFmpeg và stderr.
- `/api/system/status` cho biết kết nối database, đường dẫn/version FFmpeg, hỗ trợ NVENC, CUDA/device, trạng thái model TTS, thư mục data và dung lượng trống.

Khi debug một job lỗi, kiểm tra theo thứ tự:

1. `error_message` của job trong UI/API.
2. File `log_path` của job.
3. `/api/system/status`.
4. `logs/app.log`.
5. Quyền truy cập file, dung lượng đĩa và việc file có đang bị player khác khóa hay không.

## 15. Quy tắc và giới hạn quan trọng

- Ứng dụng được thiết kế cho một máy local, chưa có authentication hoặc phân quyền người dùng.
- CORS chỉ cho frontend development tại `127.0.0.1:5173` và `localhost:5173`.
- TTS chạy tuần tự; render/audio có thể chạy song song theo `MAX_CONCURRENT_JOBS`.
- Tối đa mặc định 100 sequence mỗi lần sinh.
- Upload mặc định tối đa 4096 MiB cho từng file.
- Import Excel tối đa 10 MiB và 1.000 nội dung.
- Backend giữ tối đa 500 job trong một request danh sách; SSE gửi 100 job mới nhất.
- Tên file được chuyển sang ASCII nên dấu tiếng Việt không còn trong file vật lý.
- File System Access API dùng để tải trực tiếp phụ thuộc trình duyệt Chromium và quyền thư mục người dùng cấp.
- Xóa project là thao tác xóa cả metadata và media trên đĩa.
- Job đang chạy bị gián đoạn khi server restart sẽ được đánh dấu lỗi; job còn queued được nộp lại.
- `event_bus.py` tồn tại nhưng luồng SSE hiện tại polling database trực tiếp mỗi 1,5 giây.
- `APP_HOST`, `APP_PORT` có trong settings nhưng các script chạy hiện đang ghi cứng host/port.
- `frontend/vite.config.js` và các file `*.tsbuildinfo` là artifact sinh từ quá trình build; nguồn cấu hình chính là `vite.config.ts`.

## 16. Hạng mục chưa có hoặc đang theo dõi

Theo mã nguồn và hồ sơ phát triển hiện tại:

- Chưa có control voice cloning riêng; workflow dùng preset voice.
- Chưa có loudness normalization EBU R128.
- Chưa có subtitle và transition giữa clip.
- Cần tiếp tục đo VRAM khi VieNeu CUDA và NVENC hoạt động trên GPU dung lượng thấp.
- `OLLAMA_INTEGRATION_PLAN.md` mô tả kế hoạch tương lai; Ollama chưa nằm trong runtime chính hiện tại.
- `development_logs/ISSUES.md` còn một ghi chú PostgreSQL từng chưa có trên máy phát triển, trong khi changelog sau đó ghi smoke test PostgreSQL 17 đã hoàn tất. Khi dùng các log này làm trạng thái dự án, nên ưu tiên bản ghi mới hơn và xác minh lại bằng `check-environment.ps1`.

## 17. Hướng mở rộng hợp lý

Các hướng mở rộng phù hợp với kiến trúc hiện tại:

1. Tách `App.tsx` thành component/hook theo từng tab để giảm kích thước và tăng khả năng kiểm thử.
2. Dùng event bus thực sự hoặc PostgreSQL notification/WebSocket thay cho polling SSE.
3. Thêm migration-only startup và bỏ `create_all()` khi quy trình deployment đã ổn định.
4. Thêm authentication nếu backend được mở ra ngoài localhost.
5. Thêm probe/validation sớm cho encoder để tự động fallback từ NVENC sang libx264.
6. Thêm chính sách cleanup file tạm, output lỗi và asset mồ côi.
7. Bổ sung test frontend và test phục hồi job sau restart.
8. Chuẩn hóa trạng thái job bằng enum dùng chung giữa backend/frontend.
9. Thêm voice cloning, subtitle, transition và loudness normalization theo backlog.

## 18. Điểm vào quan trọng cho người phát triển

- Khởi tạo app: `backend/app/main.py`.
- Cấu hình: `backend/app/core/config.py`.
- Database models: `backend/app/models/entities.py`.
- Request/response schema: `backend/app/schemas/api.py`.
- Điều phối job: `backend/app/services/job_service.py`.
- Câu lệnh FFmpeg: `backend/app/services/render_service.py`.
- Adapter VieNeu: `backend/app/services/tts_service.py`.
- Quy tắc sequence: `backend/app/services/sequence_engine.py`.
- An toàn đường dẫn và tên file: `backend/app/services/storage_service.py`.
- Giao diện chính: `frontend/src/App.tsx`.
- HTTP client frontend: `frontend/src/api.ts`.
- Script chạy production: `scripts/run-local.ps1`.

---

Tài liệu được tổng hợp trực tiếp từ mã nguồn và cấu hình repository vào ngày 12/10/2026 (múi giờ Asia/Bangkok).
