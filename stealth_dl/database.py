import os
import json
import logging
from stealth_dl.config import QUEUE_FILE

log = logging.getLogger("stealth-dl")

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
