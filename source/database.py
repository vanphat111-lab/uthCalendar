# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# database.py

import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator, Sequence

from psycopg2 import InterfaceError, OperationalError
from psycopg2.extensions import STATUS_READY, connection as PgConnection
from psycopg2.extras import RealDictCursor
from psycopg2.pool import PoolError, ThreadedConnectionPool

from utils import log


DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "10")),
    "application_name": os.getenv(
        "DB_APPLICATION_NAME",
        "uth-calendar",
    ),
}

DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "2"))

_pool: ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()

def initDbPool() -> ThreadedConnectionPool:
    global _pool

    if _pool is not None:
        return _pool

    with _pool_lock:
        if _pool is None:
            if DB_POOL_MIN < 1:
                raise ValueError("DB_POOL_MIN phải lớn hơn hoặc bằng 1")

            if DB_POOL_MAX < DB_POOL_MIN:
                raise ValueError("DB_POOL_MAX phải lớn hơn hoặc bằng DB_POOL_MIN")

            log("SYSTEM", ("Đang khởi tạo PostgreSQL connection pool " f"({DB_POOL_MIN}-{DB_POOL_MAX})..."))

            _pool = ThreadedConnectionPool(
                minconn=DB_POOL_MIN,
                maxconn=DB_POOL_MAX,
                **DB_CONFIG)

            log("INFO", "PostgreSQL connection pool đã sẵn sàng.")

    return _pool


def closeDbPool() -> None:
    global _pool

    with _pool_lock:
        if _pool is None:
            return

        _pool.closeall()
        _pool = None

        log("INFO", "Đã đóng PostgreSQL connection pool.")


def resetDbPool() -> ThreadedConnectionPool:
    closeDbPool()
    return initDbPool()


def _getPool() -> ThreadedConnectionPool:
    if _pool is None:
        return initDbPool()

    return _pool


def _prepareConnection(conn: PgConnection) -> None:
    if conn.closed:
        raise InterfaceError("Connection trong pool đã bị đóng")

    if conn.status != STATUS_READY:
        conn.rollback()

    conn.autocommit = False


@contextmanager
def transaction(*, dictCursor: bool = False) -> Iterator[tuple[PgConnection, Any]]:

    pool = _getPool()
    conn: PgConnection | None = None
    discard = False

    try:
        conn = pool.getconn()
        _prepareConnection(conn)

        cursorFactory = RealDictCursor if dictCursor else None

        with conn.cursor(cursor_factory = cursorFactory) as cursor:
            yield conn, cursor

        conn.commit()

    except (InterfaceError, OperationalError):
        discard = True

        if conn is not None and not conn.closed:
            try:
                conn.rollback()
            except Exception:
                pass

        raise

    except Exception:
        if conn is not None and not conn.closed:
            try:
                conn.rollback()
            except Exception:
                discard = True

        raise

    finally:
        if conn is not None:
            try:
                shouldClose = discard or bool(conn.closed)
                pool.putconn(conn, close = shouldClose)

            except PoolError as exc:
                log(
                    "ERROR",
                    f"Không thể trả connection về pool: {exc}",
                )


def execute(query: str, params: Sequence[Any] | None = None) -> int:
    with transaction() as (_, cursor):
        cursor.execute(query, params)
        return cursor.rowcount


def fetchOne(query: str, params: Sequence[Any] | None = None, *, dictResult: bool = False) -> Any | None:
    with transaction(dictCursor = dictResult) as (_, cursor):
        cursor.execute(query, params)
        return cursor.fetchone()


def fetchAll(query: str, params: Sequence[Any] | None = None, *, dictResult: bool = False) -> list[Any]:
    with transaction(dictCursor = dictResult) as (_, cursor):
        cursor.execute(query, params)
        return list(cursor.fetchall())


def executeMany(query: str, paramsList: Sequence[Sequence[Any]]) -> int:
    if not paramsList:
        return 0

    with transaction() as (_, cursor):
        cursor.executemany(query, paramsList)
        return cursor.rowcount


def initDb() -> bool:
    log("SYSTEM", "Bắt đầu kiểm tra và khởi tạo Database...")

    maxRetries = int(os.getenv("DB_INIT_RETRIES", "10"))
    retryDelay = int(os.getenv("DB_INIT_RETRY_DELAY", "5"))

    for attempt in range(1, maxRetries + 1):
        try:
            initDbPool()

            with transaction() as (_, cursor):
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        chat_id TEXT PRIMARY KEY,
                        uth_user TEXT NOT NULL,
                        uth_pass TEXT NOT NULL,
                        notify_enabled BOOLEAN DEFAULT TRUE,
                        notify_deadline BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

                cursor.execute(
                    """
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS notify_enabled
                    BOOLEAN DEFAULT TRUE
                    """
                )

                cursor.execute(
                    """
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS notify_deadline
                    BOOLEAN DEFAULT TRUE
                    """
                )

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS completed_tasks (
                        id SERIAL PRIMARY KEY,
                        chat_id TEXT NOT NULL,
                        task_id TEXT NOT NULL,
                        completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(chat_id, task_id)
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_completed_tasks_chat_id
                    ON completed_tasks (chat_id)
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_users_notify_enabled
                    ON users (notify_enabled)
                    WHERE notify_enabled = TRUE
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_users_notify_deadline
                    ON users (notify_deadline)
                    WHERE notify_deadline = TRUE
                    """
                )

            log(
                "INFO", ("Hệ thống Database đã sẵn sàng " "(Users & Completed Tasks)."))
            return True

        except Exception as exc:
            log("RETRY", (f"DB chưa sẵn sàng " f"[{attempt}/{maxRetries}]: {exc}"))

            closeDbPool()

            if attempt < maxRetries:
                time.sleep(retryDelay)

    log("ERROR", ("Không thể khởi tạo Database sau " f"{maxRetries} lần thử."))
    return False


def checkDbHealth() -> tuple[bool, int]:
    startTime = time.perf_counter()

    try:
        result = fetchOne("SELECT 1")
        latencyMs = round(
            (time.perf_counter() - startTime) * 1000
        )

        return bool(result and result[0] == 1), latencyMs

    except Exception as exc:
        latencyMs = round(
            (time.perf_counter() - startTime) * 1000
        )

        log("ERROR", f"Database health check thất bại: {exc}")

        return False, latencyMs


def getCompletedTaskIds(chatId: int | str) -> list[str]:
    try:
        rows = fetchAll(
            """
            SELECT task_id
            FROM completed_tasks
            WHERE chat_id = %s
            """,
            (str(chatId),),
        )

        return [row[0] for row in rows]

    except Exception as exc:
        log("ERROR", ("Lỗi lấy danh sách task hoàn thành " f"của user {chatId}: {exc}"))
        return []


def markTaskCompleted(chatId: int | str, taskId: int | str) -> bool:
    try:
        execute(
            """
            INSERT INTO completed_tasks (
                chat_id,
                task_id
            )
            VALUES (%s, %s)
            ON CONFLICT (chat_id, task_id)
            DO NOTHING
            """,
            (
                str(chatId),
                str(taskId),
            ),
        )

        return True

    except Exception as exc:
        log("ERROR", (f"Lỗi đánh dấu task {taskId} hoàn thành " f"cho user {chatId}: {exc}"))
        return False


def unmarkTaskCompleted(chatId: int | str, taskId: int | str) -> bool:
    try:
        execute(
            """
            DELETE FROM completed_tasks
            WHERE chat_id = %s
              AND task_id = %s
            """,
            (
                str(chatId),
                str(taskId),
            ),
        )

        return True

    except Exception as exc:
        log("ERROR", (f"Lỗi bỏ đánh dấu task {taskId} " f"của user {chatId}: {exc}"))
        return False


def getUserCredentials(chatId: int | str) -> dict[str, Any] | None:
    try:
        row = fetchOne(
            """
            SELECT
                chat_id,
                uth_user,
                uth_pass,
                notify_enabled,
                notify_deadline,
                created_at
            FROM users
            WHERE chat_id = %s
            """,
            (str(chatId),),
            dictResult=True,
        )

        return dict(row) if row else None

    except Exception as exc:
        log("ERROR", f"Lỗi lấy user {chatId}: {exc}")
        return None


def upsertUserCredentials(chatId: int | str, encryptedUser: str, encryptedPassword: str) -> bool:
    try:
        execute(
            """
            INSERT INTO users (
                chat_id,
                uth_user,
                uth_pass
            )
            VALUES (%s, %s, %s)
            ON CONFLICT (chat_id)
            DO UPDATE SET
                uth_user = EXCLUDED.uth_user,
                uth_pass = EXCLUDED.uth_pass
            """,
            (
                str(chatId),
                encryptedUser,
                encryptedPassword,
            ),
        )

        return True

    except Exception as exc:
        log("ERROR", ("Lỗi lưu thông tin đăng nhập " f"của user {chatId}: {exc}"))
        return False


def updateDeadlineStatus(chatId: int | str, status: bool) -> bool:
    try:
        affectedRows = execute(
            """
            UPDATE users
            SET notify_deadline = %s
            WHERE chat_id = %s
            """,
            (
                bool(status),
                str(chatId),
            ),
        )

        return affectedRows > 0

    except Exception as exc:
        log("ERROR", ("Lỗi cập nhật trạng thái nhắc deadline " f"của user {chatId}: {exc}"))
        return False


def updateNotifyStatus(chatId: int | str, status: bool) -> bool:
    try:
        affectedRows = execute(
            """
            UPDATE users
            SET notify_enabled = %s
            WHERE chat_id = %s
            """,
            (
                bool(status),
                str(chatId),
            ),
        )

        return affectedRows > 0

    except Exception as exc:
        log("ERROR", ("Lỗi cập nhật trạng thái nhắc lịch " f"của user {chatId}: {exc}"))
        return False


def getDeadlineStatus(chatId: int | str) -> bool:
    try:
        row = fetchOne(
            """
            SELECT notify_deadline
            FROM users
            WHERE chat_id = %s
            """,
            (str(chatId),),
        )

        return bool(row[0]) if row else True

    except Exception as exc:
        log("ERROR", ("Lỗi lấy trạng thái nhắc deadline " f"của user {chatId}: {exc}"))
        return True


def getUsersForPortalNotify() -> list[str]:
    try:
        rows = fetchAll(
            """
            SELECT chat_id
            FROM users
            WHERE notify_enabled = TRUE
            """
        )

        return [row[0] for row in rows]

    except Exception as exc:
        log("ERROR", f"Lỗi lấy danh sách Portal Notify: {exc}")
        return []


def getUsersForDeadlineNotify() -> list[str]:
    try:
        rows = fetchAll(
            """
            SELECT chat_id
            FROM users
            WHERE notify_deadline = TRUE
            """
        )

        return [row[0] for row in rows]

    except Exception as exc:
        log(
            "ERROR",
            f"Lỗi lấy danh sách Deadline Notify: {exc}",
        )
        return []


def getAllUserIds() -> list[str]:
    try:
        rows = fetchAll(
            """
            SELECT chat_id
            FROM users
            ORDER BY created_at ASC
            """
        )

        return [row[0] for row in rows]

    except Exception as exc:
        log("ERROR", f"Lỗi lấy toàn bộ user: {exc}")
        return []


def countUsers() -> int:
    try:
        row = fetchOne(
            """
            SELECT COUNT(*)
            FROM users
            """
        )

        return int(row[0]) if row else 0

    except Exception as exc:
        log("ERROR", f"Lỗi đếm số user: {exc}")
        return 0