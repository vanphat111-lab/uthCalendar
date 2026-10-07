# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# courseService.py

from curl_cffi import requests
import time
from datetime import datetime, timedelta
import database as db
import utils
import re
import redisManager

MOODLE_SYSTEMS = {
    "course": {
        "base_url": "https://courses.ut.edu.vn",
        "session_key": "course",
        "display_name": "Courses",
    },
    "thnn": {
        "base_url": "https://thnn.ut.edu.vn",
        "session_key": "thnn",
        "display_name": "THNN",
    },
}


def getMoodleSystem(system="course"):
    if system not in MOODLE_SYSTEMS:
        supported = ", ".join(MOODLE_SYSTEMS)
        raise ValueError(
            f"Hệ thống Moodle không hợp lệ: {system}. Hỗ trợ: {supported}"
        )

    return MOODLE_SYSTEMS[system]

# courseSession = requests.Session(impersonate="chrome110")

def rebuildSession(cookieDict):
    session = requests.Session(impersonate="chrome")
    session.cookies.update(cookieDict)
    return session

def getValidCourseSession(chatId, rawUser, rawPass, system="course"):
    config = getMoodleSystem(system)
    sessionKey = config["session_key"]

    cached = redisManager.getSession(chatId, sessionKey)
    if cached:
        return cached["cookies"], cached["sesskey"]

    session, sesskey = fetchMoodleSession(rawUser, rawPass, system=system)

    if session and sesskey:
        data = {
            "sesskey": sesskey,
            "cookies": session,
            }
        redisManager.saveSession(chatId, sessionKey, data)

    return session, sesskey

def fetchMoodleSession(username, password, system="course"):
    config = getMoodleSystem(system)
    baseUrl = config["base_url"]
    displayName = config["display_name"]
    with requests.Session(impersonate="chrome") as s:
        try:
            loginUrl = f"{baseUrl}/login/index.php"

            loginPage = s.get(
                loginUrl,
                headers={
                    "Accept": (
                        "text/html,application/xhtml+xml,"
                        "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
                    )
                },
                timeout=20,
            )
            loginPage.raise_for_status()

            tokenMatch = re.search(
                r'name=["\']logintoken["\'][^>]*value=["\']([^"\']+)["\']',
                loginPage.text,
                re.IGNORECASE,
            )

            if not tokenMatch:
                utils.log("ERROR", "Không tìm thấy Moodle logintoken")
                return None, None

            loginToken = tokenMatch.group(1)

            loginResponse = s.post(
                loginUrl,
                data={
                    "anchor": "",
                    "logintoken": loginToken,
                    "username": username,
                    "password": password,
                },
                headers={
                    "Origin": baseUrl,
                    "Referer": loginUrl,
                    "Accept": (
                        "text/html,application/xhtml+xml,"
                        "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
                    ),
                },
                allow_redirects=True,
                timeout=25,
            )
            loginResponse.raise_for_status()

            if (
                "/login/index.php" in str(loginResponse.url)
                or 'name="logintoken"' in loginResponse.text
            ):
                utils.log("WARN", f"Đăng nhập Moodle {displayName} thất bại")
                return None, None

            coursePage = s.get(
                f"{baseUrl}/my/courses.php",
                headers={
                    "Referer": f"{baseUrl}/my/",
                    "Accept": (
                        "text/html,application/xhtml+xml,"
                        "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
                    ),
                },
                timeout=20,
            )
            coursePage.raise_for_status()

            sesskeyMatch = re.search(
                r'"sesskey"\s*:\s*"([^"]+)"',
                coursePage.text,
            )

            if not sesskeyMatch:
                utils.log("ERROR", f"Login {displayName} được nhưng không thấy sesskey")
                return None, None

            cookies = s.cookies.get_dict()
            sesskey = sesskeyMatch.group(1)

            return cookies, sesskey

        except Exception as e:
            utils.log("ERROR", f"Lỗi login Moodle {displayName}: {e}")
            return None, None

def prepareMonthlyPayload(startDate, numDays):
    now_ts = int(startDate.timestamp())
    end_ts = now_ts + (numDays * 24 * 60 * 60)
    endDate = datetime.fromtimestamp(end_ts)
    
    payload = [{
        "index": 0,
        "methodname": "core_calendar_get_calendar_monthly_view",
        "args": {
            "year": str(startDate.year), "month": str(startDate.month),
            "courseid": 1, "day": 1, "view": "month"
        }
    }]

    currentYear = startDate.year
    currentMonth = startDate.month
    index = 1

    while (currentYear, currentMonth) != (endDate.year, endDate.month):
        if currentMonth == 12:
            currentMonth = 1
            currentYear += 1
        else:
            currentMonth += 1

        payload.append({
            "index": index,
            "methodname": "core_calendar_get_calendar_monthly_view",
            "args": {
                "year": str(currentYear), "month": str(currentMonth),
                "courseid": 1, "day": 1, "view": "month"
            }
        })

        index += 1

    return payload, now_ts, end_ts

def getDeadlineMessages(
    chatId,
    cookieDict,
    sesskey,
    startDate=None,
    numDays=7,
    system="course",
):
    config = getMoodleSystem(system)
    baseUrl = config["base_url"]
    displayName = config["display_name"]
    if startDate is None:
        startDate = datetime.now()
        
    payload, startTs, endTs = prepareMonthlyPayload(startDate, numDays)
    url = f"{baseUrl}/lib/ajax/service.php?sesskey={sesskey}"
    
    with requests.Session(impersonate="chrome") as s:
        s.cookies.update(cookieDict)
        # Thêm headers mặc định cho Moodle Session
        s.headers.update({
            "Connection": "close",
            "Accept": "application/json, text/plain, */*",
        })
        
        try:
            r = s.post(url, json=payload, timeout=15)
            
            try:
                responses = r.json()
            except Exception:
                utils.log("ERROR", f"Moodle {displayName} Deadline: Server không trả về JSON. Mã HTTP: {r.status_code}. Nội dung: {r.text[:500]}")
                return None

            if responses and isinstance(responses, list) and responses[0].get('error'):
                utils.log("WARN", f"Session Moodle {displayName} của {chatId} đã hết hạn")
                return None
            
            allEvents = []
            completedIds = db.getCompletedTaskIds(chatId)

            for res in responses:
                if res.get('error'): continue
                for week in res['data']['weeks']:
                    for day in week['days']:
                        for event in day['events']:
                            if startTs <= event['timesort'] <= endTs:
                                if not any(e['id'] == event['id'] for e in allEvents):
                                    allEvents.append(event)
            
            allEvents.sort(key=lambda x: x['timesort'])
            
            msgList = []
            for e in allEvents:
                dueDt = (datetime.fromtimestamp(e["timesort"]) - timedelta(minutes=30))
                dueStr = dueDt.strftime('%d/%m/%Y %H:%M')
                isDone = str(e['id']) in completedIds
                status = "✅ Đã xong" if isDone else "❌ Chưa xong"
                
                text = (
                    f"🔔 <a href='{e.get('url')}'><b>{e['name']}</b></a>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📝 <b>Trạng thái:</b> {status}\n"
                    f"📚 <b>Môn:</b> {e['course']['fullname']}\n"
                    f"⏰ <b>Hạn:</b> <code>{dueStr}</code>"
                )

                msgList.append({
                    "text": text,
                    "callback": f"undone_{e['id']}" if isDone else f"done_{e['id']}",
                    "btnText": "❌ Đánh dấu chưa xong" if isDone else "✅ Đánh dấu hoàn thành"
                })
            return msgList

        except Exception as e:
            utils.log("ERROR", f"Lỗi lấy deadline {displayName}: {e}")
        return None

def scanAllDeadlines(
    bot,
    chatId,
    isManual=False,
    startDate=None,
    numDays=7,
    system="course",
):
    config = getMoodleSystem(system)
    sessionKey = config["session_key"]
    displayName = config["display_name"]

    u = db.getUserCredentials(chatId)
    if not u:
        utils.log("WARN", f"Không tìm thấy thông tin user {chatId} khi quét {displayName}")
        bot.send_message(chatId,"❌ Bạn chưa đăng ký tài khoản. Hãy dùng /login trước.", parse_mode="HTML")
        return False

    rawUser = utils.decryptData(u["uth_user"])
    rawPass = utils.decryptData(u["uth_pass"])

    session, sesskey = getValidCourseSession(
        chatId,
        rawUser,
        rawPass,
        system=system,
    )

    if not session or not sesskey:
        utils.log("WARN", f"Không thể lấy session Moodle {displayName} cho {chatId}")
        bot.send_message(chatId, f"❌ Không thể kết nối hệ thống {displayName}.")
        return False

    messages = getDeadlineMessages(
        chatId,
        session,
        sesskey,
        startDate=startDate,
        numDays=numDays,
        system=system,
    )

    if messages is None:
        utils.log(
            "INFO",
            f"Đang làm mới sesskey {displayName} cho {chatId}",
        )
        redisManager.deleteSession(chatId, sessionKey)

        session, sesskey = fetchMoodleSession(
            rawUser,
            rawPass,
            system=system,
        )

        if session and sesskey:
            data = {
                "sesskey": sesskey,
                "cookies": session,
            }
            redisManager.saveSession(chatId, sessionKey, data)
            messages = getDeadlineMessages(
                chatId,
                session,
                sesskey,
                startDate=startDate,
                numDays=numDays,
                system=system,
            )

    if messages is None:
        bot.send_message(chatId, f"❌ Không thể lấy danh sách deadline từ {displayName}.")
        return False

    if len(messages) == 0:
        bot.send_message(
            chatId,
            (
                "🎉 <b>Tuyệt vời!</b>\n"
                f"Bạn không có deadline nào trên {displayName} "
                "trong khoảng thời gian này. Nghỉ ngơi thôi!"
            ),
            parse_mode="HTML",
        )
        return True

    rangeStart = startDate if startDate else datetime.now()
    rangeEnd = rangeStart + timedelta(days=numDays)

    startStr = rangeStart.strftime("%d/%m/%Y")
    endStr = rangeEnd.strftime("%d/%m/%Y")

    if isManual:
        header = f"🔍 <b>DANH SÁCH DEADLINE {displayName.upper()}</b>\n"
    else:
        header = (
            f"🚀 <b>THÔNG BÁO DEADLINE TỰ ĐỘNG "
            f"{displayName.upper()}</b>\n"
        )

    header += f"📅 <i>Thời gian: từ {startStr} đến {endStr}</i>\n"
    header += (
        f"✍️ Tìm thấy <b>{len(messages)}</b> sự kiện "
        "trong khoảng thời gian này.\n"
    )
    header += "━━━━━━━━━━━━━━━━━━"

    bot.send_message(chatId, header, parse_mode="HTML")

    from telebot import types
    for m in messages:
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                m["btnText"],
                callback_data=m["callback"],
            )
        )
        bot.send_message(
            chatId,
            m["text"],
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
        time.sleep(0.3)
    return True

def scanAllMoodleDeadlines(
    bot,
    chatId,
    isManual=False,
    startDate=None,
    numDays=7,
):
    """
    Quét deadline của toàn bộ hệ thống Moodle.

    Mỗi hệ thống gửi một nhóm tin nhắn riêng:
    - Courses
    - THNN

    Một hệ thống lỗi không làm dừng hệ thống còn lại.
    """
    results = {}

    for system in ("course", "thnn"):
        config = getMoodleSystem(system)
        displayName = config["display_name"]

        try:
            results[system] = scanAllDeadlines(
                bot=bot,
                chatId=chatId,
                isManual=isManual,
                startDate=startDate,
                numDays=numDays,
                system=system,
            )
        except Exception as e:
            results[system] = False

            utils.log("ERROR", f"Lỗi quét deadline {displayName} của {chatId}: {e}")
            bot.send_message(chatId, f"❌ Không thể quét deadline từ hệ thống {displayName}.")

        time.sleep(0.5)

    return results

def getEventIcon(eventType):
    icons = {'assign': '📝', 'quiz': '✍️', 'course': '📚', 'site': '🌐'}
    return icons.get(eventType, '🔔')