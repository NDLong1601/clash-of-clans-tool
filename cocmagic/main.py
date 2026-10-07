#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CocMagic — main.py
Entry point: load settings → khởi động BotEngine.
"""

import sys
import os
import argparse
import getpass
import threading
import time

# Đảm bảo in ký tự UTF-8 không lỗi trên Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from cocmagic import config
from cocmagic.bot_engine import BotEngine
from cocmagic.license_client import LicenseClient, LicenseError


def parse_args():
    parser = argparse.ArgumentParser(
        description="CocMagic — Clash of Clans Auto Bot (Open Source)"
    )
    parser.add_argument(
        "--settings", "-s",
        default=config.SETTINGS_FILE,
        help=f"Đường dẫn file settings JSON (mặc định: {config.SETTINGS_FILE})"
    )
    parser.add_argument(
        "--port", "-p",
        type=int, default=None,
        help="ADB port (mặc định: auto-detect)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="In log chi tiết hơn"
    )
    parser.add_argument("--activate", action="store_true",
                        help="Nhập và kích hoạt key trên máy này")
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        license_client = LicenseClient.from_config()
        if args.activate:
            if not license_client.policy.enabled:
                print("[License] Bản thử cấp phép chưa được bật trong data/license-config.json.")
                return
            key = getpass.getpass("Nhập key CocMagic: ")
            result = license_client.check(key, remember=True)
            print(f"[License] {result.label()}")
            return
        license_result = license_client.check() if license_client.policy.enabled else None
    except LicenseError as error:
        print(f"[License] {error}")
        sys.exit(2)

    # Load settings
    if args.settings != config.SETTINGS_FILE:
        config.SETTINGS_FILE = args.settings

    settings = config.load_settings()

    # Override từ CLI
    if args.port:
        config.ADB_PORT = args.port
    if args.verbose:
        settings["verbose"] = True

    # Tạo settings.json mặc định nếu chưa có
    if not os.path.exists(config.SETTINGS_FILE):
        config.save_settings(settings)
        print(f"[Main] Đã tạo settings.json mặc định: {config.SETTINGS_FILE}")
        print("[Main] Hãy chỉnh settings.json theo ý muốn rồi chạy lại.")
        print()

    # Kiểm tra assets
    if not os.path.isdir(config.ASSETS_DIR):
        print(f"[Main] ❌ Không tìm thấy thư mục assets: {config.ASSETS_DIR}")
        print(f"[Main]    Hãy copy thư mục assets/ từ XMagic vào: {config.BASE_DIR}")
        sys.exit(1)

    # Khởi động bot
    if license_result is None:
        engine = BotEngine(settings)
        engine.start()
        return

    stop_event = threading.Event()
    watchdog_done = threading.Event()

    def watch_license():
        last_ok = time.monotonic()
        expiry_deadline = (None if license_result.expires_at is None else
                           last_ok + license_result.expires_at - license_result.server_time)
        delay = license_client.policy.check_interval_seconds
        while not watchdog_done.wait(delay):
            if expiry_deadline is not None and time.monotonic() >= expiry_deadline:
                print("[License] Key đã hết hạn; đang dừng bot.")
                stop_event.set()
                return
            try:
                renewed = license_client.check()
                last_ok = time.monotonic()
                expiry_deadline = (None if renewed.expires_at is None else
                                   last_ok + renewed.expires_at - renewed.server_time)
                delay = license_client.policy.check_interval_seconds
            except LicenseError as error:
                if (error.temporary and
                        time.monotonic() - last_ok <= license_client.policy.offline_grace_seconds and
                        (expiry_deadline is None or time.monotonic() < expiry_deadline)):
                    print(f"[License] {error}; sẽ kiểm tra lại.")
                    delay = 60
                    continue
                print(f"[License] {error}; đang dừng bot.")
                stop_event.set()
                return

    watcher = threading.Thread(target=watch_license, name="CocMagic-license", daemon=True)
    watcher.start()
    try:
        BotEngine(settings, stop_event=stop_event).start()
    finally:
        watchdog_done.set()
        watcher.join(timeout=1)


if __name__ == "__main__":
    main()
