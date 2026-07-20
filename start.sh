#!/bin/bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  STEALTH DOWNLOADER — Persistent Background Control Script
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
CDIR="$DIR"
PID_FILE="$CDIR/stealth_dl.pid"
LOG_FILE="$CDIR/stealth_dl.log"

# Pre-flight self-healing dependency verification
check_and_heal_dependencies() {
    local needs_heal=0

    if [ -f "$CDIR/venv/bin/python" ]; then
        PYTHON_BIN="$CDIR/venv/bin/python"
    else
        PYTHON_BIN="$(which python3 2>/dev/null)"
    fi

    if [ -z "$PYTHON_BIN" ]; then
        needs_heal=1
    else
        "$PYTHON_BIN" -c "import telethon, rich, dotenv" >/dev/null 2>&1
        if [ $? -ne 0 ]; then
            needs_heal=1
        fi
    fi

    if [ $needs_heal -eq 1 ]; then
        echo -e "\033[33m[!] Missing or incomplete dependencies detected. Triggering auto-installation... \033[0m"
        bash "$CDIR/install.sh" --auto
    fi
}

if [ -f "$CDIR/venv/bin/python" ]; then
    PYTHON_BIN="$CDIR/venv/bin/python"
else
    PYTHON_BIN="$(which python3 2>/dev/null)"
fi

if [ -f "$CDIR/stealth_dl_local.py" ]; then
    TARGET_SCRIPT="$CDIR/stealth_dl_local.py"
else
    TARGET_SCRIPT="$CDIR/stealth_dl.py"
fi

get_pid() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
    fi
    pgrep -f "python.*stealth_dl" | head -n 1
}

start_daemon_bg() {
    check_and_heal_dependencies

    if [ -f "$CDIR/venv/bin/python" ]; then
        PYTHON_BIN="$CDIR/venv/bin/python"
    fi

    local pid=$(get_pid)
    if [ -n "$pid" ]; then
        echo -e "\033[33m[!] Stealth Downloader is already running in background (PID: $pid).\033[0m"
        return 0
    fi

    echo -e "\033[36m[⚡] Launching Stealth Downloader in persistent background mode...\033[0m"
    # Execute detached with nohup & disown to remain active after SSH disconnection
    nohup "$PYTHON_BIN" "$TARGET_SCRIPT" > "$LOG_FILE" 2>&1 &
    local new_pid=$!
    disown $new_pid 2>/dev/null
    echo "$new_pid" > "$PID_FILE"
    
    sleep 1
    if kill -0 "$new_pid" 2>/dev/null; then
        echo -e "\033[32m[✓] Daemon started in background (PID: $new_pid).\033[0m"
        echo -e "\033[32m[✓] Immune to SSH disconnection. Runs continuously until reboot/shutdown.\033[0m"
        echo -e "\033[35m[i] Activity log: $LOG_FILE\033[0m"
        echo -e "\033[35m[i] Control commands: ./start.sh stop | ./start.sh status\033[0m"
    else
        echo -e "\033[31m[x] Failed to start daemon. Check $LOG_FILE for details.\033[0m"
    fi
}

start_daemon_fg() {
    check_and_heal_dependencies

    if [ -f "$CDIR/venv/bin/python" ]; then
        PYTHON_BIN="$CDIR/venv/bin/python"
    fi

    echo -e "\033[36m[⚡] Launching Stealth Downloader interactive TUI in foreground...\033[0m"
    "$PYTHON_BIN" "$TARGET_SCRIPT"
}

stop_daemon() {
    local pid=$(get_pid)
    if [ -z "$pid" ]; then
        echo -e "\033[33m[!] No running Stealth Downloader daemon found.\033[0m"
        rm -f "$PID_FILE" 2>/dev/null
        return 0
    fi

    echo -e "\033[36m[🛑] Stopping Stealth Downloader daemon (PID: $pid)...\033[0m"
    kill "$pid" 2>/dev/null
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null
    fi
    rm -f "$PID_FILE" 2>/dev/null
    echo -e "\033[32m[✓] Daemon stopped.\033[0m"
}

status_daemon() {
    local pid=$(get_pid)
    if [ -n "$pid" ]; then
        echo -e "\033[32m[🟢 ONLINE] Stealth Downloader is running in background (PID: $pid).\033[0m"
    else
        echo -e "\033[31m[🔴 OFFLINE] Stealth Downloader daemon is not running.\033[0m"
    fi
}

install_systemd_service() {
    check_and_heal_dependencies

    if [ "$EUID" -ne 0 ]; then
        echo -e "\033[33m[!] Systemd service installation requires root privileges.\033[0m"
        echo -e "Please re-run: \033[1msudo ./start.sh install-service\033[0m"
        exit 1
    fi

    local current_user="${SUDO_USER:-$USER}"
    local service_dest="/etc/systemd/system/stealth-dl.service"

    echo -e "\033[36m[⚙️] Installing systemd background service ($service_dest)...\033[0m"

    cat <<EOF > "$service_dest"
[Unit]
Description=Stealth Downloader — High-Speed Telegram Daemon
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$current_user
WorkingDirectory=$CDIR
ExecStart=$PYTHON_BIN $TARGET_SCRIPT
Restart=always
RestartSec=5s
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable --now stealth-dl
    echo -e "\033[32m[✓] Systemd service 'stealth-dl' installed and enabled on boot!\033[0m"
    echo -e "\033[32m[✓] Service status:\033[0m"
    systemctl status stealth-dl --no-pager
}

case "$1" in
    start|bg|background)
        start_daemon_bg
        ;;
    fg|foreground|interactive)
        start_daemon_fg
        ;;
    stop)
        stop_daemon
        ;;
    restart)
        stop_daemon
        start_daemon_bg
        ;;
    status)
        status_daemon
        ;;
    install-service)
        install_systemd_service
        ;;
    *)
        start_daemon_bg
        ;;
esac
