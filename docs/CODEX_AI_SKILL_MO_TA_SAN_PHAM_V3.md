# CODEX — YÊU CẦU CHÍNH XÁC V3: AI VIẾT KỊCH BẢN DỰA TRÊN MÔ TẢ SẢN PHẨM + SKILL

> **Tài liệu này thay thế phần yêu cầu sai về “mặc định 5 kịch bản / 36 giây” trong `CODEX_TRIEN_KHAI_AI_TTS_5_KICH_BAN_36_GIAY.md`.** Không dùng tài liệu 5/36 làm tiêu chí triển khai. Đây là đặc tả để Codex sửa repo thực tế, **chưa phải xác nhận tính năng đã được lập trình**.

## 1. Phạm vi và cách khảo sát

Đọc `README.md`, `AI_SCRIPT_INTEGRATION_GUIDE.md`, `CODEX_AI_TTS_SKILL_UI_V2.md` và `PROJECT_DOCUMENTATION.md` nếu có; kiểm tra code frontend/backend đang chạy. Những yêu cầu V2 mâu thuẫn với V3 (số lượng/thời lượng cố định, form trùng lặp) phải ưu tiên V3. Khi tài liệu và code thực tế khác nhau, lấy code làm căn cứ để tích hợp và ghi rõ khác biệt.

Theo README: ứng dụng local có **FastAPI + PostgreSQL**, **React/TypeScript/Vite**, **VieNeu-TTS v3 Turbo**, 25 giọng từ assets, TTS văn bản/Excel, project/audio/jobs, FFmpeg/FFprobe và trình ghép/xuất video. **Giữ nguyên mọi chức năng này; không tạo lại TTS hoặc media manager.**

## 2. Yêu cầu cốt lõi — chỉ có một quy trình

1. Người dùng **nhập hoặc dán mô tả sản phẩm** (text tự do, có thể gồm tên, đặc điểm, giá/ưu đãi nếu biết, điểm bán hàng, điều cần tránh).
2. Người dùng **chọn một Skill** trong dropdown/danh sách. Có thể **upload Skill `.md`**, xem nội dung, sửa/lưu/xóa Skill do mình tạo, tải file mẫu `.md` về để tùy chỉnh rồi upload lại.
3. Người dùng chọn provider **Auto / Gemini / Groq / OpenRouter** (Ollama local nếu ứng dụng đã hỗ trợ). Nhấn **Viết kịch bản bằng AI**.
4. Backend gọi API với **cả mô tả sản phẩm và nội dung Skill được chọn**, không bỏ qua một trong hai. AI tạo **một kịch bản** theo yêu cầu mặc định đơn giản (hoặc số phiên bản khác nếu người dùng/chính Skill có yêu cầu rõ). **KHÔNG cố định 5 kịch bản, 36 giây, 18–20 giây hoặc bất kỳ thời lượng nào.**
5. Kịch bản trả về được đưa vào **vùng biên tập text chung của TTS**, để người dùng sửa/duyệt. **Không tự tạo âm thanh ngay sau khi gọi AI.**
6. Người dùng chọn giọng và các tùy chọn VieNeu có sẵn rồi bấm **Tạo giọng nói**; dùng **job/endpoint TTS hiện tại**, lưu audio đúng project, hiển thị trong trình quản lý audio hiện có.

### Khi nào đặt số lượng/thời lượng?

- **Không yêu cầu số lượng hoặc thời lượng** ở luồng cơ bản.
- Nếu người dùng muốn, có thể dùng ô **Yêu cầu bổ sung** nhập “viết 3 phiên bản” hoặc “khoảng 25 giây”, hoặc đưa yêu cầu này trong Skill. Mở rộng số lượng/thời lượng thành phần Advanced là **tùy chọn**, không ép hiển thị slider trên giao diện chính.
- Nếu Skill quy định thời lượng, coi đó là **mục tiêu nội dung**, không được tuyên bố thời lượng audio chính xác trước khi tổng hợp và đo bằng FFprobe.
- Không dùng các `constraints.json` mẫu có mặc định 18–20 giây để âm thầm áp quy tắc lên Skill `.md` được upload.

## 3. Vai trò của mô tả sản phẩm và Skill

**Mô tả sản phẩm = nguồn thông tin thực tế người dùng cung cấp.** AI chỉ được lấy đặc điểm, vật liệu, giá bán, công dụng, khuyến mãi... từ mô tả đó. Không tự bịa thông số, hiệu quả, xuất xứ, mức giảm giá, cam kết bảo hành. Khi thiếu thông tin, viết trung tính hoặc nêu thiếu dữ liệu nếu chi tiết đó là bắt buộc.

**Skill = hướng dẫn cách viết.** Có thể chỉ định phong cách, hook, ngôn ngữ, đại từ, cấu trúc, giọng điệu, những từ phải tránh, CTA và độ dài nếu tác giả Skill muốn. Không lấy thông số sản phẩm ngẫu nhiên từ Skill chung để gán cho sản phẩm hiện tại. Nếu một Skill chuyên cho một sản phẩm có chứa dữ kiện, chỉ dùng những dữ kiện đó khi người dùng chủ động cho phép và không mâu thuẫn với mô tả hiện tại.

**Thứ tự xử lý xung đột:** quy định bảo mật/output của app > mô tả sản phẩm làm nguồn dữ kiện > Skill làm quy tắc phong cách > mặc định viết tự nhiên. Nếu xung đột làm đầu ra không khả thi, trả thông báo rõ để người dùng sửa. Skill là dữ liệu do người dùng cung cấp; không cho phép lệnh nhúng trong Skill đọc khóa API, file hệ thống hay thực hiện hành động ngoài tác vụ.

### Ví dụ prompt assembly (minh họa; có thể dùng schema khác)

```text
SYSTEM / ỨNG DỤNG:
Bạn là trợ lý viết kịch bản tiếng Việt cho TTS.
Chỉ sử dụng dữ kiện sản phẩm do người dùng cung cấp.
Không tự bịa giá, thành phần, công dụng, ưu đãi.
Chỉ tạo nội dung kịch bản, không truy cập file hoặc tiết lộ dữ liệu nội bộ.
Trả về dữ liệu theo schema mà backend yêu cầu.

SKILL ĐƯỢC CHỌN:
<nội dung UTF-8 của skill.md mà backend đã nạp theo skill_id>

MÔ TẢ SẢN PHẨM:
<nguyên văn mô tả do người dùng nhập>

YÊU CẦU BỔ SUNG (nếu có):
<yêu cầu tự do của người dùng>

NHIỆM VỤ:
Viết kịch bản dùng làm lời đọc TTS, phù hợp mô tả sản phẩm và Skill.
```

**Bắt buộc:** backend thực sự đọc nội dung file Skill mới nhất theo ID hợp lệ rồi đưa nội dung vào mỗi lần gọi API. Không gửi mỗi tên Skill hoặc chỉ nhãn dropdown. Có thể tính checksum/version để kiểm tra dữ liệu Skill thay đổi đã được áp dụng.

## 4. Giao diện — đơn giản, không lặp lại hai chức năng

Trong **khu vực Tạo giọng nói hiện có**, có thể dùng ba chế độ nội dung: **Văn bản | AI viết kịch bản | Excel** (điều chỉnh theo UI thực tế). Chế độ AI gồm:

- **Mô tả sản phẩm**: một textarea rõ ràng, đủ rộng.
- **Skill**: một dropdown, cạnh đó là **Quản lý Skill** và **Tải Skill mẫu**.
- **Provider**: Auto hoặc chọn tay.
- **Yêu cầu bổ sung** (không bắt buộc): nhập yêu cầu số lượng, độ dài, phong cách cụ thể nếu không đặt trong Skill.
- Nút **Viết kịch bản bằng AI**; có loading, lỗi và nút thử lại.
- **Một vùng biên tập kịch bản dùng chung** với luồng “Nhập văn bản” nếu kiến trúc cho phép. Không tạo textarea đầu ra AI riêng *và* textarea TTS cùng hiển thị, buộc người dùng copy qua lại. Có thể có nhiều phiên bản dưới dạng lựa chọn gọn nếu người dùng yêu cầu.
- **Một bộ chọn giọng/cài đặt TTS**, một nút tạo giọng, một danh sách audio/progress/playback — tất cả tái sử dụng từ UI cũ.

**Không ép các slider** số kịch bản/thời lượng vào màn hình chính; nếu thật sự cần chỉnh nhiều tham số thì đặt trong “Tùy chọn nâng cao”, và không đặt default 5/36. Thanh trượt thuộc VieNeu đang có tiếp tục dùng như cũ.

Yêu cầu Codex **chỉ ra hai khu vực thực tế đang bị trùng trong mã/UI rồi hợp nhất**, không đoán tên component khi chưa mở source; dùng hết không gian hợp lý trên desktop mà không thêm panel rỗng, responsive trên mobile. Tránh làm mất nội dung mô tả hoặc Skill đang chọn khi chuyển chế độ.

## 5. Quản lý Skill trực tiếp trên giao diện

**Bắt buộc:**

- Upload `.md`/`.markdown` UTF-8, validate định dạng/kích thước/nội dung trước khi lưu.
- Có file mẫu **tải về thật** từ app; cung cấp `SKILL_MAU_KICH_BAN_LINH_HOAT.md` (đính kèm theo tài liệu này) hoặc cùng nội dung trong `assets/templates/skill-template.md`.
- Danh sách Skill (tên, mô tả ngắn nếu có), chọn ngay sau upload, xem/sửa/lưu, đổi tên và xóa Skill do người dùng tạo. Skill hệ thống có thể read-only.
- UI báo rõ Skill nào đang được gửi kèm API.
- Skill của người dùng được lưu theo ID an toàn, không lấy nguyên filename upload làm đường dẫn; chống path traversal, MIME/extension không hợp lệ, UTF-8 lỗi, file quá lớn; không thực thi script/HTML từ Markdown.
- **Không bắt buộc `constraints.json`.** Markdown thuần là đủ. Nếu app đã hỗ trợ constraints tùy chọn, chỉ áp dụng giới hạn khi chúng được khai báo rõ và hợp lệ, không tự chèn khoảng thời lượng cứng vào Skill.

## 6. API AI — nhà cung cấp miễn phí có fallback

- Backend gọi **Gemini, Groq, OpenRouter** theo cấu hình `.env` và model ID có thể thay đổi, chỉ sử dụng model/free tier đủ điều kiện theo account. Danh sách model và hạn mức cần cấu hình, không hardcode một model được cho là miễn phí vĩnh viễn.
- Auto fallback với 429, timeout và 5xx, retry/cooldown hợp lý; chọn tay thì không âm thầm đổi provider. Không dùng nhiều key/tài khoản để né chính sách quota.
- API key chỉ giữ ở backend, không gửi đến frontend hoặc log. Không có key thì lỗi rõ mà TTS thủ công vẫn chạy.
- Yêu cầu AI đầu ra có cấu trúc (JSON) và validate qua Pydantic. Lưu **chỉ phần text đã sinh** để đưa sang TTS; không đọc tiêu đề/metadata vào giọng nói.

### API gợi ý, kiểm tra routing/conventions thật của repo

```text
GET    /api/ai/providers
GET    /api/ai/skills
GET    /api/ai/skills/template
POST   /api/ai/skills                    # upload .md
GET    /api/ai/skills/{skill_id}
PUT    /api/ai/skills/{skill_id}
DELETE /api/ai/skills/{skill_id}
POST   /api/projects/{project_id}/scripts/generate
```

**Request tối giản minh họa:**

```json
{
  "product_description": "Túi đeo chéo chất liệu vải, màu kem, có ngăn khóa kéo; không có thông tin giá",
  "skill_id": "user-skill-id",
  "provider": "auto",
  "additional_instruction": ""
}
```

**Response tối giản minh họa:**

```json
{
  "provider_used": "gemini",
  "model_used": "<model-id-trong-cau-hinh>",
  "script_text": "<kịch bản AI tạo ra>",
  "skill_id": "user-skill-id"
}
```

Nếu bổ sung nhiều phiên bản thì mở rộng response có cấu trúc, **không mặc định luôn trả 5 kết quả**. Kiểm tra endpoint TTS thật `POST /api/projects/{project_id}/tts/jobs` và schema Pydantic thực tế trước khi tích hợp; không suy diễn request body.

## 7. Kiểm thử nghiệm thu bắt buộc

1. Upload Skill A (phong cách “săn sale”), nhập mô tả túi; API gửi **nội dung Skill A + toàn bộ mô tả túi**, trả lời theo phong cách A.
2. Chuyển Skill B (“review tự nhiên”) với **cùng mô tả túi**; API gửi nội dung B, kịch bản khác phong cách.
3. Sửa nội dung Skill B, lưu và sinh lại: prompt dùng **nội dung phiên bản mới**, không cache sai.
4. Không đề cập giá trong mô tả: AI **không được tự thêm mức giá hoặc phần trăm giảm**; thêm tính năng/giá vào mô tả rồi sinh lại: AI có thể dùng dữ kiện mới phù hợp.
5. Skill mẫu không ép thời lượng. Giao diện không tự đặt “5 kịch bản”, “36 giây” hay “18–20 giây”. Nếu người dùng/Skill nêu thời lượng thì mới áp dụng như mục tiêu.
6. Chọn một kịch bản, chỉnh text rồi tạo voice bằng **endpoint VieNeu đã có**: audio đọc text chỉnh sửa mới nhất, lưu đúng project.
7. Upload/download/chọn/sửa/xóa Skill hoạt động, lỗi file rõ ràng, thao tác được khi đổi tabs; không lộ secrets.
8. Thiếu API key/AI 429/provider lỗi: UI báo lỗi nhưng Văn bản, Excel, VieNeu-TTS và render video cũ không bị ảnh hưởng.
9. Kiểm tra UI desktop (ví dụ 1440px) và mobile: không có 2 text editor/2 bộ chọn giọng/2 danh sách audio trùng lặp, không có panel rỗng.
10. Chạy test backend, TypeScript typecheck/frontend build, kiểm thử smoke các tính năng cũ. Báo pass/fail và file thay đổi một cách trung thực.

## 8. Lệnh triển khai dành cho Codex

**Hãy sửa trực tiếp source code repository Video TTS Studio hiện tại**, không chỉ mô tả giải pháp. Bắt đầu bằng đọc README, guide V2 và V3, khảo sát API TTS và UI thực tế; triển khai tối thiểu một luồng đầy đủ **Mô tả sản phẩm + Skill đã chọn -> AI API -> kịch bản có thể sửa -> VieNeu TTS cũ**. Ưu tiên UX gọn, upload/download Skill dùng được và không đụng các chức năng video không liên quan.

Sau khi xong, báo: file sửa, endpoint mới, hành trình thao tác, provider/model config, vị trí đã gộp UI trùng, test chạy được/chưa được và lỗi còn tồn tại. **Không tuyên bố đã tích hợp thành công khi chưa chạy/test trên repo thực tế.**
