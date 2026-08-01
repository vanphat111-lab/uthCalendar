# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# teleFunc.py

import database as db
import portalService
import utils
import time
import redisManager
import courseService

def getSystemStatus(bot, chatId, msgWaitId):
    u = db.getUserCredentials(chatId)
    if not u:
        bot.edit_message_text("❌ Bạn chưa đăng ký tài khoản.", chatId, msgWaitId)
        return

    try:
        # --- 1. ĐO PING TELEGRAM (NETWORK LATENCY) ---
        start_tg = time.time()
        bot.get_me() # Gọi nhẹ tới Telegram API
        tg_lat = round((time.time() - start_tg) * 1000)

        # --- 2. XÁC THỰC TÀI KHOẢN ---
        rawUser = utils.decryptData(u['uth_user'])
        rawPass = utils.decryptData(u['uth_pass'])

        # Check Portal & Moodle
        start_pt = time.time()
        portal_ok, portal_msg = portalService.verifyUthCredentials(rawUser, rawPass)
        pt_lat = round((time.time() - start_pt) * 1000)
        md_session, md_sesskey = courseService.fetchMoodleSession(rawUser, rawPass)
        moodle_ok = True if md_sesskey else False

        # --- 3. KIỂM TRA HẠ TẦNG & ĐỘ TRỄ ---
        # Database
        db_healthy, db_lat = db.checkDbHealth()
        db_ok = "🟢" if db_healthy else "🔴"

        # Redis
        start_rd = time.time()
        rd_ok = "🟢" if redisManager.redisClient.ping() else "🔴"
        rd_lat = round((time.time() - start_rd) * 1000)

        # --- 4. FORMAT DASHBOARD ---
        status_msg = (
            f"📊 <b>HỆ THỐNG MONITORING</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔐 <b>XÁC THỰC TÀI KHOẢN:</b>\n"
            f"  ├ Portal UTH: {'✅ Hợp lệ' if portal_ok else f'❌ Sai Pass ({portal_msg})'}\n"
            f"  └ Courses UTH: {'✅ Hợp lệ' if moodle_ok else '❌ Không thể Login'}\n\n"
            f"⚡ <b>ĐỘ TRỄ MẠNG (PING):</b>\n"
            f"  ├ Telegram API: <code>{tg_lat}ms</code>\n"
            f"  ├ Portal Server: <code>{pt_lat if portal_ok else 'ERR'}ms</code>\n"
            f"  ├ Database Local: <code>{db_lat}ms</code>\n"
            f"  └ Redis Local: <code>{rd_lat}ms</code>\n\n"
            f"🏗️ <b>HẠ TẦNG (SERVER):</b>\n"
            f"  ├ PostgreSQL: {db_ok}\n"
            f"  └ Redis Cache: {rd_ok}\n\n"
            f"📢 <b>THÔNG BÁO:</b>\n"
            f"  ├ Nhắc lịch: {'🔔 Bật' if u['notify_enabled'] else '🔕 Tắt'}\n"
            f"  └ Deadline: {'🔔 Bật' if u['notify_deadline'] else '🔕 Tắt'}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <i>Cập nhật: {time.strftime('%H:%M:%S')}</i>"
        )

        bot.edit_message_text(status_msg, chatId, msgWaitId, parse_mode="HTML")

    except Exception as e:
        utils.log("ERROR", f"Lỗi Dashboard: {e}")
        bot.edit_message_text("⚠️ Có chút trục trặc", chatId, msgWaitId)

def broadcastToAllUsers(bot, content):
    userList = db.getAllUserIds()

    if not userList:
        return 0

    count = 0

    for chatId in userList:
        try:
            bot.send_message(chatId, f"📢 <b>THÔNG BÁO MỚI</b>\n\n{content}\n\n<i>Chúc bạn học tốt!</i>", parse_mode="HTML")
            count += 1
            time.sleep(0.3)

        except Exception as e:
            utils.log("WARN", f"Không thể gửi broadcast cho user {chatId}: {e}")

    return count

def handleToggleNotify(chatId):
    u = db.getUserCredentials(chatId)
    if not u:
        return None, "❌ Bạn chưa đăng ký tài khoản."

    newStatus = not u['notify_enabled']

    if not db.updateNotifyStatus(chatId, newStatus):
        return None, "❌ Không thể cập nhật trạng thái thông báo. Vui lòng thử lại."

    return newStatus, f"✅ Đã <b>{'BẬT' if newStatus else 'TẮT'}</b> nhắc lịch tự động!"

def handleToggleDeadlineNotify(chatId):
    u = db.getUserCredentials(chatId)
    if not u:
        return None, "❌ Bạn chưa đăng ký tài khoản."

    newStatus = not u['notify_deadline']

    if not db.updateDeadlineStatus(chatId, newStatus):
        return None, "❌ Không thể cập nhật trạng thái deadline. Vui lòng thử lại."

    return newStatus, f"✅ Đã <b>{'BẬT' if newStatus else 'TẮT'}</b> thông báo deadline hằng tuần!"

def getAdminStats(adminId):
    try:
        utils.log("ADMIN", f"Admin {adminId} đang xem thống kê")

        count = db.countUsers()

        return f"👥 Tổng số người dùng: {count}"

    except Exception as e:
        utils.log("ERROR", f"Lỗi lấy thống kê hệ thống: {e}")
        return "⚠️ Không thể lấy thống kê."


def handleSendFeedback(bot, message, adminId):
    if not message.text or len(message.text) < 5:
        bot.send_message(message.chat.id, "⚠️ Nội dung góp ý hơi ngắn, bạn vui lòng mô tả chi tiết hơn một chút để mình hỗ trợ nhé.")
        return False

    user = message.from_user
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Người dùng"
    username_display = f" (@{user.username})" if user.username else ""
    user_link = f"tg://user?id={user.id}" # Link nhấn vào là mở Profile

    bot.send_message(message.chat.id, "✅ Cảm ơn bạn rất nhiều! Góp ý của bạn đã được mình gửi đến Admin rồi nha.")

    if adminId:
        feedback_msg = (
            "📩 <b>CÓ GÓP Ý/BÁO LỖI MỚI!</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Người gửi:</b> <a href='{user_link}'>{full_name}</a>{username_display}\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
            f"📝 <b>Nội dung:</b>\n<i>{message.text}</i>\n"
            "━━━━━━━━━━━━━━━━━━\n"
        )
        bot.send_message(adminId, feedback_msg, parse_mode="HTML")
    return True