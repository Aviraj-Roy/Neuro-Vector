"""Post-OCR cleanup utilities for temporary image files.

This module provides safe, production-ready cleanup of temporary images
after successful OCR processing and database persistence.

Design Principles:
- Cleanup only after verified success (OCR + DB save)
- Never delete directories, only files within them
- Safe for concurrent processing (no global wipes)
- Robust error handling (never crashes the pipeline)
- Comprehensive logging for audit trail
"""

import logging
import os
import time
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def cleanup_images(
    upload_dir: str | Path,
    processed_dir: str | Path,
    max_retries: int = 3,
    retry_delay_seconds: float = 0.5,
) -> Tuple[int, int, List[str]]:
    """Delete all image files from upload and processed directories.
    
    This function safely removes temporary images after successful OCR and
    database persistence. It preserves directory structure and handles
    Windows file locks with retry logic.
    
    Args:
        upload_dir: Directory containing original uploaded images (e.g., 'uploads/')
        processed_dir: Directory containing preprocessed images (e.g., 'uploads/processed/')
        max_retries: Maximum retry attempts for locked files (Windows compatibility)
        retry_delay_seconds: Delay between retry attempts
        
    Returns:
        Tuple of (files_deleted, files_failed, failed_paths)
        - files_deleted: Number of successfully deleted files
        - files_failed: Number of files that could not be deleted
        - failed_paths: List of paths that failed to delete
        
    Example:
        >>> deleted, failed, errors = cleanup_images("uploads", "uploads/processed")
        >>> logger.info(f"Cleanup: {deleted} deleted, {failed} failed")
        
    Notes:
        - Directories are never deleted, only files within them
        - Handles missing directories gracefully (no error)
        - Logs each deletion for audit trail
        - Windows file lock errors are retried automatically
    """
    upload_path = Path(upload_dir)
    processed_path = Path(processed_dir)
    
    files_deleted = 0
    files_failed = 0
    failed_paths: List[str] = []
    
    logger.info(f"Starting post-OCR image cleanup: upload_dir={upload_path}, processed_dir={processed_path}")
    
    # Cleanup both directories
    for directory in [upload_path, processed_path]:
        deleted, failed, errors = _cleanup_directory(
            directory,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay_seconds,
        )
        files_deleted += deleted
        files_failed += failed
        failed_paths.extend(errors)
    
    if files_failed > 0:
        logger.warning(
            f"Image cleanup completed with errors: {files_deleted} deleted, "
            f"{files_failed} failed. Failed paths: {failed_paths}"
        )
    else:
        logger.info(f"Image cleanup completed successfully: {files_deleted} files deleted")
    
    return files_deleted, files_failed, failed_paths


def _cleanup_directory(
    directory: Path,
    max_retries: int = 3,
    retry_delay_seconds: float = 0.5,
) -> Tuple[int, int, List[str]]:
    """Delete all files in a directory (non-recursive).
    
    Args:
        directory: Directory to clean
        max_retries: Maximum retry attempts for locked files
        retry_delay_seconds: Delay between retries
        
    Returns:
        Tuple of (files_deleted, files_failed, failed_paths)
    """
    files_deleted = 0
    files_failed = 0
    failed_paths: List[str] = []
    
    # Check if directory exists
    if not directory.exists():
        logger.debug(f"Directory does not exist, skipping: {directory}")
        return files_deleted, files_failed, failed_paths
    
    if not directory.is_dir():
        logger.warning(f"Path is not a directory, skipping: {directory}")
        return files_deleted, files_failed, failed_paths
    
    # Get all files in directory (non-recursive)
    try:
        files = [f for f in directory.iterdir() if f.is_file()]
    except PermissionError as e:
        logger.error(f"Permission denied reading directory {directory}: {e}")
        return files_deleted, files_failed, failed_paths
    except Exception as e:
        logger.error(f"Error listing directory {directory}: {e}")
        return files_deleted, files_failed, failed_paths
    
    if not files:
        logger.debug(f"No files to delete in directory: {directory}")
        return files_deleted, files_failed, failed_paths
    
    logger.info(f"Found {len(files)} files to delete in {directory}")
    
    # Delete each file with retry logic
    for file_path in files:
        success = _delete_file_with_retry(
            file_path,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay_seconds,
        )
        
        if success:
            files_deleted += 1
            logger.debug(f"Deleted file: {file_path}")
        else:
            files_failed += 1
            failed_paths.append(str(file_path))
            logger.warning(f"Failed to delete file after {max_retries} retries: {file_path}")
    
    return files_deleted, files_failed, failed_paths


def _delete_file_with_retry(
    file_path: Path,
    max_retries: int = 3,
    retry_delay_seconds: float = 0.5,
) -> bool:
    """Attempt to delete a file with retry logic for Windows file locks.
    
    Args:
        file_path: Path to file to delete
        max_retries: Maximum retry attempts
        retry_delay_seconds: Delay between retries
        
    Returns:
        True if file was deleted successfully, False otherwise
    """
    for attempt in range(max_retries):
        try:
            file_path.unlink(missing_ok=True)  # missing_ok=True prevents error if already deleted
            return True
        except PermissionError as e:
            # Windows file lock - retry with delay
            if attempt < max_retries - 1:
                logger.debug(
                    f"File locked (attempt {attempt + 1}/{max_retries}), retrying: {file_path}"
                )
                time.sleep(retry_delay_seconds)
            else:
                logger.error(f"PermissionError deleting file after {max_retries} attempts: {file_path} - {e}")
                return False
        except FileNotFoundError:
            # File already deleted (race condition) - consider success
            logger.debug(f"File already deleted: {file_path}")
            return True
        except Exception as e:
            # Unexpected error - log and fail
            logger.error(f"Unexpected error deleting file {file_path}: {type(e).__name__}: {e}")
            return False
    
    return False


def should_cleanup(
    ocr_success: bool,
    db_success: bool,
    force_cleanup: bool = False,
) -> Tuple[bool, Optional[str]]:
    """Determine whether cleanup should proceed based on pipeline status.
    
    Args:
        ocr_success: Whether OCR completed successfully
        db_success: Whether database save succeeded
        force_cleanup: Force cleanup regardless of status (use with caution)
        
    Returns:
        Tuple of (should_cleanup, reason)
        - should_cleanup: Boolean indicating if cleanup should proceed
        - reason: String explaining the decision (for logging)
        
    Example:
        >>> should_run, reason = should_cleanup(ocr_success=True, db_success=True)
        >>> if should_run:
        >>>     cleanup_images("uploads", "uploads/processed")
        >>> else:
        >>>     logger.info(f"Cleanup skipped: {reason}")
    """
    if force_cleanup:
        return True, "Forced cleanup (force_cleanup=True)"
    
    if not ocr_success:
        return False, "OCR processing failed - preserving images for debugging"
    
    if not db_success:
        return False, "Database save failed - preserving images for retry"
    
    return True, "OCR and DB save successful"


def cleanup_specific_files(
    file_paths: List[str | Path],
    max_retries: int = 3,
    retry_delay_seconds: float = 0.5,
) -> Tuple[int, int, List[str]]:
    """Delete specific image files by path.
    
    This is useful for cleaning up only the images associated with a specific
    bill/upload session when processing multiple bills concurrently.
    
    Args:
        file_paths: List of file paths to delete
        max_retries: Maximum retry attempts for locked files
        retry_delay_seconds: Delay between retries
        
    Returns:
        Tuple of (files_deleted, files_failed, failed_paths)
        
    Example:
        >>> # Clean only files from this specific upload
        >>> image_paths = ["uploads/bill_page_1.png", "uploads/bill_page_2.png"]
        >>> processed_paths = ["uploads/processed/bill_page_1.png", ...]
        >>> deleted, failed, _ = cleanup_specific_files(image_paths + processed_paths)
    """
    files_deleted = 0
    files_failed = 0
    failed_paths: List[str] = []
    
    logger.info(f"Starting cleanup of {len(file_paths)} specific files")
    
    for file_path in file_paths:
        path = Path(file_path)
        
        if not path.exists():
            logger.debug(f"File already deleted or does not exist: {path}")
            continue
        
        if not path.is_file():
            logger.warning(f"Path is not a file, skipping: {path}")
            continue
        
        success = _delete_file_with_retry(
            path,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay_seconds,
        )
        
        if success:
            files_deleted += 1
            logger.debug(f"Deleted file: {path}")
        else:
            files_failed += 1
            failed_paths.append(str(path))
            logger.warning(f"Failed to delete file: {path}")
    
    if files_failed > 0:
        logger.warning(
            f"Specific file cleanup completed with errors: {files_deleted} deleted, "
            f"{files_failed} failed"
        )
    else:
        logger.info(f"Specific file cleanup completed: {files_deleted} files deleted")
    
    return files_deleted, files_failed, failed_paths


def get_directory_file_count(directory: str | Path) -> int:
    """Count files in a directory (for pre/post cleanup verification).
    
    Args:
        directory: Directory path to check
        
    Returns:
        Number of files in directory (0 if directory doesn't exist)
    """
    path = Path(directory)
    
    if not path.exists() or not path.is_dir():
        return 0
    
    try:
        return sum(1 for f in path.iterdir() if f.is_file())
    except Exception as e:
        logger.error(f"Error counting files in {directory}: {e}")
        return 0
