#!/bin/bash

# Detect TTY and NO_COLOR
IS_TTY=0
if [ -t 1 ]; then
    IS_TTY=1
fi
if [ -n "$NO_COLOR" ]; then
    IS_TTY=0
fi

# Colors & Formatting (POSIX \033 compatible)
if [ "$IS_TTY" -eq 1 ]; then
    CLR_CYAN="\033[36m"
    CLR_GREEN="\033[32m"
    CLR_RED="\033[31m"
    CLR_MAGENTA="\033[35m"
    CLR_YELLOW="\033[33m"
    CLR_BOLD="\033[1m"
    CLR_RESET="\033[0m"
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
        # Run command in background, hide output
        eval "$cmd" >/dev/null 2>&1 &
        local pid=$!
        
        # Hide cursor
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
        
        # Wait for actual command exit code
        wait "$pid"
        local exit_code=$?
        
        # Clear line and show cursor
        printf "\r\033[K"
        tput cnorm 2>/dev/null
        return $exit_code
    else
        echo "$msg..."
        eval "$cmd"
        return $?
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

typewriter "${CLR_BOLD}Starting system diagnostics & installation...${CLR_RESET}"
echo

# 1. Check Python
if [ "$IS_TTY" -eq 1 ]; then
    printf "${CLR_CYAN}[⠋]${CLR_RESET} Checking Python3 environment..."
    sleep 0.5
fi

if ! command -v python3 &> /dev/null; then
    printf "\r${CLR_RED}[x]${CLR_RESET} Error: python3 is not installed or not in PATH.\n"
    typewriter "Please install Python 3.12+ and try again."
    exit 1
fi
python_ver=$(python3 --version 2>&1)
printf "\r${CLR_GREEN}[✓]${CLR_RESET} Python3 found: $python_ver\n"
sleep 0.3

# 2. Virtual Environment / Dependency Resolution
PY_CMD="python3"
PIP_CMD="pip3"

echo
typewriter "${CLR_BOLD}Setting up virtual environment & dependencies...${CLR_RESET}"

# Attempt venv creation to support Debian PEP 668 externally-managed environments
if [ ! -d "venv" ]; then
    run_with_spinner "python3 -m venv venv" "Creating isolated virtual environment (venv)"
fi

if [ -f "venv/bin/pip" ]; then
    PY_CMD="./venv/bin/python"
    PIP_CMD="./venv/bin/pip"
    printf "${CLR_GREEN}[✓] Using isolated venv environment at ./venv${CLR_RESET}\n"
    run_with_spinner "$PIP_CMD install -r requirements.txt" "Installing python packages (telethon, cryptg, rich, dotenv)"
    INSTALL_RES=$?
else
    printf "${CLR_YELLOW}[!] venv module not found, attempting system pip installation...${CLR_RESET}\n"
    run_with_spinner "pip3 install -r requirements.txt --break-system-packages" "Installing python packages via system pip"
    INSTALL_RES=$?
fi

if [ $INSTALL_RES -ne 0 ]; then
    printf "${CLR_RED}[x] Failed to install dependencies via pip.${CLR_RESET}\n"
    printf "On Debian/Ubuntu, please install python3-venv: sudo apt install python3-venv\n"
    exit 1
fi
printf "${CLR_GREEN}[✓] Dependencies successfully resolved.${CLR_RESET}\n"
sleep 0.5

# 3. Launch Configuration Wizard
echo
typewriter "${CLR_BOLD}Launching configuration wizard...${CLR_RESET}"
sleep 0.5
$PY_CMD configure.py

# 4. Background Service Prompt
echo
if [ -f "start.sh" ]; then
    chmod +x start.sh
fi

typewriter "${CLR_BOLD}Installation finished!${CLR_RESET}"
printf "${CLR_CYAN}To run as a continuous background daemon that survives reboots:${CLR_RESET}\n"
printf "  • Start in background:   ${CLR_BOLD}./start.sh start${CLR_BOLD}\n"
printf "  • Install system service: ${CLR_BOLD}sudo cp stealth-dl.service /etc/systemd/system/ && sudo systemctl enable --now stealth-dl${CLR_RESET}\n\n"
