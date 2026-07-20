import os
import json
import pytest
import stealth_dl.database
from stealth_dl.database import (
    _load_pending_queue, _save_pending_queue, _load_download_state, _save_download_state
)

@pytest.fixture
def temp_queue_file(tmp_path):
    # Patch the queue file path in the database module
    original_file = stealth_dl.database.QUEUE_FILE
    temp_file = tmp_path / "pending_queue.json"
    stealth_dl.database.QUEUE_FILE = str(temp_file)
    yield str(temp_file)
    stealth_dl.database.QUEUE_FILE = original_file

def test_load_pending_queue_empty(temp_queue_file):
    assert _load_pending_queue() == []

def test_save_and_load_pending_queue(temp_queue_file):
    test_data = [
        {"message_id": 123, "chat_id": 456, "file_name": "test.mp4", "status": "pending"}
    ]
    _save_pending_queue(test_data)
    assert _load_pending_queue() == test_data

def test_load_download_state_missing(tmp_path):
    dest_path = str(tmp_path / "some_file.mp4")
    assert _load_download_state(dest_path, 1000) == set()

def test_save_and_load_download_state(tmp_path):
    dest_path = str(tmp_path / "some_file.mp4")
    # Create mock file to pass exists check
    with open(dest_path, "wb") as f:
        f.write(b"data")
        
    completed = {1, 2, 3}
    _save_download_state(dest_path, 1000, completed)
    assert _load_download_state(dest_path, 1000) == completed
