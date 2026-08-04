# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# teleBot.py

import os

from telebot import types
# import portalService
import payosService
import utils
import teleFunc
# import courseService
from datetime import datetime, timedelta
import database as db
import cronService
import task
import rate_limit
import retention_service

adminId = utils.os.getenv("ADMIN_ID")

def mainMenu(chatId):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("🏛️ Portal Menu", "📚 Course Menu") 
    markup.add("🔑 Đăng ký", "📩 Góp ý/Báo lỗi")

    if payosService.payos:
        markup.add("🛠️ Kiểm tra hệ thống", "💰 Donate")
    else:
        markup.add("🛠️ Kiểm tra hệ thống")

    if str(chatId) == str(adminId):
        btn_admin = types.KeyboardButton("⚙️ Admin Panel")
        markup.add(btn_admin)
    return markup

def portalSubMenu():
    markup = types.ReplyKeyboardMarkup(row_width=3, resize_keyboard=True)
    markup.add("🔔 Bật tắt thông báo lịch")
    markup.add("📅 Lịch hôm nay", "⏭️ Lịch ngày mai", "📆 Lịch ngày tùy chọn")
    markup.add("📅 Lịch cả tuần", "🗓️ Lịch tuần sau")
    markup.add("🏠 Quay lại menu chính")
    return markup

def courseSubMenu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("📢 Bật tắt thông báo hằng tuần")
    markup.add("📑 Quét deadline", "🔍 Quét tùy chỉnh")
    markup.add("🏠 Quay lại menu chính")
    return markup

def adminSubMenu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🔄 Test Quét Lịch (Portal)", callback_data="test_cron_portal"),
        types.InlineKeyboardButton("📅 Test Quét Deadline (Course)", callback_data="test_cron_deadline"),
        types.InlineKeyboardButton("📨 Yêu cầu tất cả user xác nhận", callback_data="retention_admin_all"),
        types.InlineKeyboardButton("📊 Thống kê DB", callback_data="admin_db_stats")
    )
    return markup

def setBotCommands(bot):
    try:
        commands = [
            types.BotCommand("start", "🏠 Menu chính"),
            types.BotCommand("login", "🔑 Đăng ký tài khoản"),
            types.BotCommand("feedback", "📩 Góp ý/Báo lỗi"),
            types.BotCommand("help", "❓ Hướng dẫn sử dụng")
        ]
        bot.set_my_commands(commands)
    except: pass

def registerHandlers(bot):
    # Rate limit handler
    limit = rate_limit.ratelimit_handler(bot)
    
    @bot.message_handler(commands=['start', 'help'])
    @limit
    def welcome(message):
        welcomeText = (
            "👋 <b>Chào bạn! Mình là Bot nhắc lịch UTH.</b>\n\n"
            "Mình sẽ đồng hành cùng bạn trong việc theo dõi lịch học Portal và các deadline từ hệ thống Courses một cách tự động.\n\n"
            "📢 <b>Tham gia nhóm hỗ trợ và nhận cập nhật mới nhất tại:</b>\n"
            "👉 https://t.me/uth_notifier_group\n\n"
            "Bạn hãy chọn các chức năng ở menu bên dưới để bắt đầu trải nghiệm nhé! 😊"
        )
        bot.send_message(message.chat.id, welcomeText, parse_mode="HTML", reply_markup=mainMenu(message.chat.id))

    @bot.message_handler(commands=['broadcast'])
    @limit
    def handleAdminBroadcast(message):
        if str(message.chat.id) != adminId: return
        rawInput = message.text.split(maxsplit=1)
        if len(rawInput) < 2:
            bot.reply_to(message, "Vui lòng nhập nội dung: <code>/broadcast Nội dung</code>", parse_mode="HTML")
            return
        bot.send_message(message.chat.id, "⏳ Đang gửi thông báo đến mọi người...")
        total = teleFunc.broadcastToAllUsers(bot, rawInput[1])
        bot.send_message(message.chat.id, f"✅ Đã gửi thông báo thành công cho {total} người dùng.")

    @bot.message_handler(func=lambda m: m.text == "🏛️ Portal Menu")
    def openPortal(message):
        bot.send_message(message.chat.id, "🏛️ <b>HỆ THỐNG PORTAL</b>", parse_mode="HTML", reply_markup=portalSubMenu())

    @bot.message_handler(func=lambda m: m.text == "📚 Course Menu")
    def openCourse(message):
        bot.send_message(message.chat.id, "📚 <b>HỆ THỐNG COURSES</b>", parse_mode="HTML", reply_markup=courseSubMenu())

    @bot.message_handler(func=lambda m: m.text == "🏠 Quay lại menu chính")
    def backToMain(message):
        bot.send_message(message.chat.id, "🏠 Đã quay lại Menu chính.", reply_markup=mainMenu(message.chat.id))

    @bot.message_handler(func=lambda m: m.text == "📅 Lịch hôm nay")
    @limit
    def handleToday(message):
        bot.send_message(message.chat.id, "⏳ Đang điều phối Worker để quét lịch cho bạn...")
        today = datetime.now().strftime("%d/%m/%Y")
        task.portalTask.delay(message.chat.id, today)

    @bot.message_handler(func=lambda m: m.text == "⏭️ Lịch ngày mai")
    @limit
    def handleTomorrow(message):
        bot.send_message(message.chat.id, "⏳ Đang điều phối Worker để quét lịch ngày mai cho bạn...")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
        task.portalTask.delay(message.chat.id, tomorrow)

    @bot.message_handler(func=lambda m: m.text == "📆 Lịch ngày tùy chọn")
    @limit
    def handleCustomDateRequest(message):
        msg = bot.send_message(message.chat.id, "📅 Bạn vui lòng nhập ngày muốn xem (Định dạng: <code>DD/MM/YYYY</code>):", parse_mode="HTML")
        utils.startStepTimeout(bot, message.chat.id) 
        bot.register_next_step_handler(msg, processCustomDate, bot)

    @bot.message_handler(func=lambda m: m.text == "🔔 Bật tắt thông báo lịch")
    @limit
    def handleTogglePortal(message):
        _, resMsg = teleFunc.handleToggleNotify(message.chat.id)
        bot.send_message(message.chat.id, resMsg, parse_mode="HTML")

    @bot.message_handler(func=lambda m: m.text == "📅 Lịch cả tuần")
    @limit
    def handleWeekSchedule(message):
        chatId = message.chat.id
        bot.send_message(chatId, "⏳ Đang tổng hợp lịch tuần này cho bạn...")
        
        today = datetime.now().strftime("%d/%m/%Y")
        task.portalWeekTask.delay(chatId, today)

    @bot.message_handler(func=lambda m: m.text == "🗓️ Lịch tuần sau")
    @limit
    def handleNextWeek(message):
        chatId = message.chat.id
        bot.send_message(chatId, "⏳ Đang tổng hợp lịch tuần sau cho bạn...")
        
        next_week_dt = datetime.now() + timedelta(days=7)
        next_week_str = next_week_dt.strftime("%d/%m/%Y")
        
        task.portalWeekTask.delay(chatId, next_week_str)

    @bot.message_handler(func=lambda m: m.text == "📑 Quét deadline")
    @limit
    def handleDeadlineScan(message):
        bot.send_message(message.chat.id, "🔍 Đang điều phối Worker kiểm tra Deadline giúp bạn...")
        task.deadlineTask.delay(message.chat.id)

    @bot.message_handler(func=lambda message: message.text == "🔍 Quét tùy chỉnh")
    @limit
    def handleCustomScan(message):
        msg = bot.send_message(message.chat.id, "📅 Nhập ngày bắt đầu quét (Định dạng: DD/MM/YYYY\nVD: 01/04/2026):")
        bot.register_next_step_handler(msg, processDateStep, bot)

    @bot.message_handler(func=lambda m: m.text == "📢 Bật tắt thông báo hằng tuần")
    @limit
    def handleToggleCourse(message):
        chatId = message.chat.id
        _, resMsg = teleFunc.handleToggleDeadlineNotify(chatId)
        bot.send_message(chatId, resMsg, parse_mode="HTML")

    @bot.message_handler(commands=['login'])
    @bot.message_handler(func=lambda m: m.text == "🔑 Đăng ký")
    @limit
    def handleRegister(message):
        msg = bot.send_message(message.chat.id, "🔑 <b>Bắt đầu đăng ký:</b>\n\nBạn vui lòng nhập <b>MSSV</b> của mình nhé:", parse_mode="HTML")
        bot.register_next_step_handler(msg, processMssvStep, bot)

    @bot.message_handler(func=lambda m: m.text == "📩 Góp ý/Báo lỗi")
    def handleFeedbackRequest(message):
        msg = bot.send_message(message.chat.id, "😊 Bạn có thể nhập nội dung góp ý tại đây (Bạn có 60 giây để nhập):")
        utils.startStepTimeout(bot, message.chat.id)
        bot.register_next_step_handler(msg, processFeedback, bot)

    @bot.message_handler(func=lambda m: m.text == "🛠️ Kiểm tra hệ thống")
    @limit
    def handleStatus(message):
        msgWait = bot.send_message(message.chat.id, "⏳ Đang điều phối Worker kiểm tra kết nối...")
        task.systemStatusTask.delay(message.chat.id, msgWait.message_id)

    @bot.message_handler(func=lambda m: m.text == "📊 Admin Stats" and str(m.chat.id) == adminId)
    def handleAdminStats(message):
        bot.send_message(message.chat.id, teleFunc.getAdminStats(adminId), parse_mode="HTML")

    @bot.message_handler(func=lambda m: m.text == "💰 Donate")
    @limit
    def handleDonateMenu(message):
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("20k VNĐ", callback_data="donate_20000"),
            types.InlineKeyboardButton("50k VNĐ", callback_data="donate_50000"),
            types.InlineKeyboardButton("100k VNĐ", callback_data="donate_100000"),
            types.InlineKeyboardButton("200k VNĐ", callback_data="donate_200000"),
            types.InlineKeyboardButton("✏️ Số tiền tùy chọn", callback_data="donate_custom")
        )
        bot.send_message(
            message.chat.id, 
            "☕ <b>ỦNG HỘ PHÁT TRIỂN BOT</b>\n\nSự ủng hộ của bạn giúp mình có thêm chi phí duy trì server và phát triển các tính năng mới cho Bot UTH.\nVui lòng chọn số tiền bạn muốn donate dưới đây:", 
            parse_mode="HTML", 
            reply_markup=markup
        )

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith("retention_keep_")
    )
    def handle_retention_keep(call):
        retention_service.confirm_retention(bot, call)

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith("retention_delete_")
    )
    def handle_retention_delete(call):
        retention_service.delete_user_by_request(bot, call)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('done_'))
    def onMarkDone(call):
        handleMarkDone(bot, call)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('undone_'))
    def onMarkUndone(call):
        handleMarkUndone(bot, call)

    @bot.message_handler(func=lambda m: m.text == "⚙️ Admin Panel")
    def handleAdminPanel(message):
        if str(message.chat.id) == str(adminId):
            bot.send_message(message.chat.id, "🛠 **ADMIN CONTROL PANEL**\nMày muốn test lập lịch nào?", 
                            reply_markup=adminSubMenu(), parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda call: call.data == "retention_admin_all")
    def handle_admin_retention_all(call):
        if str(call.from_user.id) != str(adminId):
            bot.answer_callback_query(call.id, "⛔ Bạn không có quyền sử dụng.")
            return

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(
                "✅ Gửi cho tất cả",
                callback_data="retention_admin_all_confirm",
            ),
            types.InlineKeyboardButton(
                "❌ Hủy",
                callback_data="retention_admin_all_cancel",
            ),
        )

        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            (
                "⚠️ <b>XÁC NHẬN GỬI HÀNG LOẠT</b>\n\n"
                "Hệ thống sẽ gửi yêu cầu xác nhận tiếp tục sử dụng tới toàn bộ người dùng chưa có yêu cầu đang chờ.\n\n"
                "Người dùng không phản hồi trong 48 giờ sẽ bị xóa khỏi hệ thống.\n\n"
            ),
            parse_mode="HTML",
            reply_markup=markup,
        )

    @bot.callback_query_handler(
        func=lambda call: call.data in {
            "retention_admin_all_confirm",
            "retention_admin_all_cancel",
        }
    )
    def handle_admin_retention_confirmation(call):
        if str(call.from_user.id) != str(adminId):
            bot.answer_callback_query(call.id, "⛔ Bạn không có quyền sử dụng.")
            return

        if call.data == "retention_admin_all_cancel":
            bot.answer_callback_query(call.id, "Đã hủy.")
            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=None,
            )
            return

        task.retention_request_all_task.delay(call.from_user.id)
        bot.answer_callback_query(call.id, "🚀 Đã đưa yêu cầu vào hàng đợi.")
        bot.edit_message_text(
            "⏳ <b>ĐANG GỬI YÊU CẦU XÁC NHẬN</b>\n\n"
            "Worker sẽ gửi báo cáo cho admin sau khi hoàn tất.",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=None,
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('test_cron_'))
    def handleTestCron(call):
        import threading
        if call.data == "test_cron_portal":
            bot.answer_callback_query(call.id, "🚀 Đang chạy quét lịch...")
            threading.Thread(target=cronService.autoCheckAndNotify, args=(bot,)).start()
        elif call.data == "test_cron_deadline":
            bot.answer_callback_query(call.id, "🚀 Đang chạy quét deadline...")
            threading.Thread(target=cronService.autoScanAllUsers, args=(bot,)).start()

    @bot.callback_query_handler(func=lambda call: call.data.startswith('donate_'))
    def onDonateCallback(call):
        chatId = call.message.chat.id
        action = call.data.split('_')[1]
        
        if action == "custom":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chatId, "💰 Nhập số tiền muốn donate (Ví dụ: 30000):")
            utils.startStepTimeout(bot, chatId)
            bot.register_next_step_handler(msg, processCustomDonateAmount, bot)
        else:
            try:
                amount = int(action)
                bot.answer_callback_query(call.id)
                bot.send_message(chatId, "⏳ Đang điều phối Worker khởi tạo mã VietQR...")
                task.donateTask.delay(chatId, call.from_user.username, amount)
                bot.edit_message_reply_markup(chatId, call.message.message_id, reply_markup=None)
            except Exception as e:
                utils.log("ERROR", f"Lỗi xử lý callback donate: {e}")

    @bot.message_handler(func=lambda m: True)
    @limit
    def handleUnknown(message):
        bot.reply_to(message, "⚠️ Lệnh này mình chưa hiểu, bạn vui lòng sử dụng các nút ở menu nhé!", reply_markup=mainMenu(message.chat.id))

def processMssvStep(message, bot):
    mssv = message.text
    if not mssv or len(mssv) < 5:
        bot.reply_to(message, "Mã số sinh viên có vẻ chưa đúng, bạn vui lòng nhập lại nhé.")
        return
    msg = bot.send_message(message.chat.id, f"✅ Đã nhận MSSV: <code>{mssv}</code>\n\nTiếp theo, bạn hãy nhập <b>Mật khẩu Portal</b> nha:", parse_mode="HTML")
    bot.register_next_step_handler(msg, processPasswordStep, bot, mssv)

def processPasswordStep(message, bot, mssv):
    pwd = message.text
    bot.send_message(message.chat.id, "⏳ Thông tin đã được gửi cho Worker xác thực...")
    task.registrationTask.delay(message.chat.id, mssv, pwd)

def processCustomDate(message, bot):
    utils.cancelStepTimeout(message.chat.id)
    try:
        dateStr = message.text
        datetime.strptime(dateStr, "%d/%m/%Y")
        bot.send_message(message.chat.id, f"⏳ Đang điều phối Worker để quét lịch ngày {dateStr} cho bạn...")
        task.portalTask.delay(message.chat.id, dateStr)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Định dạng ngày chưa đúng!\nHãy nhập theo kiểu: <b>DD/MM/YYYY</b> (ví dụ: 20/03/2026).", parse_mode="HTML")
    except Exception as e:
        utils.log("ERROR", f"Lỗi processCustomDate: {e}")

def processDateStep(message, bot):
    try:
        startDateStr = message.text
        datetime.strptime(startDateStr, "%d/%m/%Y")
        msg = bot.send_message(message.chat.id, "⏳ Bạn muốn quét trong bao nhiêu ngày tới? (VD: 14):")
        bot.register_next_step_handler(msg, processDaysStep, startDateStr, bot)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Sai định dạng ngày rồi bạn ơi! Bấm lại nút để làm lại nhé.")

def processDaysStep(message, startDateStr, bot):
    try:
        numDays = int(message.text)
        if numDays <= 0:
            raise ValueError("Số ngày phải lớn hơn 0")
        bot.send_message(message.chat.id, f"🚀 Đang gửi yêu cầu quét từ {startDateStr} trong {numDays} ngày...")
        task.customDeadlineTask.delay(message.chat.id, startDateStr, numDays)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Số ngày phải là số nguyên dương!")

def processFeedback(message, bot):
    utils.cancelStepTimeout(message.chat.id)
    teleFunc.handleSendFeedback(bot, message, adminId)

def handleMarkDone(bot, call):
    chatId = call.message.chat.id
    taskId = call.data.split('_')[1]
    if db.markTaskCompleted(chatId, taskId):
        new_text = call.message.text.replace("❌ Chưa xong", "✅ Đã xong")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Đánh dấu chưa xong", callback_data=f"undone_{taskId}"))
        try:
            bot.edit_message_text(new_text, chatId, call.message.message_id, parse_mode="HTML", reply_markup=markup)
        except: pass
        bot.answer_callback_query(call.id, "✅ Tuyệt vời! Đã ghi nhận bạn hoàn thành bài tập.")

def handleMarkUndone(bot, call):
    chatId = call.message.chat.id
    taskId = call.data.split('_')[1]
    if db.unmarkTaskCompleted(chatId, taskId):
        new_text = call.message.text.replace("✅ Đã xong", "❌ Chưa xong")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Đánh dấu hoàn thành", callback_data=f"done_{taskId}"))
        try:
            bot.edit_message_text(new_text, chatId, call.message.message_id, parse_mode="HTML", reply_markup=markup)
        except: pass
        bot.answer_callback_query(call.id, "❌ Đã chuyển trạng thái về chưa hoàn thành.")

def processCustomDonateAmount(message, bot):
    utils.cancelStepTimeout(message.chat.id)
    try:
        amount = int(message.text.strip())
        if amount < 2000:
            bot.send_message(message.chat.id, "⚠️ Số tiền tối thiểu để tạo mã QR là 2.000 VNĐ.")
            return
        bot.send_message(message.chat.id, "⏳ Đang điều phối Worker khởi tạo mã VietQR...")
        task.donateTask.delay(message.chat.id, message.from_user.username, amount)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Số tiền phải là số nguyên dương! Vui lòng bấm lại nút Donate để làm lại.")