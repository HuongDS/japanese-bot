# Japanese Kaiwa AI Friend - Bot Luyện Tiếng Nhật 24/7 Qua Discord

Bot Discord đóng vai người bạn thân người Nhật (Yuki - ユキ):
- Nhận biết khung giờ thực tế tại Nhật Bản (Tokyo GMT+9): Tự động thay đổi trạng thái sinh hoạt (sáng đi tàu điện, trưa ăn Bento, chiều uống cà phê, tối xem Anime, đêm khuya nhắc bạn đi ngủ sớm).
- Giao tiếp bằng Giọng nói 2 chiều (Voice Note / TTS & Speech-to-Text): Tự động gửi kèm file âm thanh phát âm tiếng Nhật chuẩn người bản xứ trong mỗi tin nhắn, đồng thời nghe và nhận diện được tin nhắn thoại (Voice Message) tiếng Nhật của bạn.
- Văn phong tiếng Nhật đời thường (LINE-style & Aizuchi): Sử dụng tự nhiên các từ đệm cảm thán (Aizuchi) và ngữ điệu bạn bè thân thiết thay vì văn phong sách giáo khoa cứng nhắc.
- Mỗi sáng chủ động nhắn tin hỏi thăm đời sống thường ngày theo giờ hẹn (mặc định 08:30 sáng, múi giờ Việt Nam) và đề xuất chủ đề Kaiwa mới.
- Điều chỉnh độ khó linh hoạt theo trình độ JLPT (N5, N4, N3, N2, N1).
- Bộ nhớ ngữ cảnh (Conversation Memory) giúp cuộc đối thoại diễn ra liền mạch.
- Hoạt động 24/7 trên Cloud (Render, Railway, VPS) thông qua Docker.

---

## Danh Sách Lệnh Điều Khiển

| Lệnh | Ý nghĩa và Cách sử dụng |
| :--- | :--- |
| !daily | Nhận ngay tin nhắn hỏi thăm theo khung giờ Tokyo và chủ đề Kaiwa kèm giọng nói. |
| !voice [on\|off\|nanami\|aoi\|mayu\|keita] | Bật/tắt tự động gửi giọng nói hoặc đổi giọng đọc (nữ/nam). |
| !speak [câu tiếng Nhật] | Yêu cầu bot phát âm một câu tiếng Nhật bất kỳ (hoặc gõ `!speak` để đọc lại tin nhắn vừa rồi). |
| !time | Xem giờ thực tế tại Tokyo (GMT+9) và trạng thái sinh hoạt hiện tại của Yuki. |
| !topic [chủ đề] | Đổi chủ đề hội thoại mới (Ví dụ: `!topic anime`, `!topic du lịch Tokyo` hoặc gõ `!topic` để bot tự chọn). |
| !level [n5\|n4\|n3\|n2\|n1] | Xem hoặc thay đổi trình độ tiếng Nhật (Ví dụ: `!level N4`, `!level N3`). |
| !reset | Làm mới bộ nhớ trò chuyện để bắt đầu cuộc trò chuyện mới từ đầu. |
| !model [tên_model] | Xem hoặc đổi model GPT (`gpt-4o`, `gpt-4o-mini`). |
| !status | Kiểm tra trạng thái bot, giờ Tokyo, cấu hình giọng nói, trình độ Kaiwa. |
| !help | Xem danh sách hướng dẫn chi tiết các lệnh. |
| Nhắn chữ hoặc Gửi Voice Chat | Gõ tiếng Nhật/tiếng Việt hoặc gửi tin nhắn thoại (Voice Message), bot sẽ phản hồi kèm giọng nói. |

---

## Hướng Dẫn Cấu Hình Bot Vào Discord Từ A Đến Z

### Bước 1: Tạo Ứng Dụng Và Bot Trên Discord Developer Portal
1. Truy cập trang quản trị ứng dụng của Discord: https://discord.com/developers/applications
2. Đăng nhập bằng tài khoản Discord cá nhân của bạn.
3. Nhấn nút "New Application" ở góc trên bên phải.
4. Nhập tên ứng dụng (ví dụ: `Yuki Japanese Friend`) và nhấn "Create".

### Bước 2: Bật Quyền Đọc Tin Nhắn (Bắt Buộc)
1. Trong menu bên trái, chọn thẻ "Bot".
2. Cuộn xuống phần "Privileged Gateway Intents".
3. Bật mục "MESSAGE CONTENT INTENT" sang trạng thái ON.
4. Nhấn "Save Changes" ở cuối trang để lưu lại.
(Lưu ý: Nếu không bật quyền này, bot sẽ không thể đọc được nội dung tin nhắn và các lệnh bạn gửi).

### Bước 3: Lấy Token Của Bot (DISCORD_BOT_TOKEN)
1. Vẫn tại thẻ "Bot", tìm phần "Token" ở phía trên.
2. Nhấn nút "Reset Token" (hoặc "Copy").
3. Sao chép chuỗi mã này lại cẩn thận. Đây chính là giá trị của biến `DISCORD_BOT_TOKEN`.
(Lưu ý: Tuyệt đối không để lộ token này cho người khác).

### Bước 4: Lấy User ID Của Bạn (DISCORD_ALLOWED_USER_ID)
Để đảm bảo bot chỉ nhận lệnh và trò chuyện với riêng bạn:
1. Mở ứng dụng Discord trên máy tính hoặc điện thoại.
2. Vào phần Cài đặt người dùng (User Settings) -> chọn Nâng cao (Advanced).
3. Bật tùy chọn "Chế độ nhà phát triển" (Developer Mode).
4. Quay lại giao diện Discord, nhấp chuột phải (hoặc nhấn giữ trên điện thoại) vào tên tài khoản của bạn -> chọn "Sao chép ID người dùng" (Copy User ID).
5. Dãy số bạn vừa copy chính là `DISCORD_ALLOWED_USER_ID`.

### Bước 5: Mời Bot Vào Server Discord Của Bạn
1. Tạo một Server Discord riêng cho bạn (nếu chưa có).
2. Quay lại trang Discord Developer Portal -> chọn thẻ "Installation" (hoặc "OAuth2" -> "URL Generator").
3. Tại phần "Scopes", tích chọn: `bot`.
4. Tại phần "Bot Permissions", tích chọn các quyền sau:
   - Send Messages
   - Send Messages in Threads
   - Read Message History
   - Embed Links
   - Attach Files
5. Sao chép đường dẫn tại mục "Install Link" (hoặc Generated URL).
6. Dán đường link đó vào trình duyệt web, chọn Server Discord của bạn và nhấn "Authorize" để hoàn tất thêm bot vào server.

---

## Cấu Hình Biến Môi Trường

Tạo file `.env` (sao chép từ `.env.example`):

```env
DISCORD_BOT_TOKEN=token_bot_lay_o_buoc_3
DISCORD_ALLOWED_USER_ID=id_tai_khoan_lay_o_buoc_4
DISCORD_CHANNEL_ID=
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o
DAILY_CHECKIN_HOUR=8
DAILY_CHECKIN_MINUTE=30
JAPANESE_LEVEL=N4-N3
JAPANESE_BOT_NAME=Yuki (ユキ)
VOICE_ENABLED=true
JAPANESE_VOICE=nanami
```

Ghi chú về các biến cấu hình:
- `DISCORD_CHANNEL_ID`: (Tùy chọn) ID của kênh văn bản muốn bot nhắn tin hàng ngày. Nếu để trống, bot sẽ nhắn tin trực tiếp vào tin nhắn riêng (DM) của bạn.
- `DAILY_CHECKIN_HOUR`: Giờ nhắn tin hàng ngày (theo múi giờ Việt Nam UTC+7, ví dụ: 8 là 8 giờ sáng).
- `DAILY_CHECKIN_MINUTE`: Phút nhắn tin hàng ngày (ví dụ: 30).
- `JAPANESE_LEVEL`: Cấp độ tiếng Nhật mặc định (`N5`, `N4`, `N4-N3`, `N3`, `N2`, `N1`).
- `VOICE_ENABLED`: Bật hoặc tắt tự động gửi kèm file giọng đọc tiếng Nhật (`true` hoặc `false`).
- `JAPANESE_VOICE`: Giọng đọc mặc định (`nanami`, `aoi`, `mayu`, `keita`).

---

## Triển Khai Chạy 24/7 Trên Cloud (Render.com)

1. Đăng ký hoặc đăng nhập tài khoản tại https://render.com bằng GitHub.
2. Nhấn nút "New +" -> chọn "Web Service".
3. Kết nối với repository GitHub của bạn (`HuongDS/japanese-bot`).
4. Tại mục cấu hình:
   - Name: Đặt tên cho dịch vụ (ví dụ: `japanese-kaiwa-bot`).
   - Region: Chọn khu vực gần nhất (ví dụ: Singapore).
   - Environment: Chọn `Docker`.
   - Plan: Chọn gói `Free`.
5. Cuộn xuống phần "Environment Variables" và thêm các biến môi trường:
   - `DISCORD_BOT_TOKEN`: Token lấy từ Bước 3.
   - `DISCORD_ALLOWED_USER_ID`: ID người dùng lấy từ Bước 4.
   - `OPENAI_API_KEY`: API Key của OpenAI.
   - `OPENAI_MODEL`: `gpt-4o` (hoặc `gpt-4o-mini`).
   - `DAILY_CHECKIN_HOUR`: `8`
   - `DAILY_CHECKIN_MINUTE`: `30`
   - `JAPANESE_LEVEL`: `N4-N3`
   - `VOICE_ENABLED`: `true`
   - `JAPANESE_VOICE`: `nanami`
6. Nhấn "Create Web Service". Render sẽ tự động build Docker và duy trì bot hoạt động 24/7.

---

## Chạy Thử Nghiệm Trên Máy Cục Bộ (Local)

1. Cài đặt các thư viện cần thiết:
   ```bash
   pip install -r requirements.txt
   ```
2. Khởi chạy bot:
   ```bash
   python discord_bot.py
   ```
3. Mở Discord và gửi lệnh `!help`, `!time` hoặc `!daily` để bắt đầu luyện tập.
