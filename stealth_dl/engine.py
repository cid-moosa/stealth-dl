import os
import time
import math
import asyncio
from typing import Optional, Union, AsyncGenerator

from telethon import TelegramClient, utils
from telethon.network import MTProtoSender
from telethon.tl.alltlobjects import LAYER
from telethon.tl.functions import InvokeWithLayerRequest
from telethon.tl.functions.auth import ExportAuthorizationRequest, ImportAuthorizationRequest
from telethon.tl.functions.upload import GetFileRequest
from telethon.tl.types import (
    Document, InputFileLocation, InputDocumentFileLocation,
    InputPhotoFileLocation, InputPeerPhotoFileLocation, Photo
)

from stealth_dl.config import PARALLEL_WORKERS
from stealth_dl.utils import _human_size, _elapsed, _make_progress_bar
from stealth_dl.database import _load_download_state, _save_download_state
from stealth_dl.state import active_download, log

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


async def _hyper_download(client: TelegramClient, message, dest_path, status_msg, file_size):
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
    downloader = ParallelTransferrer(client, dc_id)

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


async def _sequential_download(client: TelegramClient, message, dest_path, status_msg):
    """
    Fallback downloader for media where file size is unknown (photos, etc).
    """
    start_ts = time.time()
    media = message.media

    await status_msg.edit("⬇️ **Downloading** (sequential fallback) ⠋…")

    result = await client.download_media(media, file=dest_path)

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
