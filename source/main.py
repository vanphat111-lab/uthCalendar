# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# main.py

import telebot, os, threading, schedule, time, sys
import teleBot, cronService, database as db
import task
from utils import log

critical_vars = ["TELE_TOKEN", "ADMIN_ID", "ENCRYPTION_KEY", "DB_HOST", "DB_NAME", "DB_USER", "DB_PASS", "CELERY_BROKER_URL"]
missing_critical = [v for v in critical_vars if not os.getenv(v)]
if missing_critical:
    log("CRITICAL", f"Thiếu các biến môi trường bắt buộc: {', '.join(missing_critical)}. Dừng hệ thống!")
    sys.exit(1)
log("SUCCESS", "Cấu hình hệ thống cốt lõi đã tải thành công.")

payos_vars = ["PAYOS_CLIENT_ID", "PAYOS_API_KEY", "PAYOS_CHECKSUM_KEY"]
payos_enabled = all(os.getenv(v) for v in payos_vars)
if payos_enabled:
    log("SUCCESS", "Cấu hình PayOS hợp lệ. Kích hoạt chức năng Donate.")
else:
    log("WARN", "Thiếu cấu hình PayOS. Hủy bỏ chức năng Donate.")

weather_enabled = bool(os.getenv("WEATHER_API_KEY"))
if weather_enabled:
    log("SUCCESS", "Cấu hình WeatherAPI hợp lệ. Kích hoạt chức năng thời tiết.")
else:
    log("WARN", "Thiếu WEATHER_API_KEY. Hủy bỏ chức năng thời tiết.")

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
adminId = os.getenv("ADMIN_ID")

def runScheduler():
    schedule.every().day.at("05:00").do(cronService.autoCheckAndNotify, bot)
    schedule.every().day.at("12:00").do(cronService.autoCheckAndNotify, bot)
    schedule.every().day.at("17:00").do(cronService.autoCheckAndNotify, bot)
    schedule.every().day.at("19:00").do(cronService.autoCheckAndNotify, bot, 1)
    schedule.every().monday.at("19:00").do(cronService.autoScanAllUsers, bot)
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    if not db.initDb():
        log("CRITICAL", "Không thể khởi tạo PostgreSQL. Dừng hệ thống!")
        sys.exit(1)

    if weather_enabled:
        task.updateWeatherTask.delay()

    teleBot.registerHandlers(bot)

    threading.Thread(
        target=runScheduler,
        daemon=True
    ).start()

    log("SYSTEM", "Bot UTH v2.3.3 đã sẵn sàng!")

    try:
        bot.infinity_polling(
            timeout=20,
            long_polling_timeout=5
        )

    except KeyboardInterrupt:
        log("SYSTEM", "Đang dừng Bot UTH...")

    except Exception as e:
        log("CRITICAL", f"Bot polling bị dừng do lỗi: {e}")
        raise

    finally:
        db.closeDbPool()