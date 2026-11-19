# 🌸 Japanese Kaiwa AI Friend — Bot Luyện Tiếng Nhật 24/7 Qua Discord

Bot Discord đóng vai **người bạn thân người Nhật (Yuki - ユキ)**:
- ⏰ **Mỗi sáng chủ động nhắn tin hỏi thăm** đời sống thường ngày (mặc định 08:30 sáng, giờ Việt Nam).
- 💬 **Đề xuất một chủ đề Kaiwa mới mỗi ngày** để bạn luyện phản xạ giao tiếp tiếng Nhật.
- 💡 **Nhẹ nhàng sửa lỗi & gợi ý cách nói tự nhiên** của người bản xứ.
- 🎌 **Điều chỉnh độ khó linh hoạt theo trình độ JLPT** (`N5`, `N4`, `N3`, `N2`, `N1`).
- 🧠 **Nhớ mạch trò chuyện** (Conversation Memory) giúp cuộc đối thoại diễn ra liền mạch như nói chuyện với người thật.
- ☁️ **Chạy 24/7 trên Cloud (Render)**, bạn có thể chat qua Discord trên điện thoại iOS / Android bất cứ lúc nào ngay cả khi máy tính tắt.

---

## 📜 Danh Sách Lệnh Tiện Ích

| Lệnh | Ý nghĩa & Cách dùng |
| :--- | :--- |
| `!daily` | Nhận ngay tin nhắn hỏi thăm & chủ đề Kaiwa hôm nay (thử ngay mà không cần đợi giờ hẹn). |
| `!topic [chủ đề]` | Đổi chủ đề hội thoại mới (Ví dụ: `!topic anime`, `!topic du lịch Tokyo` hoặc gõ `!topic` để Yuki tự chọn). |
| `!level [n5\|n4\|n3\|n2\|n1]` | Xem hoặc đổi trình độ tiếng Nhật (Ví dụ: `!level N4`, `!level N3`). |
| `!reset` | Làm mới bộ nhớ trò chuyện để bắt đầu cuộc trò chuyện mới từ đầu. |
| `!model [tên_model]` | Xem hoặc đổi model GPT (`gpt-4o`, `gpt-4o-mini`). |
| `!status` | Kiểm tra trạng thái bot, model AI, trình độ Kaiwa, giờ hẹn nhắn tin. |
| `!help` | Xem danh sách hướng dẫn chi tiết các lệnh. |
| **Nhắn tin tự do** | Gõ tiếng Nhật hoặc tiếng Việt tự nhiên trong kênh/tin nhắn riêng, Yuki sẽ trò chuyện cùng bạn. |

---

## 🛠️ Hướng Dẫn Cài Đặt & Chạy Thử

### 1. Cấu hình biến môi trường (`.env`)
Tạo file `.env` từ `.env.example`:
```bash
cp .env.example .env
```
Điền các thông tin:
```env
DISCORD_BOT_TOKEN=token_bot_discord_của_bạn
DISCORD_ALLOWED_USER_ID=id_discord_của_bạn
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o
DAILY_CHECKIN_HOUR=8
DAILY_CHECKIN_MINUTE=30
JAPANESE_LEVEL=N4-N3
```

### 2. Cài đặt thư viện & khởi động
```bash
cd d:\my_ai_team\cloud_discord_agent
pip install -r requirements.txt
python discord_bot.py
```

### 3. Đưa lên Cloud (Render) chạy 24/7
1. Đăng ký tài khoản tại [Render.com](https://render.com).
2. Tạo mới **Web Service** (hoặc Background Worker).
3. Kết nối với repo GitHub của bạn, chọn môi trường **Docker**.
4. Cài đặt các biến môi trường trong tab **Environment**:
   - `DISCORD_BOT_TOKEN`
   - `DISCORD_ALLOWED_USER_ID`
   - `OPENAI_API_KEY`
   - `DAILY_CHECKIN_HOUR` = `8`
   - `DAILY_CHECKIN_MINUTE` = `30`
   - `JAPANESE_LEVEL` = `N4-N3`
5. Bấm **Deploy**. Bot sẽ online 24/7 và đồng hành cùng bạn mỗi ngày!
