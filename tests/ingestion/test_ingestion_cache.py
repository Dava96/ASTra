"""Tests for IngestionCache."""

import json
from pathlib import Path

import pytest

from astra.ingestion.ingestion_cache import IngestionCache


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / ".astra_cache"

@pytest.fixture
def cache(cache_dir):
    return IngestionCache(persist_path=str(cache_dir))

def test_calculate_hash(tmp_path):
    f = tmp_path / "test.py"
    f.write_text("print('hello')")
    h1 = IngestionCache.calculate_hash(f)
    assert h1 is not None

    f.write_text("print('hello world')")
    h2 = IngestionCache.calculate_hash(f)
    assert h1 != h2

def test_cache_update_and_get(cache, tmp_path):
    f = tmp_path / "test.py"
    f.write_text("content")
    content_hash = cache.calculate_hash(f)

    cache.update(str(f), content_hash)
    assert cache.get_hash(f) == content_hash

def test_check_file_metadata(cache, tmp_path):
    f = tmp_path / "test.py"
    f.write_text("content")
    content_hash = cache.calculate_hash(f)

    cache.update(str(f), content_hash)

    # mtime and size should match
    assert cache.check_file(f) is True

    # Change content (size stays same if we are careful, but mtime changes)
    import time
    time.sleep(0.01) # Ensure mtime difference
    f.write_text("changed")

    assert cache.check_file(f) is False

def test_cache_persistence(cache_dir, tmp_path):
    c1 = IngestionCache(persist_path=str(cache_dir))
    f = tmp_path / "test.py"
    f.write_text("content")

    c1.update(str(f), "hash123")
    c1.save()

    # Load in new instance
    c2 = IngestionCache(persist_path=str(cache_dir))
    assert c2.get_hash(f) == "hash123"

def test_backward_compatibility(cache_dir):
    # Old format was {path: hash_string}
    old_data = {"file1.py": "oldhash"}
    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_dir, "w") as f:
        json.dump(old_data, f)

    cache = IngestionCache(persist_path=str(cache_dir))
    assert cache.get_hash(Path("file1.py")) == "oldhash"
    # mtime/size should be missing but not crash
    assert cache.check_file(Path("file1.py")) is False
