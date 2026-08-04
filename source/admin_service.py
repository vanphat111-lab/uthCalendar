# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import datetime
import html

import database as db
import redisManager
from celeryApp import app
from utils import log


BROADCAST_STATE_TTL = 10 * 60


def save_broadcast_draft(admin_id: int | str, content: str) -> bool:
    try:
        redisManager.redisClient.set(
            f"admin:broadcast:{admin_id}",
            content,
            ex=BROADCAST_STATE_TTL,
        )
        return True
    except Exception as exc:
        log("ERROR", f"Không thể lưu broadcast draft của admin {admin_id}: {exc}")
        return False


def get_broadcast_draft(admin_id: int | str) -> str | None:
    try:
        return redisManager.redisClient.get(f"admin:broadcast:{admin_id}")
    except Exception as exc:
        log("ERROR", f"Không thể đọc broadcast draft của admin {admin_id}: {exc}")
        return None


def delete_broadcast_draft(admin_id: int | str) -> None:
    try:
        redisManager.redisClient.delete(f"admin:broadcast:{admin_id}")
    except Exception as exc:
        log("WARN", f"Không thể xóa broadcast draft của admin {admin_id}: {exc}")


def get_admin_overview(bot) -> str:
    total_users = db.countUsers()

    notify_portal = _count_scalar(
        "SELECT COUNT(*) FROM users WHERE notify_enabled = TRUE"
    )
    notify_deadline = _count_scalar(
        "SELECT COUNT(*) FROM users WHERE notify_deadline = TRUE"
    )
    pending_retention = _count_scalar(
        "SELECT COUNT(*) FROM users WHERE retention_requested_at IS NOT NULL"
    )
    deleted_last_30_days = _count_scalar(
        """
        SELECT COUNT(*)
        FROM user_deletion_logs
        WHERE deleted_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
        """
    )

    postgres_status = _check_postgres()
    redis_status = _check_redis()
    telegram_status = _check_telegram(bot)
    worker_status = _check_celery_workers()

    return (
        "📊 <b>TỔNG QUAN HỆ THỐNG</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Tổng user:</b> {total_users}\n"
        f"🔔 <b>Bật nhắc lịch:</b> {notify_portal}\n"
        f"📚 <b>Bật deadline:</b> {notify_deadline}\n"
        f"⏳ <b>Chờ retention:</b> {pending_retention}\n"
        f"🗑️ <b>Đã xóa trong 30 ngày:</b> {deleted_last_30_days}\n\n"
        "🏗️ <b>HẠ TẦNG</b>\n"
        f"├ PostgreSQL: {postgres_status}\n"
        f"├ Redis: {redis_status}\n"
        f"├ Telegram API: {telegram_status}\n"
        f"└ Celery worker: {worker_status}\n\n"
        f"🕒 <i>Cập nhật: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}</i>"
    )


def get_retention_stats() -> str:
    pending = _count_scalar(
        "SELECT COUNT(*) FROM users WHERE retention_requested_at IS NOT NULL"
    )
    expiring_soon = _count_scalar(
        """
        SELECT COUNT(*)
        FROM users
        WHERE retention_requested_at IS NOT NULL
          AND retention_requested_at <= CURRENT_TIMESTAMP - INTERVAL '36 hours'
          AND retention_requested_at > CURRENT_TIMESTAMP - INTERVAL '48 hours'
        """
    )
    expired = _count_scalar(
        """
        SELECT COUNT(*)
        FROM users
        WHERE retention_requested_at IS NOT NULL
          AND retention_requested_at <= CURRENT_TIMESTAMP - INTERVAL '48 hours'
        """
    )
    confirmed_last_30_days = _count_scalar(
        """
        SELECT COUNT(*)
        FROM users
        WHERE last_retention_confirmed_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
        """
    )
    deleted_timeout = _count_scalar(
        """
        SELECT COUNT(*)
        FROM user_deletion_logs
        WHERE reason = 'retention_timeout'
          AND deleted_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
        """
    )
    deleted_unreachable = _count_scalar(
        """
        SELECT COUNT(*)
        FROM user_deletion_logs
        WHERE reason = 'telegram_unreachable'
          AND deleted_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
        """
    )

    return (
        "📊 <b>THỐNG KÊ RETENTION</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"⏳ Đang chờ phản hồi: <b>{pending}</b>\n"
        f"⚠️ Còn dưới 12 giờ: <b>{expiring_soon}</b>\n"
        f"⌛ Đã quá 48 giờ: <b>{expired}</b>\n"
        f"✅ Xác nhận trong 30 ngày: <b>{confirmed_last_30_days}</b>\n"
        f"🗑️ Xóa do timeout trong 30 ngày: <b>{deleted_timeout}</b>\n"
        f"🚫 Xóa do không thể liên hệ trong 30 ngày: <b>{deleted_unreachable}</b>"
    )


def format_broadcast_preview(content: str) -> str:
    return (
        "👁️ <b>XEM TRƯỚC BROADCAST</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "📢 <b>THÔNG BÁO MỚI</b>\n\n"
        f"{content}\n\n"
        "<i>Chúc bạn học tốt!</i>"
    )


def escape_for_plain_preview(content: str) -> str:
    return html.escape(content)


def _count_scalar(query: str) -> int:
    try:
        row = db.fetchOne(query)
        return int(row[0]) if row else 0
    except Exception as exc:
        log("ERROR", f"Lỗi lấy thống kê admin: {exc}")
        return 0


def _check_postgres() -> str:
    try:
        ok, latency_ms = db.checkDbHealth()
        return f"🟢 {latency_ms} ms" if ok else "🔴 Lỗi"
    except Exception as exc:
        log("WARN", f"Admin health check PostgreSQL lỗi: {exc}")
        return "🔴 Lỗi"


def _check_redis() -> str:
    try:
        return "🟢 Hoạt động" if redisManager.redisClient.ping() else "🔴 Lỗi"
    except Exception as exc:
        log("WARN", f"Admin health check Redis lỗi: {exc}")
        return "🔴 Lỗi"


def _check_telegram(bot) -> str:
    try:
        bot.get_me()
        return "🟢 Hoạt động"
    except Exception as exc:
        log("WARN", f"Admin health check Telegram lỗi: {exc}")
        return "🔴 Lỗi"


def _check_celery_workers() -> str:
    try:
        replies = app.control.inspect(timeout=1.0).ping() or {}
        worker_count = len(replies)
        return f"🟢 {worker_count} worker" if worker_count else "🔴 Không phản hồi"
    except Exception as exc:
        log("WARN", f"Admin health check Celery lỗi: {exc}")
        return "🔴 Không phản hồi"
