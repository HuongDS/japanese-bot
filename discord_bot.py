import os
import sys
import asyncio
import logging
import datetime
import discord
from discord.ext import commands, tasks
from aiohttp import web
from dotenv import load_dotenv
from openai import OpenAI

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

# Cấu hình giờ hỏi thăm hàng ngày (Múi giờ Việt Nam UTC+7)
DAILY_CHECKIN_HOUR = int(os.getenv("DAILY_CHECKIN_HOUR", "8"))
DAILY_CHECKIN_MINUTE = int(os.getenv("DAILY_CHECKIN_MINUTE", "30"))
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

CURRENT_MODEL = OPENAI_MODEL
CURRENT_LEVEL = os.getenv("JAPANESE_LEVEL", "N4-N3")  # N5, N4, N4-N3, N3, N2, N1, NATIVE
BOT_NAME = os.getenv("JAPANESE_BOT_NAME", "Yuki (ユキ)")

if not DISCORD_BOT_TOKEN:
    raise ValueError("Thiếu DISCORD_BOT_TOKEN trong file .env!")

# Khởi tạo OpenAI Client nếu có key
base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
openai_client = OpenAI(api_key=OPENAI_API_KEY, base_url=base_url) if OPENAI_API_KEY else None

# Bộ nhớ hội thoại (user_id -> list[dict])
CONVERSATION_HISTORY = {}
MAX_HISTORY_TURNS = 14  # Lưu khoảng 7 lượt hỏi - đáp gần nhất để giữ mạch trò chuyện

# Cấu hình Discord Intents
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


def is_authorized(user_id: int) -> bool:
    """Kiểm tra quyền truy cập (Chỉ cho phép chủ nhân sử dụng)"""
    if not ALLOWED_USER_ID:
        return True
    return str(user_id) == str(ALLOWED_USER_ID)


def build_system_prompt(level: str) -> str:
    """Tạo System Prompt đóng vai người bạn Nhật Bản theo cấp độ"""
    level_descriptions = {
        "N5": (
            "Trình độ người học: N5 (Mới bắt đầu). "
            "Hãy dùng câu ngắn gọn, từ vựng sơ cấp, ngữ pháp cơ bản. "
            "Hạn chế Kanji khó (nếu có Kanji hãy phiên âm Hiragana đi kèm). "
            "Kèm nghĩa tiếng Việt tóm tắt ở cuối câu nếu có từ mới để bạn ấy dễ hiểu."
        ),
        "N4": (
            "Trình độ người học: N4 (Sơ cấp - Sơ trung cấp). "
            "Dùng ngữ pháp thường ngày, câu từ rõ ràng, thân thiện. "
            "Kanji cơ bản có giải thích nếu là từ ít gặp. Luôn khích lệ bạn ấy nói nhiều hơn."
        ),
        "N4-N3": (
            "Trình độ người học: N4 - N3 (Giao tiếp thường nhật gần gũi). "
            "Trò chuyện tự nhiên như hai người bạn thân cùng lứa tuổi. "
            "Dùng từ vựng thực tế và cách nói quen thuộc của người Nhật trong đời sống."
        ),
        "N3": (
            "Trình độ người học: N3 (Trung cấp). "
            "Hội thoại tự nhiên, linh hoạt mở rộng nhiều chủ đề (cuộc sống, văn hóa, ẩm thực, trải nghiệm ở Nhật). "
            "Khuyến khích bạn ấy biểu đạt cảm xúc và suy nghĩ cá nhân."
        ),
        "N2": (
            "Trình độ người học: N2 (Trung cao cấp). "
            "Giao tiếp trôi chảy, đa dạng từ vựng, thảo luận các vấn đề sâu hơn."
        ),
        "N1": (
            "Trình độ người học: N1 / Native (Cao cấp). "
            "Nói chuyện 100% tự nhiên như người bản xứ, dùng thành ngữ, từ lóng đời thường của giới trẻ Nhật."
        ),
    }

    level_guide = level_descriptions.get(level, level_descriptions["N4-N3"])

    return f"""
Bạn là {BOT_NAME} — một người bạn thân người Nhật Bản (Japanese close friend) của người dùng.
Nhiệm vụ chính: Trò chuyện tâm sự thường ngày, hỏi thăm nhau và cùng nhau luyện tập hội thoại tiếng Nhật (Kaiwa) thật tự nhiên, thoải mái.

🌸 Tính cách & Phong thái của bạn:
1. Bạn là người bạn ấm áp, tươi vui, nhiệt tình, luôn biết lắng nghe và động viên người bạn của mình học tiếng Nhật.
2. Bạn sống ở Nhật Bản, rất thích chia sẻ những mẩu chuyện đời thường ở Tokyo/Nhật Bản (thời tiết, các mùa, món ăn ngon, quán cafe, anime, manga, lễ hội...).
3. Tương tác 2 chiều: Đừng bao giờ trả lời cộc lốc. Luôn chủ động đặt câu hỏi mở hoặc chia sẻ thêm về bản thân để giữ cho cuộc trò chuyện tiếp diễn tự nhiên.

🎌 Phong cách ngôn ngữ & Quy tắc luyện Kaiwa:
- {level_guide}
- Ngôn ngữ: Dùng tiếng Nhật tự nhiên, thân thiện (phong cách bạn bè đời thường).
- Góp ý Kaiwa khéo léo: Nếu người dùng nói câu tiếng Nhật chưa tự nhiên hoặc bị sai ngữ pháp, bạn vẫn vui vẻ hiểu ý họ và trả lời trước, sau đó ở cuối tin nhắn thêm một dòng nhỏ:
  💡 [Gợi ý Kaiwa]: <cách nói tự nhiên hơn của người Nhật> (<giải thích ngắn bằng tiếng Việt>)
- Nếu người dùng nhắn bằng tiếng Việt hoặc hỏi về ngữ pháp/từ vựng: Hãy nhiệt tình giải thích bằng tiếng Việt thật dễ hiểu và đưa ví dụ minh họa bằng tiếng Nhật.
""".strip()


async def generate_daily_checkin(level: str) -> str:
    """Tạo tin nhắn hỏi thăm hàng ngày và chủ đề Kaiwa mới"""
    if not openai_client:
        return (
            "🌸 おはよう！(Ohayou!)\n"
            "Hôm nay bạn thế nào? Hôm nay chúng mình cùng trò chuyện về chủ đề: **『好きな食べ物 (Món ăn yêu thích)』** nhé!\n"
            "あなたの一番好きな食べ物は何ですか？ (Món ăn yêu thích nhất của bạn là gì?)"
        )

    prompt = f"""
Hôm nay là một ngày mới. Bạn hãy tạo một tin nhắn chào buổi sáng ngắn (khoảng 3 - 5 câu tiếng Nhật) để gửi cho người bạn của bạn:
1. Chào buổi sáng bằng tiếng Nhật một cách ấm áp, hỏi thăm bạn ngủ có ngon không hoặc hôm nay thế nào.
2. Giới thiệu MỘT chủ đề thú vị để hai người cùng trò chuyện Kaiwa hôm nay (ví dụ: món ăn sáng, thời tiết, sở thích, âm nhạc, một bộ phim hay, kế hoạch trong ngày, du lịch Nhật Bản...).
3. Đặt một câu hỏi mở đơn giản để bạn ấy có thể dễ dàng trả lời và bắt đầu cuộc trò chuyện.
4. Trình độ người học hiện tại: {level}.
5. Ở cuối tin nhắn, hãy thêm:
   - Bản dịch tiếng Việt tóm tắt.
   - Gợi ý 2-3 từ vựng hữu ích liên quan đến chủ đề để bạn ấy tự tin trả lời.
""".strip()

    try:
        response = openai_client.chat.completions.create(
            model=CURRENT_MODEL,
            messages=[
                {"role": "system", "content": build_system_prompt(level)},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_tokens=850,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Lỗi tạo tin nhắn hàng ngày: {e}")
        return (
            "🌸 おはようございます！\n"
            "Hôm nay bạn thế nào? Hãy cùng Yuki luyện Kaiwa hôm nay nhé!\n"
            "今日の気分はどうですか？ (Tâm trạng hôm nay của bạn thế nào?)"
        )


async def send_daily_greeting(target_channel=None):
    """Gửi tin nhắn hỏi thăm và chủ đề hàng ngày tới người dùng"""
    greeting = await generate_daily_checkin(CURRENT_LEVEL)

    # Nếu được gọi trực tiếp trong kênh (qua lệnh !daily)
    if target_channel:
        await target_channel.send(greeting)
        return

    sent = False
    # 1. Nếu có cấu hình DISCORD_CHANNEL_ID thì gửi vào kênh đó
    if DISCORD_CHANNEL_ID:
        try:
            channel = bot.get_channel(int(DISCORD_CHANNEL_ID)) or await bot.fetch_channel(int(DISCORD_CHANNEL_ID))
            if channel:
                mention = f"<@{ALLOWED_USER_ID}> " if ALLOWED_USER_ID else ""
                await channel.send(f"{mention}\n{greeting}")
                sent = True
        except Exception as e:
            logger.warning(f"Không thể gửi tin nhắn vào channel {DISCORD_CHANNEL_ID}: {e}")

    # 2. Nếu chưa gửi được và có ALLOWED_USER_ID, gửi trực tiếp qua tin nhắn riêng (DM)
    if not sent and ALLOWED_USER_ID:
        try:
            user = bot.get_user(int(ALLOWED_USER_ID)) or await bot.fetch_user(int(ALLOWED_USER_ID))
            if user:
                await user.send(greeting)
                sent = True
        except Exception as e:
            logger.warning(f"Không thể gửi tin nhắn DM cho user {ALLOWED_USER_ID}: {e}")

    if sent:
        logger.info("✅ Đã gửi thành công tin nhắn Kaiwa hỏi thăm hàng ngày!")
    else:
        logger.warning("⚠️ Chưa cấu hình DISCORD_CHANNEL_ID hoặc DISCORD_ALLOWED_USER_ID để gửi tin nhắn tự động.")


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

    # Cập nhật trạng thái hiển thị
    activity = discord.Activity(
        type=discord.ActivityType.listening,
        name=f"日本語 Kaiwa ({CURRENT_LEVEL}) | !help",
    )
    await bot.change_presence(status=discord.Status.online, activity=activity)

    # Bật lịch nhắn tin hàng ngày nếu chưa chạy
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

    embed = discord.Embed(
        title=f"🌸 {BOT_NAME} — NGƯỜI BẠN LUYỆN KAIWA TIẾNG NHẬT",
        description=(
            "Chào bạn! Mình là bạn thân người Nhật của bạn, luôn sẵn sàng trò chuyện thường ngày "
            "và cùng bạn luyện tập Kaiwa tiếng Nhật 24/7."
        ),
        color=0xFF77A9,  # Sakura Pink
    )
    embed.add_field(
        name="!daily",
        value="Nhận ngay tin nhắn hỏi thăm & chủ đề luyện Kaiwa hôm nay (không cần đợi giờ hẹn).",
        inline=False,
    )
    embed.add_field(
        name="!topic [chủ đề]",
        value="Đổi chủ đề nói chuyện mới (Ví dụ: `!topic anime`, `!topic du lịch Tokyo` hoặc gõ trơn `!topic` để Yuki tự chọn).",
        inline=False,
    )
    embed.add_field(
        name="!level [n5|n4|n3|n2|n1]",
        value="Xem hoặc thay đổi trình độ tiếng Nhật (Ví dụ: `!level N4`, `!level N3`).",
        inline=False,
    )
    embed.add_field(
        name="!reset",
        value="Làm mới bộ nhớ trò chuyện để bắt đầu cuộc trò chuyện mới từ đầu.",
        inline=False,
    )
    embed.add_field(
        name="!model [tên_model]",
        value=f"Xem hoặc đổi model AI (Hiện tại: `{CURRENT_MODEL}`).",
        inline=False,
    )
    embed.add_field(
        name="!status",
        value="Xem thông tin server, level hiện tại, giờ nhắn tin hàng ngày.",
        inline=False,
    )
    embed.add_field(
        name="💬 Nhắn tin tự do",
        value="Bạn cứ gõ tiếng Nhật hoặc tiếng Việt tự nhiên trong kênh/tin nhắn riêng, Yuki sẽ trò chuyện và đồng hành cùng bạn!",
        inline=False,
    )
    embed.set_footer(text=f"Mỗi ngày Yuki sẽ chủ động nhắn tin lúc {DAILY_CHECKIN_HOUR:02d}:{DAILY_CHECKIN_MINUTE:02d} sáng.")
    await ctx.send(embed=embed)


@bot.command(name="daily")
async def daily_manual_command(ctx):
    """Kích hoạt ngay tin nhắn hỏi thăm và chủ đề hàng ngày"""
    if not is_authorized(ctx.author.id):
        return

    status_msg = await ctx.send(f"🌸 {BOT_NAME} đang chuẩn bị chủ đề hôm nay cho bạn nhé...")
    greeting = await generate_daily_checkin(CURRENT_LEVEL)
    await status_msg.delete()
    await ctx.send(greeting)


@bot.command(name="topic")
async def topic_command(ctx, *, custom_topic: str = ""):
    """Đổi chủ đề luyện Kaiwa"""
    if not is_authorized(ctx.author.id):
        return

    status_msg = await ctx.send("🌸 Đang chọn chủ đề trò chuyện mới...")
    if custom_topic:
        user_prompt = (
            f"Chúng mình hãy đổi sang chủ đề này nhé: '{custom_topic}'. "
            f"Hãy mở đầu câu chuyện bằng tiếng Nhật thật tự nhiên và đặt cho mình một câu hỏi nhé!"
        )
    else:
        user_prompt = (
            "Hãy đổi sang một chủ đề Kaiwa mới thật thú vị và quen thuộc trong đời sống Nhật Bản. "
            "Mở đầu bằng tiếng Nhật và đặt câu hỏi cho mình nhé!"
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
        await status_msg.delete()
        await ctx.send(reply)
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
                "• `!level N5`: Mới bắt đầu (câu ngắn, từ vựng cơ bản, kèm dịch)\n"
                "• `!level N4`: Sơ cấp (giao tiếp đơn giản, thân thiện)\n"
                "• `!level N3`: Trung cấp (giao tiếp tự nhiên, biểu cảm phong phú)\n"
                "• `!level N2`: Trung cao cấp (nói chuyện trôi chảy nhiều đề tài)\n"
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
        "✨ Đã làm mới bộ nhớ trò chuyện! Chúng mình cùng bắt đầu cuộc trò chuyện mới nhé (新しく始めましょう！)"
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
                "• `gpt-4o`: Thông minh nhất, giải thích ngữ pháp và văn cảnh xuất sắc\n"
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
    """Kiểm tra tình trạng bot và server"""
    if not is_authorized(ctx.author.id):
        return

    embed = discord.Embed(
        title=f"🌸 TRẠNG THÁI {BOT_NAME.upper()}",
        color=0x16A34A,
    )
    embed.add_field(name="Trình độ Kaiwa", value=f"`{CURRENT_LEVEL}`", inline=True)
    embed.add_field(name="Giờ nhắn tin hàng ngày", value=f"`{DAILY_CHECKIN_HOUR:02d}:{DAILY_CHECKIN_MINUTE:02d} (VN)`", inline=True)
    embed.add_field(name="Model AI", value=f"`{CURRENT_MODEL}`", inline=True)
    embed.add_field(name="OpenAI API", value="`Sẵn sàng ✓`" if openai_client else "`Chưa có Key ❌`", inline=True)
    embed.add_field(name="Kênh chỉ định", value=f"`{DISCORD_CHANNEL_ID or 'DM trực tiếp'}`", inline=True)
    embed.add_field(name="Môi trường", value=f"`Python {sys.version.split()[0]}`", inline=True)
    await ctx.send(embed=embed)


@bot.event
async def on_message(message: discord.Message):
    # Bỏ qua tin nhắn do chính bot gửi
    if message.author == bot.user:
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

    # Lưu tin nhắn người dùng vào bộ nhớ
    CONVERSATION_HISTORY[user_id].append({"role": "user", "content": message.content})

    # Giới hạn số lượng tin nhắn trong lịch sử
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
                temperature=0.75,
                max_tokens=1500,
            )

            reply_text = response.choices[0].message.content.strip()

            # Lưu phản hồi của bot vào lịch sử
            CONVERSATION_HISTORY[user_id].append({"role": "assistant", "content": reply_text})

            # Chia nhỏ tin nhắn nếu vượt quá 1900 ký tự (giới hạn Discord là 2000)
            if len(reply_text) <= 1900:
                await message.reply(reply_text)
            else:
                chunks = [reply_text[i : i + 1800] for i in range(0, len(reply_text), 1800)]
                for chunk in chunks:
                    await message.reply(chunk)

        except Exception as e:
            logger.error(f"Lỗi khi gọi OpenAI: {e}")
            await message.reply(f"❌ Lỗi khi trò chuyện với AI: `{str(e)}`")


async def health_check_handler(request):
    """Health check endpoint cho Cloud Web Service (Render, Railway, v.v.)"""
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="utf-8">
        <title>{BOT_NAME} - Japanese Kaiwa AI Friend</title>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #FFF5F7; color: #4A5568; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0;">
        <div style="background: white; padding: 40px; border-radius: 20px; box-shadow: 0 10px 25px rgba(255,119,169,0.15); text-align: center; max-width: 460px; border: 1px solid #FFE4EC;">
            <div style="font-size: 52px; margin-bottom: 12px;">🌸</div>
            <h1 style="color: #D53F8C; margin: 0 0 8px 0; font-size: 26px;">{BOT_NAME}</h1>
            <p style="color: #38A169; font-weight: 700; margin: 0 0 14px 0; letter-spacing: 0.5px;">ONLINE 24/7 • JAPANESE KAIWA FRIEND</p>
            <p style="color: #718096; font-size: 15px; line-height: 1.5; margin: 0 0 16px 0;">
                Sẵn sàng trò chuyện tiếng Nhật và cùng bạn luyện Kaiwa mỗi ngày qua Discord!
            </p>
            <div style="background: #FFF0F5; padding: 10px 16px; border-radius: 12px; font-size: 13px; color: #B83280; display: inline-block;">
                ⏰ Nhắn tin hỏi thăm mỗi ngày: {DAILY_CHECKIN_HOUR:02d}:{DAILY_CHECKIN_MINUTE:02d} (Giờ VN)
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
    app.router.add_get("/", health_check_handler)
    app.router.add_get("/health", health_check_handler)
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
