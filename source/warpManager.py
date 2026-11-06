# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# warpManager.py

import os
import random
import threading
from app_logger import log


class WarpManager:
    def __init__(self):
        raw_proxies = os.getenv("WARP_PROXIES", "")
        if raw_proxies:
            self.proxies = [p.strip() for p in raw_proxies.split(",") if p.strip()]
        else:
            single = os.getenv("WARP_PROXY_URL", "socks5://uth_warp:1080")
            self.proxies = [single]

        self._round_robin_idx = 0
        self._lock = threading.Lock()

    def _get_redis(self):
        try:
            import redisManager
            return redisManager.redisClient
        except Exception:
            return None

    def is_blocked(self, proxy_url):
        r = self._get_redis()
        if not r:
            return False
        try:
            return bool(r.exists(f"proxy:blocked:{proxy_url}"))
        except Exception:
            return False

    def mark_blocked(self, proxy_url, reason="429", cooldown_seconds=180):
        r = self._get_redis()
        if r:
            try:
                r.set(f"proxy:blocked:{proxy_url}", str(reason), ex=cooldown_seconds)
                log("WARN", f"Proxy {proxy_url} bị tạm dừng trong {cooldown_seconds}s do dính lỗi: {reason}")
            except Exception as e:
                log("ERROR", f"Không thể lưu trạng thái blocked proxy vào Redis: {e}")

    def get_proxy(self):
        if not self.proxies:
            return os.getenv("WARP_PROXY_URL", "socks5://uth_warp:1080")

        if len(self.proxies) == 1:
            return self.proxies[0]

        healthy = [p for p in self.proxies if not self.is_blocked(p)]

        if healthy:
            with self._lock:
                selected = healthy[self._round_robin_idx % len(healthy)]
                self._round_robin_idx += 1
            return selected

        log("WARN", "Tất cả proxy trong pool đều bị chặn. Chọn tạm proxy có thời gian chờ ngắn nhất.")
        r = self._get_redis()
        if r:
            try:
                min_ttl = float("inf")
                best_proxy = self.proxies[0]
                for p in self.proxies:
                    ttl = r.ttl(f"proxy:blocked:{p}")
                    if ttl < min_ttl:
                        min_ttl = ttl
                        best_proxy = p
                return best_proxy
            except Exception:
                pass

        return random.choice(self.proxies)

    def get_status(self):
        r = self._get_redis()
        status_list = []
        for p in self.proxies:
            blocked = False
            ttl = 0
            if r:
                try:
                    ttl = r.ttl(f"proxy:blocked:{p}")
                    blocked = ttl > 0
                except Exception:
                    pass
            status_list.append({
                "proxy": p,
                "healthy": not blocked,
                "cooldown_remaining": max(0, ttl) if blocked else 0
            })
        return status_list


warp_manager = WarpManager()
