# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# redisManager.py

import redis
import json
import os
from utils import log
import utils
from datetime import date, datetime, time, timedelta
# from zoneinfo import ZoneInfo
# from curl_cffi import requests

redisClient = redis.Redis(
    host=os.getenv('REDIS_HOST', 'uth_redis'), 
    port=6379, 
    db=0, 
    decode_responses=True
)

def _portalMuteDate(targetDate):
    if isinstance(targetDate, datetime):
        raise TypeError("targetDate phải là date hoặc chuỗi YYYY-MM-DD")

    if isinstance(targetDate, date):
        return targetDate

    return date.fromisoformat(targetDate)


def mutePortalDate(chatId, targetDate):
    targetDate = _portalMuteDate(targetDate)

    expiresAt = datetime.combine(
        targetDate + timedelta(days=1),
        time.min,
        tzinfo=utils.APP_TZ,
    )

    if expiresAt <= datetime.now(expiresAt.tzinfo):
        return False

    key = f"portal:mute:{chatId}:{targetDate.isoformat()}"

    return bool(
        redisClient.set(
            key,
            "1",
            exat=int(expiresAt.timestamp()),
        )
    )


def isPortalDateMuted(chatId, targetDate):
    targetDate = _portalMuteDate(targetDate)
    key = f"portal:mute:{chatId}:{targetDate.isoformat()}"

    return bool(redisClient.exists(key))

def saveSession(chatId, serviceType, data, expire=7200):
    key = f"auth:{serviceType}:{chatId}"
    redisClient.set(key, json.dumps(data), ex=expire)
    log("REDIS", f"Đã lưu cache session cho {chatId} - {serviceType}")

def getSession(chatId, serviceType):
    key = f"auth:{serviceType}:{chatId}"
    data = redisClient.get(key)
    if data:
        log("REDIS", f"Đã đẩy cache cho {chatId} - {serviceType}")
        return json.loads(data)
    return None

def deleteSession(chatId, serviceType):
    key = f"auth:{serviceType}:{chatId}"
    redisClient.delete(key)
    log("REDIS", f"Đã xoá cache cho {chatId} - {serviceType}")

def loginAndSaveToken(chatId, user, password):
    try:
        fakeCaptcha = utils.generateFakeCaptcha()
        url = f"https://portal.ut.edu.vn/api/v1/user/login?g-recaptcha-response={fakeCaptcha}"
        r = utils.safeRequest("POST", url, json={"username": user, "password": password})
        data = r.json()
        token = data.get("token")

        if r.status_code == 200 and token:
            saveSession(chatId, 'portal', token, expire=7200)
            
            log("SUCCESS", f"Đã làm mới và lưu Token thành công cho {chatId}")
            return token
            
        log("ERROR", f"Login làm mới thất bại cho {chatId}: {data.get('message')}")
        return None
    except Exception as e:
        log("ERROR", f"Lỗi nghiêm trọng trong loginAndSaveToken: {e}")
        return None

def delete_all_user_data(chat_id):
    chat_id = str(chat_id)
    keys = [
        f"auth:portal:{chat_id}",
        f"auth:course:{chat_id}",
        f"auth:thnn:{chat_id}",
        f"spam:ban:{chat_id}",
        f"spam:cnt_min:{chat_id}",
        f"spam:cnt_hour:{chat_id}",
        f"spam:cnt_day:{chat_id}",
        f"spam:vios:{chat_id}",
    ]

    try:
        deleted = redisClient.delete(*keys)
        log("REDIS", f"Đã xóa {deleted} key của user {chat_id}")
        return True
    except Exception as exc:
        log("ERROR", f"Không thể xóa Redis của user {chat_id}: {exc}")
        return False