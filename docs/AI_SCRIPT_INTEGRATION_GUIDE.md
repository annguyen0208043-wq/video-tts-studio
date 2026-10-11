# HƯỚNG DẪN CHO CODEX — TÍCH HỢP AI VIẾT KỊCH BẢN VÀO VIDEO TTS STUDIO

## 1. Mục tiêu

Bổ sung chức năng **AI viết kịch bản video ngắn** vào ứng dụng **Video TTS Studio** hiện có.

Luồng sử dụng:

1. Người dùng nhập thông tin sản phẩm.
2. Chọn **Skill** (bộ quy tắc viết), số lượng kịch bản và thời lượng mong muốn (mặc định **18–20 giây**).
3. AI viết kịch bản tiếng Việt bằng API có hạn mức miễn phí.
4. Người dùng xem, sửa và chọn kịch bản.
5. Nhấn **Tạo giọng nói** để đưa văn bản vào **VieNeu-TTS local đã có sẵn**.

**Yêu cầu quan trọng:** Tận dụng code hiện tại; không viết lại hệ thống TTS, project, audio, video hoặc render.

## 2. Hệ thống hiện tại

Đọc `PROJECT_DOCUMENTATION.md` và kiểm tra code thực tế trước khi sửa.

- Backend: Python + FastAPI; frontend: React + TypeScript + Vite.
- Database: PostgreSQL; TTS: VieNeu-TTS v3 Turbo chạy local.
- Đã có tạo TTS theo văn bản và theo Excel, quản lý asset/job, và hàng đợi xử lý.
- Endpoint TTS hiện có: `POST /api/projects/{project_id}/tts/jobs`.
- Các vị trí cần xem: `backend/app/services/tts_service.py`, `backend/app/services/job_service.py`, `backend/app/schemas/api.py`, `frontend/src/App.tsx`, `frontend/src/api.ts`.

**Codex phải kiểm tra schema request/response thật của endpoint TTS**, không tự đoán cấu trúc body.

## 3. Chức năng mới cần làm (phiên bản đầu tiên)

### A. Kết nối nhiều nhà cung cấp AI

Hỗ trợ:

- **Gemini API**: ưu tiên số 1.
- **Groq API**: dự phòng số 2.
- **OpenRouter**: dự phòng số 3, chỉ chọn model miễn phí.
- **Ollama local**: tùy chọn, có thể làm sau nếu chưa cài trên máy.

Tạo **AI Router** ở backend:

- Chế độ **Auto**: thử các provider theo thứ tự cấu hình.
- Khi một provider hết hạn mức (`429`), quá tải (`5xx`) hoặc timeout thì chuyển sang provider tiếp theo.
- Có timeout, số lần retry giới hạn và cooldown để không gọi liên tục một API đang bị giới hạn.
- Nếu người dùng chọn model thủ công, thông báo lỗi rõ ràng; không âm thầm đổi model trừ khi giao diện cho phép.
- Nếu tất cả provider không khả dụng, trả về thông báo dễ hiểu; không làm hỏng chức năng TTS.
- Ưu tiên **miễn phí**, không tự kích hoạt dịch vụ/model trả phí. Model ID phải cấu hình được, **không hardcode model cũ hoặc giả định free tier luôn tồn tại**.
- Không xoay nhiều tài khoản/key để vượt chính sách hạn mức của nhà cung cấp.

Chỉ cần **một request AI để tạo nhiều kịch bản** (ví dụ 5 hoặc 10 kịch bản), nếu giới hạn output cho phép.

### B. Thư mục Skills (bắt buộc)

Tạo thư mục dễ chỉnh sửa bằng file văn bản:

```text
video-tts-studio/
├── skills/
│   ├── tiktok-ban-hang/
│   │   ├── skill.md            # Quy tắc và phong cách viết
│   │   └── constraints.json   # Quy định có thể kiểm tra bằng code
│   ├── review-san-pham/
│   │   ├── skill.md
│   │   └── constraints.json
│   └── san-sale/
│       ├── skill.md
│       └── constraints.json
└── ...
```

- Backend đọc `skill.md` và `constraints.json` của Skill được chọn rồi ghép vào yêu cầu gửi model.
- Người dùng có thể sửa nội dung file Skill, thêm thư mục Skill mới mà không phải sửa logic sinh kịch bản.
- Chỉ đọc các tên Skill hợp lệ nằm trong `skills/` (chống đọc file ngoài thư mục).
- Có thể làm giao diện **chọn Skill** trước; phần chỉnh sửa file Skill trực tiếp trên web là tính năng nâng cấp sau.

**Ví dụ `skills/tiktok-ban-hang/skill.md`:**

```md
# TikTok bán hàng

Viết tiếng Việt tự nhiên, gần gũi như người thật review sản phẩm.

Quy tắc bắt buộc:
- Có hook hấp dẫn trong 1–3 giây đầu.
- Kịch bản là một đoạn văn liên tục, dễ đọc bằng TTS.
- Không bịa giá, ưu đãi, chất liệu hay tính năng sản phẩm.
- Không chèn tiêu đề, hashtag, emoji hoặc lời giải thích vào nội dung đọc.
- Các kịch bản trong cùng một lần tạo phải khác cách mở đầu và cách diễn đạt.
- Hướng đến thời lượng đọc 18–20 giây.
```

**Ví dụ `constraints.json`:**

```json
{
  "min_duration_seconds": 18,
  "max_duration_seconds": 20,
  "one_paragraph": true,
  "allow_hashtags": false,
  "allow_emoji": false
}
```

**Lưu ý:** AI có thể không tuân thủ hoàn toàn các hướng dẫn. Backend cần kiểm tra định dạng, số lượng kịch bản và các quy tắc kiểm tra được bằng code. Việc không bịa thông tin phải được hướng dẫn rõ trong prompt; không được tuyên bố đã kiểm chứng sự thật nếu chưa có bước đối chiếu dữ liệu sản phẩm.

### C. Tạo kịch bản và kết nối TTS

Form mới trên frontend gồm:

- **Thông tin sản phẩm** (ô nhập nhiều dòng).
- **Chọn Skill**.
- **Chọn AI**: Auto / Gemini / Groq / OpenRouter (Ollama nếu bật).
- **Số kịch bản**: ví dụ 1, 5, 10.
- **Thời lượng mục tiêu**: mặc định 18–20 giây.
- Nút **Tạo kịch bản**.

Sau khi tạo:

- Hiển thị từng kịch bản thành một ô văn bản **có thể chỉnh sửa**.
- Có nút **Tạo giọng nói** cho từng kịch bản, hoặc chọn nhiều kịch bản để tạo hàng loạt.
- Dùng lại API/job TTS hiện tại để tạo WAV/MP3 và lưu vào project như audio khác.
- **Không đưa các phần như tiêu đề hoặc metadata vào chuỗi text gửi TTS**.
- Nếu muốn kiểm tra thời lượng chính xác, sau khi sinh audio dùng FFprobe đã có; số từ chỉ là ước lượng vì tốc độ nói phụ thuộc voice.

## 4. Gợi ý cấu trúc code

Có thể điều chỉnh tên file theo convention hiện tại:

```text
backend/app/services/ai_router.py       # Gọi provider và fallback
backend/app/services/skill_loader.py    # Nạp Skill
backend/app/services/script_service.py  # Sinh và kiểm tra kịch bản
backend/app/api/scripts.py              # API mới
frontend/src/                      # Bổ sung UI vào workflow hiện có
skills/                            # Các file quy tắc viết
```

API tối thiểu đề xuất (tuân theo prefix `/api` hiện tại):

```text
GET  /api/ai/providers
GET  /api/ai/skills
POST /api/projects/{project_id}/scripts/generate
```

Request tạo kịch bản ví dụ:

```json
{
  "product_info": "Túi vải đeo chéo, đựng sách vở và laptop",
  "skill_id": "tiktok-ban-hang",
  "provider": "auto",
  "count": 5,
  "duration_min": 18,
  "duration_max": 20
}
```

Response ví dụ:

```json
{
  "provider_used": "gemini",
  "model_used": "<model-id-dang-cau-hinh>",
  "scripts": [
    {"index": 1, "text": "..."},
    {"index": 2, "text": "..."}
  ]
}
```

Nên yêu cầu model trả JSON có cấu trúc; dùng Pydantic kiểm tra kết quả trước khi trả frontend. Nếu JSON không hợp lệ, có thể cho sửa lại tối đa 1 lượt.

## 5. Cấu hình và bảo mật

Đặt API key trong file `.env` của backend và cập nhật `.env.example` (chỉ để giá trị mẫu):

```dotenv
GEMINI_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
AI_DEFAULT_PROVIDER=auto
```

- Không đưa API key vào React, response API, log hoặc Git.
- Cho phép bật/tắt provider và thay **model ID** từ cấu hình.
- Hiển thị provider/model được sử dụng (không hiển thị key).
- Hạn mức miễn phí thay đổi theo thời điểm, tài khoản và khu vực. Không cam kết tất cả request đều miễn phí nếu chưa kiểm tra điều kiện thực tế.
- App chỉ chạy local; giữ backend bind localhost như thiết kế hiện tại.

## 6. Thứ tự triển khai cho Codex

1. Đọc tài liệu và kiểm tra code thực tế, đặc biệt là luồng TTS đang hoạt động.
2. Tạo `skills/` và ít nhất một Skill mẫu (`tiktok-ban-hang`).
3. Xây dựng AI Router, cấu hình key/model và fallback có kiểm soát.
4. Tạo API liệt kê Skill/provider và API sinh kịch bản.
5. Bổ sung tab **AI Viết Kịch Bản** trong React; hỗ trợ chỉnh sửa text trước khi tạo giọng.
6. Nối nút tạo giọng với job VieNeu-TTS có sẵn, không nhân đôi code xử lý TTS.
7. Thêm test tối thiểu: không có API key, provider 429 và fallback, JSON AI lỗi, Skill không hợp lệ, tạo 5 kịch bản, TTS cũ vẫn chạy.
8. Chạy test/build hiện có, báo lại file đã thay đổi và hướng dẫn chạy trên Windows.

## 7. Tiêu chí hoàn thành

- [ ] Tạo được 1–10 kịch bản tiếng Việt từ mô tả sản phẩm.
- [ ] Chọn được Skill từ các thư mục `skills/`.
- [ ] Có Auto API và chuyển sang provider dự phòng nếu provider chính bị rate limit hoặc lỗi tạm thời.
- [ ] Có thể thay key/model mà không sửa logic ứng dụng.
- [ ] Kịch bản có thể xem và sửa trước khi gửi TTS.
- [ ] Nhấn **Tạo giọng nói** sẽ dùng VieNeu-TTS hiện tại, lưu audio đúng project.
- [ ] API key không lộ trên frontend/log.
- [ ] Các chức năng cũ (TTS Excel, quản lý project, render video) không bị ảnh hưởng.

---

**Yêu cầu Codex:** Triển khai theo hướng **đơn giản, dễ bảo trì, ít phụ thuộc mới**. Ưu tiên hoàn thành một workflow chạy tốt trước khi thêm giao diện phức tạp, thống kê quota nâng cao hoặc Ollama. Nếu tài liệu và code thực tế khác nhau, ưu tiên code thực tế, ghi rõ khác biệt. Không tự ý sửa những chức năng không liên quan.
