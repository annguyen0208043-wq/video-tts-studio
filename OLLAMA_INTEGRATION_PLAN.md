# Kế hoạch tích hợp Ollama AI vào Video TTS Studio

## 1. Mục tiêu

Tích hợp một trợ lý AI chạy local vào Video TTS Studio để hỗ trợ:

1. Hỏi đáp và trò chuyện bằng tiếng Việt.
2. Tạo ý tưởng, dàn ý và kịch bản video.
3. Chuyển kịch bản thành storyboard có cấu trúc.
4. Sinh prompt cho ảnh, video, thumbnail và giọng đọc.
5. Điều phối các engine local: VieNeu-TTS, ComfyUI và FFmpeg.
6. Hỏi đáp dựa trên tài liệu riêng của project trong giai đoạn RAG.

Ollama đóng vai trò **bộ não tạo nội dung và điều phối**. Ollama không trực tiếp render ảnh, video hoặc âm thanh:

- Văn bản/kịch bản: Ollama.
- Giọng nói tiếng Việt: VieNeu-TTS hiện có.
- Ảnh và video AI: ComfyUI cùng model tương ứng.
- Ghép cảnh, giọng đọc, phụ đề: FFmpeg hiện có.

## 2. Phạm vi MVP

MVP chỉ triển khai những phần có thể vận hành ổn định trên máy hiện tại:

- Chat streaming với Ollama.
- Tạo kịch bản theo chủ đề, thời lượng, nền tảng và phong cách.
- Tạo storyboard JSON gồm nhiều cảnh.
- Sinh lời thoại tiếng Việt và prompt hình ảnh/video cho từng cảnh.
- Đưa lời thoại của từng cảnh sang quy trình VieNeu-TTS hiện có.
- Lưu cuộc hội thoại, kịch bản và storyboard theo project.
- Kiểm tra trạng thái Ollama và model từ màn hình System.
- Cho phép người dùng chỉnh sửa mọi nội dung trước khi tạo giọng/render.

Chưa đưa vào MVP:

- Tự động render ảnh/video bằng ComfyUI.
- Agent tự chạy toàn bộ pipeline mà không có bước xác nhận.
- Fine-tune model.
- RAG trên PDF/DOCX.
- Truy cập Internet từ model.
- Nhiều người dùng hoặc phân quyền.

## 3. Kiến trúc

```text
React UI
   |
   v
FastAPI backend
   |
   +-- AI service ----------> Ollama :11434
   |       |
   |       +-- prompt templates
   |       +-- JSON schema validation
   |       +-- conversation persistence
   |
   +-- TTS service ---------> VieNeu-TTS
   +-- Render service ------> FFmpeg
   +-- Generation service --> ComfyUI :8188 (giai đoạn sau)
   |
   +-- PostgreSQL ----------> metadata, chat, script, storyboard
   +-- data/projects -------> audio, video, ảnh và output
```

Frontend không gọi thẳng Ollama hoặc ComfyUI. Mọi request phải đi qua FastAPI để kiểm soát model, timeout, validation, log và tài nguyên GPU.

## 4. Ràng buộc phần cứng hiện tại

Máy hiện tại dùng NVIDIA GTX 1650 4 GB VRAM. Vì vậy:

- Model mặc định nên nằm trong nhóm 3B-4B, quantization Q4.
- Model 7B/8B có thể phải offload một phần sang RAM và sẽ chậm hơn.
- Không giữ Ollama trong VRAM khi VieNeu-TTS hoặc ComfyUI cần GPU.
- Chỉ chạy một tác vụ AI/GPU nặng tại một thời điểm.
- Ollama request cần đặt `keep_alive` ngắn hoặc `0` khi sắp chuyển sang TTS/render.
- RAM hệ thống khuyến nghị tối thiểu 16 GB, tốt hơn là 32 GB.
- Dành tối thiểu 50 GB SSD cho model và output; nếu thêm video AI nên dành 150-300 GB.

Mô hình khởi đầu đề xuất:

```text
Chat/kịch bản nhanh: qwen3:4b hoặc model 3B-4B tương đương
Reasoning tùy chọn:  model 7B/8B quantized, chỉ bật khi người dùng chọn
Embedding giai đoạn RAG: qwen3-embedding:0.6b hoặc embeddinggemma:300m
```

Tên model phải là cấu hình, không hard-code trong code. Trước khi phát hành cần test thực tế chất lượng tiếng Việt, RAM và tốc độ token/giây trên máy đích.

## 5. Cấu hình môi trường

Bổ sung vào `.env.example` ở giai đoạn triển khai:

```env
OLLAMA_ENABLED=1
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_CHAT_MODEL=qwen3:4b
OLLAMA_REASONING_MODEL=
OLLAMA_EMBED_MODEL=qwen3-embedding:0.6b
OLLAMA_REQUEST_TIMEOUT_SECONDS=180
OLLAMA_KEEP_ALIVE=30s
OLLAMA_MAX_CONTEXT=8192
OLLAMA_MAX_OUTPUT_TOKENS=4096
OLLAMA_TEMPERATURE=0.6
AI_MAX_CONCURRENT_JOBS=1

# Giai đoạn ComfyUI
COMFYUI_ENABLED=0
COMFYUI_BASE_URL=http://127.0.0.1:8188
```

Yêu cầu bảo mật:

- Ollama và ComfyUI chỉ bind `127.0.0.1` trong bản local.
- Không mở trực tiếp cổng `11434` hoặc `8188` ra Internet.
- Không cho frontend truyền URL Ollama tùy ý ở mỗi request.
- Giới hạn độ dài prompt, số message và kích thước ảnh tham chiếu.
- Loại bỏ path hệ thống, stack trace và dữ liệu nhạy cảm khỏi response UI.

## 6. Module backend cần bổ sung

```text
backend/app/
  api/
    ai.py                    # chat, script, storyboard, model/status
  schemas/
    ai.py                    # request/response và JSON schema
  services/
    ollama_client.py         # HTTP client, stream, timeout, retry
    ai_service.py            # use case và validation
    prompt_service.py        # nạp/version prompt template
    resource_manager.py      # khóa Ollama/TTS/ComfyUI dùng chung GPU
  prompts/
    chat_system.md
    script_writer.md
    storyboard_builder.md
    image_prompt_writer.md
    video_prompt_writer.md
  models/
    entities.py              # thêm conversation/script/storyboard
  db/
    migrations/              # migration mới
```

Nguyên tắc triển khai:

- Dùng HTTP API của Ollama thay vì chạy lệnh CLI từ request.
- Một `httpx.AsyncClient` dùng lại kết nối.
- Streaming từ Ollama được chuyển tiếp qua SSE.
- Retry tối đa một lần cho lỗi kết nối tạm thời; không retry tự động khi model đã sinh dở.
- Validate structured output bằng Pydantic.
- Nếu JSON không hợp lệ, thử repair tối đa một lần với prompt ngắn; sau đó trả lỗi rõ ràng.
- Mọi prompt template có `name` và `version` để truy vết kết quả.
- Không lưu nội dung suy luận nội bộ; chỉ lưu kết quả cuối và metadata cần thiết.

## 7. Mô hình dữ liệu

### AIConversation

- `id`: UUID.
- `project_id`: UUID, nullable nếu là chat chung.
- `title`.
- `model`.
- `system_prompt_version`.
- `created_at`, `updated_at`.

### AIMessage

- `id`, `conversation_id`.
- `role`: `system`, `user`, `assistant`, `tool`.
- `content`.
- `status`: `streaming`, `completed`, `failed`, `cancelled`.
- `prompt_tokens`, `output_tokens`, `duration_ms` nếu Ollama trả về.
- `created_at`.

### AIScript

- `id`, `project_id`.
- `title`, `topic`, `platform`, `language`.
- `target_duration_seconds`.
- `content`.
- `model`, `prompt_version`.
- `created_at`, `updated_at`.

### AIStoryboard

- `id`, `project_id`, `script_id`.
- `title`, `aspect_ratio`, `style`.
- `scenes_json`: dữ liệu đã validate.
- `model`, `prompt_version`.
- `created_at`, `updated_at`.

MVP có thể lưu `scenes_json` bằng PostgreSQL JSONB. Chỉ tách bảng scene riêng khi cần query, version hoặc render độc lập phức tạp.

## 8. Schema storyboard chuẩn

Ollama phải trả structured output theo schema gần với cấu trúc sau:

```json
{
  "title": "Cà phê Việt Nam trong 30 giây",
  "language": "vi",
  "platform": "tiktok",
  "aspect_ratio": "9:16",
  "total_duration_seconds": 30,
  "scenes": [
    {
      "scene_no": 1,
      "duration_seconds": 5,
      "narration": "Một ly cà phê Việt Nam bắt đầu từ những hạt cà phê được rang đậm.",
      "on_screen_text": "Cà phê Việt Nam",
      "image_prompt": "Close-up of Vietnamese coffee beans, warm cinematic light...",
      "video_prompt": "Slow macro dolly movement over roasted coffee beans...",
      "negative_prompt": "blurry, distorted, watermark, unreadable text",
      "camera": "macro, slow dolly in",
      "transition": "fade",
      "sound_effect": "soft coffee beans pouring"
    }
  ]
}
```

Validation bắt buộc:

- `scene_no` liên tục và không trùng.
- Mỗi cảnh dài 2-15 giây trong MVP.
- Tổng thời lượng cảnh lệch không quá 10% so với yêu cầu.
- `narration` không rỗng nếu chế độ video có giọng đọc.
- `aspect_ratio` chỉ nhận preset được hỗ trợ.
- Giới hạn tối đa 30 cảnh.
- Không tự động đưa nội dung vào TTS/render trước khi người dùng xác nhận.

## 9. API dự kiến

### System và model

```text
GET  /api/ai/status
GET  /api/ai/models
POST /api/ai/models/{model}/warmup
POST /api/ai/models/unload
```

`GET /api/ai/status` trả:

```json
{
  "enabled": true,
  "reachable": true,
  "base_url": "http://127.0.0.1:11434",
  "selected_model": "qwen3:4b",
  "model_available": true,
  "busy": false
}
```

### Chat

```text
POST /api/projects/{project_id}/ai/conversations
GET  /api/projects/{project_id}/ai/conversations
GET  /api/ai/conversations/{id}/messages
POST /api/ai/conversations/{id}/messages
POST /api/ai/conversations/{id}/cancel
```

Chat response dùng SSE để gửi các event:

```text
message.started
message.delta
message.completed
message.failed
```

### Kịch bản và storyboard

```text
POST  /api/projects/{project_id}/ai/scripts/generate
GET   /api/projects/{project_id}/ai/scripts
PATCH /api/ai/scripts/{id}
POST  /api/ai/scripts/{id}/storyboards/generate
GET   /api/projects/{project_id}/ai/storyboards
PATCH /api/ai/storyboards/{id}
POST  /api/ai/storyboards/{id}/create-tts-jobs
```

Payload tạo kịch bản:

```json
{
  "topic": "Giới thiệu cà phê Việt Nam",
  "platform": "tiktok",
  "target_duration_seconds": 30,
  "audience": "người trẻ yêu du lịch",
  "tone": "gần gũi, giàu cảm xúc",
  "call_to_action": "Theo dõi để khám phá thêm",
  "language": "vi"
}
```

## 10. Tích hợp với VieNeu-TTS

Luồng MVP:

1. Người dùng tạo và chỉnh storyboard.
2. Người dùng chọn các cảnh cần tạo giọng.
3. Chọn voice và thông số VieNeu.
4. Backend tạo một TTS job cho mỗi cảnh hoặc gộp thành một bài đọc.
5. Asset audio lưu quan hệ với `storyboard_id` và `scene_no`.
6. Người dùng nghe thử, sửa narration và tạo lại riêng cảnh lỗi.

Hai chế độ:

- `per_scene`: một file audio cho mỗi cảnh; dễ đồng bộ và render lại.
- `full_script`: một file audio cho toàn bộ kịch bản; tự nhiên hơn nhưng khó căn cảnh.

Mặc định chọn `per_scene` cho workflow tạo video tự động.

Resource manager phải đảm bảo Ollama được unload hoặc nhả GPU trước khi VieNeu bắt đầu job CUDA. Không giữ khóa GPU trong lúc chỉ lưu DB hoặc stream dữ liệu về frontend.

## 11. Giai đoạn ComfyUI tạo ảnh và video

ComfyUI được thêm sau khi phần kịch bản/TTS ổn định.

### Thành phần

- Một workflow JSON chuẩn cho text-to-image.
- Một workflow JSON chuẩn cho image-to-video.
- Mapping rõ node nào nhận prompt, negative prompt, seed, width, height và số frame.
- `comfyui_client.py` để submit workflow, đọc queue/history và lấy output.
- Job riêng cho từng scene.
- Asset ảnh/video liên kết với storyboard scene.

### Luồng

```text
Storyboard scene
  -> xác nhận prompt
  -> tạo keyframe ảnh
  -> người dùng chọn ảnh
  -> image-to-video 3-5 giây
  -> tạo voice
  -> FFmpeg ghép cảnh + voice + subtitle
```

Với GTX 1650 4 GB, tạo video AI local có thể rất chậm hoặc không phù hợp với nhiều model hiện đại. Do đó ComfyUI phải là module tùy chọn và UI cần báo rõ khả năng phần cứng. Không được coi render video AI là tiêu chí hoàn thành MVP Ollama.

## 12. Giao diện cần bổ sung

### AI Studio

- Chat theo project.
- Chọn model từ danh sách model cho phép.
- Hiển thị trạng thái Ollama và model đang tải.
- Nút Stop generation.
- Các action nhanh: “Tạo ý tưởng”, “Viết kịch bản”, “Rút gọn”, “Đổi giọng văn”.

### Script Editor

- Form mục tiêu video.
- Editor cho phép sửa nội dung AI.
- Lịch sử các phiên bản gần nhất.
- Nút tạo storyboard.

### Storyboard Editor

- Danh sách hoặc card theo cảnh.
- Sửa narration, prompt, thời lượng và transition.
- Cảnh báo tổng thời lượng.
- Tạo lại một cảnh, không bắt buộc tạo lại toàn bộ.
- Chọn cảnh rồi gửi sang Voice Studio.
- Giai đoạn sau: tạo keyframe/video cho từng cảnh.

### System Status

- Ollama reachable/unreachable.
- Model đã cài/chưa cài.
- Model đang loaded.
- TTS/GPU/render có đang bận không.
- Hướng dẫn lệnh cài/pull model khi thiếu.

## 13. Prompt engineering

Mỗi use case dùng system prompt riêng. Không dùng một prompt lớn cho mọi tác vụ.

Quy tắc chung:

- Viết system prompt bằng tiếng Việt rõ ràng.
- Bắt buộc phân biệt dữ liệu người dùng và chỉ dẫn hệ thống.
- Với storyboard, dùng JSON Schema và temperature thấp hơn, khoảng 0.2-0.4.
- Với ý tưởng sáng tạo, temperature có thể 0.7-0.9.
- Không đưa toàn bộ lịch sử chat vào mọi request; dùng sliding window hoặc summary.
- Giới hạn context thực tế ở 8K trước, dù model công bố context lớn hơn.
- Prompt tạo ảnh/video nên viết bằng tiếng Anh nếu model đích đáp ứng tốt hơn, còn narration giữ tiếng Việt.
- Lưu `prompt_version` trong kết quả để tái hiện và đánh giá.

## 14. Xử lý lỗi

Các lỗi phải có mã và hướng xử lý:

```text
OLLAMA_UNREACHABLE
MODEL_NOT_INSTALLED
MODEL_LOAD_FAILED
AI_BUSY
AI_TIMEOUT
AI_CANCELLED
CONTEXT_TOO_LARGE
INVALID_STRUCTURED_OUTPUT
INSUFFICIENT_MEMORY
```

Ví dụ thông báo UI:

```text
Không kết nối được Ollama tại 127.0.0.1:11434.
Hãy mở Ollama rồi thử lại. Dữ liệu kịch bản chưa bị mất.
```

Không tự động tải model nhiều GB từ request của người dùng. Màn hình setup chỉ hiển thị lệnh hoặc có bước xác nhận rõ ràng trước khi download.

## 15. Kiểm thử

### Unit test

- Validate storyboard hợp lệ và không hợp lệ.
- Tổng thời lượng và giới hạn số cảnh.
- Prompt template render đúng biến.
- Chặn model ngoài allowlist.
- Resource manager không cho Ollama và TTS CUDA chạy đồng thời.
- Cắt lịch sử chat khi vượt context budget.

### Integration test

- Mock Ollama streaming response.
- Ollama dừng giữa stream.
- Timeout và cancel.
- Model trả JSON sai.
- Tạo script, storyboard, lưu DB rồi mở lại.
- Tạo TTS job từ một scene.

### Smoke test với Ollama thật

1. `GET /api/ai/status` xác nhận model khả dụng.
2. Gửi một chat tiếng Việt và nhận stream.
3. Tạo kịch bản 30 giây.
4. Tạo storyboard 5-8 cảnh đúng schema.
5. Sửa narration của một cảnh.
6. Tạo TTS cho cảnh đó.
7. Xác nhận Ollama đã nhả tài nguyên trước TTS CUDA.

## 16. Lộ trình triển khai

### Giai đoạn A - Ollama foundation

- Thêm config và health check.
- Viết async Ollama client.
- Thêm model allowlist, timeout, cancel và logging.
- Thêm resource manager dùng chung với TTS.
- Unit test client và resource lock.

Kết quả: backend gọi được Ollama an toàn và biết rõ trạng thái model.

### Giai đoạn B - Chat local

- Migration conversation/message.
- API chat streaming SSE.
- UI AI Studio.
- Lưu và mở lại lịch sử chat.
- Stop generation.

Kết quả: chat tiếng Việt local theo từng project.

### Giai đoạn C - Script và storyboard

- Prompt templates có version.
- Schema Pydantic cho script/storyboard.
- API structured output.
- Script Editor và Storyboard Editor.
- Regenerate riêng từng scene.

Kết quả: từ một ý tưởng tạo được storyboard có thể chỉnh sửa.

### Giai đoạn D - Nối VieNeu-TTS

- Tạo TTS theo scene/full script.
- Liên kết asset với storyboard.
- Điều phối GPU Ollama/VieNeu.
- Nghe thử và retry theo scene.

Kết quả: storyboard tạo được voice tiếng Việt trong workflow hiện tại.

### Giai đoạn E - ComfyUI tùy chọn

- Health check và client ComfyUI.
- Workflow ảnh chuẩn.
- Workflow image-to-video phù hợp phần cứng.
- Queue, progress, cancel và lưu asset.

Kết quả: có thể tạo media cho từng scene nếu máy đáp ứng.

### Giai đoạn F - RAG

- Import và extract tài liệu.
- Chunking có metadata.
- Embedding qua Ollama.
- PostgreSQL pgvector hoặc Qdrant.
- Trả lời kèm nguồn tài liệu.

Kết quả: trợ lý trả lời dựa trên dữ liệu riêng của project.

## 17. Checklist trước khi code

- [ ] Ollama đã cài và chạy tại `127.0.0.1:11434`.
- [ ] Chọn model mặc định sau khi benchmark trên GTX 1650.
- [ ] Xác nhận RAM và dung lượng SSD.
- [ ] Chốt chat streaming dùng SSE.
- [ ] Chốt schema storyboard phiên bản 1.
- [ ] Chốt per-scene TTS là mặc định.
- [ ] Chốt quy tắc khóa GPU với VieNeu.
- [ ] Chốt model allowlist và giới hạn prompt.
- [ ] Viết migration có thể rollback.
- [ ] Có mock test, không bắt CI phải cài Ollama.

## 18. Definition of Done cho MVP Ollama

MVP được xem là hoàn thành khi:

- App tự kiểm tra được Ollama và model mặc định.
- Người dùng chat tiếng Việt và nhận nội dung streaming.
- Hội thoại được lưu theo project.
- Tạo được kịch bản từ form yêu cầu.
- Tạo được storyboard đúng schema và sửa được từng cảnh.
- Có thể tạo VieNeu-TTS từ narration của một hoặc nhiều cảnh.
- Có cancel, timeout và lỗi dễ hiểu.
- Ollama không làm TTS CUDA hết VRAM do chạy đồng thời.
- Backend không mở Ollama trực tiếp ra mạng ngoài.
- Unit/integration tests cốt lõi chạy mà không cần Ollama thật.
- README có hướng dẫn cài Ollama, pull model và khắc phục lỗi thường gặp.

## 19. Thứ tự ưu tiên thực tế

Thứ tự nên thực hiện:

```text
Ollama health/client
  -> chat streaming
  -> script JSON
  -> storyboard JSON
  -> VieNeu per scene
  -> render bằng media người dùng cung cấp
  -> ComfyUI ảnh
  -> ComfyUI video
  -> RAG
```

Không nên bắt đầu bằng video AI. Trên phần cứng hiện tại, giá trị lớn nhất và ổn định nhất đến từ kịch bản, storyboard, prompt và giọng đọc; phần render ảnh/video có thể thêm sau hoặc chạy trên một máy GPU mạnh hơn.
