import sys
import logging
import asyncio
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live

from stealth_dl.config import PARALLEL_WORKERS, DOWNLOAD_DIR, ALLOWED_USER_ID
from stealth_dl.utils import _human_size, _make_progress_bar
from stealth_dl.state import (
    recent_logs, IS_TTY, active_download, download_queue, ignition_pending, log
)

console = Console()

if IS_TTY:
    class LiveLogHandler(logging.Handler):
        def emit(self, record):
            try:
                msg = self.format(record)
                if record.levelno >= logging.ERROR:
                    msg = f"[bold red]❌ {msg}[/bold red]"
                elif record.levelno >= logging.WARNING:
                    msg = f"[yellow]⚠️ {msg}[/yellow]"
                else:
                    msg = f"[white]⚙️ {msg}[/white]"
                recent_logs.append(msg)
                if len(recent_logs) > 9:
                    recent_logs.pop(0)
            except Exception:
                self.handleError(record)

    h = LiveLogHandler()
    h.setFormatter(logging.Formatter("%(asctime)s │ %(message)s", datefmt="%H:%M:%S"))
    log.addHandler(h)
else:
    # Standard terminal/file logging
    standard_handler = logging.StreamHandler(sys.stdout)
    standard_handler.setFormatter(logging.Formatter("%(asctime)s │ %(levelname)-8s │ %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    log.addHandler(standard_handler)


def get_dashboard_layout():
    # Header panel
    header = Panel(
        Text("⚡ STEALTH DOWNLOADER DAEMON ⚡", justify="center", style="bold magenta"),
        border_style="cyan"
    )

    # Left Column: Daemon stats
    stats_table = Table.grid(padding=1)
    stats_table.add_column(style="cyan", justify="right")
    stats_table.add_column(style="white", justify="left")
    
    state_display = {
        "idle": "[bold blue]💤 Idle[/bold blue]",
        "downloading": "[bold green]⬇️ Downloading[/bold green]",
        "paused": "[bold yellow]⏸ Paused[/bold yellow]",
        "cancelled": "[bold red]❌ Cancelled[/bold red]"
    }.get(active_download["state"], f"[white]{active_download['state']}[/white]")
    
    stats_table.add_row("System Status:  ", state_display)
    stats_table.add_row("Connection Pool:", f"[bold green]{PARALLEL_WORKERS}[/bold green] senders")
    stats_table.add_row("Pending Queue:  ", f"[bold yellow]{download_queue.qsize()}[/bold yellow] file(s)")
    stats_table.add_row("Ignition Fuses: ", f"[bold yellow]{len(ignition_pending)}[/bold yellow] active")
    stats_table.add_row("Authorized ID:  ", f"[dim]{ALLOWED_USER_ID}[/dim]")
    stats_table.add_row("Download Dir:   ", f"[dim]{DOWNLOAD_DIR}[/dim]")
    
    stats_panel = Panel(stats_table, title="Daemon Status", border_style="blue")

    # Right Column: Active download info
    dl_table = Table.grid(padding=1)
    dl_table.add_column(style="magenta", justify="right")
    dl_table.add_column(style="white", justify="left")
    
    if active_download["state"] in ("downloading", "paused"):
        pct = (active_download["offset"] * 100 / active_download["total"]) if active_download["total"] > 0 else 0
        bar = _make_progress_bar(pct, width=20)
        
        dl_table.add_row("Filename:     ", f"[bold white]{active_download['filename']}[/bold white]")
        dl_table.add_row("Progress:     ", f"{bar} [bold green]{pct:.1f}%[/bold green]")
        dl_table.add_row("File Size:    ", f"{_human_size(active_download['offset'])} / {_human_size(active_download['total'])}")
        dl_table.add_row("Speed:        ", f"[bold cyan]{_human_size(active_download['live_speed'])}/s[/bold cyan] (Avg: {_human_size(active_download['avg_speed'])}/s)")
        dl_table.add_row("Time Stats:   ", f"Elapsed: {active_download['elapsed']} | ETA: {active_download['eta']}")
    else:
        dl_table.add_row("Active File:  ", "[dim]No active download job.[/dim]")
        dl_table.add_row("Progress:     ", "[dim]-------------------- 0.0%[/dim]")
        dl_table.add_row("Transfer Rate:", "[dim]- B/s[/dim]")
        dl_table.add_row("ETA:          ", "[dim]-[/dim]")
        
    dl_panel = Panel(dl_table, title="Active Download Progress", border_style="green")

    # Combine columns side by side
    main_table = Table.grid(padding=1)
    main_table.add_column(ratio=4)
    main_table.add_column(ratio=6)
    main_table.add_row(stats_panel, dl_panel)

    # Bottom Panel: Logs
    log_text = Text("\n".join(recent_logs))
    logs_panel = Panel(log_text, title="Daemon Activity Logs", border_style="yellow", height=12)

    # Compile Layout
    layout_table = Table.grid(padding=0)
    layout_table.add_row(header)
    layout_table.add_row(main_table)
    layout_table.add_row(logs_panel)
    
    return layout_table


async def dashboard_updater():
    # Delay startup slightly to avoid initialization race conditions
    await asyncio.sleep(0.5)
    with Live(get_dashboard_layout(), refresh_per_second=8, screen=True, console=console) as live:
        while True:
            try:
                await asyncio.sleep(0.125)
                live.update(get_dashboard_layout())
            except asyncio.CancelledError:
                break
            except Exception:
                pass
