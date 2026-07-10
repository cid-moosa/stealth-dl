import os
import sys
import logging
import asyncio

IS_TTY = sys.stdout.isatty() and not os.getenv("CI") and not os.getenv("NO_COLOR")

log = logging.getLogger("stealth-dl")
log.setLevel(logging.INFO)

recent_logs = []

# Sequential queue for bulk drops
download_queue: asyncio.Queue = asyncio.Queue()

# Ignition fuse tracker — maps ignition_msg.id → asyncio.Event
ignition_pending: dict = {}

# Active download state — shared between worker + command handlers
active_download = {
    "state": "idle",       # idle | downloading | paused | cancelled
    "offset": 0,           # bytes downloaded so far
    "total": 0,            # total file size in bytes
    "path": "",            # destination file path on disk
    "filename": "",        # original filename string
    "pause_event": None,   # asyncio.Event — cleared=paused, set=running
    "status_msg": None,    # Telegram message object for live edits
    "live_speed": 0,
    "avg_speed": 0,
    "elapsed": "0s",
    "eta": "calculating…",
}
