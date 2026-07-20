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

# 2. Virtual Environment & Dependency Resolution
echo
typewriter "${CLR_BOLD}Setting up virtual environment & dependencies...${CLR_RESET}"

# Create virtualenv if not present
if [ ! -d "venv" ]; then
    run_with_spinner "python3 -m venv venv" "Creating isolated virtual environment (venv)"
fi

if [ -f "venv/bin/python" ]; then
    PY_CMD="./venv/bin/python"
    # Ensure pip is bootstrapped inside venv
    $PY_CMD -m ensurepip --default-pip >/dev/null 2>&1
    
    printf "${CLR_GREEN}[✓] Using isolated venv environment at ./venv${CLR_RESET}\n"
    run_with_spinner "$PY_CMD -m pip install -r requirements.txt" "Installing python packages (telethon, cryptg, rich, dotenv)"
    INSTALL_RES=$?
    
    # Fallback if cryptg C-compiler build failed on minimal Linux
    if [ $INSTALL_RES -ne 0 ]; then
        printf "${CLR_YELLOW}[!] Installing core dependencies (without C-compiled cryptg module)...${CLR_RESET}\n"
        run_with_spinner "$PY_CMD -m pip install telethon python-dotenv rich" "Installing core python packages"
        INSTALL_RES=$?
    fi
else
    # Fallback for system environment
    PY_CMD="python3"
    printf "${CLR_YELLOW}[!] venv not found, attempting system pip installation...${CLR_RESET}\n"
    run_with_spinner "python3 -m pip install -r requirements.txt --break-system-packages" "Installing python packages via system pip"
    INSTALL_RES=$?
    
    if [ $INSTALL_RES -ne 0 ]; then
        run_with_spinner "python3 -m pip install telethon python-dotenv rich --break-system-packages" "Installing core python packages"
        INSTALL_RES=$?
    fi
fi

if [ $INSTALL_RES -ne 0 ]; then
    printf "${CLR_RED}[x] Failed to install dependencies.${CLR_RESET}\n"
    printf "On Debian/Ubuntu, please run: sudo apt install python3-pip python3-full\n"
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
printf "  • Install system service: ${CLR_BOLD}sudo ./start.sh install-service${CLR_RESET}\n\n"
