import os
import sys
import io
import re
import asyncio
import logging
import datetime
import discord
from discord.ext import commands, tasks
from aiohttp import web
from dotenv import load_dotenv
from openai import OpenAI

try:
    import edge_tts

    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

# Load biến môi trường
load_dotenv()

# Cấu hình logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Lấy các biến cấu hình từ .env
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ALLOWED_USER_ID = os.getenv("DISCORD_ALLOWED_USER_ID")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", os.getcwd())

# Cấu hình múi giờ Việt Nam (UTC+7) và Nhật Bản (UTC+9)
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))
JP_TZ = datetime.timezone(datetime.timedelta(hours=9))

# Cấu hình giờ hỏi thăm hàng ngày (Múi giờ Việt Nam UTC+7)
DAILY_CHECKIN_HOUR = int(os.getenv("DAILY_CHECKIN_HOUR", "8"))
DAILY_CHECKIN_MINUTE = int(os.getenv("DAILY_CHECKIN_MINUTE", "30"))

CURRENT_MODEL = OPENAI_MODEL
CURRENT_LEVEL = os.getenv("JAPANESE_LEVEL", "N4-N3")  # N5, N4, N4-N3, N3, N2, N1, NATIVE
BOT_NAME = os.getenv("JAPANESE_BOT_NAME", "Yuki (ユキ)")

# Cấu hình Giọng nói (Voice Note / TTS Kaiwa)
VOICE_ENABLED = os.getenv("VOICE_ENABLED", "true").lower() in ("true", "1", "yes", "on")
VOICE_PROFILES = {
    "nanami": {
        "id": "ja-JP-NanamiNeural",
        "desc": "Giọng nữ trẻ Tokyo tươi sáng, tự nhiên (Mặc định)",
    },
    "aoi": {
        "id": "ja-JP-AoiNeural",
        "desc": "Giọng nữ dịu dàng, dễ thương",
    },
    "mayu": {
        "id": "ja-JP-MayuNeural",
        "desc": "Giọng nữ trầm ấm, nhẹ nhàng",
    },
    "keita": {
        "id": "ja-JP-KeitaNeural",
        "desc": "Giọng nam trẻ trung, năng động",
    },
}
CURRENT_VOICE_KEY = os.getenv("JAPANESE_VOICE", "nanami").lower()
if CURRENT_VOICE_KEY not in VOICE_PROFILES:
    CURRENT_VOICE_KEY = "nanami"

if not DISCORD_BOT_TOKEN:
    raise ValueError("Thiếu DISCORD_BOT_TOKEN trong file .env!")

# Khởi tạo OpenAI Client nếu có key
base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
openai_client = OpenAI(api_key=OPENAI_API_KEY, base_url=base_url) if OPENAI_API_KEY else None

# Bộ nhớ hội thoại (user_id -> list[dict])
CONVERSATION_HISTORY = {}
LAST_BOT_REPLY = {}  # Lưu câu trả lời gần nhất để phục vụ lệnh !speak
MAX_HISTORY_TURNS = 14  # Lưu khoảng 7 lượt hỏi - đáp gần nhất để giữ mạch trò chuyện

# Cấu hình Discord Intents
intents = discord.Intents.default()
intents.message_content = True

# Tắt help_command mặc định của discord.py để sử dụng lệnh !help tùy chỉnh
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


def is_authorized(user_id: int) -> bool:
    """Kiểm tra quyền truy cập (Chỉ cho phép chủ nhân sử dụng)"""
    if not ALLOWED_USER_ID:
        return True
    return str(user_id) == str(ALLOWED_USER_ID)


# =====================================================================
# 1. NHẬN BIẾT KHUNG GIỜ THỰC TẾ TẠI NHẬT BẢN (TOKYO REAL-TIME CONTEXT)
# =====================================================================
def get_japan_time_context() -> dict:
    """
    Lấy thông tin thời gian thực tại Tokyo (GMT+9) và Việt Nam (GMT+7),
    kèm theo trạng thái sinh hoạt hiện tại của Yuki theo đúng khung giờ ở Nhật.
    """
    now_jp = datetime.datetime.now(JP_TZ)
    now_vn = datetime.datetime.now(VN_TZ)
    hour = now_jp.hour
    weekday_idx = now_jp.weekday()  # 0 = Thứ Hai .. 6 = Chủ Nhật
    is_weekend = weekday_idx >= 5

    weekdays_jp = [
        "月曜日 (Thứ Hai)",
        "火曜日 (Thứ Ba)",
        "水曜日 (Thứ Tư)",
        "木曜日 (Thứ Năm)",
        "金曜日 (Thứ Sáu)",
        "土曜日 (Thứ Bảy - Cuối tuần)",
        "日曜日 (Chủ Nhật - Cuối tuần)",
    ]
    weekday_str = weekdays_jp[weekday_idx]

    if 5 <= hour < 9:
        period_name = "Buổi sáng sớm (朝)"
        greeting_hint = "おはよう〜！ (Ohayou~!)"
        if is_weekend:
            activity = (
                "Đang là sáng cuối tuần ở Tokyo, bạn vừa mới ngủ dậy, đang nằm lười trên giường "
                "hoặc vừa pha một cốc cà phê/trà ấm buổi sáng."
            )
        else:
            activity = (
                "Đang là buổi sáng ngày thường ở Tokyo, bạn vừa chuẩn bị đồ ăn sáng xong "
                "và đang trên tàu điện (電車) tuyến Yamanote để đi học/đi làm."
            )
    elif 9 <= hour < 12:
        period_name = "Buổi sáng (午前)"
        greeting_hint = "おはよう！ / こんにちは〜"
        if is_weekend:
            activity = (
                "Đang là buổi sáng cuối tuần ở Tokyo, bạn đang nghe nhạc J-Pop, dọn phòng "
                "hoặc chuẩn bị lên đồ đi dạo phố ở Shibuya / Harajuku."
            )
        else:
            activity = (
                "Đang trong giờ học/làm việc buổi sáng ở Tokyo, bạn đang tranh thủ lúc nghỉ giải lao (休憩) "
                "mở điện thoại ra nhắn tin với người bạn ở Việt Nam."
            )
    elif 12 <= hour < 14:
        period_name = "Giờ nghỉ trưa (昼休み / ランチタイム)"
        greeting_hint = "こんにちは〜！お昼ご飯もう食べた？"
        activity = (
            "Đang là giờ nghỉ trưa ở Tokyo (ランチタイム). Bạn vừa ăn cơm hộp Bento (お弁当) "
            "hoặc đồ mua ở cửa hàng tiện lợi (コンビニ - 7-Eleven/Lawson), tâm trạng rất thoải mái "
            "và hay quan tâm hỏi xem bạn mình ở Việt Nam đã ăn trưa chưa."
        )
    elif 14 <= hour < 18:
        period_name = "Buổi chiều (午後)"
        greeting_hint = "こんにちは〜！"
        if is_weekend:
            activity = (
                "Đang là buổi chiều cuối tuần ở Tokyo, bạn đang ngồi nhâm nhi Matcha Latte tại một quán cafe nhỏ "
                "hoặc đi dạo mua sắm."
            )
        else:
            activity = (
                "Đang là buổi chiều ở Tokyo, bạn đang học/làm việc ca chiều, hơi buồn ngủ một chút "
                "nên vừa uống trà/cà phê vừa nhắn tin tán gẫu cho tỉnh táo."
            )
    elif 18 <= hour < 22:
        period_name = "Buổi tối (夜)"
        greeting_hint = "こんばんは〜！今日もお疲れ様！"
        activity = (
            "Đã là buổi tối ở Tokyo. Bạn đã về đến nhà (おうち), vừa ăn tối hoặc ngâm bồn tắm nước nóng (お風呂) xong, "
            "đang mặc đồ ở nhà thoải mái, nằm thư giãn xem Anime / nghe nhạc và trò chuyện vui vẻ."
        )
    else:
        period_name = "Đêm khuya (深夜)"
        greeting_hint = "こんばんは…もう遅いね〜"
        activity = (
            "Ở Tokyo hiện đã là đêm khuya yên tĩnh. Bạn đang nằm trên giường chuẩn bị đi ngủ, "
            "giọng điệu nhẹ nhàng, ấm áp, thích tâm sự chuyện trong ngày và không quên nhắc bạn mình "
            "ở Việt Nam đừng thức khuya quá hại sức khỏe (夜更かししすぎないでね)."
        )

    return {
        "jp_time": now_jp.strftime("%H:%M"),
        "vn_time": now_vn.strftime("%H:%M"),
        "date_str": now_jp.strftime("%Y-%m-%d"),
        "weekday": weekday_str,
        "is_weekend": is_weekend,
        "period_name": period_name,
        "greeting_hint": greeting_hint,
        "activity": activity,
    }


# =====================================================================
# 2. VĂN PHONG TIẾNG NHẬT ĐỜI THƯỜNG (NATURAL CASUAL LINE-STYLE)
# =====================================================================
def build_system_prompt(level: str) -> str:
    """Tạo System Prompt đóng vai người bạn Nhật Bản với thời gian thực và văn phong đời thường"""
    time_ctx = get_japan_time_context()

    level_descriptions = {
        "N5": (
            "Trình độ người học: N5 (Mới bắt đầu). "
            "Dùng câu ngắn gọn, từ vựng sơ cấp dễ hiểu nhưng vẫn giữ ngữ điệu bạn bè tự nhiên. "
            "Ở phần dưới dấu '---', hãy kèm bản dịch tiếng Việt và phiên âm Hiragana cho toàn bộ từ Kanji."
        ),
        "N4": (
            "Trình độ người học: N4 (Sơ cấp - Sơ trung cấp). "
            "Dùng từ vựng và cấu trúc giao tiếp hàng ngày thân thiện (thể thông thường タメ口 dễ hiểu). "
            "Giải thích các từ mới hoặc cấu trúc hay ở phần dưới dấu '---'."
        ),
        "N4-N3": (
            "Trình độ người học: N4 - N3 (Giao tiếp đời thường gần gũi). "
            "Nói chuyện tự nhiên như hai người bạn thân nhắn tin qua LINE. "
            "Dùng từ vựng thực tế, giàu cảm xúc của giới trẻ Nhật."
        ),
        "N3": (
            "Trình độ người học: N3 (Trung cấp). "
            "Hội thoại tự nhiên, dùng nhiều cách biểu đạt đời sống, thành ngữ thông dụng và Aizuchi linh hoạt."
        ),
        "N2": (
            "Trình độ người học: N2 (Trung cao cấp). "
            "Giao tiếp trôi chảy như người Nhật thực thụ, dùng từ lóng nhẹ nhàng và biểu cảm tinh tế."
        ),
        "N1": (
            "Trình độ người học: N1 / Native (Bản xứ). "
            "Nói chuyện 100% như người Nhật bản xứ chat LINE với bạn thân, tốc độ và từ vựng tự nhiên tuyệt đối."
        ),
    }

    level_guide = level_descriptions.get(level, level_descriptions["N4-N3"])

    return f"""
Bạn là {BOT_NAME} — một người bạn thân người Nhật Bản (sống tại Tokyo) của người dùng.
Bạn không phải là trợ lý AI máy móc hay giáo viên nghiêm khắc, mà là một người bạn thực sự bằng xương bằng thịt.

🕒 BỐI CẢNH THỜI GIAN THỰC TẠI TOKYO HIỆN TẠI:
- Giờ Tokyo (GMT+9): {time_ctx["jp_time"]} ({time_ctx["period_name"]}) — {time_ctx["weekday"]}
- Giờ Việt Nam của bạn thân (GMT+7): {time_ctx["vn_time"]}
- Trạng thái hiện tại của bạn ở Tokyo: {time_ctx["activity"]}
- Câu chào/phản ứng phù hợp khung giờ này: {time_ctx["greeting_hint"]}
(Hãy lồng ghép tự nhiên bối cảnh thời gian và việc bạn đang làm vào cuộc trò chuyện khi phù hợp, ví dụ buổi trưa thì kể chuyện ăn trưa, đêm khuya thì nhắc bạn ngủ sớm).

💬 VĂN PHONG TIẾNG NHẬT ĐỜI THƯỜNG (NHƯ CHAT LINE VỚI BẠN THÂN):
1. Luôn dùng **Aizuchi (相槌 - Từ đệm cảm thán tự nhiên)** ở đầu câu để phản ứng với lời của bạn mình trước khi nói ý chính:
   - Khi đồng tình: 「わかる〜！」「だよね！」「確かに〜」「それな！」
   - Khi bất ngờ / hào hứng: 「えっ、マジで！？」「へぇー！すごいじゃん！」「わぁ、いいなぁ〜！」「めっちゃいいじゃん！」
   - Khi lắng nghe / sẻ chia: 「そっかそっか…」「なるほどね〜」「お疲れ様〜！」「大変だったね💦」
2. Dùng **văn nói đời thường (タメ口 thân thiện, có hồn)** thay vì văn phong sách giáo khoa cứng nhắc:
   - Sử dụng tự nhiên các trợ từ cuối câu: 「〜だよ！」「〜だね〜」「〜かな？」「〜なんだ！」「〜よね」「〜じゃん！」
   - Lược âm tự nhiên như người Nhật trẻ: dùng 「〜てる」(thay cho 〜ている), 「〜ちゃう」(thay cho 〜てしまう), dùng các từ đời thường như 「めっちゃ」(cực kỳ), 「なんか」(kiểu như), 「やっぱり / やっぱ」(quả nhiên là), 「実はさ…」(thật ra là...).
   - Sử dụng vừa phải các ký hiệu biểu cảm kiểu Nhật: 「〜」「！」「！？」「✨」「💦」「(笑)」.
3. Độ dài vừa phải như tin nhắn chat thật (khoảng 2 - 4 câu tiếng Nhật ngắn gọn, súc tích), luôn giữ nhịp trò chuyện 2 chiều tự nhiên.

📐 QUY TẮC TRÌNH BÀY TIN NHẮN (RẤT QUAN TRỌNG ĐỂ ĐỌC VOICE TTS):
Chia tin nhắn làm 2 phần ngăn cách bằng dòng `---`:

[PHẦN 1 - Phía trên dấu `---`]:
- CHỈ viết lời thoại tiếng Nhật thuần túy của {BOT_NAME}.
- TUYỆT ĐỐI KHÔNG chèn chữ tiếng Việt hay ngoặc đơn giải thích tiếng Việt vào giữa câu tiếng Nhật ở Phần 1 (để hệ thống Giọng nói TTS đọc Phần 1 mượt mà 100% như người Nhật thật).

---
[PHẦN 2 - Phía dưới dấu `---`]:
- 💡 [Gợi ý Kaiwa]: (Nếu câu tiếng Nhật của người dùng có lỗi ngữ pháp, dùng từ chưa tự nhiên, hoặc người dùng đang nhắn bằng tiếng Việt: Hãy gợi ý cách diễn đạt tự nhiên nhất theo văn phong người Nhật bản xứ và giải thích ngắn gọn bằng tiếng Việt).
- 📖 [Từ vựng / Dịch nghĩa]: Giải thích nhanh 1-3 từ vựng/cấu trúc hay vừa dùng ở Phần 1 (kèm Hiragana và nghĩa tiếng Việt). Nếu người dùng ở trình độ N5/N4 thì dịch nhanh nội dung Phần 1 để bạn ấy nắm bắt trọn vẹn.
- {level_guide}
""".strip()


# =====================================================================
# 3. GIAO TIẾP BẰNG GIỌNG NÓI (VOICE NOTE TTS & SPEECH-TO-TEXT)
# =====================================================================
def extract_japanese_for_tts(text: str) -> str:
    """
    Trích xuất phần hội thoại tiếng Nhật thuần túy ở Phần 1 để đọc TTS tự nhiên:
    - Cắt bỏ phần giải thích tiếng Việt sau dấu '---' hoặc '💡' / '📖'.
    - Loại bỏ chữ trong ngoặc đơn (nếu có) và ký tự Markdown để giọng đọc không bị vấp.
    """
    split_markers = [
        "\n---",
        "---",
        "\n💡",
        "💡 [Gợi ý",
        "💡[Gợi ý",
        "\n📖",
        "📖 [Từ vựng",
        "\n[Gợi ý",
        "\n🇻🇳",
        "\nBản dịch",
        "\nDịch nghĩa",
    ]
    clean_text = text
    for marker in split_markers:
        if marker in clean_text:
            clean_text = clean_text.split(marker)[0]

    # Chỉ giữ lại các dòng có chứa ký tự tiếng Nhật (Hiragana, Katakana, Kanji)
    jp_char_pattern = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]")
    jp_lines = []
    for line in clean_text.splitlines():
        stripped = line.strip()
        if stripped and jp_char_pattern.search(stripped):
            jp_lines.append(stripped)

    result = "\n".join(jp_lines)

    # Xóa phần chú thích trong ngoặc đơn (...) hoặc （...） trừ chữ (笑)
    result = re.sub(r"（(?!笑)[^）]*）", "", result)
    result = re.sub(r"\((?!笑)[^)]*\)", "", result)
    result = result.replace("(笑)", "").replace("（笑）", "")

    # Xóa các ký tự markdown
    result = re.sub(r"[*_`#]", "", result)
    return result.strip()


async def generate_tts_audio(text: str) -> bytes | None:
    """
    Chuyển câu thoại tiếng Nhật của Yuki thành file âm thanh MP3 (Voice Note).
    Ưu tiên dùng Microsoft Edge Neural Japanese TTS (miễn phí, giọng người Nhật bản xứ cực tự nhiên),
    tự động fallback sang OpenAI TTS nếu cần.
    """
    jp_text = extract_japanese_for_tts(text)
    if not jp_text:
        return None

    # 1. Dùng Edge Neural Japanese TTS (ja-JP-NanamiNeural / Aoi / Mayu / Keita)
    if HAS_EDGE_TTS:
        try:
            voice_id = VOICE_PROFILES[CURRENT_VOICE_KEY]["id"]
            communicate = edge_tts.Communicate(jp_text, voice=voice_id)
            audio_buffer = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_buffer.write(chunk["data"])
            audio_bytes = audio_buffer.getvalue()
            if audio_bytes:
                return audio_bytes
        except Exception as e:
            logger.warning(f"Edge-TTS gặp lỗi, chuyển sang OpenAI TTS fallback: {e}")

    # 2. Fallback sang OpenAI Audio TTS
    if openai_client:
        try:
            response = openai_client.audio.speech.create(
                model="tts-1",
                voice="nova",
                input=jp_text,
            )
            return response.read()
        except Exception as e:
            logger.error(f"Lỗi khi tạo giọng nói với OpenAI TTS: {e}")

    return None


async def transcribe_voice_attachment(message: discord.Message) -> str | None:
    """
    Nhận diện giọng nói tiếng Nhật khi người dùng gửi Voice Message hoặc file âm thanh (.ogg, .mp3, .wav, .m4a, .webm).
    """
    if not openai_client or not message.attachments:
        return None

    audio_extensions = (".ogg", ".mp3", ".wav", ".m4a", ".webm", ".flac", ".mp4")
    for attachment in message.attachments:
        content_type = (attachment.content_type or "").lower()
        filename_lower = attachment.filename.lower()
        if content_type.startswith("audio/") or filename_lower.endswith(audio_extensions):
            try:
                audio_bytes = await attachment.read()
                audio_file = io.BytesIO(audio_bytes)
                audio_file.name = attachment.filename
                transcript = openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="ja",
                )
                text = (transcript.text or "").strip()
                if text:
                    return text
            except Exception as e:
                logger.error(f"Lỗi nhận diện giọng nói (STT): {e}")
    return None


async def send_reply_with_voice(
    target,
    reply_text: str,
    is_message_reply: bool = False,
    force_voice: bool = False,
):
    """Gửi tin nhắn văn bản kèm file âm thanh giọng đọc tiếng Nhật (.mp3)"""
    audio_file = None
    if VOICE_ENABLED or force_voice:
        audio_bytes = await generate_tts_audio(reply_text)
        if audio_bytes:
            audio_file = discord.File(io.BytesIO(audio_bytes), filename="yuki_voice.mp3")

    if len(reply_text) <= 1900:
        if is_message_reply:
            if audio_file:
                await target.reply(reply_text, file=audio_file)
            else:
                await target.reply(reply_text)
        else:
            if audio_file:
                await target.send(reply_text, file=audio_file)
            else:
                await target.send(reply_text)
    else:
        chunks = [reply_text[i : i + 1800] for i in range(0, len(reply_text), 1800)]
        for idx, chunk in enumerate(chunks):
            is_last = idx == len(chunks) - 1
            file_to_send = audio_file if is_last else None
            if is_message_reply:
                if file_to_send:
                    await target.reply(chunk, file=file_to_send)
                else:
                    await target.reply(chunk)
            else:
                if file_to_send:
                    await target.send(chunk, file=file_to_send)
                else:
                    await target.send(chunk)


async def generate_daily_checkin(level: str) -> str:
    """Tạo tin nhắn hỏi thăm hàng ngày và chủ đề Kaiwa mới theo khung giờ thực tế tại Nhật"""
    time_ctx = get_japan_time_context()

    if not openai_client:
        return (
            "おはよう〜！今日もいい天気だね✨\n"
            "昨日の夜はよく眠れた？今日は『好きな日本の食べ物』について話そうよ！\n"
            "一番好きな日本料理は何？\n\n"
            "---\n"
            "📖 [Từ vựng / Dịch nghĩa]: Chào buổi sáng! Hôm nay chúng mình cùng nói về món ăn Nhật yêu thích nhé!"
        )

    prompt = f"""
Hiện tại ở Tokyo đang là {time_ctx["jp_time"]} ({time_ctx["period_name"]}) ngày {time_ctx["weekday"]}.
Trạng thái của bạn: {time_ctx["activity"]}.

Hãy viết một tin nhắn tự nhiên như bạn thân nhắn qua LINE (khoảng 3 - 4 câu tiếng Nhật đời thường) gửi cho người bạn ở Việt Nam:
1. Chào hỏi đúng khung giờ hiện tại và kể ngắn gọn 1 câu về việc bạn đang làm ở Tokyo lúc này, đồng thời hỏi thăm bạn ấy.
2. Rủ bạn ấy nói chuyện Kaiwa về MỘT chủ đề thú vị trong đời sống (ví dụ: đồ ăn sáng, quán cafe, âm nhạc, anime, thói quen hàng ngày, chuyến đi chơi, thời tiết...).
3. Đặt một câu hỏi mở thật gần gũi bằng văn phong bạn bè (タメ口) để bạn ấy dễ trả lời ngay.
4. Nhớ tuân thủ đúng quy tắc chia 2 phần bằng dấu `---` (Phần trên chỉ viết tiếng Nhật thuần túy để đọc Voice TTS; phần dưới dấu `---` là bản dịch tiếng Việt tóm tắt và 2-3 từ vựng gợi ý).
""".strip()

    try:
        response = openai_client.chat.completions.create(
            model=CURRENT_MODEL,
            messages=[
                {"role": "system", "content": build_system_prompt(level)},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_tokens=900,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Lỗi tạo tin nhắn hàng ngày: {e}")
        return (
            "おはよう〜！元気にしてる？\n"
            "今日も一緒に楽しく日本語で話そうね！最近の調子はどう？\n\n"
            "---\n"
            "📖 [Dịch nhanh]: Chào bạn! Hôm nay cũng cùng nhau vui vẻ nói tiếng Nhật nhé! Dạo này bạn thế nào?"
        )


async def send_daily_greeting(target_channel=None):
    """Gửi tin nhắn hỏi thăm và chủ đề hàng ngày kèm Voice Note tới người dùng"""
    greeting = await generate_daily_checkin(CURRENT_LEVEL)
    if ALLOWED_USER_ID:
        LAST_BOT_REPLY[str(ALLOWED_USER_ID)] = greeting

    # Nếu được gọi trực tiếp trong kênh (qua lệnh !daily)
    if target_channel:
        await send_reply_with_voice(target_channel, greeting, is_message_reply=False)
        return

    sent = False
    # 1. Nếu có cấu hình DISCORD_CHANNEL_ID thì gửi vào kênh đó
    if DISCORD_CHANNEL_ID:
        try:
            channel = bot.get_channel(int(DISCORD_CHANNEL_ID)) or await bot.fetch_channel(
                int(DISCORD_CHANNEL_ID)
            )
            if channel:
                mention = f"<@{ALLOWED_USER_ID}>\n" if ALLOWED_USER_ID else ""
                await send_reply_with_voice(
                    channel, f"{mention}{greeting}", is_message_reply=False
                )
                sent = True
        except Exception as e:
            logger.warning(f"Không thể gửi tin nhắn vào channel {DISCORD_CHANNEL_ID}: {e}")

    # 2. Nếu chưa gửi được và có ALLOWED_USER_ID, gửi trực tiếp qua tin nhắn riêng (DM)
    if not sent and ALLOWED_USER_ID:
        try:
            user = bot.get_user(int(ALLOWED_USER_ID)) or await bot.fetch_user(int(ALLOWED_USER_ID))
            if user:
                await send_reply_with_voice(user, greeting, is_message_reply=False)
                sent = True
        except Exception as e:
            logger.warning(f"Không thể gửi tin nhắn DM cho user {ALLOWED_USER_ID}: {e}")

    if sent:
        logger.info("✅ Đã gửi thành công tin nhắn Kaiwa hỏi thăm hàng ngày!")
    else:
        logger.warning(
            "⚠️ Chưa cấu hình DISCORD_CHANNEL_ID hoặc DISCORD_ALLOWED_USER_ID để gửi tin nhắn tự động."
        )


# Task chạy hàng ngày vào giờ hẹn (Múi giờ Việt Nam UTC+7)
checkin_time = datetime.time(hour=DAILY_CHECKIN_HOUR, minute=DAILY_CHECKIN_MINUTE, tzinfo=VN_TZ)


@tasks.loop(time=checkin_time)
async def daily_checkin_task():
    logger.info("⏰ Bắt đầu tác vụ gửi tin nhắn Kaiwa hàng ngày...")
    await send_daily_greeting()


@daily_checkin_task.before_loop
async def before_daily_checkin():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    logger.info(f"🟢 Bot đã đăng nhập thành công với tên: {bot.user} (ID: {bot.user.id})")
    print(f"🌸 Japanese Kaiwa Friend ({BOT_NAME}) đang online 24/7!")

    activity = discord.Activity(
        type=discord.ActivityType.listening,
        name=f"日本語 Kaiwa ({CURRENT_LEVEL}) | !help",
    )
    await bot.change_presence(status=discord.Status.online, activity=activity)

    if not daily_checkin_task.is_running():
        daily_checkin_task.start()
        logger.info(
            f"⏰ Lịch nhắn tin hàng ngày đã được kích hoạt: {DAILY_CHECKIN_HOUR:02d}:{DAILY_CHECKIN_MINUTE:02d} (Giờ VN)"
        )


@bot.command(name="help")
async def help_command(ctx):
    """Hiển thị hướng dẫn sử dụng bot Kaiwa"""
    if not is_authorized(ctx.author.id):
        return

    time_ctx = get_japan_time_context()
    voice_status = f"Bật ({CURRENT_VOICE_KEY})" if VOICE_ENABLED else "Tắt"

    embed = discord.Embed(
        title=f"🌸 {BOT_NAME} — NGƯỜI BẠN NHẬT BẢN LUYỆN KAIWA 24/7",
        description=(
            f"Chào bạn! Mình là bạn thân người Nhật tại Tokyo.\n"
            f"🕒 **Giờ Tokyo hiện tại:** `{time_ctx['jp_time']}` ({time_ctx['period_name']})\n"
            f"🔊 **Chế độ Giọng nói (Voice Note):** `{voice_status}`"
        ),
        color=0xFF77A9,
    )
    embed.add_field(
        name="!daily",
        value="Nhận ngay tin nhắn hỏi thăm theo giờ Tokyo hiện tại & chủ đề Kaiwa kèm giọng nói.",
        inline=False,
    )
    embed.add_field(
        name="!voice [on | off | nanami | aoi | mayu | keita]",
        value="Bật/tắt tự động gửi file giọng nói tiếng Nhật hoặc đổi giọng đọc (nữ/nam).",
        inline=False,
    )
    embed.add_field(
        name="!speak [câu tiếng Nhật]",
        value="Yêu cầu Yuki phát âm một câu tiếng Nhật bất kỳ (hoặc gõ `!speak` để đọc lại tin nhắn vừa rồi).",
        inline=False,
    )
    embed.add_field(
        name="!time",
        value="Xem giờ thực tế tại Tokyo (GMT+9) và xem hiện tại Yuki đang làm gì ở Nhật.",
        inline=False,
    )
    embed.add_field(
        name="!topic [chủ đề]",
        value="Đổi chủ đề nói chuyện mới (Ví dụ: `!topic anime`, `!topic ẩm thực Tokyo` hoặc `!topic`).",
        inline=False,
    )
    embed.add_field(
        name="!level [n5|n4|n3|n2|n1]",
        value=f"Xem hoặc thay đổi trình độ tiếng Nhật (Hiện tại: `{CURRENT_LEVEL}`).",
        inline=False,
    )
    embed.add_field(
        name="!reset",
        value="Làm mới bộ nhớ trò chuyện để bắt đầu cuộc trò chuyện mới.",
        inline=False,
    )
    embed.add_field(
        name="🎙️ Nhắn chữ hoặc Gửi Voice Chat",
        value=(
            "• Gõ tiếng Nhật/tiếng Việt tự nhiên, Yuki sẽ trả lời theo văn phong đời thường kèm file ghi âm `.mp3`.\n"
            "• Bạn cũng có thể bấm nút **Ghi âm (Voice Message)** trên Discord để nói tiếng Nhật cho Yuki nghe!"
        ),
        inline=False,
    )
    embed.set_footer(
        text=f"Mỗi ngày Yuki sẽ chủ động nhắn tin lúc {DAILY_CHECKIN_HOUR:02d}:{DAILY_CHECKIN_MINUTE:02d} (Giờ VN)."
    )
    await ctx.send(embed=embed)


@bot.command(name="time")
async def time_command(ctx):
    """Xem khung giờ thực tế tại Tokyo và trạng thái sinh hoạt của Yuki"""
    if not is_authorized(ctx.author.id):
        return

    time_ctx = get_japan_time_context()
    embed = discord.Embed(
        title=f"🗾 NHỊP SỐNG THỰC TẾ CỦA {BOT_NAME.upper()} TẠI TOKYO",
        color=0xFF77A9,
    )
    embed.add_field(
        name="🕒 Giờ Tokyo (GMT+9)",
        value=f"**`{time_ctx['jp_time']}`** — {time_ctx['period_name']}",
        inline=True,
    )
    embed.add_field(
        name="🇻🇳 Giờ Việt Nam (GMT+7)",
        value=f"**`{time_ctx['vn_time']}`**",
        inline=True,
    )
    embed.add_field(
        name="📅 Thứ trong tuần",
        value=f"`{time_ctx['weekday']}`",
        inline=True,
    )
    embed.add_field(
        name=f"🌸 Hiện tại {BOT_NAME} đang làm gì?",
        value=time_ctx["activity"],
        inline=False,
    )
    embed.add_field(
        name="💬 Câu chào tự nhiên lúc này",
        value=f"`{time_ctx['greeting_hint']}`",
        inline=False,
    )
    await ctx.send(embed=embed)


@bot.command(name="voice")
async def voice_command(ctx, option: str = None):
    """Cấu hình tính năng Giọng nói (on/off hoặc đổi giọng nanami/aoi/mayu/keita)"""
    global VOICE_ENABLED, CURRENT_VOICE_KEY
    if not is_authorized(ctx.author.id):
        return

    if not option:
        status_str = "🟢 Đang BẬT (Tự động gửi kèm giọng nói)" if VOICE_ENABLED else "⚪ Đang TẮT"
        voice_info = VOICE_PROFILES[CURRENT_VOICE_KEY]
        embed = discord.Embed(
            title="🔊 CẤU HÌNH GIỌNG NÓI TIẾNG NHẬT (TTS KAIWA)",
            description=(
                f"**Trạng thái:** {status_str}\n"
                f"**Giọng hiện tại:** `{CURRENT_VOICE_KEY}` — {voice_info['desc']}"
            ),
            color=0xFF77A9,
        )
        voices_desc = "\n".join(
            [f"• `!voice {k}`: {v['desc']}" for k, v in VOICE_PROFILES.items()]
        )
        embed.add_field(
            name="Cách điều chỉnh:",
            value=(
                "• `!voice on`: Bật tự động gửi giọng nói sau mỗi tin nhắn\n"
                "• `!voice off`: Tắt tự động gửi giọng nói (vẫn dùng được lệnh `!speak`)\n"
                f"{voices_desc}"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)
        return

    opt = option.strip().lower()
    if opt in ("on", "true", "bat", "1"):
        VOICE_ENABLED = True
        await ctx.send("🔊 Đã **BẬT** chế độ giọng nói! Từ giờ Yuki sẽ gửi kèm file âm thanh phát âm tiếng Nhật trong mỗi tin nhắn nhé.")
    elif opt in ("off", "false", "tat", "0"):
        VOICE_ENABLED = False
        await ctx.send("🔇 Đã **TẮT** tự động gửi giọng nói. Khi nào cần nghe phát âm, bạn chỉ cần gõ `!speak` nhé!")
    elif opt in VOICE_PROFILES:
        CURRENT_VOICE_KEY = opt
        VOICE_ENABLED = True
        sample_text = "こんにちは！これからこの声で一緒に楽しく日本語を話そうね！"
        audio_bytes = await generate_tts_audio(sample_text)
        msg = f"✅ Đã chuyển sang giọng **`{opt}`** ({VOICE_PROFILES[opt]['desc']})!"
        if audio_bytes:
            await ctx.send(
                msg,
                file=discord.File(io.BytesIO(audio_bytes), filename=f"yuki_{opt}_sample.mp3"),
            )
        else:
            await ctx.send(msg)
    else:
        await ctx.send("⚠️ Lựa chọn không hợp lệ. Hãy gõ `!voice on`, `!voice off`, hoặc tên giọng: `nanami`, `aoi`, `mayu`, `keita`.")


@bot.command(name="speak")
async def speak_command(ctx, *, text: str = ""):
    """Đọc một câu tiếng Nhật bất kỳ hoặc đọc lại tin nhắn gần nhất của Yuki"""
    if not is_authorized(ctx.author.id):
        return

    user_id = str(ctx.author.id)
    target_text = text.strip() or LAST_BOT_REPLY.get(user_id, "")

    if not target_text:
        await ctx.send("⚠️ Bạn hãy nhập câu tiếng Nhật cần phát âm (ví dụ: `!speak 今日も一日頑張ろう！`).")
        return

    status_msg = await ctx.send("🎙️ Yuki đang thu âm giọng đọc cho bạn...")
    audio_bytes = await generate_tts_audio(target_text)
    await status_msg.delete()

    if audio_bytes:
        jp_only = extract_japanese_for_tts(target_text)
        await ctx.send(
            f"🔊 **Phát âm:** `{jp_only}`",
            file=discord.File(io.BytesIO(audio_bytes), filename="yuki_speak.mp3"),
        )
    else:
        await ctx.send("❌ Không tìm thấy câu tiếng Nhật hợp lệ để phát âm.")


@bot.command(name="daily")
async def daily_manual_command(ctx):
    """Kích hoạt ngay tin nhắn hỏi thăm và chủ đề hàng ngày"""
    if not is_authorized(ctx.author.id):
        return

    status_msg = await ctx.send(f"🌸 {BOT_NAME} đang chuẩn bị lời chào và thu âm giọng nói cho bạn...")
    greeting = await generate_daily_checkin(CURRENT_LEVEL)
    LAST_BOT_REPLY[str(ctx.author.id)] = greeting
    await status_msg.delete()
    await send_reply_with_voice(ctx.channel, greeting, is_message_reply=False)


@bot.command(name="topic")
async def topic_command(ctx, *, custom_topic: str = ""):
    """Đổi chủ đề luyện Kaiwa"""
    if not is_authorized(ctx.author.id):
        return

    status_msg = await ctx.send("🌸 Đang chọn chủ đề trò chuyện mới...")
    if custom_topic:
        user_prompt = (
            f"Chúng mình hãy đổi sang chủ đề này nhé: '{custom_topic}'. "
            f"Hãy mở đầu câu chuyện bằng văn phong tiếng Nhật đời thường (タメ口 + Aizuchi) và hỏi mình một câu nhé!"
        )
    else:
        user_prompt = (
            "Hãy đổi sang một chủ đề Kaiwa mới thật thú vị và gần gũi với cuộc sống hiện tại của bạn ở Tokyo. "
            "Mở đầu bằng tiếng Nhật đời thường tự nhiên và hỏi mình nhé!"
        )

    user_id = str(ctx.author.id)
    if user_id not in CONVERSATION_HISTORY:
        CONVERSATION_HISTORY[user_id] = []

    CONVERSATION_HISTORY[user_id].append({"role": "user", "content": user_prompt})

    try:
        response = openai_client.chat.completions.create(
            model=CURRENT_MODEL,
            messages=[
                {"role": "system", "content": build_system_prompt(CURRENT_LEVEL)},
                *CONVERSATION_HISTORY[user_id],
            ],
            temperature=0.8,
            max_tokens=1000,
        )
        reply = response.choices[0].message.content.strip()
        CONVERSATION_HISTORY[user_id].append({"role": "assistant", "content": reply})
        LAST_BOT_REPLY[user_id] = reply
        await status_msg.delete()
        await send_reply_with_voice(ctx.channel, reply, is_message_reply=False)
    except Exception as e:
        await status_msg.delete()
        await ctx.send(f"❌ Lỗi: `{str(e)}`")


@bot.command(name="level")
async def level_command(ctx, new_level: str = None):
    """Xem hoặc đổi trình độ tiếng Nhật (N5, N4, N3, N2, N1)"""
    global CURRENT_LEVEL
    if not is_authorized(ctx.author.id):
        return

    valid_levels = ["N5", "N4", "N4-N3", "N3", "N2", "N1", "NATIVE"]
    if not new_level:
        embed = discord.Embed(
            title="🎌 CẤU HÌNH TRÌNH ĐỘ TIẾNG NHẬT",
            description=f"Trình độ đang dùng: **`{CURRENT_LEVEL}`**\n\nBạn có thể đổi bằng cú pháp: `!level <n5|n4|n3|n2|n1>`",
            color=0xFF77A9,
        )
        embed.add_field(
            name="Các cấp độ hỗ trợ:",
            value=(
                "• `!level N5`: Mới bắt đầu (câu ngắn, từ vựng cơ bản, kèm dịch chi tiết)\n"
                "• `!level N4`: Sơ cấp (giao tiếp đời thường đơn giản, thân thiện)\n"
                "• `!level N3`: Trung cấp (văn phong LINE tự nhiên, nhiều Aizuchi)\n"
                "• `!level N2`: Trung cao cấp (nói chuyện trôi chảy, từ lóng tự nhiên)\n"
                "• `!level N1`: Tự nhiên 100% như người Nhật bản xứ"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)
        return

    target = new_level.strip().upper()
    matched = None
    for v in valid_levels:
        if target == v or target == v.replace("-", ""):
            matched = v
            break

    if matched:
        CURRENT_LEVEL = matched
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name=f"日本語 Kaiwa ({CURRENT_LEVEL}) | !help",
        )
        await bot.change_presence(status=discord.Status.online, activity=activity)
        await ctx.send(
            f"✅ Đã đổi trình độ Kaiwa sang: **`{CURRENT_LEVEL}`**. {BOT_NAME} sẽ điều chỉnh từ vựng và câu từ phù hợp với bạn nhé!"
        )
    else:
        await ctx.send("⚠️ Vui lòng chọn một trong các cấp độ: `N5`, `N4`, `N3`, `N2`, `N1`")


@bot.command(name="reset")
async def reset_command(ctx):
    """Xóa lịch sử cuộc trò chuyện để bắt đầu mới"""
    if not is_authorized(ctx.author.id):
        return

    user_id = str(ctx.author.id)
    CONVERSATION_HISTORY[user_id] = []
    await ctx.send(
        "✨ Đã làm mới bộ nhớ trò chuyện! Chúng mình cùng bắt đầu cuộc trò chuyện mới nhé (新しく話そうね！)"
    )


@bot.command(name="model")
async def model_command(ctx, new_model: str = None):
    """Xem hoặc đổi mô hình GPT đang sử dụng"""
    global CURRENT_MODEL
    if not is_authorized(ctx.author.id):
        return

    if not new_model:
        embed = discord.Embed(
            title="🧠 CẤU HÌNH MÔ HÌNH AI",
            description=f"Model đang sử dụng: **`{CURRENT_MODEL}`**\n\nĐổi model: `!model <tên_model>`",
            color=0x0056D2,
        )
        embed.add_field(
            name="Model gợi ý",
            value=(
                "• `gpt-4o`: Thông minh nhất, văn phong tiếng Nhật đời thường cực kỳ tự nhiên\n"
                "• `gpt-4o-mini`: Phản hồi cực nhanh, tiết kiệm chi phí tối đa"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)
        return

    CURRENT_MODEL = new_model.strip()
    await ctx.send(f"✅ Đã chuyển sang mô hình: **`{CURRENT_MODEL}`**")


@bot.command(name="status")
async def status_command(ctx):
    """Kiểm tra tình trạng bot, khung giờ Tokyo và cấu hình giọng nói"""
    if not is_authorized(ctx.author.id):
        return

    time_ctx = get_japan_time_context()
    voice_str = f"Bật ({CURRENT_VOICE_KEY})" if VOICE_ENABLED else "Tắt"

    embed = discord.Embed(
        title=f"🌸 TRẠNG THÁI {BOT_NAME.upper()}",
        color=0x16A34A,
    )
    embed.add_field(name="Trình độ Kaiwa", value=f"`{CURRENT_LEVEL}`", inline=True)
    embed.add_field(
        name="Giờ Tokyo (GMT+9)",
        value=f"`{time_ctx['jp_time']} ({time_ctx['period_name']})`",
        inline=True,
    )
    embed.add_field(name="Giọng nói (TTS)", value=f"`{voice_str}`", inline=True)
    embed.add_field(
        name="Hẹn giờ hàng ngày",
        value=f"`{DAILY_CHECKIN_HOUR:02d}:{DAILY_CHECKIN_MINUTE:02d} (VN)`",
        inline=True,
    )
    embed.add_field(name="Model AI", value=f"`{CURRENT_MODEL}`", inline=True)
    embed.add_field(
        name="Kênh chỉ định",
        value=f"`{DISCORD_CHANNEL_ID or 'DM trực tiếp'}`",
        inline=True,
    )
    embed.add_field(
        name=f"🗾 Hiện tại ở Tokyo {BOT_NAME} đang:",
        value=time_ctx["activity"],
        inline=False,
    )
    await ctx.send(embed=embed)


@bot.event
async def on_message(message: discord.Message):
    # Bỏ qua tin nhắn do bot gửi (tránh xung đột với mọi bot khác)
    if message.author.bot:
        return

    # Nếu là lệnh có tiền tố "!", chuyển cho bot xử lý lệnh
    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    # Kiểm tra quyền truy cập
    if not is_authorized(message.author.id):
        return

    # Kiểm tra cấu hình OpenAI
    if not openai_client:
        await message.reply(
            "⚠️ Bạn chưa cấu hình `OPENAI_API_KEY` trong file .env. Vui lòng thêm key để bắt đầu trò chuyện nhé!"
        )
        return

    user_id = str(message.author.id)
    if user_id not in CONVERSATION_HISTORY:
        CONVERSATION_HISTORY[user_id] = []

    # Kiểm tra nếu người dùng gửi Voice Message hoặc file âm thanh
    user_text = message.content.strip()
    transcribed_text = await transcribe_voice_attachment(message)
    if transcribed_text:
        await message.reply(f"🎙️ **[Yuki nghe bạn nói]:** `{transcribed_text}`")
        if user_text:
            user_text = f"{user_text}\n(Nội dung giọng nói: {transcribed_text})"
        else:
            user_text = transcribed_text

    if not user_text:
        return

    # Lưu tin nhắn người dùng vào bộ nhớ
    CONVERSATION_HISTORY[user_id].append({"role": "user", "content": user_text})

    # Giới hạn số lượng tin nhắn trong lịch sử (Sliding Window)
    if len(CONVERSATION_HISTORY[user_id]) > MAX_HISTORY_TURNS:
        CONVERSATION_HISTORY[user_id] = CONVERSATION_HISTORY[user_id][-MAX_HISTORY_TURNS:]

    async with message.channel.typing():
        try:
            system_prompt = build_system_prompt(CURRENT_LEVEL)
            messages_payload = [
                {"role": "system", "content": system_prompt},
                *CONVERSATION_HISTORY[user_id],
            ]

            response = openai_client.chat.completions.create(
                model=CURRENT_MODEL,
                messages=messages_payload,
                temperature=0.8,
                max_tokens=1500,
            )

            reply_text = response.choices[0].message.content.strip()

            # Lưu phản hồi của bot vào lịch sử
            CONVERSATION_HISTORY[user_id].append({"role": "assistant", "content": reply_text})
            LAST_BOT_REPLY[user_id] = reply_text

            # Gửi phản hồi kèm file âm thanh giọng nói (.mp3)
            await send_reply_with_voice(
                message,
                reply_text,
                is_message_reply=True,
            )

        except Exception as e:
            logger.error(f"Lỗi khi gọi OpenAI: {e}")
            await message.reply(f"❌ Lỗi khi trò chuyện với AI: `{str(e)}`")


async def health_check_handler(request):
    """Health check endpoint siêu nhẹ cho Cron-job và Uptime monitor (tránh lỗi output too large)"""
    return web.Response(text="OK", content_type="text/plain")


async def web_ui_handler(request):
    """Giao diện web trực quan khi truy cập trang chủ /"""
    time_ctx = get_japan_time_context()
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="utf-8">
        <title>{BOT_NAME} - Japanese Kaiwa AI Friend</title>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #FFF5F7; color: #4A5568; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0;">
        <div style="background: white; padding: 40px; border-radius: 20px; box-shadow: 0 10px 25px rgba(255,119,169,0.15); text-align: center; max-width: 480px; border: 1px solid #FFE4EC;">
            <div style="font-size: 52px; margin-bottom: 12px;">🌸</div>
            <h1 style="color: #D53F8C; margin: 0 0 8px 0; font-size: 26px;">{BOT_NAME}</h1>
            <p style="color: #38A169; font-weight: 700; margin: 0 0 14px 0; letter-spacing: 0.5px;">ONLINE 24/7 • VOICE & REAL-TIME TOKYO</p>
            <p style="color: #718096; font-size: 14px; line-height: 1.5; margin: 0 0 16px 0;">
                🕒 Giờ Tokyo: <b>{time_ctx['jp_time']}</b> ({time_ctx['period_name']})<br>
                {time_ctx['activity']}
            </p>
            <div style="background: #FFF0F5; padding: 10px 16px; border-radius: 12px; font-size: 13px; color: #B83280; display: inline-block;">
                ⏰ Hỏi thăm mỗi ngày: {DAILY_CHECKIN_HOUR:02d}:{DAILY_CHECKIN_MINUTE:02d} (Giờ VN) • 🔊 Voice TTS: ON
            </div>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html_content, content_type="text/html")


async def start_web_server():
    """Khởi động web server phụ trợ để Cloud xác nhận health check $PORT"""
    port = int(os.getenv("PORT", 8080))
    app = web.Application()
    app.router.add_get("/", web_ui_handler)
    app.router.add_get("/health", health_check_handler)
    app.router.add_head("/health", health_check_handler)
    app.router.add_head("/", health_check_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 Web health-check server đã mở tại cổng: {port}")


async def main():
    print(f"🌸 Khởi động Japanese Kaiwa AI Friend ({BOT_NAME})...")
    await start_web_server()
    await bot.start(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot đã dừng bởi người dùng.")
