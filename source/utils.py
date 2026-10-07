# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# utils.py

import os
from datetime import datetime
from cryptography.fernet import Fernet
from dotenv import load_dotenv
import threading
import json
import string
import random
from curl_cffi import requests
import time
from zoneinfo import ZoneInfo

load_dotenv()

encryptionKey = os.getenv("ENCRYPTION_KEY")
cipherSuite = Fernet(encryptionKey.encode()) if encryptionKey else None
WARP_PROXY = os.getenv("WARP_PROXY_URL", "socks5://uth_warp:1080")
TZ_NAME = os.getenv("TZ", "Asia/Ho_Chi_Minh").strip()
APP_TZ = ZoneInfo(TZ_NAME)

os.environ["TZ"] = TZ_NAME
time.tzset()

def getNow(): return datetime.now().strftime('%d/%m/%Y %H:%M:%S')
def log(level, message): print(f"[{getNow()}] [{level}] {message}", flush=True)

def encryptData(data):
    if not data: return None
    return cipherSuite.encrypt(data.encode()).decode()

def decryptData(encryptedData):
    if not encryptedData: return None
    return cipherSuite.decrypt(encryptedData.encode()).decode()

userTimers = {}

def startStepTimeout(bot, chatId, seconds=60):
    cancelStepTimeout(chatId)
    
    def timeoutCallback():
        try:
            bot.clear_step_handler_by_chat_id(chatId)
            bot.send_message(chatId, "⏰ <b>Hết thời gian!</b>\nLệnh của bạn đã bị hủy do quá lâu không có phản hồi.", parse_mode="HTML")
            log("TIMEOUT", f"Đã hủy lệnh chờ của user {chatId} do hết thời gian.")
        except Exception as e:
            log("ERROR", f"Lỗi khi xử lý timeout: {e}")
        finally:
            if chatId in userTimers:
                del userTimers[chatId]

    timer = threading.Timer(seconds, timeoutCallback)
    timer.start()
    userTimers[chatId] = timer

def cancelStepTimeout(chatId):
    if chatId in userTimers:
        userTimers[chatId].cancel()
        del userTimers[chatId]

def getWeatherByHour(campusCode, targetTimeStr, dateStr):
    import redisManager
    try:
        cachedForecast = redisManager.redisClient.get(f"forecast:{campusCode}")
        if not cachedForecast: 
            return None
        
        forecastList = json.loads(cachedForecast)
        
        dtObj = datetime.strptime(f"{dateStr} {targetTimeStr}", "%d/%m/%Y %H:%M")
        targetHourStr = dtObj.strftime("%Y-%m-%d %H:00")

        for hourData in forecastList:
            if hourData['time'] == targetHourStr:
                conditionText = hourData['condition']['text'].lower()
                icon = "☀️"
                if "mưa" in conditionText: icon = "🌧️"
                elif "dông" in conditionText: icon = "⛈️"
                elif "mây" in conditionText: icon = "☁️"

                return {
                    "temp": hourData['temp_c'],
                    "desc": hourData['condition']['text'],
                    "icon": icon
                }
    except Exception as e:
        log("ERROR", f"Lỗi getWeatherByHour: {e}")
    
    return None

def generateFakeCaptcha(length=30):
    chars = string.ascii_letters + string.digits + "-_"
    return ''.join(random.choice(chars) for _ in range(length))

def safeRequest(method, url, use_proxy=True, silent=False, retries=3, **kwargs):
    # CHỖ NÀY: Import bên trong hàm để tránh Circular Import
    from warpManager import warp_manager 
    
    headers = kwargs.get("headers", {})
    headers.update({"Connection": "close"})
    
    headers.setdefault("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36")
    headers.setdefault("Accept", "application/json, text/plain, */*")
    
    kwargs["headers"] = headers
    kwargs.setdefault("impersonate", "chrome110")
    kwargs.setdefault("timeout", 10)

    for attempt in range(retries):
        if use_proxy:
            kwargs["proxies"] = {
                "http": WARP_PROXY,
                "https": WARP_PROXY
            }
        else:
            kwargs.pop("proxies", None)

        try:
            with requests.Session() as s:
                response = getattr(s, method.lower())(url, **kwargs)
                if not silent: 
                    log(method, f"Thành công: {url}")
                
                if response.status_code == 429:
                    log("WARN", "Dính lỗi 429 (Spam). Đang thực hiện reset WARP...")
                    warp_manager.restart_warp()
                    # Nghỉ 5s cho tunnel ổn định rồi thử lại lượt tiếp theo
                    time.sleep(5)
                    continue 
                    
                return response
        except Exception as e:
            if not silent:
                log("WARN", f"Lần thử {attempt+1} qua WARP thất bại: {e}")
            
            if attempt == retries - 1:
                return None
            
            time.sleep(2)
    return None