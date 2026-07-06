import os
import time
import sys

def main():
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text
        from rich.prompt import Prompt
        from rich.status import Status
    except ImportError:
        # Fallback if rich is not available yet
        print("==================================================")
        print("   Stealth Downloader - Configuration Wizard")
        print("==================================================")
        api_id = input("Enter TG_API_ID: ").strip()
        api_hash = input("Enter TG_API_HASH: ").strip()
        bot_token = input("Enter TG_BOT_TOKEN: ").strip()
        allowed_user_id = input("Enter TG_ALLOWED_USER_ID: ").strip()
        download_dir = input("Enter TG_DOWNLOAD_DIR [/DATA/Media/Movies/]: ").strip() or "/DATA/Media/Movies/"
        
        with open(".env", "w", encoding="utf-8") as f:
            f.write(f"TG_API_ID={api_id}\n")
            f.write(f"TG_API_HASH=\"{api_hash}\"\n")
            f.write(f"TG_BOT_TOKEN=\"{bot_token}\"\n")
            f.write(f"TG_ALLOWED_USER_ID={allowed_user_id}\n")
            f.write(f"TG_DOWNLOAD_DIR=\"{download_dir}\"\n")
        print("[+] Configuration saved to .env.")
        return

    console = Console()

    # Clear console for premium feel
    if console.is_terminal:
        console.clear()

    console.print()
    console.print(Panel(
        Text("⚡ STEALTH TELEGRAM DOWNLOADER ⚡\nInteractive Setup & Configuration", justify="center", style="bold magenta"),
        subtitle="[bold cyan]v2.0 • Animated TUI Wizard[/bold cyan]",
        border_style="cyan",
        expand=False
    ))
    console.print()

    # Try to load existing .env
    existing = {}
    if os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        existing[k.strip()] = v.strip().strip('"').strip("'")
        except Exception:
            pass

    # Prompt values using rich Prompt with defaults
    api_id = Prompt.ask(
        "[bold cyan]Enter TG_API_ID[/bold cyan] (from my.telegram.org)",
        default=existing.get('TG_API_ID', ''),
        console=console
    ).strip()

    api_hash = Prompt.ask(
        "[bold cyan]Enter TG_API_HASH[/bold cyan]",
        default=existing.get('TG_API_HASH', ''),
        console=console
    ).strip()

    bot_token = Prompt.ask(
        "[bold cyan]Enter TG_BOT_TOKEN[/bold cyan] (from @BotFather)",
        default=existing.get('TG_BOT_TOKEN', ''),
        console=console
    ).strip()

    allowed_user_id = Prompt.ask(
        "[bold cyan]Enter TG_ALLOWED_USER_ID[/bold cyan] (your Telegram ID)",
        default=existing.get('TG_ALLOWED_USER_ID', ''),
        console=console
    ).strip()
    
    default_dir = existing.get('TG_DOWNLOAD_DIR', '/DATA/Media/Movies/')
    download_dir = Prompt.ask(
        "[bold cyan]Enter TG_DOWNLOAD_DIR[/bold cyan]",
        default=default_dir,
        console=console
    ).strip()

    if not api_id or not api_hash or not bot_token or not allowed_user_id:
        console.print("\n[bold red][x] Error: All fields (except Download Directory) are strictly required.[/bold red]")
        sys.exit(1)

    console.print()

    # 1. Write .env with animated status spinner
    with console.status("[bold green]Writing `.env` configuration file...[/bold green]", spinner="dots") as status:
        time.sleep(0.8)  # Smooth animation pause
        try:
            with open(".env", "w", encoding="utf-8") as f:
                f.write(f"TG_API_ID={api_id}\n")
                f.write(f"TG_API_HASH=\"{api_hash}\"\n")
                f.write(f"TG_BOT_TOKEN=\"{bot_token}\"\n")
                f.write(f"TG_ALLOWED_USER_ID={allowed_user_id}\n")
                f.write(f"TG_DOWNLOAD_DIR=\"{download_dir}\"\n")
            console.print("[bold green][✓] Successfully wrote configuration variables to `.env` file.[/bold green]")
        except Exception as e:
            console.print(f"[bold red][x] Error writing `.env` file: {e}[/bold red]")
            sys.exit(1)

    # 2. Read stealth_dl.py and generate stealth_dl_local.py with animated spinner
    if os.path.exists("stealth_dl.py"):
        with console.status("[bold magenta]Generating standalone `stealth_dl_local.py`...[/bold magenta]", spinner="clock") as status:
            time.sleep(1.0)  # Smooth transition animation
            try:
                with open("stealth_dl.py", "r", encoding="utf-8") as f:
                    content = f.read()

                # Perform placeholder replacement
                content = content.replace('int(os.getenv("TG_API_ID", "0"))  # TG_API_ID_PLACEHOLDER', api_id)
                content = content.replace('os.getenv("TG_API_HASH", "")  # TG_API_HASH_PLACEHOLDER', f'"{api_hash}"')
                content = content.replace('os.getenv("TG_BOT_TOKEN", "")  # TG_BOT_TOKEN_PLACEHOLDER', f'"{bot_token}"')
                content = content.replace('int(os.getenv("TG_ALLOWED_USER_ID", "0"))  # TG_ALLOWED_USER_ID_PLACEHOLDER', allowed_user_id)
                content = content.replace('os.getenv("TG_DOWNLOAD_DIR", "/DATA/Media/Movies/")  # TG_DOWNLOAD_DIR_PLACEHOLDER', f'"{download_dir}"')

                with open("stealth_dl_local.py", "w", encoding="utf-8") as f:
                    f.write(content)
                console.print("[bold magenta][✓] Standalone executable `stealth_dl_local.py` generated with embedded credentials.[/bold magenta]")
            except Exception as e:
                console.print(f"[bold yellow][!] Warning generating standalone client: {e}[/bold yellow]")
    else:
         console.print("[bold yellow][!] Base script `stealth_dl.py` not found. Standalone compilation skipped.[/bold yellow]")

    console.print()
    console.print(Panel(
        Text("✨ Configuration Completed Successfully! ✨\n\n"
             "• Run public version:   python stealth_dl.py\n"
             "• Run standalone local:  python stealth_dl_local.py", 
             justify="left", style="bold green"),
        border_style="green",
        expand=False
    ))
    console.print()

if __name__ == "__main__":
    main()
