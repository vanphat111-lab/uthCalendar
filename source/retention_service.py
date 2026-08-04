# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# retention_service.py

import time

from telebot import types
from telebot.apihelper import ApiTelegramException

import database as db
import redisManager
from utils import log


RETENTION_MODES = {"due", "all"}

RETENTION_MESSAGE = (
    "🧹 <b>XÁC NHẬN TIẾP TỤC SỬ DỤNG</b>\n\n"
    "Bạn còn sử dụng Bot nhắc lịch UTH không?\n\n"
    "Để bảo vệ thông tin tài khoản và dọn dẹp dữ liệu không còn "
    "sử dụng, hệ thống sẽ xóa tài khoản đã lưu nếu không nhận được "
    "phản hồi trong vòng <b>48 giờ</b>.\n\n"
    "Sau khi bị xóa, bạn vẫn có thể đăng ký lại bất cứ lúc nào."
)

RETENTION_CONFIRMED_MESSAGE = (
    "✅ <b>ĐÃ XÁC NHẬN</b>\n\n"
    "Cảm ơn bạn! Tài khoản sẽ tiếp tục được duy trì và các chức năng thông báo vẫn hoạt động bình thường.\n\n"
    "Hệ thống sẽ hỏi lại sau khoảng 1 tháng."
)

RETENTION_DELETED_MESSAGE = (
    "🗑️ <b>DỮ LIỆU ĐÃ ĐƯỢC XÓA</b>\n\n"
    "Thông tin đăng nhập, thiết lập thông báo và dữ liệu liên quan của bạn đã được xóa khỏi hệ thống.\n\n"
    "Bạn có thể dùng /login để đăng ký lại bất cứ lúc nào."
)

RETENTION_EXPIRED_MESSAGE = (
    "🗑️ <b>TÀI KHOẢN ĐÃ HẾT THỜI GIAN XÁC NHẬN</b>\n\n"
    "Hệ thống không nhận được phản hồi của bạn trong vòng 48 giờ.\n\n"
    "Thông tin đăng nhập, thiết lập thông báo và dữ liệu liên quan sẽ được xóa ngay sau thông báo này để bảo vệ dữ liệu của bạn.\n\n"
    "Bạn vẫn có thể dùng /login để đăng ký lại bất cứ lúc nào."
)


def _build_retention_markup(requested_at):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("✅ Tôi vẫn sử dụng", callback_data=f"retention_keep_{requested_at}"),
        types.InlineKeyboardButton("🗑️ Xóa dữ liệu của tôi", callback_data=f"retention_delete_{requested_at}"),
    )
    return markup


def _is_telegram_user_unreachable(exc):
    if not isinstance(exc, ApiTelegramException):
        return False

    description = str(getattr(exc, "description", exc)).lower()
    error_code = getattr(exc, "error_code", None)

    unreachable_markers = (
        "bot was blocked by the user",
        "user is deactivated",
        "chat not found",
        "user not found",
        "bot can't initiate conversation with a user",
    )

    return error_code in {400, 403} and any(
        marker in description for marker in unreachable_markers
    )


def delete_user_data(chat_id, reason):
    """Delete PostgreSQL first, then clear best-effort Redis cache."""
    deleted = db.delete_user_completely(chat_id, reason)
    if not deleted:
        return False

    redisManager.delete_all_user_data(chat_id)
    log("RETENTION", f"Đã xóa user {chat_id}; reason={reason}")
    return True


def send_retention_requests(bot, mode="due", requested_by=None):
    if mode not in RETENTION_MODES:
        raise ValueError(f"Retention mode không hợp lệ: {mode}")

    if mode == "due":
        user_ids = db.get_users_due_for_retention_check()
    else:
        user_ids = db.get_all_users_without_pending_retention()

    report = {
        "selected": len(user_ids),
        "sent": 0,
        "unreachable": 0,
        "temporary_errors": 0,
        "deleted": 0,
    }

    for chat_id in user_ids:
        requested_at = int(time.time())
        markup = _build_retention_markup(requested_at)

        try:
            bot.send_message(chat_id, RETENTION_MESSAGE, parse_mode="HTML", reply_markup=markup)

            if db.mark_retention_requested(chat_id, requested_at):
                report["sent"] += 1
            else:
                log("WARN", f"Đã gửi retention nhưng không đánh dấu được user {chat_id}")
                report["temporary_errors"] += 1

        except Exception as exc:
            if _is_telegram_user_unreachable(exc):
                report["unreachable"] += 1
                if delete_user_data(chat_id, "telegram_unreachable"):
                    report["deleted"] += 1
            else:
                report["temporary_errors"] += 1
                log("WARN", f"Lỗi tạm thời khi gửi retention cho {chat_id}: {exc}")

        time.sleep(0.3)

    if requested_by is not None:
        _send_admin_report(bot, requested_by, report)

    return report


def cleanup_expired_users(bot):
    user_ids = db.get_expired_retention_requests()
    report = {
        "expired": len(user_ids),
        "notified": 0,
        "unreachable": 0,
        "temporary_errors": 0,
        "deleted": 0,
    }

    for chat_id in user_ids:
        reason = "retention_timeout"

        try:
            bot.send_message(chat_id, RETENTION_EXPIRED_MESSAGE, parse_mode="HTML")
            report["notified"] += 1

        except Exception as exc:
            if _is_telegram_user_unreachable(exc):
                reason = "telegram_unreachable"
                report["unreachable"] += 1
            else:
                report["temporary_errors"] += 1
                log("WARN", f"Lỗi tạm thời khi báo retention hết hạn cho {chat_id}: {exc}")
                continue

        if delete_user_data(chat_id, reason):
            report["deleted"] += 1

        time.sleep(0.3)

    return report


def run_maintenance(bot):
    request_report = send_retention_requests(bot, mode="due")
    cleanup_report = cleanup_expired_users(bot)
    return {
        "requests": request_report,
        "cleanup": cleanup_report,
    }


def confirm_retention(bot, call):
    chat_id = call.message.chat.id
    requested_at = _parse_callback_timestamp(call.data)

    if requested_at is None:
        bot.answer_callback_query(call.id, "❌ Dữ liệu xác nhận không hợp lệ.")
        return False

    if not db.confirm_user_retention(chat_id, requested_at):
        bot.answer_callback_query(call.id, "⚠️ Yêu cầu này đã hết hạn hoặc đã được xử lý.", show_alert=True)
        return False

    bot.edit_message_text(
        RETENTION_CONFIRMED_MESSAGE,
        chat_id,
        call.message.message_id,
        parse_mode="HTML",
        reply_markup=None,
    )
    bot.answer_callback_query(call.id, "✅ Đã duy trì tài khoản của bạn.")
    return True


def delete_user_by_request(bot, call):
    chat_id = call.message.chat.id
    requested_at = _parse_callback_timestamp(call.data)

    if requested_at is None or not db.has_pending_retention_request(chat_id, requested_at):
        bot.answer_callback_query(call.id, "⚠️ Yêu cầu này đã hết hạn hoặc đã được xử lý.", show_alert=True)
        return False

    if not delete_user_data(chat_id, "user_requested"):
        bot.answer_callback_query(call.id, "❌ Không thể xóa dữ liệu lúc này. Vui lòng thử lại.", show_alert=True)
        return False

    bot.edit_message_text(
        RETENTION_DELETED_MESSAGE,
        chat_id,
        call.message.message_id,
        parse_mode="HTML",
        reply_markup=None,
    )
    bot.answer_callback_query(call.id, "🗑️ Dữ liệu đã được xóa.")
    return True


def _parse_callback_timestamp(callback_data):
    try:
        return int(callback_data.rsplit("_", maxsplit=1)[1])
    except (IndexError, TypeError, ValueError):
        return None


def _send_admin_report(bot, admin_id, report):
    message = (
        "✅ <b>HOÀN TẤT GỬI YÊU CẦU XÁC NHẬN</b>\n\n"
        f"👥 Tổng user đủ điều kiện: <b>{report['selected']}</b>\n"
        f"📨 Gửi thành công: <b>{report['sent']}</b>\n"
        f"🚫 Không thể liên hệ: <b>{report['unreachable']}</b>\n"
        f"⚠️ Lỗi tạm thời: <b>{report['temporary_errors']}</b>\n"
        f"🗑️ Đã xóa ngay: <b>{report['deleted']}</b>"
    )

    try:
        bot.send_message(admin_id, message, parse_mode="HTML")
    except Exception as exc:
        log("ERROR", f"Không thể gửi báo cáo retention cho admin: {exc}")
