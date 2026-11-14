# Hướng dẫn cài đặt Video TTS Studio cho máy không có GPU (chạy CPU)

> Tài liệu này dành cho máy **không có card NVIDIA** hoặc muốn chạy hoàn toàn bằng CPU.
> TTS sẽ dùng backend **ONNX** (chậm hơn CUDA nhưng không cần GPU).
> Video encode sẽ dùng **libx264** thay vì NVENC.

---

## 1. Yêu cầu hệ thống

| Thành phần | Yêu cầu tối thiểu |
|---|---|
| Hệ điều hành | Windows 10/11 (64-bit) |
| RAM | 8 GB (khuyến nghị 16 GB) |
| CPU | 4 cores trở lên |
| Dung lượng đĩa | ~5 GB cho phần mềm + dung lượng cho video/audio |
| Python | 3.10 – 3.12 (nằm trong môi trường VieNeu-TTS) |
| PostgreSQL | 15 hoặc 17 |
| Node.js | 18 LTS trở lên |
| FFmpeg | 6.0 trở lên |

---

## 2. Cài đặt từng bước

### Bước 1: Clone repository

```powershell
git clone https://github.com/annguyen0208043-wq/video-tts-studio.git
cd video-tts-studio
```

### Bước 2: Cài đặt VieNeu-TTS

Repository VieNeu-TTS cần nằm cạnh thư mục `video-tts-studio`:

```text
D:\D\tools\
├── VieNeu-TTS\          ← repo VieNeu-TTS
│   └── .venv\           ← môi trường Python
└── video-tts-studio\    ← repo này
```

```powershell
# Clone VieNeu-TTS (nếu chưa có)
cd ..
git clone <url-vieneu-tts> VieNeu-TTS
cd VieNeu-TTS

# Tạo môi trường ảo và cài đặt
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

> [!IMPORTANT]
> Với máy **không có GPU**, bạn **không cần** cài `torch` phiên bản CUDA.
> Cài PyTorch CPU-only để tiết kiệm dung lượng:
> ```powershell
> pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
> ```

### Bước 3: Cài công cụ bổ trợ (FFmpeg, Node.js)

**Cách 1 – Dùng script tự động** (cần Internet):

```powershell
cd video-tts-studio
powershell -ExecutionPolicy Bypass -File .\scripts\setup-tools.ps1
```

Script sẽ tải FFmpeg và Node.js vào thư mục `.tools/` và tự thêm vào PATH khi chạy.

**Cách 2 – Cài thủ công:**

- Tải [FFmpeg](https://ffmpeg.org/download.html) và thêm thư mục `bin/` vào PATH
- Tải [Node.js LTS](https://nodejs.org/) và cài đặt

Kiểm tra:

```powershell
ffmpeg -version
ffprobe -version
node --version
npm --version
```

### Bước 4: Cài PostgreSQL

Tải và cài [PostgreSQL](https://www.postgresql.org/download/windows/) (khuyến nghị phiên bản 17).

Sau khi cài, chạy script setup tự động:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-postgres.ps1
```

Script sẽ hỏi mật khẩu admin PostgreSQL, tạo user `video_tts_app`, database `video_tts_studio` và ghi file `.env`.

**Hoặc làm thủ công:**

```sql
-- Mở psql với user postgres
CREATE USER video_tts_app WITH PASSWORD 'mat_khau_manh_cua_ban';
CREATE DATABASE video_tts_studio OWNER video_tts_app;
```

Rồi copy `.env.example` thành `.env` và sửa `DATABASE_URL`:

```powershell
Copy-Item .env.example .env
```

Sửa dòng `DATABASE_URL` trong `.env`:

```dotenv
DATABASE_URL=postgresql+psycopg://video_tts_app:mat_khau_manh_cua_ban@127.0.0.1:5432/video_tts_studio
```

### Bước 5: Cài backend dependencies

```powershell
cd video-tts-studio
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv pip install --python ..\VieNeu-TTS\.venv\Scripts\python.exe -r backend\requirements.txt
```

> [!NOTE]
> Nếu chưa có `uv`, cài bằng: `pip install uv`
> Hoặc dùng pip trực tiếp:
> ```powershell
> ..\VieNeu-TTS\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
> ```

### Bước 6: Cài và build frontend

```powershell
npm.cmd --prefix frontend install
npm.cmd --prefix frontend run build
```

---

## 3. Cấu hình cho máy CPU

Sửa file `.env` với các giá trị quan trọng cho CPU:

```dotenv
# === Cấu hình cho CPU ===
TTS_DEVICE=cpu
# Không cần NVENC, render sẽ tự dùng libx264
```

> [!TIP]
> - `TTS_DEVICE=cpu` → VieNeu-TTS sẽ dùng backend ONNX, không cần CUDA.
> - Khi render video, chọn encoder **libx264** trong giao diện (thay vì h264_nvenc).
> - libx264 dùng preset `medium` và CRF 20 — chất lượng tốt, chỉ chậm hơn NVENC.

File `.env` đầy đủ mẫu cho CPU:

```dotenv
DATABASE_URL=postgresql+psycopg://video_tts_app:mat_khau@127.0.0.1:5432/video_tts_studio
APP_HOST=127.0.0.1
APP_PORT=8765
DATA_DIR=./data
LOG_DIR=./logs
VIENEU_REPO=../VieNeu-TTS
TTS_DEVICE=cpu
TTS_PRELOAD=1
MAX_SEQUENCE_OUTPUTS=100
MAX_UPLOAD_MB=4096
MAX_CONCURRENT_JOBS=4
VIENEU_OFFLINE=1
SKILLS_DIR=./skills
AI_DEFAULT_PROVIDER=auto
AI_TIMEOUT_SECONDS=30
AI_MAX_RETRIES=1
AI_COOLDOWN_SECONDS=60
GEMINI_API_KEY=
GEMINI_MODEL=
GROQ_API_KEY=
GROQ_MODEL=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=
```

---

## 4. Chạy ứng dụng

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-local.ps1
```

Hoặc dùng file bat:

```powershell
.\run.bat
```

Mở trình duyệt tại: **http://127.0.0.1:8765**

Dừng server:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-local.ps1
```

---

## 5. Kiểm tra môi trường

Chạy script kiểm tra để xác nhận mọi thứ đã sẵn sàng:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check-environment.ps1
```

Kết quả mong đợi trên máy CPU:

```
FFmpeg: ffmpeg version 8.x ...
FFprobe: ffprobe version 8.x ...
PostgreSQL: psql (PostgreSQL) 17.x
NVIDIA: <sẽ báo lỗi — bình thường vì không có GPU>
VieNeu Python: 2.x.x False   ← torch.cuda.is_available() = False là đúng
```

> [!NOTE]
> Lỗi ở dòng **NVIDIA** là bình thường vì máy không có GPU.
> Quan trọng là `torch.cuda.is_available()` trả về `False` — ứng dụng sẽ tự chuyển sang CPU/ONNX.

---

## 6. Lưu ý khi sử dụng trên CPU

### TTS (Tạo giọng đọc)

- Chọn **Device: CPU** trong giao diện khi tạo giọng.
- Tốc độ sinh audio sẽ **chậm hơn 3-5 lần** so với CUDA.
- ONNX backend ổn định và không cần driver NVIDIA.

### Render video

- Trong giao diện xuất video, chọn encoder **libx264** (không chọn h264_nvenc).
- Nếu chọn nhầm h264_nvenc mà không có GPU, render sẽ báo lỗi.
- Chất lượng libx264 tương đương NVENC, chỉ khác về tốc độ encode.

### Hiệu năng

| Tác vụ | GPU (CUDA + NVENC) | CPU (ONNX + libx264) |
|---|---|---|
| TTS 100 ký tự | ~2-5 giây | ~10-25 giây |
| Render 1 phút video | ~10-20 giây | ~30-90 giây |

> [!TIP]
> Để tăng tốc trên CPU:
> - Giảm `MAX_CONCURRENT_JOBS` xuống 2 nếu máy yếu.
> - Dùng độ phân giải thấp hơn (ví dụ 1280x720 thay vì 1920x1080).
> - Dùng format WAV thay vì MP3 cho TTS (bỏ bước chuyển đổi FFmpeg).

---

## 7. Khắc phục sự cố thường gặp

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| `Không tìm thấy VieNeu-TTS` | Đường dẫn `VIENEU_REPO` sai | Kiểm tra `.env` và vị trí thư mục VieNeu-TTS |
| `psql was not found` | PostgreSQL chưa cài hoặc chưa có trong PATH | Cài PostgreSQL và thêm `bin/` vào PATH |
| `Frontend chưa build` | Chưa chạy `npm run build` | Chạy lại bước 6 |
| `h264_nvenc` lỗi khi render | Chọn encoder GPU nhưng không có GPU | Đổi sang **libx264** trong giao diện |
| TTS quá chậm | CPU yếu hoặc RAM thiếu | Giảm batch size, giảm concurrent jobs |
| `ModuleNotFoundError: vieneu` | Chưa cài VieNeu vào venv | Chạy lại `pip install -e .` trong thư mục VieNeu-TTS |
| Database connection refused | PostgreSQL chưa chạy | Kiểm tra service PostgreSQL: `Get-Service *postgres*` |

---

## 8. Tóm tắt lệnh cài đặt nhanh

```powershell
# 1. Clone repo
git clone https://github.com/annguyen0208043-wq/video-tts-studio.git
cd video-tts-studio

# 2. Cài tools (FFmpeg + Node.js)
powershell -ExecutionPolicy Bypass -File .\scripts\setup-tools.ps1

# 3. Setup PostgreSQL + tạo .env
powershell -ExecutionPolicy Bypass -File .\scripts\setup-postgres.ps1

# 4. Cài backend dependencies
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv pip install --python ..\VieNeu-TTS\.venv\Scripts\python.exe -r backend\requirements.txt

# 5. Cài + build frontend
npm.cmd --prefix frontend install
npm.cmd --prefix frontend run build

# 6. Sửa .env: TTS_DEVICE=cpu

# 7. Chạy
powershell -ExecutionPolicy Bypass -File .\scripts\run-local.ps1
```
