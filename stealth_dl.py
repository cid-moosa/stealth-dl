#!/bin/bash
"exec" "$(dirname "$0")/venv/bin/python" "$0" "$@" 2>/dev/null || "exec" python3 "$0" "$@"
# -*- coding: utf-8 -*-
"""
Stealth Telegram Downloader — Entry Point with Venv Auto-Reexec
"""

import os
import sys

# Self-bootstrapping venv launcher: re-exec under local ./venv if available
base_dir = os.path.dirname(os.path.abspath(__file__))
venv_python = os.path.join(base_dir, "venv", "bin", "python")
if os.name != "nt" and os.path.exists(venv_python) and os.path.abspath(sys.executable) != os.path.abspath(venv_python):
    os.execv(venv_python, [venv_python] + sys.argv)

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
