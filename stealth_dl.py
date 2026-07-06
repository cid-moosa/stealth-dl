#!/usr/bin/env python3
"""
Stealth Multi-Threaded Telegram Downloader — JSON Recovery Edition
──────────────────────────────────────────────────────────────────
A private, high-speed media downloader daemon with:
  • Local JSON-based Queue Persistence (pending_queue.json)
  • Safe Boot-Time Reconstruction via bot.get_messages()
  • Smart Resume using local chunk-state tracking (.state files)
  • Auto-delete original messages on successful completion
  • Multi-connection Parallel Chunk Downloader (MTProto Sender Pool)
  • 5-second ignition delay with inline cancel button
  • /clear command to wipe chat history
  • /cancel /pause /resume interactive stream control
  • asyncio.Queue sequential queue for bulk drops
  • Reconnect Watchdog to keep the bot online continuously
"""

# ──────────────────────────── Stdlib ────────────────────────────────
import os
import sys
import time
import json
import math
import asyncio
import logging
import traceback
from typing import Optional, Union, AsyncGenerator

# ──────────────────────────── Third-party ───────────────────────────
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button, utils, helpers
from telethon.errors import FloodWaitError
from telethon.network import MTProtoSender
from telethon.tl.alltlobjects import LAYER
from telethon.tl.functions import InvokeWithLayerRequest
from telethon.tl.functions.auth import ExportAuthorizationRequest, ImportAuthorizationRequest
from telethon.tl.functions.upload import GetFileRequest
from telethon.tl.types import (
    Document, InputFileLocation, InputDocumentFileLocation,
    InputPhotoFileLocation, InputPeerPhotoFileLocation, Photo
)
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live

# Load environment variables from .env file if it exists
load_dotenv()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API_ID: int          = int(os.getenv("TG_API_ID", "0"))  # TG_API_ID_PLACEHOLDER
API_HASH: str        = os.getenv("TG_API_HASH", "")  # TG_API_HASH_PLACEHOLDER
BOT_TOKEN: str       = os.getenv("TG_BOT_TOKEN", "")  # TG_BOT_TOKEN_PLACEHOLDER
ALLOWED_USER_ID: int = int(os.getenv("TG_ALLOWED_USER_ID", "0"))  # TG_ALLOWED_USER_ID_PLACEHOLDER
DOWNLOAD_DIR: str    = os.getenv("TG_DOWNLOAD_DIR", "/DATA/Media/Movies/")  # TG_DOWNLOAD_DIR_PLACEHOLDER

# ── Daemon Run-Safe Gate ──────────────────────────────────────────
if not API_ID or not API_HASH or not BOT_TOKEN or not ALLOWED_USER_ID:
    print("[x] Error: Configuration is incomplete.")
    print("Please run 'install.bat' (Windows) or 'install.sh' (Linux) to configure your credentials.")
    sys.exit(1)

# Ensure absolute path with trailing slash
if not DOWNLOAD_DIR.endswith("/") and not DOWNLOAD_DIR.endswith("\\"):
    DOWNLOAD_DIR += "/"

# ── Speed Parameters ────────────────────────────────────────────────
PARALLEL_WORKERS: int = 8             # Number of concurrent connection senders
IGNITION_DELAY: int   = 5             # seconds before auto-queue

# Path to the queue recovery database file
QUEUE_FILE: str       = os.path.join(DOWNLOAD_DIR, "pending_queue.json")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LOGGING & TUI DETECTOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IS_TTY = sys.stdout.isatty() and not os.getenv("CI") and not os.getenv("NO_COLOR")

log = logging.getLogger("stealth-dl")
log.setLevel(logging.INFO)

recent_logs = []

if IS_TTY:
    class LiveLogHandler(logging.Handler):
        def emit(self, record):
            try:
                msg = self.format(record)
                if record.levelno >= logging.ERROR:
                    msg = f"[bold red]❌ {msg}[/bold red]"
                elif record.levelno >= logging.WARNING:
                    msg = f"[yellow]⚠️ {msg}[/yellow]"
                else:
                    msg = f"[white]⚙️ {msg}[/white]"
                recent_logs.append(msg)
                if len(recent_logs) > 9:
                    recent_logs.pop(0)
            except Exception:
                self.handleError(record)

    h = LiveLogHandler()
    h.setFormatter(logging.Formatter("%(asctime)s │ %(message)s", datefmt="%H:%M:%S"))
    log.addHandler(h)
else:
    # Standard terminal/file logging
    standard_handler = logging.StreamHandler(sys.stdout)
    standard_handler.setFormatter(logging.Formatter("%(asctime)s │ %(levelname)-8s │ %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    log.addHandler(standard_handler)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BOOT — defensive directory creation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    log.info("Created download directory: %s", DOWNLOAD_DIR)
else:
    log.info("Download directory verified: %s", DOWNLOAD_DIR)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CLIENT INSTANTIATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
bot = TelegramClient("stealth_bot", API_ID, API_HASH)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GLOBAL STATE — queue, download tracker, ignition fuses
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

# ─────────────────────── Helpers ────────────────────────────────────

def _human_size(size_bytes: float) -> str:
    """Convert raw bytes to a human-readable string (B / KB / MB / GB)."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"


def _elapsed(start: float) -> str:
    """Return a formatted elapsed-time string."""
    delta = time.time() - start
    mins, secs = divmod(int(delta), 60)
    return f"{mins}m {secs}s" if mins else f"{secs}s"


def _get_file_info(message):
    """Extract filename and file size from a Telegram message."""
    file_name = None
    file_size = 0

    if message.document:
        file_size = message.document.size or 0
        for attr in (message.document.attributes or []):
            if hasattr(attr, "file_name"):
                file_name = attr.file_name
                break

    if not file_name:
        ext = ".bin"
        if message.photo:
            ext = ".jpg"
        elif message.video:
            ext = ".mp4"
        elif message.voice:
            ext = ".ogg"
        elif message.audio:
            ext = ".mp3"
        file_name = f"tg_{int(time.time())}{ext}"

    return file_name, file_size


def _make_progress_bar(pct: float, width: int = 15) -> str:
    """Create a high-precision Unicode partial-block progress bar."""
    if pct < 0:
        pct = 0.0
    elif pct > 100:
        pct = 100.0
    
    filled_width = (pct / 100) * width
    full_blocks = int(filled_width)
    fractional = filled_width - full_blocks
    
    chars = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉"]
    char_idx = int(fractional * 8)
    
    bar = "█" * full_blocks
    if full_blocks < width:
        bar += chars[char_idx]
        bar += "░" * (width - full_blocks - 1)
    return bar


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LOCAL STATE DATABASE FILE OPERATIONS — safely atomic
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _load_pending_queue() -> list:
    """Load the local recovery queue JSON database."""
    if not os.path.exists(QUEUE_FILE):
        return []
    try:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error("⚠️ Failed to load pending queue JSON: %s", e)
        return []


def _save_pending_queue(queue_list: list):
    """Safely persist the pending queue using atomic file renaming."""
    temp_file = f"{QUEUE_FILE}.tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(queue_list, f, indent=2)
        # Atomic replacement survives unexpected power cuts
        os.replace(temp_file, QUEUE_FILE)
    except Exception as e:
        log.error("⚠️ Failed to write pending queue JSON: %s", e)
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except OSError:
                pass


def _load_download_state(dest_path: str, file_size: int) -> set:
    """Load indices of chunks completed in a previous session."""
    state_path = f"{dest_path}.state"
    if not os.path.exists(state_path) or not os.path.exists(dest_path):
        return set()
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("total_size") == file_size:
            return set(data.get("completed_chunks", []))
    except Exception as e:
        log.warning("⚠️ Failed to load download state: %s", e)
    return set()


def _save_download_state(dest_path: str, file_size: int, completed_chunks: set):
    """Persist chunk completion state to a tracker file."""
    state_path = f"{dest_path}.state"
    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({
                "total_size": file_size,
                "completed_chunks": list(completed_chunks)
            }, f)
    except Exception as e:
        log.warning("⚠️ Failed to save download state: %s", e)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CONNECTION POOL PARALLEL DOWNLOAD LOGIC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TypeLocation = Union[
    Document, Photo, InputDocumentFileLocation,
    InputPeerPhotoFileLocation, InputFileLocation, InputPhotoFileLocation
]

class DownloadSender:
    def __init__(self, client: TelegramClient, sender: MTProtoSender, file: TypeLocation,
                 offset: int, limit: int, stride: int, count: int, transferrer: 'ParallelTransferrer') -> None:
        self.client = client
        self.sender = sender
        self.request = GetFileRequest(file, offset=offset, limit=limit)
        self.stride = stride
        self.remaining = count
        self.transferrer = transferrer

    async def next(self) -> bytes:
        if not self.remaining:
            return b""
        
        # Resilient individual connection retries
        for attempt in range(3):
            try:
                result = await self.client._call(self.sender, self.request)
                self.remaining -= 1
                self.request.offset += self.stride
                return result.bytes
            except Exception as e:
                log.warning(f"Connection pool sender error: {e}. Reconnecting stream (attempt {attempt+1}/3)...")
                if attempt < 2:
                    try:
                        await self.sender.disconnect()
                        self.sender = await self.transferrer._create_sender()
                    except Exception as reconn_err:
                        log.error(f"Failed to recreate connection: {reconn_err}")
                    await asyncio.sleep(2)
                else:
                    raise e
        return b""

    async def disconnect(self) -> None:
        try:
            await self.sender.disconnect()
        except Exception:
            pass


class ParallelTransferrer:
    def __init__(self, client: TelegramClient, dc_id: Optional[int] = None) -> None:
        self.client = client
        self.loop = client.loop
        self.dc_id = dc_id or client.session.dc_id
        self.auth_key = (None if dc_id and client.session.dc_id != dc_id
                         else client.session.auth_key)
        self.senders = []

    async def _cleanup(self) -> None:
        if self.senders:
            await asyncio.gather(*[sender.disconnect() for sender in self.senders], return_exceptions=True)
            self.senders = []

    @staticmethod
    def _get_connection_count(file_size: int, max_count: int = 16,
                              full_size: int = 100 * 1024 * 1024) -> int:
        if file_size > full_size:
            return max_count
        return math.ceil((file_size / full_size) * max_count) or 1

    async def _init_download(self, connections: int, file: TypeLocation, part_count: int,
                             part_size: int, start_part: int = 0) -> None:
        remaining_parts = part_count - start_part
        minimum, remainder = divmod(remaining_parts, connections)

        def get_part_count() -> int:
            nonlocal remainder
            if remainder > 0:
                remainder -= 1
                return minimum + 1
            return minimum

        # The first connection exports the session auth keys
        self.senders = []
        first_count = get_part_count()
        if first_count > 0:
            first_sender = await self._create_download_sender(file, start_part, part_size, connections * part_size, first_count)
            self.senders.append(first_sender)

        # Establish remaining connections concurrently
        remaining_tasks = []
        for i in range(1, connections):
            cnt = get_part_count()
            if cnt > 0:
                remaining_tasks.append(self._create_download_sender(file, start_part + i, part_size, connections * part_size, cnt))
        
        if remaining_tasks:
            other_senders = await asyncio.gather(*remaining_tasks)
            self.senders.extend(other_senders)

    async def _create_download_sender(self, file: TypeLocation, index: int, part_size: int,
                                      stride: int, part_count: int) -> DownloadSender:
        sender_conn = await self._create_sender()
        return DownloadSender(self.client, sender_conn, file, index * part_size, part_size, stride, part_count, self)

    async def _create_sender(self) -> MTProtoSender:
        dc = await self.client._get_dc(self.dc_id)
        sender = MTProtoSender(self.auth_key, loggers=self.client._log)
        await sender.connect(self.client._connection(dc.ip_address, dc.port, dc.id,
                                                     loggers=self.client._log,
                                                     proxy=self.client._proxy))
        if not self.auth_key:
            log.debug(f"Exporting auth to DC {self.dc_id}")
            auth = await self.client(ExportAuthorizationRequest(self.dc_id))
            self.client._init_request.query = ImportAuthorizationRequest(id=auth.id, bytes=auth.bytes)
            req = InvokeWithLayerRequest(LAYER, self.client._init_request)
            await sender.send(req)
            self.auth_key = sender.auth_key
        return sender

    async def download(self, file: TypeLocation, file_size: int,
                       part_size_kb: Optional[int] = None,
                       connection_count: Optional[int] = None,
                       start_offset: int = 0) -> AsyncGenerator[bytes, None]:
        connection_count = connection_count or self._get_connection_count(file_size)
        part_size = (part_size_kb or utils.get_appropriated_part_size(file_size)) * 1024
        part_count = math.ceil(file_size / part_size)
        start_part = start_offset // part_size

        await self._init_download(connection_count, file, part_count, part_size, start_part)

        part = start_part
        while part < part_count:
            tasks = []
            active_senders = [s for s in self.senders if s.remaining > 0]
            if not active_senders:
                break

            for sender in active_senders:
                tasks.append(self.loop.create_task(sender.next()))

            for task in tasks:
                data = await task
                if data:
                    yield data
                    part += 1

        await self._cleanup()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HYPER-THREAD DOWNLOAD ENGINE — Multi-Connection Parallel Chunks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _hyper_download(message, dest_path, status_msg, file_size):
    """
    Parallel multi-connection chunk downloader with Smart Resume.
    """
    start_ts = time.time()
    media = message.document or message.photo or message.media
    dc_id, location = utils.get_input_location(media)

    # Calculate part size
    part_size = utils.get_appropriated_part_size(file_size) * 1024

    # ── Load existing state for Smart Resume ────────────────────────
    completed_chunks = _load_download_state(dest_path, file_size)
    start_chunk = 0
    while start_chunk in completed_chunks:
        start_chunk += 1

    start_offset = start_chunk * part_size
    downloaded_bytes = start_offset
    active_download["offset"] = downloaded_bytes

    if start_offset > 0:
        log.info("🔌 Smart Resume: Found %d completed parts. Resuming from %s...",
                 start_chunk, _human_size(start_offset))

    # ── Open / Resume file stream ───────────────────────────────────
    if start_offset > 0 and os.path.exists(dest_path):
        fd = open(dest_path, "r+b")
        fd.seek(start_offset)
    else:
        fd = open(dest_path, "wb")
        completed_chunks = set()
        start_chunk = 0
        start_offset = 0

    # ── Progress updater ────────────────────────────────────────────
    async def _progress_updater():
        nonlocal downloaded_bytes
        last_bytes = downloaded_bytes
        last_time = start_ts

        while downloaded_bytes < file_size:
            if active_download["state"] == "cancelled":
                return

            await asyncio.sleep(1)

            now = time.time()
            current = downloaded_bytes

            dt = now - last_time
            d = current - last_bytes
            live_speed = d / dt if dt > 0 else 0
            avg_speed = current / (now - start_ts + 0.001)

            last_bytes = current
            last_time = now

            # Store for live TUI dashboard
            active_download["live_speed"] = live_speed
            active_download["avg_speed"] = avg_speed
            active_download["elapsed"] = _elapsed(start_ts)

            pct = current * 100 / file_size if file_size > 0 else 0
            bar = _make_progress_bar(pct, width=20)

            remaining = file_size - current
            if avg_speed > 0:
                eta_secs = int(remaining / avg_speed)
                eta_m, eta_s = divmod(eta_secs, 60)
                eta_str = f"{eta_m}m {eta_s}s" if eta_m else f"{eta_s}s"
            else:
                eta_str = "calculating…"

            active_download["eta"] = eta_str

            # Cycle spinner frame for Telegram
            spin_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            frame = spin_frames[int(now) % len(spin_frames)]

            if active_download["state"] == "paused":
                header = f"⏸ **Download Paused** {frame}"
            else:
                header = f"⬇️ **High-Speed Connection Pool Active** {frame}"

            text = (
                f"{header}\n\n"
                f"`[{bar}]` **{pct:.1f}%**\n\n"
                f"📦 `{_human_size(current)}` / `{_human_size(file_size)}`\n"
                f"🚀 Speed: **{_human_size(live_speed)}/s**\n"
                f"📊 Avg: `{_human_size(avg_speed)}/s`\n"
                f"⚡ Connections: `{PARALLEL_WORKERS}` parallel pool\n"
                f"⏱ Elapsed: `{active_download['elapsed']}`  ⏳ ETA: `{eta_str}`\n\n"
                f"💡 `/pause` · `/resume` · `/cancel`"
            )

            try:
                await status_msg.edit(text)
            except Exception:
                pass

    progress_task = asyncio.create_task(_progress_updater())
    downloader = ParallelTransferrer(bot, dc_id)

    try:
        current_chunk = start_chunk
        async for chunk_data in downloader.download(
            location,
            file_size,
            connection_count=PARALLEL_WORKERS,
            start_offset=start_offset
        ):
            if active_download["state"] == "cancelled":
                raise asyncio.CancelledError("Download cancelled by user")

            await active_download["pause_event"].wait()

            if active_download["state"] == "cancelled":
                raise asyncio.CancelledError("Download cancelled by user")

            fd.write(chunk_data)
            downloaded_bytes += len(chunk_data)
            active_download["offset"] = downloaded_bytes

            completed_chunks.add(current_chunk)
            _save_download_state(dest_path, file_size, completed_chunks)
            current_chunk += 1

    finally:
        fd.close()
        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass

    if active_download["state"] == "cancelled":
        raise asyncio.CancelledError("Download cancelled by user")

    # Clean up state tracker file on success
    state_path = f"{dest_path}.state"
    if os.path.exists(state_path):
        try:
            os.remove(state_path)
        except OSError:
            pass

    return dest_path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SEQUENTIAL FALLBACK — for photos/media with unknown file size
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _sequential_download(message, dest_path, status_msg):
    """
    Fallback downloader for media where file size is unknown (photos, etc).
    """
    start_ts = time.time()
    media = message.media

    await status_msg.edit("⬇️ **Downloading** (sequential fallback) ⠋…")

    result = await bot.download_media(media, file=dest_path)

    elapsed = _elapsed(start_ts)
    final_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
    avg_speed = final_size / (time.time() - start_ts + 0.001)

    await status_msg.edit(
        f"✅ **Download Complete** 💾\n"
        f"📦 {_human_size(final_size)}\n"
        f"🚀 Avg speed: {_human_size(avg_speed)}/s\n"
        f"⏱ Elapsed: {elapsed}\n"
        f"📂 `{dest_path}`"
    )

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  IGNITION SEQUENCE — 5-second fuse before auto-queueing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def _ignition_sequence(event, ignition_msg, message):
    """
    5-second countdown fuse.
    User can click the inline ❌ Cancel button to abort.
    If countdown expires, the file is auto-queued for download.
    """
    cancel_event = asyncio.Event()
    ign_id = str(ignition_msg.id)
    ignition_pending[ign_id] = cancel_event

    try:
        spin_frames = ["⠋", "⠙", "⠹", "⠸", "⠼"]
        for i in range(IGNITION_DELAY, 0, -1):
            frame = spin_frames[i % len(spin_frames)]
            try:
                await ignition_msg.edit(
                    f"⏱ **Ignition in {i}s** {frame} — File drop detected\n"
                    f"Auto-queueing unless cancelled…",
                    buttons=[[Button.inline(
                        f"❌ Cancel ({i}s)",
                        data=f"ign_{ign_id}".encode(),
                    )]],
                )
            except Exception:
                pass

            try:
                await asyncio.wait_for(cancel_event.wait(), timeout=1.0)
                log.info("🚫 [IGNITION] Cancelled by user: msg %s", ign_id)
                try:
                    await ignition_msg.edit(
                        "❌ **Download Cancelled**\nFile was not queued.",
                        buttons=None,
                    )
                except Exception:
                    pass
                return
            except asyncio.TimeoutError:
                continue

        # ── Countdown expired — auto-queue the file ─────────────────
        position = download_queue.qsize() + 1
        if active_download["state"] != "idle":
            position += 1

        await ignition_msg.edit(
            f"📋 **Queued for Download** — Position: `#{position}`\n"
            f"Waiting for active download to finish…",
            buttons=None,
        )

        # ── Persist to local JSON before pushing to queue ────────────
        file_name, file_size = _get_file_info(message)
        queue_list = _load_pending_queue()
        if not any(item["message_id"] == message.id for item in queue_list):
            queue_list.append({
                "message_id": message.id,
                "chat_id": message.chat_id,
                "status_msg_id": ignition_msg.id,
                "file_name": file_name,
                "status": "pending"
            })
            _save_pending_queue(queue_list)

        await download_queue.put((message, ignition_msg))
        log.info("📋 [QUEUE] Auto-queued at position #%d (ignition expired)", position)

    finally:
        ignition_pending.pop(ign_id, None)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BACKGROUND QUEUE WORKER — sequential download processor
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def queue_worker():
    """
    Sequential download processor.
    """
    log.info("🔄 [WORKER] Queue worker started — waiting for downloads…")

    # Initialize pause event inside the running event loop
    active_download["pause_event"] = asyncio.Event()
    active_download["pause_event"].set()

    while True:
        message, status_msg = await download_queue.get()

        try:
            file_name, file_size = _get_file_info(message)
            dest_path = os.path.join(DOWNLOAD_DIR, file_name)
            size_str = _human_size(file_size) if file_size else "unknown size"

            # ── Reset state manager for this download ──────────────
            active_download["state"] = "downloading"
            active_download["offset"] = 0
            active_download["total"] = file_size
            active_download["path"] = dest_path
            active_download["filename"] = file_name
            active_download["status_msg"] = status_msg
            active_download["pause_event"].set()

            queue_remaining = download_queue.qsize()
            await status_msg.edit(
                f"📡 **High-Speed Connection Pool Engaged**\n"
                f"📄 `{file_name}` ({size_str})\n"
                f"⚡ Connections: `{PARALLEL_WORKERS}` parallel pool\n"
                f"📋 Queue behind: `{queue_remaining}` file(s)"
            )

            log.info("▶ [STEALTH] Downloading: %s (%s) → %s", file_name, size_str, dest_path)
            start_ts = time.time()

            # ── Route to engine ────────────────────────────────────
            if file_size > 0:
                # Known size → hyper-threaded parallel engine
                await _hyper_download(message, dest_path, status_msg, file_size)

                # Final completion & ghost message
                elapsed = _elapsed(start_ts)
                final_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
                avg_speed = final_size / (time.time() - start_ts + 0.001)

                await status_msg.edit(
                    f"✅ **Download Complete & Ghosted**\n"
                    f"📄 `{file_name}`\n"
                    f"📦 {_human_size(final_size)} │ ⏱ {elapsed}\n"
                    f"🗑 Wiping original message..."
                )
                log.info("✅ [WORKER] Complete: %s | %s | %s", file_name, _human_size(final_size), elapsed)

                # Remove from persistent JSON queue
                queue_list = _load_pending_queue()
                queue_list = [item for item in queue_list if not (item["message_id"] == message.id and item["chat_id"] == message.chat_id)]
                _save_pending_queue(queue_list)

                # Auto-delete original Telegram file drop message
                try:
                    await message.delete()
                    log.info("🗑 [GHOST] Original message deleted.")
                except Exception as e:
                    log.warning("⚠️ Failed to delete original message: %s", e)

                # Auto-delete status message after 5 seconds
                await asyncio.sleep(5)
                try:
                    await status_msg.delete()
                except Exception as e:
                    log.warning("⚠️ Failed to delete status message: %s", e)

            else:
                # Unknown size → sequential fallback (photos, etc.)
                await _sequential_download(message, dest_path, status_msg)
                log.info("✅ [WORKER] Complete (sequential): %s", file_name)

                # Remove from persistent JSON queue
                queue_list = _load_pending_queue()
                queue_list = [item for item in queue_list if not (item["message_id"] == message.id and item["chat_id"] == message.chat_id)]
                _save_pending_queue(queue_list)

                # Auto-delete original Telegram file drop message
                try:
                    await message.delete()
                    log.info("🗑 [GHOST] Original message deleted.")
                except Exception as e:
                    log.warning("⚠️ Failed to delete original message: %s", e)

                # Auto-delete status message after 5 seconds
                await asyncio.sleep(5)
                try:
                    await status_msg.delete()
                except Exception as e:
                    log.warning("⚠️ Failed to delete status message: %s", e)

        except asyncio.CancelledError:
            cancelled_name = active_download.get("filename", "unknown")
            cancelled_path = active_download.get("path", "")
            log.info("🚫 [WORKER] Download cancelled: %s", cancelled_name)

            # Remove from JSON queue
            queue_list = _load_pending_queue()
            queue_list = [item for item in queue_list if not (item["message_id"] == message.id and item["chat_id"] == message.chat_id)]
            _save_pending_queue(queue_list)

            if cancelled_path:
                if os.path.exists(cancelled_path):
                    try:
                        os.remove(cancelled_path)
                        log.info("🗑 Removed partial file: %s", cancelled_path)
                    except OSError:
                        pass
                state_path = f"{cancelled_path}.state"
                if os.path.exists(state_path):
                    try:
                        os.remove(state_path)
                        log.info("🗑 Removed partial state file: %s", state_path)
                    except OSError:
                        pass

        except Exception as exc:
            error_trace = traceback.format_exc()
            log.error("❌ [WORKER] Download failed:\n%s", error_trace)

            try:
                await status_msg.edit(
                    f"❌ **Download Failed**\n"
                    f"🔥 `{type(exc).__name__}: {exc}`\n\n"
                    f"Check server logs for details."
                )
            except Exception:
                pass

        finally:
            active_download["state"] = "idle"
            active_download["offset"] = 0
            active_download["total"] = 0
            active_download["path"] = ""
            active_download["filename"] = ""
            active_download["status_msg"] = None
            download_queue.task_done()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CALLBACK HANDLER — ignition cancel button clicks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    """
    Handles inline button clicks from the ignition countdown.
    """
    if event.sender_id != ALLOWED_USER_ID:
        await event.answer("⛔ Unauthorized", alert=True)
        return

    data = event.data.decode("utf-8")

    if data.startswith("ign_"):
        ign_id = data[4:]
        cancel_event = ignition_pending.get(ign_id)
        if cancel_event:
            cancel_event.set()
            await event.answer("❌ Download cancelled!")
        else:
            await event.answer("⏱ Ignition already expired.", alert=True)
    else:
        await event.answer()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  EVENT HANDLER — gatekeeper + command router
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@bot.on(events.NewMessage)
async def handler(event):
    """
    Strict access security gate + interactive command router.
    """
    if event.sender_id != ALLOWED_USER_ID:
        log.warning("⛔ Rejected event from unauthorized ID: %s", event.sender_id)
        return

    text = (event.raw_text or "").strip().lower()

    # ━━━━━━━━ /start ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if text == "/start":
        await event.reply(
            "🟢 **Anti-Gravity Stealth Downloader Online**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📂 Storage: `{DOWNLOAD_DIR}`\n"
            f"⚡ Engine: {PARALLEL_WORKERS}-connection parallel pool\n"
            f"📋 Mode: Sequential queue (persistent JSON recovery)\n"
            f"⏱ Ignition: {IGNITION_DELAY}s delay\n"
            f"🔒 Firewall: sender-locked to `{ALLOWED_USER_ID}`\n\n"
            "**Commands:**\n"
            "`/queue`   — Check queue status\n"
            "`/pause`   — Freeze active download stream\n"
            "`/resume`  — Resume from saved byte offset\n"
            "`/cancel`  — Nuke active download + delete partial file\n"
            "`/clear`   — Wipe all chat history\n\n"
            "Send files or forward media to begin."
        )
        return

    # ━━━━━━━━ /clear — wipe all chat messages ━━━━━━━━━━━━━━━━━━━━━
    if text == "/clear":
        log.info("🧹 [CMD] Chat clear requested")
        notice = await event.reply("🧹 **Wiping chat history…**")

        msg_ids = []
        async for msg in bot.iter_messages(event.chat_id):
            msg_ids.append(msg.id)

        deleted = 0
        for i in range(0, len(msg_ids), 100):
            batch = msg_ids[i : i + 100]
            try:
                await bot.delete_messages(event.chat_id, batch)
                deleted += len(batch)
            except Exception as e:
                log.warning("🧹 Batch delete error: %s", e)

        log.info("🧹 [CMD] Deleted %d messages", deleted)
        return

    # ━━━━━━━━ /queue — queue + active download status ━━━━━━━━━━━━━
    if text == "/queue":
        state = active_download["state"]
        pending = download_queue.qsize()
        fname = active_download.get("filename", "")

        if state == "idle":
            status_line = "💤 Idle — no active download"
        elif state == "downloading":
            pct = 0
            if active_download["total"] > 0:
                pct = active_download["offset"] * 100 / active_download["total"]
            status_line = (
                f"⬇️ Downloading: `{fname}` ({pct:.1f}%)\n"
                f"📦 `{_human_size(active_download['offset'])}` / "
                f"`{_human_size(active_download['total'])}`"
            )
        elif state == "paused":
            pct = 0
            if active_download["total"] > 0:
                pct = active_download["offset"] * 100 / active_download["total"]
            status_line = (
                f"⏸ Paused: `{fname}` ({pct:.1f}%)\n"
                f"📦 `{_human_size(active_download['offset'])}` / "
                f"`{_human_size(active_download['total'])}`"
            )
        else:
            status_line = f"🔄 State: `{state}`"

        ignitions = len(ignition_pending)
        await event.reply(
            f"📋 **Queue Status**\n\n"
            f"{status_line}\n"
            f"📋 Pending: `{pending}` file(s)\n"
            f"⏱ Igniting: `{ignitions}` file(s)"
        )
        return

    # ━━━━━━━━ /cancel — nuke active download ━━━━━━━━━━━━━━━━━━━━━
    if text == "/cancel":
        if active_download["state"] in ("downloading", "paused"):
            fname = active_download.get("filename", "unknown")
            active_download["state"] = "cancelled"
            active_download["pause_event"].set()

            smsg = active_download.get("status_msg")
            if smsg:
                try:
                    await smsg.edit(
                        f"❌ **Download Cancelled**\n"
                        f"📄 `{fname}`\n"
                        f"🗑 Partial file will be removed."
                    )
                except Exception:
                    pass

            await event.reply(f"🚫 Cancelling: `{fname}`\nMoving to next in queue…")
            log.info("🚫 [CMD] Cancel requested: %s", fname)
        else:
            await event.reply("⚠️ No active download to cancel.")
        return

    # ━━━━━━━━ /pause — freeze the active byte stream ━━━━━━━━━━━━━
    if text == "/pause":
        if active_download["state"] == "downloading":
            active_download["state"] = "paused"
            active_download["pause_event"].clear()

            fname = active_download.get("filename", "unknown")
            offset = active_download.get("offset", 0)
            total = active_download.get("total", 0)
            pct = (offset * 100 / total) if total > 0 else 0

            smsg = active_download.get("status_msg")
            if smsg:
                try:
                    await smsg.edit(
                        f"⏸ **Download Paused**\n\n"
                        f"📄 `{fname}`\n"
                        f"📦 `{_human_size(offset)}` / `{_human_size(total)}` ({pct:.1f}%)\n"
                        f"💾 Byte offset saved: `{offset}`\n"
                        f"⚡ All connections paused\n\n"
                        f"Use `/resume` to continue or `/cancel` to abort."
                    )
                except Exception:
                    pass

            await event.reply(f"⏸ Paused: `{fname}` at {_human_size(offset)}")
            log.info("⏸ [CMD] Paused: %s at offset %d", fname, offset)

        elif active_download["state"] == "paused":
            await event.reply("⏸ Already paused. Use `/resume` to continue.")
        else:
            await event.reply("⚠️ No active download to pause.")
        return

    # ━━━━━━━━ /resume — unfreeze all workers ━━━━━━━━━━━━━━━━━━━━━
    if text == "/resume":
        if active_download["state"] == "paused":
            active_download["state"] = "downloading"
            active_download["pause_event"].set()

            fname = active_download.get("filename", "unknown")
            offset = active_download.get("offset", 0)

            await event.reply(f"▶️ Resumed: `{fname}` from {_human_size(offset)}")
            log.info("▶️ [CMD] Resumed: %s from offset %d", fname, offset)

        elif active_download["state"] == "downloading":
            await event.reply("⬇️ Already downloading. Use `/pause` to pause.")
        else:
            await event.reply("⚠️ No paused download to resume.")
        return

    # ━━━━━━━━ Media detection — trigger ignition sequence ━━━━━━━━━
    if not event.message or not event.message.media:
        await event.reply("⚠️ No downloadable media detected. Send a file or document.")
        return

    # ── Send ignition countdown message ─────────────────────────────
    ignition_msg = await event.reply(
        f"⏱ **Ignition in {IGNITION_DELAY}s** — File drop detected\n"
        f"Auto-queueing unless cancelled…",
    )

    # ── Launch ignition fuse as a background task (non-blocking) ────
    asyncio.create_task(_ignition_sequence(event, ignition_msg, event.message))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BOOT SWEEP PROTOCOL — scans local JSON database to rebuild queue
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def boot_sweep():
    """
    Power restored / daemon startup scan.
    Reconstructs the queue from pending_queue.json without requesting DM history.
    """
    log.info("🔌 Power restored. Boot Sweep initiated...")
    queue_list = _load_pending_queue()
    if not queue_list:
        log.info("🔌 Boot Sweep complete: no pending targets found.")
        return

    log.info("Found %d pending targets in recovery log. Rebuilding queue...", len(queue_list))
    recovered_count = 0

    for item in queue_list:
        try:
            chat_id = item["chat_id"]
            message_id = item["message_id"]
            status_msg_id = item.get("status_msg_id")
            file_name = item.get("file_name", "unknown")

            # Retrieve the exact message object directly by ID (valid for bot tokens)
            message = await bot.get_messages(chat_id, ids=message_id)
            if not message or not message.media:
                log.warning("⚠️ Message %d not found or has no media. Skipping.", message_id)
                continue

            # Retrieve or recreate the status message
            status_msg = None
            if status_msg_id:
                try:
                    status_msg = await bot.get_messages(chat_id, ids=status_msg_id)
                except Exception:
                    pass

            if not status_msg:
                status_msg = await bot.send_message(
                    chat_id,
                    f"📋 **Recovered from Recovery Log**\n"
                    f"📄 `{file_name}`\n"
                    f"Queued for download…"
                )
                # Update tracker with new status msg ID
                item["status_msg_id"] = status_msg.id
                _save_pending_queue(queue_list)

            # Re-inject back into queue
            await download_queue.put((message, status_msg))
            recovered_count += 1

        except Exception as e:
            log.error("❌ Failed to recover queued message %d: %s", item.get("message_id"), e)

    # Cleanup invalid entries that weren't recovered
    if recovered_count < len(queue_list):
        cleaned_list = []
        for item in queue_list:
            try:
                msg = await bot.get_messages(item["chat_id"], ids=item["message_id"])
                if msg and msg.media:
                    cleaned_list.append(item)
            except Exception:
                pass
        _save_pending_queue(cleaned_list)

    log.info("🔌 Boot Sweep complete: successfully enqueued %d files.", recovered_count)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CONSOLE LIVE TUI DASHBOARD RENDERER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
console = Console()

def get_dashboard_layout():
    # Header panel
    header = Panel(
        Text("⚡ STEALTH DOWNLOADER DAEMON ⚡", justify="center", style="bold magenta"),
        border_style="cyan"
    )

    # Left Column: Daemon stats
    stats_table = Table.grid(padding=1)
    stats_table.add_column(style="cyan", justify="right")
    stats_table.add_column(style="white", justify="left")
    
    state_display = {
        "idle": "[bold blue]💤 Idle[/bold blue]",
        "downloading": "[bold green]⬇️ Downloading[/bold green]",
        "paused": "[bold yellow]⏸ Paused[/bold yellow]",
        "cancelled": "[bold red]❌ Cancelled[/bold red]"
    }.get(active_download["state"], f"[white]{active_download['state']}[/white]")
    
    stats_table.add_row("System Status:  ", state_display)
    stats_table.add_row("Connection Pool:", f"[bold green]{PARALLEL_WORKERS}[/bold green] senders")
    stats_table.add_row("Pending Queue:  ", f"[bold yellow]{download_queue.qsize()}[/bold yellow] file(s)")
    stats_table.add_row("Ignition Fuses: ", f"[bold yellow]{len(ignition_pending)}[/bold yellow] active")
    stats_table.add_row("Authorized ID:  ", f"[dim]{ALLOWED_USER_ID}[/dim]")
    stats_table.add_row("Download Dir:   ", f"[dim]{DOWNLOAD_DIR}[/dim]")
    
    stats_panel = Panel(stats_table, title="Daemon Status", border_style="blue")

    # Right Column: Active download info
    dl_table = Table.grid(padding=1)
    dl_table.add_column(style="magenta", justify="right")
    dl_table.add_column(style="white", justify="left")
    
    if active_download["state"] in ("downloading", "paused"):
        pct = (active_download["offset"] * 100 / active_download["total"]) if active_download["total"] > 0 else 0
        bar = _make_progress_bar(pct, width=20)
        
        dl_table.add_row("Filename:     ", f"[bold white]{active_download['filename']}[/bold white]")
        dl_table.add_row("Progress:     ", f"{bar} [bold green]{pct:.1f}%[/bold green]")
        dl_table.add_row("File Size:    ", f"{_human_size(active_download['offset'])} / {_human_size(active_download['total'])}")
        dl_table.add_row("Speed:        ", f"[bold cyan]{_human_size(active_download['live_speed'])}/s[/bold cyan] (Avg: {_human_size(active_download['avg_speed'])}/s)")
        dl_table.add_row("Time Stats:   ", f"Elapsed: {active_download['elapsed']} | ETA: {active_download['eta']}")
    else:
        dl_table.add_row("Active File:  ", "[dim]No active download job.[/dim]")
        dl_table.add_row("Progress:     ", "[dim]-------------------- 0.0%[/dim]")
        dl_table.add_row("Transfer Rate:", "[dim]- B/s[/dim]")
        dl_table.add_row("ETA:          ", "[dim]-[/dim]")
        
    dl_panel = Panel(dl_table, title="Active Download Progress", border_style="green")

    # Combine columns side by side
    main_table = Table.grid(padding=1)
    main_table.add_column(ratio=4)
    main_table.add_column(ratio=6)
    main_table.add_row(stats_panel, dl_panel)

    # Bottom Panel: Logs
    log_text = Text("\n".join(recent_logs))
    logs_panel = Panel(log_text, title="Daemon Activity Logs", border_style="yellow", height=12)

    # Compile Layout
    layout_table = Table.grid(padding=0)
    layout_table.add_row(header)
    layout_table.add_row(main_table)
    layout_table.add_row(logs_panel)
    
    return layout_table


async def dashboard_updater():
    # Delay startup slightly to avoid initialization race conditions
    await asyncio.sleep(0.5)
    with Live(get_dashboard_layout(), refresh_per_second=8, screen=True, console=console) as live:
        while True:
            try:
                await asyncio.sleep(0.125)
                live.update(get_dashboard_layout())
            except asyncio.CancelledError:
                break
            except Exception:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DAEMON MAIN RUNNER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def main():
    # ── Run the Boot Sweep to reconstruct state from local JSON log ──
    await boot_sweep()

    # ── Spawn background queue worker ────────────────────────────────
    bot.loop.create_task(queue_worker())

    # ── Spawn TUI Console Dashboard if running in TTY ────────────────
    if IS_TTY:
        bot.loop.create_task(dashboard_updater())

    # ── Watchdog Connection Loop ─────────────────────────────────────
    while True:
        try:
            log.info("📡 Connecting Telegram Client...")
            await bot.start(bot_token=BOT_TOKEN)
            log.info("🟢 Bot connected and authorized.")
            await bot.run_until_disconnected()
        except Exception as e:
            log.error("❌ Connection lost or daemon crash: %s. Reconnecting in 10s...", e)
            try:
                await bot.disconnect()
            except Exception:
                pass
            await asyncio.sleep(10)


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
        bot.loop.run_until_complete(main())
    except KeyboardInterrupt:
        log.info("🛑 Daemon terminated by user.")
