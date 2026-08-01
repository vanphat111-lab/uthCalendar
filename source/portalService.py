# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# portalService.py

# from curl_cffi import requests
from datetime import datetime, timedelta
import database as db
import utils
import redisManager

# session = requests.Session(impersonate="chrome110")

def verifyUthCredentials(user, password):
    try:
        fakeCaptcha = utils.generateFakeCaptcha()
        url = f"https://portal.ut.edu.vn/api/v1/user/login?g-recaptcha-response={fakeCaptcha}" 

        r = utils.safeRequest("POST", url, json={"username": user, "password": password})
        
        try:
            data = r.json()
        except Exception:
            utils.log("ERROR", f"Server không trả về JSON. Mã lỗi HTTP: {r.status_code}. Nội dung: {r.text[:500]}")
            return False, "Lỗi phản hồi từ server trường"

        utils.log("INFO", f"Portal trả về: {data.get('message')}")
        
        if r.status_code == 200 and data.get("token"): 
            return True, "Thành công"
        return False, data.get("message", "Sai tài khoản hoặc mật khẩu")
    except Exception as e: 
        utils.log("ERROR", f"Lỗi verifyUthCredentials: {e}")
        return False, "Lỗi kết nối server trường"

def get_classes_by_week(chat_id, user, password, targetDate):
    try:
        date_obj = datetime.strptime(targetDate, "%d/%m/%Y")
        iso_date = date_obj.strftime("%Y-%m-%d")

        tk = getValidPortalToken(chat_id, user, password)
        if not tk: 
            return False, "Không thể lấy Token. Vui lòng kiểm tra lại tài khoản/mật khẩu."

        headers = {
            "authorization": f"Bearer {tk}",
            "Referer": "https://portal.ut.edu.vn/calendar",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "accept": "application/json, text/plain, */*"
        }

        url = f"https://portal.ut.edu.vn/api/v1/lichhoc/lichTuan?date={iso_date}"
        res = utils.safeRequest("GET", url, headers=headers)

        if res.status_code == 401:
            utils.log("WARN", f"Token của {chat_id} bị Invalid khi lấy lịch tuần. Đang login lại...")
            tk = redisManager.loginAndSaveToken(chat_id, user, password)
            if not tk: 
                return False, "Phiên đăng nhập hết hạn và không thể gia hạn. Hãy đăng ký lại."
            
            headers["Authorization"] = f"Bearer {tk}"
            res = utils.safeRequest("GET", url, headers=headers)

        if res.status_code == 200:
            data = res.json().get("body", [])
            return data, None

        return False, f"Lỗi không xác định từ server trường (Mã: {res.status_code})"

    except Exception as e:
        utils.log("ERROR", f"Lỗi get_classes_by_week: {e}")
        return False, "Lỗi hệ thống không xác định khi lấy lịch tuần."

def getClassesByDate(chatId, user, password, targetDate):
    try:
        week_data, error = get_classes_by_week(chatId, user, password, targetDate)

        if week_data is False:
            return False, error

        classes = [c for c in week_data if c.get("ngayBatDauHoc") == targetDate]

        return classes, None

    except Exception as e:
        utils.log("ERROR", f"Lỗi getClassesByDate: {e}")
        return False, "Lỗi hệ thống không xác định. Vui lòng thử lại sau ít phút."
    
def verifyAndSaveUser(chatId, mssv, password):
    isValid, reason = verifyUthCredentials(mssv, password)

    if not isValid:
        utils.log("ERROR", f"User {chatId} đăng ký thất bại: {reason}")
        return False, f"❌ Thất bại: {reason}"

    encryptedUser = utils.encryptData(mssv)
    encryptedPassword = utils.encryptData(password)

    saved = db.upsertUserCredentials(
        chatId,
        encryptedUser,
        encryptedPassword
    )

    if not saved:
        utils.log("ERROR", f"Không thể lưu tài khoản của user {chatId}")
        return False, "❌ Xác thực thành công nhưng không thể lưu tài khoản."

    utils.log("SUCCESS", f"User {chatId} đã đăng ký thành công")
    return True, "🎉 <b>Đăng ký thành công!</b> Mình sẽ tự động nhắc lịch cho bạn."


def getValidPortalToken(chatId, rawUser, rawPass):
    cachedToken = redisManager.getSession(chatId, 'portal')
    if cachedToken: return cachedToken

    try:
        fakeCaptcha = utils.generateFakeCaptcha()
        url = f"https://portal.ut.edu.vn/api/v1/user/login?g-recaptcha-response={fakeCaptcha}"
        r = utils.safeRequest("POST", url, json={"username": rawUser, "password": rawPass})

        try:
            res_data = r.json()
        except Exception:
            utils.log("ERROR", f"Server không trả về JSON. Mã lỗi HTTP: {r.status_code}. Nội dung: {r.text[:500]}")
            return None

        token = res_data.get("token")
        utils.log("INFO", f"Portal trả về: {res_data.get('message')}")
        if token:
            redisManager.saveSession(chatId, 'portal', token, expire=7200)
            return token
    except Exception as e:
        utils.log("ERROR", f"Lỗi Server Portal: {e}")
    return None

def formatCalendarMessage(chatId, dateStr, isAuto=False):
    u = db.getUserCredentials(chatId)
    if not u: return "Bạn chưa đăng ký tài khoản!"
    
    rawUser = utils.decryptData(u['uth_user'])
    rawPass = utils.decryptData(u['uth_pass'])

    classes, error = getClassesByDate(chatId, rawUser, rawPass, dateStr)
    if classes is False:
        return f"❌ {error}"
    
    if classes:
        header = f"🔔 <b>NHẮC LỊCH TỰ ĐỘNG ({dateStr})</b>\n" if isAuto else f"📅 <b>LỊCH HỌC {dateStr}</b>\n"
        msg = header + "━━━━━━━━━━━━━━━━━━\n"
        for c in classes:
            courseLink = c.get('link', 'https://courses.ut.edu.vn/')
            statusLabel = "🛑 Tạm ngưng" if c.get("isTamNgung") else "🟢 Bình thường"

            weatherLabel = ""
            target_cs = detectCampus(c)
            
            if target_cs:
                weatherData = utils.getWeatherByHour(target_cs, c['tuGio'], dateStr)
                if weatherData:
                    weatherLabel = (
                        f"\n🌡️ {target_cs} (<code>{c['tuGio']}</code>): "
                        f"{weatherData['icon']} {weatherData['temp']}°C ({weatherData['desc']})"
                    )

            msg += f"\n📘 <a href='{courseLink}'>{c['tenMonHoc']}</a>"
            msg += f"\n⏰ {c['tuGio']} - {c['denGio']}"
            msg += f"\n📍 {c['tenPhong']}"
            msg += weatherLabel
            msg += f"\n📌 {statusLabel}\n"
        msg += f"\n🔗 <a href='https://portal.ut.edu.vn/'>Portal UTH</a>"
        return msg
    else:
        return f"🎉 Ngày {dateStr} bạn được nghỉ nè!"
    
def format_week_calendar_message(chat_id, startDateStr):
    u = db.getUserCredentials(chat_id)
    if not u: return "⚠️ Bạn chưa đăng ký tài khoản!"

    raw_user = utils.decryptData(u['uth_user'])
    raw_pass = utils.decryptData(u['uth_pass'])
    
    now = datetime.strptime(startDateStr, "%d/%m/%Y")
    monday = now - timedelta(days=now.weekday())

    data, error = get_classes_by_week(chat_id, raw_user, raw_pass, startDateStr)
    
    if data is False:
        return f"❌ <b>Có lỗi xảy ra:</b>\n{error}"
    
    if not data:
        return f"🎉 Tuần từ {monday.strftime('%d/%m')} bạn không có lịch học nào cả. Nghỉ ngơi nhé!"

    week_data = { (monday + timedelta(days=i)).strftime("%d/%m/%Y"): [] for i in range(7) }
    
    for item in data:
        date_key = item.get("ngayBatDauHoc")
        if date_key in week_data:
            week_data[date_key].append(item)

    msg = f"📅 <b>LỊCH HỌC CẢ TUẦN</b>\n"
    msg += f"<i>(Từ {monday.strftime('%d/%m')} đến {(monday + timedelta(days=6)).strftime('%d/%m')})</i>\n"
    msg += "━━━━━━━━━━━━━━━━━━\n"

    day_names = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ Nhật"]
    
    for i, (date_str, classes) in enumerate(week_data.items()):
        msg += f"\n📍 <b>{day_names[i]} ({date_str}):</b>\n"
        
        if not classes:
            msg += "   ╰ 🏝️ <i>Bạn được nghỉ</i>\n"
        else:
            for c in classes:
                status = " (🛑 <b>Tạm ngưng</b>)" if c.get("isTamNgung") else ""
                courseLink = c.get('link') or 'https://courses.ut.edu.vn/'
                
                # --- Logic xác định cơ sở dựa trên code cũ của mày ---
                target_cs = detectCampus(c)
                
                # Nhúng link vào tên môn và thêm cơ sở ở sau
                msg += f"   ╰ 📘 <code>{c['tuGio']}</code>: <a href='{courseLink}'>{c['tenMonHoc']}</a> ({target_cs}){status}\n"

    msg += "\n━━━━━━━━━━━━━━━━━━\n"
    msg += "💡 <i>Dùng 'Lịch hôm nay' để xem chi tiết phòng học và thời tiết bạn nhé!</i>"
    
    return msg

def detectCampus(class_data):
    ten_phong = str(class_data.get("tenPhong") or "")
    co_so_display = str(class_data.get("coSoToDisplay") or "")

    combined = f"{ten_phong} {co_so_display}".lower()

    if "cs1" in combined or "cơ sở 1" in combined:
        return "CS1"
    if "cs2" in combined or "cơ sở 2" in combined:
        return "CS2"
    if "cs3" in combined or "cơ sở 3" in combined:
        return "CS3"

    return "N/A"