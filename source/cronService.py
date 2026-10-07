# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# cronService.py

import time
import traceback

from dateutil.utils import today
import database as db
from utils import log
import task
from datetime import datetime, timedelta
import redisManager
# from zoneinfo import ZoneInfo


def autoCheckAndNotify(bot, dayOffset=0):
    today = datetime.now().date()
    targetDate = today + timedelta(days=dayOffset)
    dateStr = targetDate.strftime("%d/%m/%Y")

    log("CRON", "Bắt đầu chu kỳ quét Portal")
    try:
        users = db.getUsersForPortalNotify()
        if not users:
            log("CRON", "Không có user nào cần quét Portal")
            return

        # today = time.strftime("%d/%m/%Y")
        for chat_id in users:
            try:
                if targetDate == today and redisManager.isPortalDateMuted(chat_id, targetDate):
                    log("CRON", f"Bỏ qua lịch đã mute cho user: {chat_id}, ngày: {dateStr}")
                    continue

                task.periodicPortalTask.delay(chat_id, dateStr)
                log("CRON", f"Đã đẩy task Portal cho user: {chat_id}")
            except Exception:
                log("ERROR", f"Lỗi đẩy task cho {chat_id}: {traceback.format_exc()}")

    except Exception:
        log("CRITICAL", f"Crash tại autoCheckAndNotify: {traceback.format_exc()}")

def autoScanAllUsers(bot):
    log("CRON", "Bắt đầu chu kỳ quét Course Deadline")
    try:
        users = db.getUsersForDeadlineNotify()
        if not users:
            log("CRON", "Không có user nào cần quét Deadline")
            return

        for chat_id in users:
            try:
                task.periodicCourseTask.delay(chat_id)
                log("CRON", f"Đã đẩy task Course cho user: {chat_id}")
            except Exception:
                log("ERROR", f"Lỗi đẩy task cho {chat_id}: {traceback.format_exc()}")

    except Exception:
        log("CRITICAL", f"Crash tại autoScanAllUsers: {traceback.format_exc()}")