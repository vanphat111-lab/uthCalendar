# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from telebot import types

import admin_security
import admin_service
import task
import utils


ADMIN_BUTTON_TEXT = "⚙️ Admin Panel"


def register_admin_handlers(bot) -> None:
    @bot.message_handler(commands=["admin"])
    @bot.message_handler(func=lambda message: message.text == ADMIN_BUTTON_TEXT)
    def open_admin_panel(message):
        if not _ensure_admin_message(bot, message):
            return

        bot.send_message(
            message.chat.id,
            _home_text(),
            parse_mode="HTML",
            reply_markup=_home_markup(),
        )

    @bot.message_handler(commands=["broadcast"])
    def broadcast_command(message):
        if not _ensure_admin_message(bot, message):
            return

        raw_input = message.text.split(maxsplit=1)
        if len(raw_input) < 2:
            _request_broadcast_content(bot, message.chat.id)
            return

        _store_and_preview_broadcast(bot, message.chat.id, raw_input[1])

    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin:"))
    def handle_admin_callback(call):
        if not _ensure_admin_callback(bot, call):
            return

        callback = call.data
        bot.answer_callback_query(call.id)

        if callback == "admin:home":
            _edit_panel(bot, call, _home_text(), _home_markup())
        elif callback == "admin:overview":
            _edit_panel(
                bot,
                call,
                admin_service.get_admin_overview(bot),
                _back_home_markup(refresh_callback="admin:overview"),
            )
        elif callback == "admin:broadcast":
            _request_broadcast_content(bot, call.message.chat.id)
        elif callback == "admin:broadcast:test":
            _send_broadcast_test(bot, call)
        elif callback == "admin:broadcast:confirm":
            _confirm_broadcast(bot, call)
        elif callback == "admin:broadcast:cancel":
            admin_service.delete_broadcast_draft(call.from_user.id)
            _edit_panel(bot, call, "❌ Đã hủy broadcast.", _home_markup())
        elif callback == "admin:retention":
            _edit_panel(bot, call, _retention_text(), _retention_markup())
        elif callback == "admin:retention:stats":
            _edit_panel(
                bot,
                call,
                admin_service.get_retention_stats(),
                _back_retention_markup(),
            )
        elif callback == "admin:retention:all":
            _edit_panel(bot, call, _retention_all_confirm_text(), _retention_all_confirm_markup())
        elif callback == "admin:retention:all:go":
            task.retention_request_all_task.delay(call.from_user.id)
            _edit_panel(
                bot,
                call,
                "⏳ <b>ĐÃ ĐƯA VÀO HÀNG ĐỢI</b>\n\nWorker đang gửi yêu cầu xác nhận tới toàn bộ user đủ điều kiện. Báo cáo sẽ được gửi lại khi hoàn tất.",
                _back_retention_markup(),
            )
        elif callback == "admin:retention:cleanup":
            _edit_panel(bot, call, _retention_cleanup_confirm_text(), _retention_cleanup_confirm_markup())
        elif callback == "admin:retention:cleanup:go":
            task.admin_retention_cleanup_task.delay(call.from_user.id)
            _edit_panel(
                bot,
                call,
                "⏳ <b>ĐÃ ĐƯA CLEANUP VÀO HÀNG ĐỢI</b>\n\nWorker sẽ xử lý các yêu cầu đã quá 48 giờ và gửi báo cáo khi hoàn tất.",
                _back_retention_markup(),
            )
        elif callback == "admin:tasks":
            _edit_panel(bot, call, _tasks_text(), _tasks_markup())
        elif callback == "admin:tasks:weather":
            task.admin_update_weather_task.delay(call.from_user.id)
            _edit_panel(bot, call, "🌦️ Đã đưa tác vụ cập nhật thời tiết vào hàng đợi.", _back_tasks_markup())
        elif callback == "admin:tasks:portal":
            task.admin_portal_scan_task.delay(call.from_user.id)
            _edit_panel(bot, call, "📅 Đã đưa tác vụ quét Portal toàn hệ thống vào hàng đợi.", _back_tasks_markup())
        elif callback == "admin:tasks:deadline":
            task.admin_deadline_scan_task.delay(call.from_user.id)
            _edit_panel(bot, call, "📚 Đã đưa tác vụ quét deadline toàn hệ thống vào hàng đợi.", _back_tasks_markup())
        elif callback == "admin:tasks:retention":
            task.admin_retention_maintenance_task.delay(call.from_user.id)
            _edit_panel(bot, call, "🧹 Đã đưa retention maintenance vào hàng đợi.", _back_tasks_markup())
        elif callback == "admin:close":
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                bot.edit_message_reply_markup(
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=None,
                )


def _request_broadcast_content(bot, chat_id: int) -> None:
    message = bot.send_message(
        chat_id,
        "📝 <b>NHẬP NỘI DUNG BROADCAST</b>\n\n"
        "Gửi nội dung ở tin nhắn tiếp theo. Hỗ trợ HTML của Telegram. Draft tự hết hạn sau 10 phút.",
        parse_mode="HTML",
    )
    bot.register_next_step_handler(message, _receive_broadcast_content, bot)


def _receive_broadcast_content(message, bot) -> None:
    if not _ensure_admin_message(bot, message):
        return

    content = message.text
    if not content or not content.strip():
        bot.send_message(message.chat.id, "❌ Nội dung broadcast không được để trống.")
        return

    content = content.strip()
    if len(content) > 3500:
        bot.send_message(
            message.chat.id,
            "❌ Nội dung broadcast quá dài. Giới hạn an toàn là 3500 ký tự.",
        )
        return

    _store_and_preview_broadcast(bot, message.chat.id, content)


def _store_and_preview_broadcast(bot, admin_id: int, content: str) -> None:
    if not admin_security.is_admin(admin_id):
        return

    if not admin_service.save_broadcast_draft(admin_id, content):
        bot.send_message(admin_id, "❌ Không thể lưu bản nháp broadcast. Vui lòng thử lại.")
        return

    try:
        bot.send_message(
            admin_id,
            admin_service.format_broadcast_preview(content),
            parse_mode="HTML",
            reply_markup=_broadcast_preview_markup(),
        )
    except Exception as exc:
        utils.log("WARN", f"Broadcast preview HTML không hợp lệ: {exc}")
        bot.send_message(
            admin_id,
            "❌ Nội dung HTML không hợp lệ hoặc Telegram không thể hiển thị. Hãy sửa nội dung rồi thử lại.",
        )


def _send_broadcast_test(bot, call) -> None:
    content = admin_service.get_broadcast_draft(call.from_user.id)
    if not content:
        _edit_panel(bot, call, "⚠️ Draft đã hết hạn. Hãy nhập lại nội dung broadcast.", _home_markup())
        return

    try:
        bot.send_message(
            call.from_user.id,
            f"📢 <b>THÔNG BÁO MỚI</b>\n\n{content}\n\n<i>Chúc bạn học tốt!</i>",
            parse_mode="HTML",
        )
    except Exception as exc:
        utils.log("ERROR", f"Không gửi được broadcast test cho {call.from_user.id}: {exc}")
        bot.send_message(call.from_user.id, "❌ Nội dung broadcast test không gửi được.")


def _confirm_broadcast(bot, call) -> None:
    content = admin_service.get_broadcast_draft(call.from_user.id)
    if not content:
        _edit_panel(bot, call, "⚠️ Draft đã hết hạn. Hãy nhập lại nội dung broadcast.", _home_markup())
        return

    task.admin_broadcast_task.delay(call.from_user.id, content)
    admin_service.delete_broadcast_draft(call.from_user.id)
    _edit_panel(
        bot,
        call,
        "⏳ <b>ĐÃ ĐƯA BROADCAST VÀO HÀNG ĐỢI</b>\n\nWorker sẽ gửi thông báo và báo cáo kết quả sau khi hoàn tất.",
        _home_markup(),
    )


def _ensure_admin_message(bot, message) -> bool:
    if admin_security.is_admin(message.chat.id):
        return True

    bot.send_message(message.chat.id, "⛔ Bạn không có quyền sử dụng chức năng này.")
    utils.log("WARN", f"Từ chối truy cập admin từ chat_id={message.chat.id}")
    return False


def _ensure_admin_callback(bot, call) -> bool:
    if admin_security.is_admin(call.from_user.id):
        return True

    bot.answer_callback_query(
        call.id,
        "⛔ Bạn không có quyền sử dụng chức năng này.",
        show_alert=True,
    )
    utils.log("WARN", f"Từ chối admin callback từ chat_id={call.from_user.id}")
    return False


def _edit_panel(bot, call, text: str, markup) -> None:
    try:
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=markup,
        )
    except Exception as exc:
        utils.log("WARN", f"Không thể edit admin panel: {exc}")
        bot.send_message(
            call.message.chat.id,
            text,
            parse_mode="HTML",
            reply_markup=markup,
        )


def _home_text() -> str:
    return (
        "🛠️ <b>ADMIN PANEL</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Chọn nhóm chức năng cần sử dụng."
    )


def _home_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📊 Tổng quan hệ thống", callback_data="admin:overview"),
        types.InlineKeyboardButton("📨 Gửi thông báo", callback_data="admin:broadcast"),
        types.InlineKeyboardButton("🧹 Bảo trì dữ liệu", callback_data="admin:retention"),
        types.InlineKeyboardButton("⚙️ Tác vụ hệ thống", callback_data="admin:tasks"),
        types.InlineKeyboardButton("❌ Đóng", callback_data="admin:close"),
    )
    return markup


def _retention_text() -> str:
    return "🧹 <b>BẢO TRÌ DỮ LIỆU</b>\n━━━━━━━━━━━━━━━━━━\nChọn tác vụ retention cần chạy."


def _retention_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📨 Yêu cầu tất cả user xác nhận", callback_data="admin:retention:all"),
        types.InlineKeyboardButton("🗑️ Chạy cleanup quá hạn ngay", callback_data="admin:retention:cleanup"),
        types.InlineKeyboardButton("📊 Thống kê retention", callback_data="admin:retention:stats"),
        types.InlineKeyboardButton("⬅️ Quay lại", callback_data="admin:home"),
    )
    return markup


def _tasks_text() -> str:
    return "⚙️ <b>TÁC VỤ HỆ THỐNG</b>\n━━━━━━━━━━━━━━━━━━\nCác tác vụ sẽ chạy qua Celery worker."


def _tasks_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🌦️ Cập nhật thời tiết ngay", callback_data="admin:tasks:weather"),
        types.InlineKeyboardButton("📅 Quét Portal toàn hệ thống", callback_data="admin:tasks:portal"),
        types.InlineKeyboardButton("📚 Quét deadline toàn hệ thống", callback_data="admin:tasks:deadline"),
        types.InlineKeyboardButton("🧹 Chạy retention maintenance", callback_data="admin:tasks:retention"),
        types.InlineKeyboardButton("⬅️ Quay lại", callback_data="admin:home"),
    )
    return markup


def _broadcast_preview_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🧪 Gửi thử cho admin", callback_data="admin:broadcast:test"),
        types.InlineKeyboardButton("✅ Gửi toàn bộ user", callback_data="admin:broadcast:confirm"),
        types.InlineKeyboardButton("❌ Hủy", callback_data="admin:broadcast:cancel"),
    )
    return markup


def _retention_all_confirm_text() -> str:
    return (
        "⚠️ <b>XÁC NHẬN GỬI HÀNG LOẠT</b>\n\n"
        "Hệ thống sẽ yêu cầu toàn bộ user chưa có yêu cầu đang chờ xác nhận tiếp tục sử dụng.\n\n"
        "User không phản hồi trong 48 giờ sẽ bị xóa."
    )


def _retention_all_confirm_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("✅ Gửi cho tất cả", callback_data="admin:retention:all:go"),
        types.InlineKeyboardButton("❌ Hủy", callback_data="admin:retention"),
    )
    return markup


def _retention_cleanup_confirm_text() -> str:
    return (
        "⚠️ <b>XÁC NHẬN CLEANUP RETENTION</b>\n\n"
        "Job sẽ xử lý toàn bộ yêu cầu đã quá 48 giờ. User không thể liên hệ có thể bị xóa ngay."
    )


def _retention_cleanup_confirm_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("✅ Chạy cleanup", callback_data="admin:retention:cleanup:go"),
        types.InlineKeyboardButton("❌ Hủy", callback_data="admin:retention"),
    )
    return markup


def _back_home_markup(refresh_callback: str | None = None):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if refresh_callback:
        markup.add(types.InlineKeyboardButton("🔄 Làm mới", callback_data=refresh_callback))
    markup.add(types.InlineKeyboardButton("⬅️ Quay lại", callback_data="admin:home"))
    return markup


def _back_retention_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("⬅️ Quay lại", callback_data="admin:retention"))
    return markup


def _back_tasks_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("⬅️ Quay lại", callback_data="admin:tasks"))
    return markup
