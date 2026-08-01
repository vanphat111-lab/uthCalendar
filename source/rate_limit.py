# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# rate_limit.py

import redisManager
from utils import log
import math
from functools import wraps

LIMIT_MIN = 10
LIMIT_HOUR = 50
LIMIT_DAY = 80

def check_spam(chat_id):
    chat_id = str(chat_id)
    
    ban_key = f"spam:ban:{chat_id}"
    ban_ttl = redisManager.redisClient.ttl(ban_key) 
    
    if ban_ttl > 0:
        minutes_left = math.ceil(ban_ttl / 60)
        return False, f"🚫 Bạn đang bị BAN. Thử lại sau {minutes_left} phút nữa nhé."

    key_min = f"spam:cnt_min:{chat_id}"
    key_hour = f"spam:cnt_hour:{chat_id}"
    key_day = f"spam:cnt_day:{chat_id}"

    cnt_min = incr_with_ttl(key_min, 60)
    cnt_hour = incr_with_ttl(key_hour, 3600)
    cnt_day = incr_with_ttl(key_day, 86400)

    violated = False
    reason = ""

    if cnt_min > LIMIT_MIN:
        violated, reason = True, f"vượt quá {LIMIT_MIN} tin/phút"
    elif cnt_hour > LIMIT_HOUR:
        violated, reason = True, f"vượt quá {LIMIT_HOUR} tin/giờ"
    elif cnt_day > LIMIT_DAY:
        violated, reason = True, f"vượt quá {LIMIT_DAY} tin/ngày"

    if violated:
        vios_key = f"spam:vios:{chat_id}"
        vios_count_raw = redisManager.redisClient.get(vios_key)
        vios_count = int(vios_count_raw) + 1 if vios_count_raw else 1
        
        redisManager.redisClient.set(vios_key, vios_count)
        
        ban_minutes = 2 ** vios_count
        redisManager.redisClient.setex(ban_key, ban_minutes * 60, "true")
        
        log("WARN", f"User {chat_id} bị ban {ban_minutes}p do {reason} (Lần {vios_count})")
        
        next_penalty = 2 ** (vios_count + 1)
        msg = (
            f"⚠️ **PHÁT HIỆN SPAM!**\n\n"
            f"Bạn đã {reason}.\n"
            f"🛡 **Hình phạt:** BAN {ban_minutes} phút.\n"
            f"🛑 **Cảnh báo:** Tái phạm lần sau sẽ bị BAN {next_penalty} phút!"
        )
        return False, msg

    return True, None

def incr_with_ttl(key, ttl):
    val = redisManager.redisClient.incr(key)
    if val == 1:
        redisManager.redisClient.expire(key, ttl)
    return val

def ratelimit_handler(bot):
    def decorator(func):
        @wraps(func)
        def wrapped(message, *args, **kwargs):
            chat_id = message.chat.id
            # Gọi lại hàm check_spam cũ của mày
            is_allowed, msg = check_spam(chat_id)
            
            if not is_allowed:
                bot.reply_to(message, msg, parse_mode="Markdown")
                return # Chặn đứng, không cho chạy vào hàm xử lý chính
            
            return func(message, *args, **kwargs)
        return wrapped
    return decorator