# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import os


def get_admin_chat_ids() -> set[int]:
    """Read admin chat IDs from ENV.

    ADMIN_CHAT_IDS supports comma-separated IDs. ADMIN_ID is kept as a
    backward-compatible fallback for the current deployment.
    """
    raw_values = []

    admin_chat_ids = os.getenv("ADMIN_CHAT_IDS", "")
    if admin_chat_ids:
        raw_values.extend(admin_chat_ids.split(","))

    legacy_admin_id = os.getenv("ADMIN_ID", "")
    if legacy_admin_id:
        raw_values.append(legacy_admin_id)

    result: set[int] = set()
    for raw_value in raw_values:
        value = raw_value.strip()
        if not value:
            continue

        try:
            result.add(int(value))
        except ValueError:
            continue

    return result


def is_admin(chat_id: int | str) -> bool:
    try:
        normalized_chat_id = int(chat_id)
    except (TypeError, ValueError):
        return False

    return normalized_chat_id in get_admin_chat_ids()


def get_primary_admin_id() -> int | None:
    admin_ids = sorted(get_admin_chat_ids())
    return admin_ids[0] if admin_ids else None
