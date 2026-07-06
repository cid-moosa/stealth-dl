#!/bin/bash

# Detect TTY and NO_COLOR
IS_TTY=0
if [ -t 1 ]; then
    IS_TTY=1
fi
if [ -n "$NO_COLOR" ]; then
    IS_TTY=0
fi

# Colors & Formatting
if [ "$IS_TTY" -eq 1 ]; then
    CLR_CYAN="\e[36m"
    CLR_GREEN="\e[32m"
    CLR_RED="\e[31m"
    CLR_MAGENTA="\e[35m"
    CLR_YELLOW="\e[33m"
    CLR_BOLD="\e[1m"
    CLR_RESET="\e[0m"
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
        printf "\r\e[K"
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
echo -e "${CLR_MAGENTA}${CLR_BOLD}"
echo "  ┌────────────────────────────────────────────────────────┐"
echo "  │   ▲ STEALTH DOWNLOADER — High-Speed Telegram Daemon    │"
echo "  └────────────────────────────────────────────────────────┘"
echo -e "${CLR_RESET}"

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

# 2. Check Pip
if [ "$IS_TTY" -eq 1 ]; then
    printf "${CLR_CYAN}[⠋]${CLR_RESET} Checking pip package manager..."
    sleep 0.5
fi

if ! command -v pip3 &> /dev/null; then
    printf "\r${CLR_RED}[x]${CLR_RESET} Error: pip3 is not installed.\n"
    typewriter "Please install pip3 for Python and try again."
    exit 1
fi
printf "\r${CLR_GREEN}[✓]${CLR_RESET} pip3 is ready.\n"
sleep 0.3

# 3. Install Dependencies
echo
typewriter "${CLR_BOLD}Resolving dependencies...${CLR_RESET}"
run_with_spinner "pip3 install -r requirements.txt" "Installing python packages (telethon, cryptg, rich, dotenv)"
if [ $? -ne 0 ]; then
    echo -e "${CLR_RED}[x] Failed to install dependencies via pip3.${CLR_RESET}"
    exit 1
fi
echo -e "${CLR_GREEN}[✓] Dependencies successfully resolved.${CLR_RESET}"
sleep 0.5

# 4. Launch Configuration Wizard
echo
typewriter "${CLR_BOLD}Launching configuration wizard...${CLR_RESET}"
sleep 0.5
python3 configure.py
