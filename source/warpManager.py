# Copyright (C) 2026 vanphat111 <phathovan14122006@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# warpManager.py

import docker
import time
from utils import log

class WarpManager:
    def __init__(self, container_name="uth_warp"):
        self.container_name = container_name
        try:
            self.client = docker.from_env()
        except Exception as e:
            log("ERROR", f"Không thể kết nối Docker Socket: {e}")
            self.client = None

    def restart_warp(self):
        if not self.client: return False
        try:
            from utils import log

            container = self.client.containers.get(self.container_name)
            log("SYSTEM", f"Đang khởi động lại {self.container_name}...")
            container.restart()
            time.sleep(5)
            log("SUCCESS", "WARP đã được khởi động lại thành công.")
            return True
        except Exception as e:
            log("ERROR", f"Lỗi khi restart WARP: {e}")
            return False

    def change_identity(self):
        if not self.client: return False
        try:
            container = self.client.containers.get(self.container_name)
            log("SYSTEM", "Đang làm mới danh tính WARP (New Registration)...")
            
            container.exec_run("rm -rf /var/lib/cloudflare-warp/registration.json")
            container.restart()
            
            time.sleep(7)
            log("SUCCESS", "Đã đổi danh tính WARP thành công.")
            return True
        except Exception as e:
            log("ERROR", f"Lỗi khi đổi danh tính WARP: {e}")
            return False

    def get_status(self):
        if not self.client: return "Unknown"
        try:
            container = self.client.containers.get(self.container_name)
            return container.status
        except:
            return "Not Found"

warp_manager = WarpManager()