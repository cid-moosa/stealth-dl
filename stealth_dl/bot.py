import os
import sys
import time
import asyncio
import traceback

from telethon import TelegramClient, events, Button

from stealth_dl.config import (
    API_ID, API_HASH, BOT_TOKEN, ALLOWED_USER_ID, DOWNLOAD_DIR,
    PARALLEL_WORKERS, IGNITION_DELAY
)
from stealth_dl.utils import _human_size, _elapsed, _get_file_info
from stealth_dl.database import _load_pending_queue, _save_pending_queue
from stealth_dl.engine import _hyper_download, _sequential_download
from stealth_dl.state import (
    active_download, download_queue, ignition_pending, log, IS_TTY
)
from stealth_dl.tui import dashboard_updater

# Initialize Telegram client
bot = TelegramClient("stealth_bot", API_ID, API_HASH)

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
            f"**Commands:**\n"
            f"`/queue`   — Check queue status\n"
            f"`/pause`   — Freeze active download stream\n"
            f"`/resume`  — Resume from saved byte offset\n"
            f"`/cancel`  — Nuke active download + delete partial file\n"
            f"`/clear`   — Wipe all chat history\n\n"
            f"Send files or forward media to begin."
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
                await _hyper_download(bot, message, dest_path, status_msg, file_size)

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
                await _sequential_download(bot, message, dest_path, status_msg)
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
#  DAEMON MAIN RUNNER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def run_daemon():
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
