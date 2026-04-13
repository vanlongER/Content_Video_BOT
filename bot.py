"""
Telegram Bot: Quản lý quy trình làm Video Sản Phẩm

Logic mới:
- Bước 1 (Quay Video): Chung cho cả video, tick 1 lần
- Sau đó thêm các nội dung con (bất cứ lúc nào)
- Mỗi nội dung con có tiến trình RIÊNG:
    ⬜ Viết nội dung → ⬜ Lồng tiếng → ⬜ Chỉnh sửa → ⬜ Đăng YT/Shopee/TT
- Nội dung nào xong chỉnh sửa thì đăng được luôn, không cần đợi cái khác
- Khi TẤT CẢ nội dung đều đăng hết 3 nền tảng → video hoàn thành
"""

import json
import os
import logging
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# ── Config ──────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATA_FILE = "data.json"

WAITING_VIDEO_NAME = 1
PLATFORMS = ["YouTube", "Shopee", "TikTok"]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ── Data persistence ────────────────────────────────────
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"videos": {}}


def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_next_id(data: dict) -> int:
    if not data["videos"]:
        return 1
    return max(int(k) for k in data["videos"].keys()) + 1


# ── Content item structure ──────────────────────────────
def new_content_item(text: str) -> dict:
    """Mỗi nội dung con có trạng thái riêng cho từng bước."""
    return {
        "text": text,
        "written": False,     # Bước 2: Viết nội dung
        "dubbed": False,      # Bước 3: Lồng tiếng
        "edited": False,      # Bước 4: Chỉnh sửa
        "platforms": {         # Bước 5: Đăng video
            "YouTube": False,
            "Shopee": False,
            "TikTok": False
        }
    }


def content_step(c: dict) -> str:
    """Trả về bước hiện tại của nội dung con."""
    if not c["written"]:
        return "write"
    if not c["dubbed"]:
        return "dub"
    if not c["edited"]:
        return "edit"
    if not all(c["platforms"].values()):
        return "publish"
    return "done"


def content_step_icon(c: dict) -> str:
    step = content_step(c)
    return {
        "write": "📝",
        "dub": "🎙️",
        "edit": "✂️",
        "publish": "📤",
        "done": "✅"
    }.get(step, "⬜")


def content_step_label(c: dict) -> str:
    step = content_step(c)
    return {
        "write": "Chờ viết",
        "dub": "Chờ lồng tiếng",
        "edit": "Chờ chỉnh sửa",
        "publish": "Chờ đăng",
        "done": "Hoàn thành"
    }.get(step, "")


def is_content_done(c: dict) -> bool:
    return content_step(c) == "done"


def is_video_done(vid: dict) -> bool:
    """Video hoàn thành khi đã quay xong VÀ tất cả nội dung con đều done."""
    if not vid.get("filmed"):
        return False
    contents = vid.get("contents", [])
    if not contents:
        return False
    return all(is_content_done(c) for c in contents)


# ── Helper: Build video status text ────────────────────
def video_status_text(vid: dict, video_id: str) -> str:
    name = vid["name"]
    created = vid.get("created_at", "N/A")
    filmed = vid.get("filmed", False)
    contents = vid.get("contents", [])

    lines = [f"🎬 <b>{name}</b>  (ID: {video_id})", f"📅 Tạo: {created}", ""]

    # Bước 1: Quay video
    film_icon = "✅" if filmed else "🔄"
    lines.append(f"  {film_icon} Bước 1: 📹 Quay Video")
    lines.append("")

    if not contents:
        lines.append("  📝 (chưa có nội dung nào)")
    else:
        for i, c in enumerate(contents):
            step = content_step(c)
            icon = content_step_icon(c)
            label = content_step_label(c)

            lines.append(f"  📌 <b>{c['text']}</b> — {icon} {label}")

            # Show detail of each sub-step
            w = "✅" if c["written"] else "⬜"
            d = "✅" if c["dubbed"] else "⬜"
            e = "✅" if c["edited"] else "⬜"
            lines.append(f"        {w} Viết  {d} Lồng tiếng  {e} Chỉnh sửa")

            # Platforms
            pf = c.get("platforms", {})
            pf_parts = []
            for p in PLATFORMS:
                pf_parts.append(f"{'✅' if pf.get(p) else '⬜'} {p}")
            lines.append(f"        {' '.join(pf_parts)}")
            lines.append("")

    return "\n".join(lines)


def build_action_buttons(vid: dict, vid_id: str) -> list:
    """Build inline keyboard based on video state."""
    filmed = vid.get("filmed", False)
    contents = vid.get("contents", [])
    buttons = []

    if not filmed:
        buttons.append([InlineKeyboardButton("✅ Quay xong!", callback_data=f"film_{vid_id}")])
        buttons.append([InlineKeyboardButton("🔙 Danh sách", callback_data="backtolist")])
        return buttons

    # Always allow adding content
    buttons.append([InlineKeyboardButton("➕ Thêm nội dung", callback_data=f"addcontent_{vid_id}")])

    # For each content item, show the next action button
    for i, c in enumerate(contents):
        step = content_step(c)
        txt = c["text"]

        if step == "write":
            buttons.append([
                InlineKeyboardButton(f"📝 Viết xong: {txt}", callback_data=f"tick_{vid_id}_{i}_write"),
                InlineKeyboardButton("🗑️", callback_data=f"delcontent_{vid_id}_{i}")
            ])
        elif step == "dub":
            buttons.append([
                InlineKeyboardButton(f"🎙️ Lồng tiếng xong: {txt}", callback_data=f"tick_{vid_id}_{i}_dub")
            ])
        elif step == "edit":
            buttons.append([
                InlineKeyboardButton(f"✂️ Chỉnh sửa xong: {txt}", callback_data=f"tick_{vid_id}_{i}_edit")
            ])
        elif step == "publish":
            # Show remaining platforms
            pf = c.get("platforms", {})
            row = []
            for p in PLATFORMS:
                if not pf.get(p):
                    row.append(InlineKeyboardButton(
                        f"📤 {p}: {txt}", callback_data=f"pub_{vid_id}_{i}_{p}"
                    ))
            if row:
                # Split into separate rows if too many
                for btn in row:
                    buttons.append([btn])
        # "done" items don't need buttons

    buttons.append([InlineKeyboardButton("🔙 Danh sách", callback_data="backtolist")])
    return buttons


# ── /start ──────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎬 <b>Video Sản Phẩm Manager</b>\n\n"
        "Bot giúp bạn quản lý quy trình làm video sản phẩm.\n\n"
        "Mỗi nội dung con có tiến trình riêng:\n"
        "📝 Viết → 🎙️ Lồng Tiếng → ✂️ Chỉnh Sửa → 📤 Đăng\n\n"
        "<b>Lệnh:</b>\n"
        "/new - Tạo video mới\n"
        "/list - Xem video đang làm\n"
        "/done - Xem video đã hoàn thành\n"
        "/remind - Nhắc việc tổng quan\n"
        "/help - Hướng dẫn"
    )
    await update.message.reply_text(text, parse_mode="HTML")


# ── /help ───────────────────────────────────────────────
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 <b>Hướng dẫn sử dụng</b>\n\n"
        "1️⃣ <b>Quay Video</b> - Bấm ✅ khi quay xong\n"
        "2️⃣ <b>Thêm nội dung</b> - Thêm bất cứ lúc nào\n\n"
        "Mỗi nội dung con tiến trình RIÊNG:\n"
        "  📝 Viết xong → 🎙️ Lồng tiếng xong → ✂️ Chỉnh sửa xong\n"
        "  → 📤 Đăng YouTube/Shopee/TikTok\n\n"
        "💡 Nội dung nào xong chỉnh sửa thì đăng được luôn!\n"
        "💡 Khi tất cả nội dung đăng hết → video hoàn thành\n\n"
        "<b>Lệnh:</b>\n"
        "/new - Tạo video mới\n"
        "/list - Danh sách video đang làm\n"
        "/done - Video đã hoàn thành\n"
        "/remind - Nhắc việc\n"
        "/delete - Xóa video"
    )
    await update.message.reply_text(text, parse_mode="HTML")


# ── /new ────────────────────────────────────────────────
async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📹 <b>Tạo video mới</b>\n\nNhập tên sản phẩm/video:",
        parse_mode="HTML"
    )
    return WAITING_VIDEO_NAME


async def receive_video_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    data = load_data()
    vid_id = str(get_next_id(data))

    data["videos"][vid_id] = {
        "name": name,
        "filmed": False,
        "created_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "contents": [],
        "completed": False
    }
    save_data(data)

    text = f"✅ Đã tạo video <b>{name}</b> (ID: {vid_id})\n\nBước tiếp: 📹 Quay Video"
    keyboard = [[InlineKeyboardButton("📋 Xem chi tiết", callback_data=f"view_{vid_id}")]]
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


# ── /list ───────────────────────────────────────────────
async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    active = {k: v for k, v in data["videos"].items() if not v.get("completed")}

    if not active:
        await update.message.reply_text("📭 Chưa có video nào đang làm.\n/new để tạo mới!")
        return

    keyboard = []
    for vid_id, vid in active.items():
        total = len(vid.get("contents", []))
        done_count = sum(1 for c in vid.get("contents", []) if is_content_done(c))
        filmed = "📹" if not vid.get("filmed") else f"📝 {done_count}/{total}"
        keyboard.append([
            InlineKeyboardButton(
                f"{filmed} {vid['name']}",
                callback_data=f"view_{vid_id}"
            )
        ])

    await update.message.reply_text(
        f"📋 <b>Video đang làm ({len(active)}):</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ── /done ───────────────────────────────────────────────
async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    completed = {k: v for k, v in data["videos"].items() if v.get("completed")}

    if not completed:
        await update.message.reply_text("📭 Chưa có video nào hoàn thành.")
        return

    lines = ["🏆 <b>Video đã hoàn thành:</b>\n"]
    for vid_id, vid in completed.items():
        lines.append(f"  ✅ {vid['name']} (ID: {vid_id}) - {vid.get('completed_at', '')}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ── View video detail ───────────────────────────────────
async def view_video(update: Update, context: ContextTypes.DEFAULT_TYPE, vid_id: str):
    query = update.callback_query
    data = load_data()

    if vid_id not in data["videos"]:
        await query.answer("Video không tồn tại!")
        return

    vid = data["videos"][vid_id]
    text = video_status_text(vid, vid_id)
    keyboard = build_action_buttons(vid, vid_id)

    try:
        await query.edit_message_text(
            text, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        pass


# ── Check completion ────────────────────────────────────
def check_video_completion(vid: dict):
    """Mark video as completed if all contents are done."""
    if is_video_done(vid):
        vid["completed"] = True
        vid["completed_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")


# ── Callback handler ────────────────────────────────────
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cb = query.data

    # ── View video
    if cb.startswith("view_"):
        vid_id = cb.split("_", 1)[1]
        await view_video(update, context, vid_id)
        return

    # ── Back to list
    if cb == "backtolist":
        data = load_data()
        active = {k: v for k, v in data["videos"].items() if not v.get("completed")}
        if not active:
            await query.edit_message_text("📭 Chưa có video nào đang làm.\n/new để tạo mới!")
            return
        keyboard = []
        for vid_id, vid in active.items():
            total = len(vid.get("contents", []))
            done_count = sum(1 for c in vid.get("contents", []) if is_content_done(c))
            filmed = "📹" if not vid.get("filmed") else f"📝 {done_count}/{total}"
            keyboard.append([
                InlineKeyboardButton(
                    f"{filmed} {vid['name']}",
                    callback_data=f"view_{vid_id}"
                )
            ])
        await query.edit_message_text(
            f"📋 <b>Video đang làm ({len(active)}):</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # ── Film done
    if cb.startswith("film_"):
        vid_id = cb.split("_", 1)[1]
        data = load_data()
        data["videos"][vid_id]["filmed"] = True
        save_data(data)
        await view_video(update, context, vid_id)
        return

    # ── Add content
    if cb.startswith("addcontent_"):
        vid_id = cb.split("_", 1)[1]
        context.user_data["pending_action"] = f"addcontent_{vid_id}"
        await query.edit_message_text(
            "📝 Nhập tên nội dung cần thêm:\n(Gõ text rồi gửi)",
            parse_mode="HTML"
        )
        return

    # ── Delete content
    if cb.startswith("delcontent_"):
        parts = cb.split("_")
        vid_id = parts[1]
        idx = int(parts[2])
        data = load_data()
        vid = data["videos"][vid_id]
        if idx < len(vid["contents"]):
            vid["contents"].pop(idx)
        save_data(data)
        await view_video(update, context, vid_id)
        return

    # ── Tick step (write/dub/edit)
    if cb.startswith("tick_"):
        parts = cb.split("_")
        vid_id = parts[1]
        idx = int(parts[2])
        step = parts[3]
        data = load_data()
        vid = data["videos"][vid_id]

        if idx < len(vid["contents"]):
            c = vid["contents"][idx]
            if step == "write":
                c["written"] = True
            elif step == "dub":
                c["dubbed"] = True
            elif step == "edit":
                c["edited"] = True

            check_video_completion(vid)

        save_data(data)

        if vid.get("completed"):
            await query.edit_message_text(
                f"🎉 <b>{vid['name']}</b> đã hoàn thành tất cả!\n\n/list để xem video khác",
                parse_mode="HTML"
            )
            return

        await view_video(update, context, vid_id)
        return

    # ── Publish to platform
    if cb.startswith("pub_"):
        parts = cb.split("_")
        vid_id = parts[1]
        idx = int(parts[2])
        platform = parts[3]
        data = load_data()
        vid = data["videos"][vid_id]

        if idx < len(vid["contents"]):
            vid["contents"][idx]["platforms"][platform] = True
            check_video_completion(vid)

        save_data(data)

        if vid.get("completed"):
            await query.edit_message_text(
                f"🎉 <b>{vid['name']}</b> đã hoàn thành tất cả!\n\n/list để xem video khác",
                parse_mode="HTML"
            )
            return

        await view_video(update, context, vid_id)
        return


# ── Text message handler ───────────────────────────────
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get("pending_action")
    if not pending:
        return

    text = update.message.text.strip()
    data = load_data()

    if pending.startswith("addcontent_"):
        vid_id = pending.split("_", 1)[1]
        if vid_id not in data["videos"]:
            context.user_data.pop("pending_action", None)
            return

        vid = data["videos"][vid_id]
        vid["contents"].append(new_content_item(text))
        save_data(data)
        context.user_data.pop("pending_action", None)

        status = video_status_text(vid, vid_id)
        keyboard = build_action_buttons(vid, vid_id)
        await update.message.reply_text(
            f"✅ Đã thêm: <b>{text}</b>\n\n{status}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# ── /delete ─────────────────────────────────────────────
async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    active = {k: v for k, v in data["videos"].items() if not v.get("completed")}

    if not active:
        await update.message.reply_text("📭 Không có video nào để xóa.")
        return

    keyboard = []
    for vid_id, vid in active.items():
        keyboard.append([
            InlineKeyboardButton(
                f"🗑️ {vid['name']}", callback_data=f"confirmdelete_{vid_id}"
            )
        ])

    await update.message.reply_text(
        "🗑️ <b>Chọn video muốn xóa:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cb = query.data

    if cb.startswith("confirmdelete_"):
        vid_id = cb.split("_", 1)[1]
        data = load_data()
        if vid_id not in data["videos"]:
            await query.edit_message_text("Video không tồn tại!")
            return
        name = data["videos"][vid_id]["name"]
        keyboard = [
            [
                InlineKeyboardButton("✅ Xác nhận xóa", callback_data=f"dodelete_{vid_id}"),
                InlineKeyboardButton("❌ Hủy", callback_data="backtolist")
            ]
        ]
        await query.edit_message_text(
            f"⚠️ Bạn chắc muốn xóa <b>{name}</b>?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif cb.startswith("dodelete_"):
        vid_id = cb.split("_", 1)[1]
        data = load_data()
        if vid_id not in data["videos"]:
            await query.edit_message_text("Video không tồn tại!")
            return
        name = data["videos"][vid_id]["name"]
        del data["videos"][vid_id]
        save_data(data)
        await query.edit_message_text(
            f"🗑️ Đã xóa <b>{name}</b>\n/list để xem danh sách",
            parse_mode="HTML"
        )


# ── /remind ─────────────────────────────────────────────
async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    active = {k: v for k, v in data["videos"].items() if not v.get("completed")}

    if not active:
        await update.message.reply_text("🎉 Không có việc gì cần làm! Tạo video mới bằng /new")
        return

    lines = ["⏰ <b>NHẮC VIỆC:</b>\n"]
    for vid_id, vid in active.items():
        lines.append(f"🔸 <b>{vid['name']}</b>")

        if not vid.get("filmed"):
            lines.append("   📹 Cần quay video")
        else:
            for c in vid.get("contents", []):
                step = content_step(c)
                if step == "write":
                    lines.append(f"   📝 Cần viết: {c['text']}")
                elif step == "dub":
                    lines.append(f"   🎙️ Cần lồng tiếng: {c['text']}")
                elif step == "edit":
                    lines.append(f"   ✂️ Cần chỉnh sửa: {c['text']}")
                elif step == "publish":
                    undone = [p for p in PLATFORMS if not c["platforms"].get(p)]
                    lines.append(f"   📤 {c['text']} → chưa đăng: {', '.join(undone)}")

            if not vid.get("contents"):
                lines.append("   📝 Chưa thêm nội dung nào")

        lines.append("")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ── Main ────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    new_conv = ConversationHandler(
        entry_points=[CommandHandler("new", cmd_new)],
        states={
            WAITING_VIDEO_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_video_name)
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_start)],
    )

    app.add_handler(new_conv)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("remind", cmd_remind))

    app.add_handler(CallbackQueryHandler(delete_callback, pattern=r"^(confirmdelete_|dodelete_)"))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("🤖 Bot đang chạy...")
    app.run_polling()


if __name__ == "__main__":
    import asyncio
    import sys

    if sys.version_info >= (3, 13):
        asyncio.set_event_loop(asyncio.new_event_loop())

    main()
