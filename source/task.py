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
from telebot import types
import urllib.parse

# Khởi tạo Bot để gửi tin nhắn
bot = TeleBot(os.getenv("TELE_TOKEN"))
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

def sendWorkerCheckIn(_self, _chatId):
    workerName = _self.request.hostname

    try:
        bot.send_message(_chatId, f"🤖 <b>[{workerName}]</b> Đã tiếp nhận lệnh của bạn. Đang xử lý... ⏳", parse_mode="HTML")
        log("INFO", f"Đang xử lí lệnh cho user: {_chatId}")
    except Exception as e:
        log("ERROR", f"Không thể gửi báo danh: {e}")

# ==========================================
# 1. TASK ƯU TIÊN CAO (Dành cho User gọi lệnh)
# ==========================================

@app.task(bind=True, name='tasks.portalTask', queue='high_priority')
def portalTask(self, chatId, dateStr):
    sendWorkerCheckIn(self, chatId)
    try:
        msg = portalService.formatCalendarMessage(chatId, dateStr)
        if msg:
            bot.send_message(chatId, msg, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        log("ERROR", f"Lỗi Portal Task cho {chatId}: {e}")

@app.task(bind=True, name='tasks.deadlineTask', queue='high_priority')
def deadlineTask(self, chatId):
    sendWorkerCheckIn(self, chatId)
    try:
        courseService.scanAllMoodleDeadlines(bot, chatId, isManual=True)
    except Exception as e:
        log("ERROR", f"Lỗi Deadline Task cho {chatId}: {e}")

@app.task(bind=True, name='tasks.registrationTask')
def registrationTask(self, chatId, mssv, password):
    sendWorkerCheckIn(self, chatId)
    success, resultMsg = portalService.verifyAndSaveUser(chatId, mssv, password)
    if success:
        resultMsg += "\n\n✅ Tuyệt vời! Bạn đã đăng ký thành công. Bây giờ bạn có thể xem lịch và deadline rồi đó."
    bot.send_message(chatId, resultMsg, parse_mode="HTML")

@app.task(bind=True, name='tasks.systemStatusTask')
def systemStatusTask(self, chatId, msgWaitId):
    sendWorkerCheckIn(self, chatId)
    teleFunc.getSystemStatus(bot, chatId, msgWaitId)

@app.task(bind=True, name='tasks.feedbackTask')
def feedbackTask(self, chatId, text, adminId):
    import teleFunc
    teleFunc.handleSendFeedback(bot, text, chatId, adminId)

@app.task(bind=True, name='tasks.customDeadlineTask', queue='high_priority')
def customDeadlineTask(self, chatId, startDateStr, numDays):
    sendWorkerCheckIn(self, chatId)
    startDate = datetime.strptime(startDateStr, "%d/%m/%Y")
    courseService.scanAllMoodleDeadlines(bot, chatId, isManual=True, startDate=startDate, numDays=numDays)

@app.task(bind=True, name="tasks.portalWeekTask", queue='high_priority')
def portalWeekTask(self, chatId, startDateStr):
    sendWorkerCheckIn(self, chatId)
    try:
        msg = portalService.format_week_calendar_message(chatId, startDateStr)
        
        bot.send_message(chatId, msg, parse_mode="HTML", disable_web_page_preview=True)
        
    except Exception as e:
        utils.log("ERROR", f"Lỗi trong portalWeekTask: {e}")

@app.task(bind=True, name='tasks.donateTask', queue='high_priority')
def donateTask(self, chatId, username, amount):
    sendWorkerCheckIn(self, chatId)
    
    if not payosService.payos:
        bot.send_message(chatId, "❌ Chức năng Donate hiện đang tạm khóa do hệ thống chưa cấu hình PayOS. Bạn quay lại sau nhé!")
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
            checkPaymentTask.delay(chatId, username, order_code)
        except Exception as e:
            log("ERROR", f"Lỗi gửi photo QR cho {chatId}: {e}")
            bot.send_message(chatId, msg, reply_markup=markup, parse_mode="HTML")
    else:
        bot.send_message(chatId, "❌ Hệ thống tạo mã QR đang bận, bạn thử lại sau nhé.")

# ==========================================
# 2. TASK ƯU TIÊN THẤP (Dành cho Quét định kỳ)
# ==========================================

@app.task(
    bind=True,
    name='tasks.periodicCourseTask', 
    queue='low_priority', 
    rate_limit='1/s', # Khống chế 1 giây chỉ quét 1 ông để né IP trường
    autoretry_for=(Exception,), 
    retry_kwargs={'max_retries': 3, 'countdown': 60} # Lỗi thì thử lại sau 60s
)
def periodicCourseTask(self, chatId):
    sendWorkerCheckIn(self, chatId)

    log("WORKER", f"Đang quét deadline cho user: {chatId}")
    courseService.scanAllMoodleDeadlines(bot, chatId, isManual=False)


@app.task(
    bind=True,
    name='tasks.periodicPortalTask', 
    queue='low_priority', 
    rate_limit='1/s'
)
def periodicPortalTask(self, chatId, dateStr):
    sendWorkerCheckIn(self, chatId)

    log("WORKER", f"Đang quét lịch cho user: {chatId}")
    msg = portalService.formatCalendarMessage(chatId, dateStr, isAuto=True)
    if msg:
        bot.send_message(chatId, msg, parse_mode="HTML", disable_web_page_preview=True)

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