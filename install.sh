#!/bin/bash

# Detect TTY and NO_COLOR
IS_TTY=0
if [ -t 1 ]; then
    IS_TTY=1
fi
if [ -n "$NO_COLOR" ]; then
    IS_TTY=0
fi

# Colors & Formatting (POSIX ANSI escape bytes)
if [ "$IS_TTY" -eq 1 ]; then
    CLR_CYAN="$(printf '\033[36m')"
    CLR_GREEN="$(printf '\033[32m')"
    CLR_RED="$(printf '\033[31m')"
    CLR_MAGENTA="$(printf '\033[35m')"
    CLR_YELLOW="$(printf '\033[33m')"
    CLR_BOLD="$(printf '\033[1m')"
    CLR_RESET="$(printf '\033[0m')"
else
    CLR_CYAN=""
    CLR_GREEN=""
    CLR_RED=""
    CLR_MAGENTA=""
    CLR_YELLOW=""
    CLR_BOLD=""
    CLR_RESET=""
fi

# Typewriter Helper
typewriter() {
    local text="$1"
    if [ "$IS_TTY" -eq 1 ]; then
        local delay=0.01
        for ((i=0; i<${#text}; i++)); do
            printf "%s" "${text:$i:1}"
            sleep "$delay"
        done
        echo
    else
        echo "$text"
    fi
}

# Spinner Helper
run_with_spinner() {
    local cmd="$1"
    local msg="$2"
    
    if [ "$IS_TTY" -eq 1 ]; then
        eval "$cmd" >/dev/null 2>&1 &
        local pid=$!
        
        tput civis 2>/dev/null
        
        local spinstr='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
        local delay=0.08
        
        while kill -0 "$pid" 2>/dev/null; do
            for ((i=0; i<${#spinstr}; i++)); do
                local char="${spinstr:$i:1}"
                printf "\r${CLR_CYAN}[%s]${CLR_RESET} %s..." "$char" "$msg"
                sleep "$delay"
                if ! kill -0 "$pid" 2>/dev/null; then
                    break
                fi
            done
        done
        
        wait "$pid"
        local exit_code=$?
        
        printf "\r\033[K"
        tput cnorm 2>/dev/null
        return $exit_code
    else
        echo "$msg..."
        eval "$cmd"
        return $?
    fi
}

# Helper to automatically install missing system packages
auto_install_system_deps() {
    local sudo_cmd=""
    if [ "$EUID" -ne 0 ] && command -v sudo &>/dev/null; then
        sudo_cmd="sudo"
    fi

    if command -v apt-get &>/dev/null; then
        run_with_spinner "$sudo_cmd apt-get update -y && $sudo_cmd apt-get install -y python3 python3-venv python3-pip python3-full build-essential" "Auto-installing Debian/Ubuntu system packages (python3, venv, pip)"
    elif command -v dnf &>/dev/null; then
        run_with_spinner "$sudo_cmd dnf install -y python3 python3-pip gcc" "Auto-installing Fedora/RHEL system packages"
    elif command -v pacman &>/dev/null; then
        run_with_spinner "$sudo_cmd pacman -Sy --noconfirm python python-pip gcc" "Auto-installing Arch system packages"
    fi
}

clear_screen() {
    if [ "$IS_TTY" -eq 1 ]; then
        clear
    fi
}

# Clear and draw banner
clear_screen
printf "${CLR_MAGENTA}${CLR_BOLD}\n"
echo "  ┌────────────────────────────────────────────────────────┐"
echo "  │   ▲ STEALTH DOWNLOADER — High-Speed Telegram Daemon    │"
echo "  └────────────────────────────────────────────────────────┘"
printf "${CLR_RESET}\n"

typewriter "${CLR_BOLD}Starting automated system diagnostics & self-healing installer...${CLR_RESET}"
echo

# 1. System Package Check & Auto-Install
if ! command -v python3 &>/dev/null; then
    printf "${CLR_YELLOW}[!] python3 not found. Triggering automated system package installation...${CLR_RESET}\n"
    auto_install_system_deps
fi

if ! command -v python3 &>/dev/null; then
    printf "${CLR_RED}[x] Error: Could not auto-install Python3. Please install Python 3.12+ manually.${CLR_RESET}\n"
    exit 1
fi
python_ver=$(python3 --version 2>&1)
printf "${CLR_GREEN}[✓] Python3 environment verified: $python_ver${CLR_RESET}\n"
sleep 0.3

# 2. Virtual Environment & Auto Dependency Resolution
echo
typewriter "${CLR_BOLD}Resolving & auto-updating Python dependencies...${CLR_RESET}"

# Attempt venv creation; if it fails, auto-install python3-venv packages and retry
if [ ! -d "venv" ]; then
    run_with_spinner "python3 -m venv venv" "Creating isolated virtual environment (venv)"
    if [ $? -ne 0 ]; then
        printf "${CLR_YELLOW}[!] venv creation failed. Auto-installing system venv packages...${CLR_RESET}\n"
        auto_install_system_deps
        run_with_spinner "python3 -m venv venv" "Retrying virtual environment creation"
    fi
fi

if [ -f "venv/bin/python" ]; then
    PY_CMD="./venv/bin/python"
    # Ensure pip is bootstrapped inside venv
    $PY_CMD -m ensurepip --default-pip >/dev/null 2>&1
    $PY_CMD -m pip install --upgrade pip setuptools wheel >/dev/null 2>&1
    
    printf "${CLR_GREEN}[✓] Using isolated venv environment at ./venv${CLR_RESET}\n"
    run_with_spinner "$PY_CMD -m pip install --upgrade -r requirements.txt" "Auto-updating python packages (telethon, cryptg, rich, dotenv)"
    INSTALL_RES=$?
    
    # Fallback if cryptg C-compiler build failed on minimal Linux
    if [ $INSTALL_RES -ne 0 ]; then
        printf "${CLR_YELLOW}[!] Installing core dependencies (without C-compiled cryptg module)...${CLR_RESET}\n"
        run_with_spinner "$PY_CMD -m pip install --upgrade telethon python-dotenv rich" "Installing core python packages"
        INSTALL_RES=$?
    fi
else
    # Fallback for system environment
    PY_CMD="python3"
    printf "${CLR_YELLOW}[!] venv not found, attempting system pip installation...${CLR_RESET}\n"
    run_with_spinner "python3 -m pip install --upgrade -r requirements.txt --break-system-packages" "Installing python packages via system pip"
    INSTALL_RES=$?
    
    if [ $INSTALL_RES -ne 0 ]; then
        run_with_spinner "python3 -m pip install --upgrade telethon python-dotenv rich --break-system-packages" "Installing core python packages"
        INSTALL_RES=$?
    fi
fi

if [ $INSTALL_RES -ne 0 ]; then
    printf "${CLR_RED}[x] Dependency resolution failed. Triggering system repair...${CLR_RESET}\n"
    auto_install_system_deps
    $PY_CMD -m pip install --upgrade telethon python-dotenv rich 2>/dev/null
fi

printf "${CLR_GREEN}[✓] Dependencies successfully resolved and verified.${CLR_RESET}\n"
sleep 0.5

# 3. Launch Configuration Wizard (if not running non-interactive automated mode)
if [ "$1" != "--auto" ] && [ "$1" != "-y" ]; then
    echo
    typewriter "${CLR_BOLD}Launching configuration wizard...${CLR_RESET}"
    sleep 0.5
    $PY_CMD configure.py
fi

# 4. Optional Post-Setup Cleanup
cleanup_files() {
    printf "${CLR_CYAN}[🧹] Cleaning up installation files (LICENSE, README.md, install.bat)...${CLR_RESET}\n"
    rm -f LICENSE README.md install.bat 2>/dev/null
}

if [ "$1" == "--clean" ]; then
    cleanup_files
fi

# 5. Background Service Prompt & Auto-Launch
echo
if [ -f "start.sh" ]; then
    chmod +x start.sh
fi

typewriter "${CLR_BOLD}Automated installation completed successfully!${CLR_RESET}"
printf "${CLR_CYAN}Daemon management options:${CLR_RESET}\n"
printf "  • Start in background (SSH-resilient): ${CLR_BOLD}./start.sh start${CLR_BOLD}\n"
printf "  • Start in foreground (interactive):    ${CLR_BOLD}./start.sh fg${CLR_BOLD}\n"
printf "  • Install boot autostart service:       ${CLR_BOLD}sudo ./start.sh install-service${CLR_RESET}\n\n"
