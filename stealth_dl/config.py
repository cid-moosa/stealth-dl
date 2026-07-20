import os
import sys
from dotenv import load_dotenv

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
if "pytest" not in sys.modules:
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
