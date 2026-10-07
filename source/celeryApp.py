# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# celeryApp.py

from celery import Celery
from celery.schedules import crontab
import os
from celery.signals import worker_process_init, worker_process_shutdown

import database as db
from utils import log
import utils


REDIS_URL = os.getenv('CELERY_BROKER_URL', 'redis://uth_redis:6379/0')

app = Celery('uth_bot', broker=REDIS_URL, backend=REDIS_URL)

@worker_process_init.connect
def initWorkerDbPool(**kwargs):
    try:
        db.resetDbPool()
        log("INFO", "Đã khởi tạo PostgreSQL pool cho Celery worker.")

    except Exception as e:
        log("CRITICAL", f"Không thể khởi tạo PostgreSQL pool cho Celery worker: {e}")
        raise


@worker_process_shutdown.connect
def closeWorkerDbPool(**kwargs):
    db.closeDbPool()

app.conf.update(
    task_serializer='json',
    timezone=utils.TZ_NAME,
    enable_utc=True,
    task_routes={
        'tasks.portalTask': {'queue': 'high_priority'},
        'tasks.deadlineTask': {'queue': 'high_priority'},
        'tasks.registrationTask': {'queue': 'high_priority'},
        'tasks.systemStatusTask': {'queue': 'high_priority'},
        'tasks.donateTask': {'queue': 'high_priority'},
        
        'tasks.periodicPortalTask': {'queue': 'low_priority'},
        'tasks.periodicCourseTask': {'queue': 'low_priority'},
        'tasks.checkPaymentTask': {'queue': 'low_priority'},
        'tasks.retentionMaintenanceTask': {'queue': 'low_priority'},
        'tasks.retentionRequestAllTask': {'queue': 'low_priority'},
        'tasks.adminBroadcastTask': {'queue': 'low_priority'},
        'tasks.adminRetentionCleanupTask': {'queue': 'low_priority'},
        'tasks.adminRetentionMaintenanceTask': {'queue': 'low_priority'},
        'tasks.adminPortalScanTask': {'queue': 'low_priority'},
        'tasks.adminDeadlineScanTask': {'queue': 'low_priority'},
        'tasks.adminUpdateWeatherTask': {'queue': 'low_priority'},
    }
)

app.conf.beat_schedule = {
    'retention-maintenance-daily': {
        'task': 'tasks.retentionMaintenanceTask',
        'schedule': crontab(minute=0, hour=6),
    },
    'update-weather-hourly': {
        'task': 'tasks.updateWeatherTask',
        'schedule': crontab(minute=0, hour='4-22'),
    },
}