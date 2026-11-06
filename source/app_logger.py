# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# app_logger.py

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from zoneinfo import ZoneInfo

TZ_NAME = os.getenv("TZ", "Asia/Ho_Chi_Minh").strip()
try:
    APP_TZ = ZoneInfo(TZ_NAME)
except Exception:
    APP_TZ = None


class TimezoneFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        if APP_TZ:
            dt = datetime.fromtimestamp(record.created, tz=APP_TZ)
        else:
            dt = datetime.fromtimestamp(record.created)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%d/%m/%Y %H:%M:%S")


def setup_logger():
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logger = logging.getLogger("uth")
    logger.setLevel(log_level)

    if logger.handlers:
        return logger

    formatter = TimezoneFormatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%d/%m/%Y %H:%M:%S"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_file = os.getenv("LOG_FILE", "logs/uth.log")
    try:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as exc:
        sys.stderr.write(f"Không thể khởi tạo file log tại {log_file}: {exc}\n")

    return logger


logger = setup_logger()


def log(level: str, message: str, exc_info=None):
    lvl = str(level).upper()
    if lvl in ("INFO", "SUCCESS", "WORKER", "START", "DONE"):
        logger.info(message)
    elif lvl in ("WARN", "WARNING", "TIMEOUT"):
        logger.warning(message)
    elif lvl == "ERROR":
        logger.error(message, exc_info=exc_info)
    elif lvl in ("CRITICAL", "FATAL"):
        logger.critical(message, exc_info=exc_info)
    elif lvl in ("DEBUG", "REDIS"):
        logger.debug(message)
    else:
        logger.info(f"[{level}] {message}")
