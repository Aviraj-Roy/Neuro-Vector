"""
Backend Guardrail: Filter out legacy OCR artifacts before MongoDB insertion.

PHASE-7: Prevent "Hospital - / UNKNOWN / ₹0" artifacts from entering the database.

This module provides a pre-insertion filter that removes invalid/artifact items
before they are persisted to MongoDB.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """Normalize text for comparison (lowercase, strip, remove special chars)."""
    if not text:
        return ""
    return text.lower().strip().replace("-", "").replace("_", "").replace(" ", "")


def is_artifact_item(category_name: str, item_name: str, amount: float, final_amount: float = None) -> bool:
    """
    Determine if an item is a legacy OCR artifact that should be filtered out.
    
    PHASE-7 Guardrail: Prevents invalid items from entering MongoDB.
    
    An item is considered an artifact if ALL of the following are true:
    1. Category is hospital-related (normalized: "hospital", "hospitalization")
    2. Item name is "UNKNOWN" or empty
    3. Amount is 0
    4. Final amount is 0 (if provided)
    
    Args:
        category_name: Category name from OCR extraction
        item_name: Item name from OCR extraction
        amount: Item amount
        final_amount: Final amount (optional, defaults to amount)
        
    Returns:
        True if item should be filtered out, False otherwise
    """
    if final_amount is None:
        final_amount = amount
    
    # Normalize for comparison
    norm_category = normalize_text(category_name)
    norm_item = normalize_text(item_name)
    
    # Check category: must be hospital-related
    hospital_categories = {"hospital", "hospitalization", "hospitalcharges"}
    if norm_category not in hospital_categories:
        return False
    
    # Check item name: must be UNKNOWN or empty
    if norm_item not in {"unknown", ""}:
        return False
    
    # Check amounts: must be zero
    if amount != 0 or final_amount != 0:
        return False
    
    # All conditions met - this is an artifact
    logger.info(
        f"Filtering out artifact item: category='{category_name}', "
        f"item='{item_name}', amount={amount}, final_amount={final_amount}"
    )
    return True


def filter_artifact_items(bill_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filter out artifact items from bill data before MongoDB insertion.
    
    PHASE-7 Guardrail: Ensures clean data enters the database.
    
    This function:
    1. Scans all categories and items
    2. Removes items identified as artifacts
    3. Removes empty categories after filtering
    4. Logs all filtered items for audit trail
    
    Args:
        bill_data: Bill data dictionary with 'items' key
        
    Returns:
        Filtered bill data (modifies in place and returns)
    """
    items_dict = bill_data.get("items", {})
    if not items_dict:
        return bill_data
    
    categories_to_remove = []
    total_filtered = 0
    
    for category_name, items_list in items_dict.items():
        if not isinstance(items_list, list):
            continue
        
        # Filter items in this category
        filtered_items = []
        for item in items_list:
            item_name = item.get("item_name") or item.get("description") or ""
            amount = item.get("amount", 0)
            final_amount = item.get("final_amount", amount)
            
            # Check if artifact
            if is_artifact_item(category_name, item_name, amount, final_amount):
                total_filtered += 1
                logger.warning(
                    f"FILTERED ARTIFACT: [{category_name}] {item_name} - "
                    f"₹{amount} (final: ₹{final_amount})"
                )
            else:
                filtered_items.append(item)
        
        # Update category with filtered items
        if filtered_items:
            items_dict[category_name] = filtered_items
        else:
            # Mark empty category for removal
            categories_to_remove.append(category_name)
            logger.info(f"Category '{category_name}' is empty after filtering, will be removed")
    
    # Remove empty categories
    for category_name in categories_to_remove:
        del items_dict[category_name]
    
    if total_filtered > 0:
        logger.info(f"✅ Filtered {total_filtered} artifact items from bill data")
    
    return bill_data


def validate_bill_items(bill_data: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate that bill data doesn't contain obvious artifacts.
    
    This is a final sanity check before insertion.
    
    Args:
        bill_data: Bill data dictionary
        
    Returns:
        (is_valid, error_message)
    """
    items_dict = bill_data.get("items", {})
    
    # Check for "Hospital - " category (with trailing space)
    if "Hospital - " in items_dict:
        return False, "Bill contains legacy 'Hospital - ' category (artifact)"
    
    # Check for UNKNOWN items with ₹0
    for category_name, items_list in items_dict.items():
        if not isinstance(items_list, list):
            continue
        
        for item in items_list:
            item_name = item.get("item_name") or item.get("description") or ""
            amount = item.get("amount", 0)
            final_amount = item.get("final_amount", amount)
            
            if is_artifact_item(category_name, item_name, amount, final_amount):
                return False, (
                    f"Bill contains artifact item: [{category_name}] {item_name} - "
                    f"₹{amount} (should have been filtered)"
                )
    
    return True, ""
