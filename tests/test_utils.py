import time
from stealth_dl.utils import _human_size, _elapsed, _make_progress_bar

def test_human_size():
    assert _human_size(500) == "500.00 B"
    assert _human_size(1024) == "1.00 KB"
    assert _human_size(1024 * 1024) == "1.00 MB"
    assert _human_size(1024 * 1024 * 1024) == "1.00 GB"

def test_elapsed():
    start = time.time() - 65
    elapsed_str = _elapsed(start)
    assert elapsed_str == "1m 5s"

    start_sec = time.time() - 30
    elapsed_sec_str = _elapsed(start_sec)
    assert elapsed_sec_str == "30s"

def test_make_progress_bar():
    # 0% bar should have 15 empty characters
    assert _make_progress_bar(0, width=10) == "░" * 10
    # 100% bar should have 10 filled blocks
    assert _make_progress_bar(100, width=10) == "█" * 10
