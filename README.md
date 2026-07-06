# ▲ Stealth Telegram Downloader

[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A private, high-speed, and resilient Telegram media downloader daemon designed to run on self-hosted home servers. It automatically downloads movies, series, or files forwarded or dropped into its chat and saves them directly to your storage directory, with boot-time queue recovery and ghost deletion of processed messages.

---

## ⚡ Features
* **Parallel Chunk Downloader**: Multi-connection parallel downloading using a MTProto sender pool for maximum network saturation.
- **TUI Live Console Dashboard**: A gorgeous terminal interface built with `rich` providing real-time stats, connection pool status, and scrollable daemon logs.
- **Ticking Ignition Fuse**: A 5-second cancelable delay before auto-queueing drops, preventing accidental downloads.
- **Smart Queue Persistence**: Restores queued files atomically from a local JSON log (`pending_queue.json`) after a system crash or reboot.
- **Smart Resume**: Saves chunk offset states (`.state` files) to resume partial downloads without restarting from zero.
- **Ghost Message Deletion**: Automatically deletes original files/forwarded messages from the chat upon successful completion to maintain stealth.

---

## 🚀 Quickstart

### 1. Installation
Run the automated, fully-animated installer script for your operating system:

**Windows**:
```cmd
install.bat
```

**Linux/macOS**:
```bash
chmod +x install.sh
./install.sh
```

The installer verifies your Python environment, installs dependencies, and launches the TUI Configuration Wizard to prompt for credentials.

### 2. Run the Daemon
Start the public client version:
```bash
python stealth_dl.py
```
Or start the compiled local standalone version:
```bash
python stealth_dl_local.py
```

---

## 🛠 Commands
Send these commands directly to your Bot:
- `/start` - Displays configuration parameters and instructions.
- `/queue` - Shows queue status, pending counts, and current download details.
- `/pause` - Freezes the active download stream.
- `/resume` - Resumes a paused stream from the saved byte offset.
- `/cancel` - Aborts the current download and deletes the partial file.
- `/clear` - Wipes all chat history in the bot conversation.

---

## 📦 Tech Stack
- **Language**: Python 3.12+
- **API Engine**: Telethon + Cryptg
- **Console TUI**: Rich
- **Settings**: Dotenv

---

## 🔒 License
This project is licensed under the MIT License.

---
Developed by [cid-moosa](https://github.com/cid-moosa)
