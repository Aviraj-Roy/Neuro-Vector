"""
PHASE-7: Output Renderer Module

Provides clean separation between:
1. Debug View - Internal diagnostic view with all matching attempts
2. Final View - Clean user-facing view with one row per item

Also includes validation functions to ensure:
- Output completeness (all bill items present)
- Summary counter reconciliation
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from app.verifier.models import (
    BillInput,
    DebugItemInfo,
    RenderingOptions,
    VerificationResponse,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Validation Functions
# =============================================================================

def validate_completeness(
    bill_input: BillInput,
    verification_response: VerificationResponse
) -> Tuple[bool, str]:
    """
    Validate that every bill item appears exactly once in output.
    
    PHASE-7 CRITICAL: This ensures no items are lost during processing.
    
    PHASE-7 UPDATE: Excludes artifact items from validation:
    - Items in "Hospital - " category (with trailing space)
    - Items with name "UNKNOWN" and amount ₹0
    - These are legacy OCR artifacts that should not participate in verification
    
    Args:
        bill_input: Original bill input
        verification_response: Verification result
        
    Returns:
        (is_complete, error_message)
        - is_complete: True if all items present exactly once
        - error_message: Empty if complete, otherwise describes the issue
    """
    from app.db.artifact_filter import is_artifact_item
    
    # Count input items (excluding artifacts)
    input_items = []
    filtered_count = 0
    
    for category in bill_input.categories:
        for item in category.items:
            # PHASE-7: Skip artifacts
            if is_artifact_item(category.category_name, item.item_name, item.amount, item.amount):
                filtered_count += 1
                logger.debug(
                    f"Excluding artifact from validation: [{category.category_name}] "
                    f"{item.item_name} - ₹{item.amount}"
                )
                continue
            
            input_items.append((category.category_name, item.item_name, item.amount))
    
    input_count = len(input_items)
    
    if filtered_count > 0:
        logger.info(f"Excluded {filtered_count} artifact items from completeness validation")
    
    # Count output items
    output_items = []
    for cat_result in verification_response.results:
        for item_result in cat_result.items:
            output_items.append((cat_result.category, item_result.bill_item, item_result.bill_amount))
    
    output_count = len(output_items)
    
    # Check counts match
    if input_count != output_count:
        missing_items = []
        duplicate_items = []
        
        # Find missing items (in input but not in output)
        for inp_item in input_items:
            if inp_item not in output_items:
                missing_items.append(inp_item)
        
        # Find duplicate items (in output more than once)
        seen = set()
        for out_item in output_items:
            if out_item in seen:
                duplicate_items.append(out_item)
            seen.add(out_item)
        
        error_parts = []
        if missing_items:
            error_parts.append(f"Missing {len(missing_items)} items: {missing_items[:3]}")
        if duplicate_items:
            error_parts.append(f"Duplicate {len(duplicate_items)} items: {duplicate_items[:3]}")
        
        error_msg = (
            f"Item count mismatch: Input={input_count}, Output={output_count}. "
            + "; ".join(error_parts)
        )
        return False, error_msg
    
    # Check for duplicates even if counts match
    if len(set(output_items)) != output_count:
        return False, f"Duplicate items found in output (count={output_count}, unique={len(set(output_items))})"
    
    return True, ""


def validate_summary_counters(
    verification_response: VerificationResponse
) -> Tuple[bool, str]:
    """
    Validate that summary counters match actual items.
    
    PHASE-7 CRITICAL: Ensures GREEN + RED + MISMATCH + ALLOWED_NOT_COMPARABLE == total items
    
    Args:
        verification_response: Verification result
        
    Returns:
        (is_valid, error_message)
    """
    # Count actual items by status
    actual_green = 0
    actual_red = 0
    actual_mismatch = 0
    actual_allowed_not_comparable = 0
    
    for cat_result in verification_response.results:
        for item_result in cat_result.items:
            if item_result.status == VerificationStatus.GREEN:
                actual_green += 1
            elif item_result.status == VerificationStatus.RED:
                actual_red += 1
            elif item_result.status == VerificationStatus.MISMATCH:
                actual_mismatch += 1
            elif item_result.status == VerificationStatus.ALLOWED_NOT_COMPARABLE:
                actual_allowed_not_comparable += 1
    
    # Compare with summary counters
    summary_green = verification_response.green_count
    summary_red = verification_response.red_count
    summary_mismatch = verification_response.mismatch_count
    summary_allowed = verification_response.allowed_not_comparable_count
    
    errors = []
    
    if actual_green != summary_green:
        errors.append(f"GREEN: actual={actual_green}, summary={summary_green}")
    if actual_red != summary_red:
        errors.append(f"RED: actual={actual_red}, summary={summary_red}")
    if actual_mismatch != summary_mismatch:
        errors.append(f"MISMATCH: actual={actual_mismatch}, summary={summary_mismatch}")
    if actual_allowed_not_comparable != summary_allowed:
        errors.append(f"ALLOWED_NOT_COMPARABLE: actual={actual_allowed_not_comparable}, summary={summary_allowed}")
    
    if errors:
        error_msg = "Counter mismatch: " + "; ".join(errors)
        return False, error_msg
    
    # Verify total
    total_actual = actual_green + actual_red + actual_mismatch + actual_allowed_not_comparable
    total_summary = summary_green + summary_red + summary_mismatch + summary_allowed
    
    if total_actual != total_summary:
        return False, f"Total mismatch: actual={total_actual}, summary={total_summary}"
    
    return True, ""


# =============================================================================
# Rendering Functions
# =============================================================================

def render_final_view(
    verification_response: VerificationResponse,
    options: RenderingOptions = None
) -> str:
    """
    Render clean user-facing view.
    
    PHASE-7 Rules:
    - One row per bill item
    - Categories grouped (no duplicates)
    - Financial fields per status rules:
      * GREEN: bill_amount, allowed_amount, optional extra_amount
      * RED: bill_amount, allowed_amount, extra_amount (required)
      * MISMATCH: bill_amount, N/A for allowed/extra
      * ALLOWED_NOT_COMPARABLE: bill_amount, N/A for allowed/extra
    - Original + normalized names shown (if option enabled)
    
    Args:
        verification_response: Verification result
        options: Rendering options (defaults to standard view)
        
    Returns:
        Formatted string for display
    """
    if options is None:
        options = RenderingOptions()
    
    lines = []
    lines.append("=" * 80)
    lines.append("VERIFICATION RESULTS (FINAL VIEW)")
    lines.append("=" * 80)
    
    # Hospital info
    lines.append(f"Hospital: {verification_response.hospital}")
    if verification_response.matched_hospital:
        lines.append(f"Matched Hospital: {verification_response.matched_hospital}")
        if verification_response.hospital_similarity is not None:
            lines.append(f"Hospital Similarity: {verification_response.hospital_similarity:.2%}")
    
    # Summary statistics
    lines.append("")
    lines.append("Summary:")
    lines.append(f"  ✅ GREEN (Match): {verification_response.green_count}")
    lines.append(f"  ❌ RED (Overcharged): {verification_response.red_count}")
    lines.append(f"  ⚠️  MISMATCH (Not Found): {verification_response.mismatch_count}")
    lines.append(f"  🟦 ALLOWED_NOT_COMPARABLE: {verification_response.allowed_not_comparable_count}")
    
    total_items = (
        verification_response.green_count +
        verification_response.red_count +
        verification_response.mismatch_count +
        verification_response.allowed_not_comparable_count
    )
    lines.append(f"  📊 Total Items: {total_items}")
    
    # Financial summary
    lines.append("")
    lines.append("Financial Summary:")
    lines.append(f"  Total Bill Amount: ₹{verification_response.total_bill_amount:.2f}")
    lines.append(f"  Total Allowed Amount: ₹{verification_response.total_allowed_amount:.2f}")
    lines.append(f"  Total Extra Amount: ₹{verification_response.total_extra_amount:.2f}")
    
    # Category-wise results (PHASE-7: Each category appears ONCE)
    lines.append("")
    lines.append("Category-wise Results:")
    lines.append("-" * 80)
    
    for cat_result in verification_response.results:
        # Category header
        lines.append("")
        lines.append(f"📁 Category: {cat_result.category}")
        if cat_result.matched_category:
            lines.append(f"   Matched: {cat_result.matched_category}")
            if cat_result.category_similarity is not None:
                lines.append(f"   Similarity: {cat_result.category_similarity:.2%}")
        
        # Items in this category
        for item_result in cat_result.items:
            status = item_result.status
            status_icon = _get_status_icon(status)
            
            # Item line
            item_line = f"  {status_icon} {item_result.bill_item}"
            if options.show_normalized_names and item_result.normalized_item_name:
                item_line += f" (normalized: {item_result.normalized_item_name})"
            lines.append(item_line)
            
            # Matched item
            if item_result.matched_item:
                lines.append(f"     → Matched: {item_result.matched_item}")
                if options.show_similarity_scores and item_result.similarity_score is not None:
                    lines.append(f"     → Similarity: {item_result.similarity_score:.2%}")
            
            # Financial details (PHASE-7: Strict rules based on status)
            financial_line = f"     → "
            if status == VerificationStatus.GREEN:
                financial_line += f"Bill: ₹{item_result.bill_amount:.2f}, Allowed: ₹{item_result.allowed_amount:.2f}"
                if item_result.extra_amount > 0:
                    financial_line += f", Extra: ₹{item_result.extra_amount:.2f}"
            elif status == VerificationStatus.RED:
                financial_line += (
                    f"Bill: ₹{item_result.bill_amount:.2f}, "
                    f"Allowed: ₹{item_result.allowed_amount:.2f}, "
                    f"Extra: ₹{item_result.extra_amount:.2f}"
                )
            elif status in (VerificationStatus.MISMATCH, VerificationStatus.ALLOWED_NOT_COMPARABLE):
                financial_line += f"Bill: ₹{item_result.bill_amount:.2f}, Allowed: N/A, Extra: N/A"
            
            lines.append(financial_line)
            
            # Diagnostics (if enabled and present)
            if options.show_diagnostics and item_result.diagnostics:
                diag = item_result.diagnostics
                lines.append(f"     → Reason: {diag.failure_reason}")
                if diag.best_candidate:
                    lines.append(f"     → Best Candidate: {diag.best_candidate}")
    
    lines.append("")
    lines.append("=" * 80)
    
    return "\n".join(lines)


def render_debug_view(
    verification_response: VerificationResponse,
    debug_info: Dict[str, DebugItemInfo]
) -> str:
    """
    Render detailed debug view.
    
    PHASE-7: Contains all matching attempts, candidates, and rejection reasons.
    This is for internal diagnostics only.
    
    Args:
        verification_response: Verification result
        debug_info: Debug information for each item
        
    Returns:
        Formatted debug output
    """
    lines = []
    lines.append("=" * 80)
    lines.append("VERIFICATION RESULTS (DEBUG VIEW)")
    lines.append("=" * 80)
    
    # First show final view
    lines.append("")
    lines.append("[FINAL VIEW]")
    lines.append(render_final_view(verification_response))
    
    # Then show debug details
    lines.append("")
    lines.append("=" * 80)
    lines.append("[DEBUG DETAILS]")
    lines.append("=" * 80)
    
    for cat_result in verification_response.results:
        lines.append("")
        lines.append(f"Category: {cat_result.category}")
        lines.append("-" * 80)
        
        for item_result in cat_result.items:
            item_key = f"{cat_result.category}::{item_result.bill_item}"
            
            lines.append("")
            lines.append(f"  Item: {item_result.bill_item}")
            lines.append(f"  Status: {item_result.status}")
            
            # Show debug info if available
            if item_key in debug_info:
                info = debug_info[item_key]
                lines.append(f"  Original: {info.bill_item_original}")
                lines.append(f"  Normalized: {info.normalized_item}")
                lines.append(f"  Final Decision: {info.final_decision}")
                lines.append(f"  Decision Reason: {info.decision_reason}")
                
                if info.category_attempts:
                    lines.append("  Category Attempts:")
                    for attempt in info.category_attempts:
                        lines.append(f"    - {attempt}")
                
                if info.item_candidates:
                    lines.append("  Item Candidates:")
                    for candidate in info.item_candidates:
                        lines.append(f"    - {candidate}")
            else:
                lines.append("  [No debug info available]")
    
    lines.append("")
    lines.append("=" * 80)
    
    return "\n".join(lines)


def _get_status_icon(status: VerificationStatus) -> str:
    """Get emoji icon for verification status."""
    if status == VerificationStatus.GREEN:
        return "✅"
    elif status == VerificationStatus.RED:
        return "❌"
    elif status == VerificationStatus.MISMATCH:
        return "⚠️"
    elif status == VerificationStatus.ALLOWED_NOT_COMPARABLE:
        return "🟦"
    else:
        return "❓"
