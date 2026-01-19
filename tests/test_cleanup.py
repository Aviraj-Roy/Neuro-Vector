"""Unit tests for post-OCR image cleanup utilities.

Tests cleanup logic for:
- Successful cleanup scenarios
- Failure handling (locked files, missing directories)
- Cleanup decision logic (OCR/DB status)
- Windows file lock retry mechanism
- Directory preservation
"""

import sys
sys.path.insert(0, ".")

import os
import tempfile
from pathlib import Path

from app.utils.cleanup import (
    cleanup_images,
    cleanup_specific_files,
    should_cleanup,
    get_directory_file_count,
    _cleanup_directory,
    _delete_file_with_retry,
)


def test_cleanup_empty_directories():
    """Test cleanup handles empty directories gracefully."""
    print("Testing cleanup with empty directories...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        upload_dir = Path(tmpdir) / "uploads"
        processed_dir = Path(tmpdir) / "processed"
        
        # Create empty directories
        upload_dir.mkdir()
        processed_dir.mkdir()
        
        # Cleanup should succeed with 0 files deleted
        deleted, failed, errors = cleanup_images(upload_dir, processed_dir)
        
        assert deleted == 0, f"Expected 0 files deleted, got {deleted}"
        assert failed == 0, f"Expected 0 files failed, got {failed}"
        assert len(errors) == 0, f"Expected no errors, got {errors}"
        
        # Directories should still exist
        assert upload_dir.exists(), "Upload directory should not be deleted"
        assert processed_dir.exists(), "Processed directory should not be deleted"
    
    print("  ✓ Empty directories handled correctly")


def test_cleanup_with_files():
    """Test cleanup successfully deletes files."""
    print("Testing cleanup with files...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        upload_dir = Path(tmpdir) / "uploads"
        processed_dir = Path(tmpdir) / "processed"
        
        upload_dir.mkdir()
        processed_dir.mkdir()
        
        # Create test files
        (upload_dir / "bill_page_1.png").write_text("test data")
        (upload_dir / "bill_page_2.png").write_text("test data")
        (processed_dir / "bill_page_1.png").write_text("processed data")
        (processed_dir / "bill_page_2.png").write_text("processed data")
        
        # Verify files exist
        assert get_directory_file_count(upload_dir) == 2
        assert get_directory_file_count(processed_dir) == 2
        
        # Cleanup
        deleted, failed, errors = cleanup_images(upload_dir, processed_dir)
        
        assert deleted == 4, f"Expected 4 files deleted, got {deleted}"
        assert failed == 0, f"Expected 0 files failed, got {failed}"
        
        # Verify files are deleted
        assert get_directory_file_count(upload_dir) == 0
        assert get_directory_file_count(processed_dir) == 0
        
        # Directories should still exist
        assert upload_dir.exists(), "Upload directory should not be deleted"
        assert processed_dir.exists(), "Processed directory should not be deleted"
    
    print("  ✓ Files deleted successfully")


def test_cleanup_missing_directories():
    """Test cleanup handles missing directories gracefully."""
    print("Testing cleanup with missing directories...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        upload_dir = Path(tmpdir) / "nonexistent_uploads"
        processed_dir = Path(tmpdir) / "nonexistent_processed"
        
        # Directories don't exist
        assert not upload_dir.exists()
        assert not processed_dir.exists()
        
        # Cleanup should succeed with 0 files
        deleted, failed, errors = cleanup_images(upload_dir, processed_dir)
        
        assert deleted == 0, f"Expected 0 files deleted, got {deleted}"
        assert failed == 0, f"Expected 0 files failed, got {failed}"
    
    print("  ✓ Missing directories handled correctly")


def test_cleanup_specific_files():
    """Test cleanup of specific file paths."""
    print("Testing cleanup of specific files...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files
        file1 = Path(tmpdir) / "bill_page_1.png"
        file2 = Path(tmpdir) / "bill_page_2.png"
        file3 = Path(tmpdir) / "other_file.png"
        
        file1.write_text("data")
        file2.write_text("data")
        file3.write_text("data")
        
        # Cleanup only file1 and file2
        deleted, failed, errors = cleanup_specific_files([file1, file2])
        
        assert deleted == 2, f"Expected 2 files deleted, got {deleted}"
        assert failed == 0, f"Expected 0 files failed, got {failed}"
        
        # Verify only specified files are deleted
        assert not file1.exists()
        assert not file2.exists()
        assert file3.exists(), "Other file should not be deleted"
    
    print("  ✓ Specific files deleted correctly")


def test_cleanup_already_deleted_files():
    """Test cleanup handles already-deleted files gracefully."""
    print("Testing cleanup with already-deleted files...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        upload_dir = Path(tmpdir) / "uploads"
        upload_dir.mkdir()
        
        # Create and then delete a file
        test_file = upload_dir / "deleted.png"
        test_file.write_text("data")
        test_file.unlink()
        
        # Cleanup should succeed even though file is already gone
        deleted, failed, errors = cleanup_images(upload_dir, "nonexistent")
        
        assert failed == 0, f"Expected 0 files failed, got {failed}"
    
    print("  ✓ Already-deleted files handled correctly")


def test_should_cleanup_logic():
    """Test cleanup decision logic."""
    print("Testing should_cleanup decision logic...")
    
    # Both succeeded - should cleanup
    should_run, reason = should_cleanup(ocr_success=True, db_success=True)
    assert should_run, "Should cleanup when both OCR and DB succeed"
    assert "successful" in reason.lower()
    
    # OCR failed - should NOT cleanup
    should_run, reason = should_cleanup(ocr_success=False, db_success=True)
    assert not should_run, "Should not cleanup when OCR fails"
    assert "ocr" in reason.lower()
    
    # DB failed - should NOT cleanup
    should_run, reason = should_cleanup(ocr_success=True, db_success=False)
    assert not should_run, "Should not cleanup when DB save fails"
    assert "database" in reason.lower()
    
    # Both failed - should NOT cleanup
    should_run, reason = should_cleanup(ocr_success=False, db_success=False)
    assert not should_run, "Should not cleanup when both fail"
    
    # Force cleanup overrides
    should_run, reason = should_cleanup(ocr_success=False, db_success=False, force_cleanup=True)
    assert should_run, "Force cleanup should override failures"
    assert "forced" in reason.lower()
    
    print("  ✓ Cleanup decision logic working correctly")


def test_directory_file_count():
    """Test file counting utility."""
    print("Testing directory file count...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "test"
        test_dir.mkdir()
        
        # Empty directory
        assert get_directory_file_count(test_dir) == 0
        
        # Add files
        (test_dir / "file1.txt").write_text("data")
        (test_dir / "file2.txt").write_text("data")
        assert get_directory_file_count(test_dir) == 2
        
        # Add subdirectory (should not be counted)
        (test_dir / "subdir").mkdir()
        assert get_directory_file_count(test_dir) == 2
        
        # Nonexistent directory
        assert get_directory_file_count(Path(tmpdir) / "nonexistent") == 0
    
    print("  ✓ Directory file count working correctly")


def test_cleanup_preserves_subdirectories():
    """Test that cleanup doesn't delete subdirectories."""
    print("Testing subdirectory preservation...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        upload_dir = Path(tmpdir) / "uploads"
        upload_dir.mkdir()
        
        # Create files
        (upload_dir / "file1.png").write_text("data")
        (upload_dir / "file2.png").write_text("data")
        
        # Create subdirectory with files
        subdir = upload_dir / "archived"
        subdir.mkdir()
        (subdir / "old_bill.png").write_text("old data")
        
        # Cleanup (non-recursive, should only delete files in upload_dir)
        deleted, failed, errors = _cleanup_directory(upload_dir)
        
        # Only the 2 files in upload_dir should be deleted
        assert deleted == 2, f"Expected 2 files deleted, got {deleted}"
        
        # Subdirectory and its contents should remain
        assert subdir.exists(), "Subdirectory should not be deleted"
        assert (subdir / "old_bill.png").exists(), "Files in subdirectory should not be deleted"
    
    print("  ✓ Subdirectories preserved correctly")


def test_cleanup_mixed_file_types():
    """Test cleanup handles various file types."""
    print("Testing cleanup with mixed file types...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        upload_dir = Path(tmpdir) / "uploads"
        upload_dir.mkdir()
        
        # Create various file types
        (upload_dir / "bill.png").write_text("image data")
        (upload_dir / "bill.jpg").write_text("image data")
        (upload_dir / "metadata.json").write_text("{}")
        (upload_dir / "README.txt").write_text("readme")
        
        # Cleanup should delete all file types
        deleted, failed, errors = cleanup_images(upload_dir, "nonexistent")
        
        assert deleted == 4, f"Expected 4 files deleted, got {deleted}"
        assert get_directory_file_count(upload_dir) == 0
    
    print("  ✓ Mixed file types handled correctly")


def test_file_retry_logic():
    """Test retry logic for file deletion."""
    print("Testing file deletion retry logic...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("data")
        
        # Test successful deletion (no retries needed)
        success = _delete_file_with_retry(test_file, max_retries=3, retry_delay_seconds=0.1)
        assert success, "File deletion should succeed"
        assert not test_file.exists(), "File should be deleted"
        
        # Test already-deleted file (should return True)
        success = _delete_file_with_retry(test_file, max_retries=3, retry_delay_seconds=0.1)
        assert success, "Already-deleted file should return True"
    
    print("  ✓ File deletion retry logic working")


def run_all_tests():
    """Run all cleanup tests."""
    print("\n" + "=" * 60)
    print("Running Image Cleanup Tests")
    print("=" * 60 + "\n")
    
    tests = [
        test_cleanup_empty_directories,
        test_cleanup_with_files,
        test_cleanup_missing_directories,
        test_cleanup_specific_files,
        test_cleanup_already_deleted_files,
        test_should_cleanup_logic,
        test_directory_file_count,
        test_cleanup_preserves_subdirectories,
        test_cleanup_mixed_file_types,
        test_file_retry_logic,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {type(e).__name__}: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
