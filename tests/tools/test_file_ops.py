
import pytest
from pathlib import Path
from astra.tools.file_ops import FileOps


@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path

@pytest.fixture
def file_ops(temp_dir):
    ops = FileOps(backup_enabled=True)
    # Override root_dir to temp_dir to pass confinement checks
    ops._root_dir = temp_dir
    return ops

@pytest.mark.asyncio
async def test_file_ops_execute_read(file_ops, temp_dir):
    test_file = temp_dir / "test.txt"
    test_file.write_text("hello", encoding="utf-8")

    result = await file_ops.execute(operation="read", path=str(test_file))
    assert result == "hello"

@pytest.mark.asyncio
async def test_file_ops_execute_write(file_ops, temp_dir):
    test_file = temp_dir / "new.txt"
    result = await file_ops.execute(operation="write", path=str(test_file), content="world")
    assert "✅" in result
    assert test_file.read_text(encoding="utf-8") == "world"

@pytest.mark.asyncio
async def test_file_ops_execute_delete(file_ops, temp_dir):
    test_file = temp_dir / "delete_me.txt"
    test_file.write_text("bye", encoding="utf-8")

    result = await file_ops.execute(operation="delete", path=str(test_file))
    assert "✅" in result
    assert not test_file.exists()

@pytest.mark.asyncio
async def test_file_ops_execute_copy(file_ops, temp_dir):
    src = temp_dir / "src.txt"
    src.write_text("content", encoding="utf-8")
    dst = temp_dir / "dst.txt"

    result = await file_ops.execute(operation="copy", path=str(src), destination=str(dst))
    assert "✅" in result
    assert dst.exists()
    assert dst.read_text(encoding="utf-8") == "content"

@pytest.mark.asyncio
async def test_file_ops_execute_move(file_ops, temp_dir):
    src = temp_dir / "move_src.txt"
    src.write_text("moving", encoding="utf-8")
    dst = temp_dir / "move_dst.txt"

    result = await file_ops.execute(operation="move", path=str(src), destination=str(dst))
    assert "✅" in result
    assert dst.exists()
    assert not src.exists()

@pytest.mark.asyncio
async def test_file_ops_execute_exists(file_ops, temp_dir):
    test_file = temp_dir / "exists.txt"
    test_file.write_text("here", encoding="utf-8")

    assert await file_ops.execute(operation="exists", path=str(test_file)) is True
    assert await file_ops.execute(operation="exists", path=str(temp_dir / "none.txt")) is False

@pytest.mark.asyncio
async def test_file_ops_execute_list(file_ops, temp_dir):
    (temp_dir / "f1.txt").write_text("1")
    (temp_dir / "f2.txt").write_text("2")

    result = await file_ops.execute(operation="list", path=str(temp_dir))
    assert isinstance(result, list)
    assert len(result) >= 2

@pytest.mark.asyncio
async def test_file_ops_error_cases(file_ops, temp_dir):
    # Read non-existent
    result = await file_ops.execute(operation="read", path="non_existent.txt")
    assert "Failed" in result or "None" in str(result) or result is None

    # Missing destination
    result = await file_ops.execute(operation="copy", path="any.txt")
    assert "Destination required" in result

    result = await file_ops.execute(operation="move", path="any.txt")
    assert "Destination required" in result

    # Unknown operation
    result = await file_ops.execute(operation="unknown", path="any")
    assert "Unknown operation" in result

@pytest.mark.asyncio
async def test_file_ops_confinement_error(file_ops, temp_dir):
    # Temporarily set root to subfolder to test confinement
    sub = temp_dir / "subdir"
    sub.mkdir()
    file_ops._root_dir = sub
    
    outside = temp_dir / "outside.txt"
    outside.write_text("bad", encoding="utf-8")
    
    result = await file_ops.execute(operation="read", path=str(outside))
    # Implementation returns f"❌ Security Error: {e}" or "Failed to read"
    assert "Security Error" in result or "outside project root" in result or "Failed to read" in result

def test_file_ops_backup_behavior(file_ops, temp_dir):
    test_file = temp_dir / "backup.txt"
    test_file.write_text("old", encoding="utf-8")

    file_ops.write(test_file, "new", backup=True)
    backup_file = temp_dir / "backup.txt.bak"
    assert backup_file.exists()
    assert backup_file.read_text(encoding="utf-8") == "old"

    # Restore
    success = file_ops.restore_backup(test_file)
    assert success is True
    assert test_file.read_text(encoding="utf-8") == "old"
    assert not backup_file.exists()

def test_file_ops_delete_backup(file_ops, temp_dir):
    test_file = temp_dir / "delete_bak.txt"
    test_file.write_text("data", encoding="utf-8")

    file_ops.delete(test_file, backup=True)
    deleted_bak = temp_dir / "delete_bak.txt.deleted"
    assert deleted_bak.exists()
    assert not test_file.exists()

def test_file_ops_get_size(file_ops, temp_dir):
    test_file = temp_dir / "size.txt"
    test_file.write_text("12345", encoding="utf-8")
    assert file_ops.get_size(test_file) == 5
    assert file_ops.get_size(temp_dir / "nonexistent") == 0

def test_file_ops_max_depth(temp_dir):
    """Test max_depth logic."""
    (temp_dir / "root.txt").touch()
    (temp_dir / "sub").mkdir()
    (temp_dir / "sub" / "d1.txt").touch()
    (temp_dir / "sub" / "deep").mkdir()
    (temp_dir / "sub" / "deep" / "d2.txt").touch()

    ops = FileOps()
    # Override root because fixture does. But here we use temp_dir directly as root?
    # FileOps(root_dir=...) defaults to cwd or config.
    ops._root_dir = temp_dir 

    # depth=1 (root children only)
    # Note: list_files implementation depends on how it calculates depth.
    # If recursive=True (default list_files usually does walk).
    # Let's verify FileOps.list_files signature: (path, recursive=True, max_depth=None)
    
    files = list(ops.list_files(temp_dir, max_depth=1))
    names = [f.name for f in files]
    assert "root.txt" in names
    # d1.txt is in sub/d1.txt (depth 2 relative to root? or depth 1 relative to sub?)
    # If max_depth=1 relative to start path:
    # root contents: root.txt (file), sub (dir).
    # sub contents: d1.txt.
    # If max_depth=1, usually means immediate children.
    # d1.txt is child of sub (depth 2 from root).
    assert "d1.txt" not in names
    
    files_d2 = list(ops.list_files(temp_dir, max_depth=2))
    names_d2 = [f.name for f in files_d2]
    assert "root.txt" in names_d2
    assert "d1.txt" in names_d2
    assert "d2.txt" not in names_d2
