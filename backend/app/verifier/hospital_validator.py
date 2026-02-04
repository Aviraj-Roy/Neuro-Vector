"""
Hospital Validation and Tie-Up File Resolution.

Provides utilities to validate hospital names and resolve them to tie-up JSON files.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def normalize_hospital_name(hospital_name: str) -> str:
    """
    Normalize hospital name to a filesystem-safe slug.
    
    Examples:
        "Apollo Hospital" -> "apollo_hospital"
        "Max Super-Specialty Hospital" -> "max_super_specialty_hospital"
        "Fortis (Delhi)" -> "fortis_delhi"
    
    Args:
        hospital_name: Raw hospital name
        
    Returns:
        Normalized slug suitable for filename
    """
    if not hospital_name:
        return ""
    
    # Convert to lowercase
    slug = hospital_name.lower()
    
    # Replace special characters with underscores
    slug = re.sub(r'[^\w\s-]', '_', slug)
    
    # Replace whitespace and hyphens with underscores
    slug = re.sub(r'[-\s]+', '_', slug)
    
    # Remove consecutive underscores
    slug = re.sub(r'_+', '_', slug)
    
    # Strip leading/trailing underscores
    slug = slug.strip('_')
    
    return slug


def get_tieup_file_path(hospital_name: str, tieup_dir: str) -> Path:
    """
    Get the expected tie-up JSON file path for a hospital.
    
    Args:
        hospital_name: Hospital name
        tieup_dir: Directory containing tie-up JSON files
        
    Returns:
        Path to the tie-up JSON file
    """
    slug = normalize_hospital_name(hospital_name)
    filename = f"{slug}.json"
    return Path(tieup_dir) / filename


def list_available_hospitals(tieup_dir: str) -> List[str]:
    """
    List all available hospitals (based on JSON files in tieup directory).
    
    Args:
        tieup_dir: Directory containing tie-up JSON files
        
    Returns:
        List of hospital names (derived from filenames)
    """
    dir_path = Path(tieup_dir)
    
    if not dir_path.exists():
        logger.warning(f"Tie-up directory does not exist: {tieup_dir}")
        return []
    
    hospitals = []
    for file_path in dir_path.glob("*.json"):
        # Convert filename back to readable name
        # e.g., "apollo_hospital.json" -> "Apollo Hospital"
        name = file_path.stem.replace('_', ' ').title()
        hospitals.append(name)
    
    return sorted(hospitals)


def validate_hospital_exists(hospital_name: str, tieup_dir: str) -> tuple[bool, Optional[str]]:
    """
    Validate that a tie-up JSON file exists for the given hospital.
    
    Args:
        hospital_name: Hospital name to validate
        tieup_dir: Directory containing tie-up JSON files
        
    Returns:
        Tuple of (is_valid, error_message)
        - (True, None) if valid
        - (False, error_message) if invalid
    """
    if not hospital_name or not isinstance(hospital_name, str):
        return False, "hospital_name must be a non-empty string"
    
    tieup_path = get_tieup_file_path(hospital_name, tieup_dir)
    
    if not tieup_path.exists():
        available = list_available_hospitals(tieup_dir)
        error_msg = (
            f"Tie-up rate sheet not found for hospital: {hospital_name}\n"
            f"Expected file: {tieup_path}\n"
            f"Available hospitals ({len(available)}): {', '.join(available) if available else 'None'}"
        )
        return False, error_msg
    
    return True, None


def get_hospital_display_name(tieup_file_path: Path) -> str:
    """
    Get a display-friendly hospital name from a tie-up file path.
    
    Args:
        tieup_file_path: Path to tie-up JSON file
        
    Returns:
        Display-friendly hospital name
    """
    # Convert "apollo_hospital.json" -> "Apollo Hospital"
    return tieup_file_path.stem.replace('_', ' ').title()
