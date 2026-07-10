import time

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
        if char_idx > 0:
            bar += chars[char_idx]
            bar += "░" * (width - full_blocks - 1)
        else:
            bar += "░" * (width - full_blocks)
    return bar
