#!/usr/bin/env python3
"""
Stealth Telegram Downloader — JSON Recovery Edition Entry Point
"""

import sys
from stealth_dl.config import DOWNLOAD_DIR, ALLOWED_USER_ID, PARALLEL_WORKERS, IGNITION_DELAY
from stealth_dl.state import IS_TTY, log
from stealth_dl.bot import bot, run_daemon

if __name__ == "__main__":
    if not IS_TTY:
        log.info("━" * 60)
        log.info("  ANTI-GRAVITY STEALTH DOWNLOADER — JSON Recovery Edition")
        log.info("  Target dir : %s", DOWNLOAD_DIR)
        log.info("  Authorized : %s", ALLOWED_USER_ID)
        log.info("  Engine     : %d-worker parallel connection pool", PARALLEL_WORKERS)
        log.info("  Ignition   : %ds delay", IGNITION_DELAY)
        log.info("  Queue mode : sequential (persistent recovery-enabled)")
        log.info("  Commands   : /pause /resume /cancel /queue /clear")
        log.info("━" * 60)

    try:
        bot.loop.run_until_complete(run_daemon())
    except KeyboardInterrupt:
        log.info("🛑 Daemon terminated by user.")
