# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# tasks.py

import os
from datetime import datetime
from celeryApp import app
from telebot import TeleBot
import courseService
import portalService
from utils import log
import teleFunc
import json
import redisManager
import utils
import payosService
import retention_service
import database as db
from telebot import types
from contextlib import contextmanager
from html import escape
import traceback
from celery.exceptions import Retry
# import urllib.parse
# from zoneinfo import ZoneInfo

# Khởi tạo Bot để gửi tin nhắn
bot = TeleBot(os.getenv("TELE_TOKEN"))
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

def editTaskStatus(chatId, messageId, text):
    try:
        bot.edit_message_text(
            text,
            chat_id=chatId,
            message_id=messageId,
            parse_mode="HTML",
        )
    except Exception as exc:
        log("WARN", f"Không thể edit trạng thái {messageId}: {exc}")


def deleteTaskStatus(chatId, messageId):
    try:
        bot.delete_message(chatId, messageId)
    except Exception as exc:
        log("WARN", f"Không thể xóa trạng thái {messageId}: {exc}")


class TaskStatus:
    def __init__(self, taskSelf, chatId, messageId=None):
        self.taskSelf = taskSelf
        self.chatId = chatId
        self.messageId = messageId
        self.failed = False

    def debugText(self):
        worker = escape(str(self.taskSelf.request.hostname or "unknown"))
        taskId = escape(str(self.taskSelf.request.id or "unknown"))
        return (
            f"\n\n🤖 <b>Worker:</b> <code>{worker}</code>"
            f"\n🆔 <b>Task:</b> <code>{taskId}</code>"
        )

    def update(self, text):
        text = f"⏳ <b>{escape(text)}</b>" + self.debugText()

        if self.messageId is not None:
            editTaskStatus(self.chatId, self.messageId, text)
        else:
            try:
                msg = bot.send_message(
                    self.chatId,
                    text,
                    parse_mode="HTML",
                    disable_notification=True,
                )
                self.messageId = msg.message_id
            except Exception as exc:
                log("WARN", f"Không thể gửi báo danh: {exc}")

    def start(self):
        stages = {
            "tasks.portalTask": "Đang lấy lịch học...",
            "tasks.portalWeekTask": "Đang tổng hợp lịch tuần...",
            "tasks.deadlineTask": "Đang quét deadline...",
            "tasks.customDeadlineTask": "Đang quét deadline...",
            "tasks.periodicCourseTask": "Đang quét deadline...",
            "tasks.periodicPortalTask": "Đang kiểm tra lịch học...",
            "tasks.registrationTask": "Đang xác thực tài khoản...",
            "tasks.systemStatusTask": "Đang kiểm tra hệ thống...",
            "tasks.donateTask": "Đang tạo mã thanh toán...",
        }

        self.update(stages.get(self.taskSelf.name, "Đang xử lý..."))

        log(
            "WORKER",
            f"User={self.chatId}, "
            f"worker={self.taskSelf.request.hostname}, "
            f"task={self.taskSelf.request.id}",
        )

    def fail(self, text="❌ Không thể hoàn tất yêu cầu.", html=False):
        self.failed = True
        text = text if html else escape(text)
        text += self.debugText()

        if self.messageId is not None:
            editTaskStatus(self.chatId, self.messageId, text)
        else:
            try:
                msg = bot.send_message(
                    self.chatId,
                    text,
                    parse_mode="HTML",
                )
                self.messageId = msg.message_id
            except Exception as exc:
                log("WARN", f"Không thể gửi trạng thái lỗi: {exc}")


@contextmanager
def workerStatus(taskSelf, chatId, statusMessageId=None, keepResult=False):
    status = TaskStatus(taskSelf, chatId, statusMessageId)
    status.start()

    try:
        yield status
    except Retry:
        raise
    except Exception:
        log(
            "ERROR",
            f"Task={taskSelf.request.id}\n{traceback.format_exc()}",
        )
        status.fail()
        raise
    else:
        if not status.failed and not keepResult and status.messageId is not None:
            deleteTaskStatus(chatId, status.messageId)


def checkDeadlineResults(status, results):
    if isinstance(results, dict):
        if not results or not all(results.values()):
            status.fail("❌ Không thể quét đầy đủ deadline. Bạn kiểm tra các kết quả đã nhận nhé.")
    elif results is False:
        status.fail("❌ Không thể hoàn tất quét deadline.")

# ==========================================
# 1. TASK ƯU TIÊN CAO (Dành cho User gọi lệnh)
# ==========================================

@app.task(bind=True, name='tasks.portalTask', queue='high_priority')
def portalTask(self, chatId, dateStr, statusMessageId=None):
    with workerStatus(self, chatId, statusMessageId) as status:
        msg = portalService.formatCalendarMessage(chatId, dateStr)

        if not msg:
            status.fail("❌ Không nhận được kết quả lịch.")
            return

        bot.send_message(chatId, msg, parse_mode="HTML", disable_web_page_preview=True)

@app.task(bind=True, name='tasks.deadlineTask', queue='high_priority')
def deadlineTask(self, chatId, statusMessageId=None):
    with workerStatus(self, chatId, statusMessageId) as status:
        results = courseService.scanAllMoodleDeadlines(bot, chatId, isManual=True)
        checkDeadlineResults(status, results)

@app.task(bind=True, name='tasks.registrationTask')
def registrationTask(self, chatId, mssv, password, statusMessageId=None):
    with workerStatus(self, chatId, statusMessageId) as status:
        success, resultMsg = portalService.verifyAndSaveUser(chatId, mssv, password)
        if success:
            resultMsg += "\n\n✅ Tuyệt vời! Bạn đã đăng ký thành công. Bây giờ bạn có thể xem lịch và deadline rồi đó."
            bot.send_message(chatId, resultMsg, parse_mode="HTML")
        else:
            status.fail(resultMsg, html=True)

@app.task(bind=True, name='tasks.systemStatusTask')
def systemStatusTask(self, chatId, msgWaitId):
    with workerStatus(self, chatId, msgWaitId, keepResult=True):
        teleFunc.getSystemStatus(bot, chatId, msgWaitId)

@app.task(bind=True, name='tasks.feedbackTask')
def feedbackTask(self, chatId, text, adminId):
    import teleFunc
    teleFunc.handleSendFeedback(bot, text, chatId, adminId)

@app.task(bind=True, name='tasks.customDeadlineTask', queue='high_priority')
def customDeadlineTask(self, chatId, startDateStr, numDays, statusMessageId=None):
    with workerStatus(self, chatId, statusMessageId) as status:
        startDate = datetime.strptime(startDateStr, "%d/%m/%Y")
        results = courseService.scanAllMoodleDeadlines(bot, chatId, isManual=True, startDate=startDate, numDays=numDays)
        checkDeadlineResults(status, results)

@app.task(bind=True, name="tasks.portalWeekTask", queue='high_priority')
def portalWeekTask(self, chatId, startDateStr, statusMessageId=None):
    with workerStatus(self, chatId, statusMessageId) as status:
        msg = portalService.format_week_calendar_message(chatId, startDateStr)

        if not msg:
            status.fail("❌ Không nhận được kết quả lịch tuần.")
            return

        bot.send_message(chatId, msg, parse_mode="HTML", disable_web_page_preview=True)

@app.task(bind=True, name='tasks.donateTask', queue='high_priority')
def donateTask(self, chatId, username, amount, statusMessageId=None):
    with workerStatus(self, chatId, statusMessageId) as status:
        if not payosService.payos:
            status.fail("❌ Chức năng Donate hiện đang tạm khóa do hệ thống chưa cấu hình PayOS. Bạn quay lại sau nhé!")
            return

        checkout_url, qr_image_url, order_code = payosService.create_donate_link(str(chatId), username, amount)

        if checkout_url and qr_image_url:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💳 Mở trang thanh toán Web", url=checkout_url))

            msg = (
                f"💰 <b>THÔNG TIN ỦNG HỘ (DONATE)</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💵 <b>Số tiền:</b> <code>{amount:,} VNĐ</code>\n"
                f"🆔 <b>Mã đơn hàng:</b> <code>{order_code}</code>\n\n"
                f"👉 Quét trực tiếp mã QR ở hình trên bằng ứng dụng ngân hàng; hệ thống sẽ tự động xác nhận sau khi nhận được tiền."
            )

            try:
                bot.send_photo(chatId, qr_image_url, caption=msg, reply_markup=markup, parse_mode="HTML")
            except Exception as e:
                log("ERROR", f"Lỗi gửi photo QR cho {chatId}: {e}")
                bot.send_message(chatId, msg, reply_markup=markup, parse_mode="HTML")

            checkPaymentTask.delay(chatId, username, order_code)
        else:
            status.fail("❌ Hệ thống tạo mã QR đang bận, bạn thử lại sau nhé.")

# ==========================================
# 2. TASK ƯU TIÊN THẤP (Dành cho Quét định kỳ)
# ==========================================

@app.task(
    bind=True,
    name='tasks.periodicCourseTask',
    queue='low_priority',
    rate_limit='1/s', # Khống chế 1 giây chỉ quét 1 ông để né IP trường
    max_retries=3, # Lỗi thì thử lại sau 60s
)
def periodicCourseTask(self, chatId, statusMessageId=None):
    status = None

    try:
        with workerStatus(self, chatId, statusMessageId) as status:
            log("WORKER", f"Đang quét deadline cho user: {chatId}")
            results = courseService.scanAllMoodleDeadlines(bot, chatId, isManual=False)
            checkDeadlineResults(status, results)
    except Exception as e:
        if self.request.retries < self.max_retries:
            if status is not None:
                status.fail("⏳ Xử lý gặp lỗi, sẽ thử lại sau 60 giây.")
                statusMessageId = status.messageId

            raise self.retry(
                exc=e,
                countdown=60,
                args=(chatId,),
                kwargs={"statusMessageId": statusMessageId},
            )
        raise


@app.task(
    bind=True,
    name='tasks.periodicPortalTask',
    queue='low_priority',
    rate_limit='1/s'
)
def periodicPortalTask(self, chatId, dateStr, statusMessageId=None):
    with workerStatus(self, chatId, statusMessageId):
        log("WORKER", f"Đang quét lịch cho user: {chatId}")
        msg = portalService.formatCalendarMessage(chatId, dateStr, isAuto=True)
        if msg:
            markup = None
            targetDate = datetime.strptime(dateStr, "%d/%m/%Y").date()
            today = datetime.now().date()

            if targetDate == today:
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton(
                        "🔕 Không nhắc lại hôm nay",
                        callback_data=f"mute_portal_date_{targetDate.isoformat()}",
                    )
                )

            bot.send_message(chatId, msg, parse_mode="HTML", disable_web_page_preview=True, reply_markup=markup)

@app.task(
    name="tasks.retentionMaintenanceTask",
    queue="low_priority",
)
def retention_maintenance_task():
    log("RETENTION", "Bắt đầu retention maintenance hằng ngày")
    return retention_service.run_maintenance(bot)


@app.task(
    name="tasks.retentionRequestAllTask",
    queue="low_priority",
)
def retention_request_all_task(requested_by):
    if not _ensure_admin_task(requested_by):
        return {"authorized": False}

    log("RETENTION", f"Admin {requested_by} yêu cầu xác nhận toàn bộ user")
    return retention_service.send_retention_requests(
        bot,
        mode="all",
        requested_by=requested_by,
    )


@app.task(
    name='tasks.updateWeatherTask',
    queue='low_priority'
)
def updateWeatherTask():
    if not WEATHER_API_KEY:
        log("WARN", "Bỏ qua chu kỳ cập nhật thời tiết do thiếu cấu hình WEATHER_API_KEY.")
        return

    campuses = {
        "CS1": "10.8023,106.7147",
        "CS2": "10.7934,106.7320",
        "CS3": "10.8524,106.6361"
    }

    for code, coords in campuses.items():
        try:
            url = f"https://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={coords}&days=2&lang=vi"
            response = utils.safeRequest("GET", url, use_proxy=False)

            if response and response.status_code == 200:
                data = response.json()

                forecast_data = []
                for day in data['forecast']['forecastday']:
                    forecast_data.extend(day['hour'])

                redisManager.redisClient.set(f"forecast:{code}", json.dumps(forecast_data), ex=3600)
                log("SUCCESS", f"Đã lưu dự báo 48h cho {code}")
            else:
                log("ERROR", f"Không thể lấy weather cho {code}, Code: {response.status_code if response else 'None'}")

        except Exception as e:
            log("ERROR", f"Lỗi fetch forecast {code}: {e}")

@app.task(bind=True, name='tasks.checkPaymentTask', queue='low_priority')
def checkPaymentTask(self, chatId, username, orderCode):
    if not payosService.payos:
        log("WARN", f"Bỏ qua chu kỳ check đơn hàng {orderCode} do PayOS chưa được cấu hình (None).")
        return

    admin_id = os.getenv("ADMIN_ID")
    max_retries = 90
    current_attempt = self.request.retries + 1

    try:
        payment_info = payosService.payos.getPaymentLinkInformation(orderCode)
        status = payment_info.status

        if status == "PAID":
            amount = payment_info.amount
            user_display = f"@{username}" if username else f"ID {chatId}"

            thank_msg = (
                f"🎉 <b>CẢM ƠN BẠN ĐÃ ỦNG HỘ BOT!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💖 Hệ thống đã xác nhận khoản donate thành công từ bạn.\n"
                f"💵 <b>Số tiền:</b> <code>{amount:,} VNĐ</code>\n\n"
                f"🚀 Sự đóng góp của bạn là nguồn kinh phí quý giá giúp mình duy trì máy chủ và phát triển thêm nhiều tính năng hữu ích cho sinh viên UTH!"
            )
            bot.send_message(chatId, thank_msg, parse_mode="HTML")

            if admin_id:
                admin_msg = (
                    f"💰 <b>TÍN TÍN! CÓ ĐƠN DONATE MỚI</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"👤 <b>Người gửi:</b> {user_display}\n"
                    f"🆔 <b>Mã đơn:</b> <code>{orderCode}</code>\n"
                    f"💵 <b>Số tiền:</b> <code>{amount:,} VNĐ</code>\n"
                    f"🟢 <b>Trạng thái:</b> Thành công"
                )
                bot.send_message(admin_id, admin_msg, parse_mode="HTML")
            return

        elif status in ["CANCELLED", "EXPIRED"]:
            status_text = "đã bị hủy" if status == "CANCELLED" else "đã hết hạn"

            log("INFO",
                f"[{current_attempt}/{max_retries}] "
                f"Đơn hàng {orderCode} {status_text}.")

            bot.send_message(
                chatId, (
                    f"⏰ <b>Không thể tiếp tục thanh toán!</b>\n"
                    f"Mã QR đơn hàng <code>{orderCode}</code> {status_text}.\n"
                    f"Vui lòng tạo mã QR mới nếu bạn vẫn muốn ủng hộ."),
                parse_mode="HTML"
            )
            return

        raise RuntimeWarning("Đơn hàng chưa thanh toán.")

    except Exception as exc:
        if self.request.retries >= max_retries:
            log("WARN", f"[{current_attempt}/{max_retries}] Đơn hàng {orderCode} đã hết thời gian chờ 15 phút. Dừng quét!")
            try:
                bot.send_message(chatId, f"⏰ <b>Hết thời gian thanh toán!</b>\nMã QR đơn hàng <code>{orderCode}</code> của bạn đã hết hạn do quá 15 phút chưa nhận được tiền.", parse_mode="HTML")
            except: pass
            return

        log("INFO", f"[{current_attempt}/{max_retries}] Đang chờ đơn hàng {orderCode} thanh toán... Thử lại sau 10 giây.")
        self.retry(exc=exc, countdown=10, max_retries=max_retries)
# ==========================================
# 3. TASK ADMIN
# ==========================================


def _ensure_admin_task(requested_by):
    import admin_security

    if admin_security.is_admin(requested_by):
        return True

    log("WARN", f"Từ chối admin task từ chat_id không hợp lệ: {requested_by}")
    return False


@app.task(
    name="tasks.adminBroadcastTask",
    queue="low_priority",
)
def admin_broadcast_task(requested_by, content):
    if not _ensure_admin_task(requested_by):
        return {"authorized": False}

    user_ids = db.getAllUserIds()
    report = {
        "selected": len(user_ids),
        "sent": 0,
        "failed": 0,
    }

    for chat_id in user_ids:
        try:
            bot.send_message(
                chat_id,
                f"📢 <b>THÔNG BÁO MỚI</b>\n\n{content}\n\n<i>Chúc bạn học tốt!</i>",
                parse_mode="HTML",
            )
            report["sent"] += 1
        except Exception as exc:
            report["failed"] += 1
            log("WARN", f"Không thể gửi broadcast cho user {chat_id}: {exc}")

        import time
        time.sleep(0.3)

    bot.send_message(
        requested_by,
        (
            "✅ <b>HOÀN TẤT BROADCAST</b>\n\n"
            f"👥 Tổng user: {report['selected']}\n"
            f"📨 Gửi thành công: {report['sent']}\n"
            f"⚠️ Gửi thất bại: {report['failed']}"
        ),
        parse_mode="HTML",
    )
    return report


@app.task(
    name="tasks.adminRetentionCleanupTask",
    queue="low_priority",
)
def admin_retention_cleanup_task(requested_by):
    if not _ensure_admin_task(requested_by):
        return {"authorized": False}

    report = retention_service.cleanup_expired_users(bot)
    bot.send_message(
        requested_by,
        (
            "✅ <b>HOÀN TẤT CLEANUP RETENTION</b>\n\n"
            f"⌛ Đã quá hạn: {report['expired']}\n"
            f"📨 Đã báo trước khi xóa: {report['notified']}\n"
            f"🚫 Không thể liên hệ: {report['unreachable']}\n"
            f"⚠️ Lỗi tạm thời: {report['temporary_errors']}\n"
            f"🗑️ Đã xóa: {report['deleted']}"
        ),
        parse_mode="HTML",
    )
    return report


@app.task(
    name="tasks.adminRetentionMaintenanceTask",
    queue="low_priority",
)
def admin_retention_maintenance_task(requested_by):
    if not _ensure_admin_task(requested_by):
        return {"authorized": False}

    report = retention_service.run_maintenance(bot)
    request_report = report["requests"]
    cleanup_report = report["cleanup"]
    bot.send_message(
        requested_by,
        (
            "✅ <b>HOÀN TẤT RETENTION MAINTENANCE</b>\n\n"
            f"📨 Yêu cầu mới đã gửi: {request_report['sent']}\n"
            f"🚫 User không thể liên hệ: {request_report['unreachable']}\n"
            f"🗑️ User đã xóa lúc gửi yêu cầu: {request_report['deleted']}\n\n"
            f"⌛ Yêu cầu quá hạn: {cleanup_report['expired']}\n"
            f"🗑️ User đã xóa khi cleanup: {cleanup_report['deleted']}\n"
            f"⚠️ Lỗi tạm thời: {request_report['temporary_errors'] + cleanup_report['temporary_errors']}"
        ),
        parse_mode="HTML",
    )
    return report


@app.task(
    name="tasks.adminPortalScanTask",
    queue="low_priority",
)
def admin_portal_scan_task(requested_by):
    if not _ensure_admin_task(requested_by):
        return {"authorized": False}

    import cronService

    cronService.autoCheckAndNotify(bot)
    bot.send_message(
        requested_by,
        "✅ Đã đẩy toàn bộ tác vụ quét Portal vào hàng đợi.",
    )
    return {"authorized": True}


@app.task(
    name="tasks.adminDeadlineScanTask",
    queue="low_priority",
)
def admin_deadline_scan_task(requested_by):
    if not _ensure_admin_task(requested_by):
        return {"authorized": False}

    import cronService

    cronService.autoScanAllUsers(bot)
    bot.send_message(
        requested_by,
        "✅ Đã đẩy toàn bộ tác vụ quét deadline vào hàng đợi.",
    )
    return {"authorized": True}


@app.task(
    name="tasks.adminUpdateWeatherTask",
    queue="low_priority",
)
def admin_update_weather_task(requested_by):
    if not _ensure_admin_task(requested_by):
        return {"authorized": False}

    result = updateWeatherTask.run()
    bot.send_message(requested_by, "✅ Đã hoàn tất cập nhật dữ liệu thời tiết.")
    return result