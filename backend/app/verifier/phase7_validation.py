"""
Phase-7 Validation Module for Hospital Bill Verifier.

Ensures output completeness, correctness, and presentation quality.

Phase-7 Goals:
1. No items lost - Every input item appears in output
2. Clean categories - No duplicate category blocks
3. Strict financial rules - Bill amount always present
4. Summary reconciliation - Counts match totals
5. No regressions - Phases 1-6 unchanged

This module provides comprehensive validation without changing matching logic.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from app.verifier.models import VerificationStatus
from app.verifier.models_v3 import DebugItemTrace, DebugView, FinalView

logger = logging.getLogger(__name__)


# =============================================================================
# Completeness Validation
# =============================================================================


def validate_completeness(
    input_items: List[str],
    debug_view: DebugView
) -> Dict:
    """
    Validate that no items were lost during processing.
    
    Phase-7 Requirement: Every bill item must appear exactly once in output.
    
    Args:
        input_items: Original bill item texts from input
        debug_view: Debug view containing all processed items
        
    Returns:
        Validation result with:
        - all_items_present: bool
        - input_count: int
        - output_count: int
        - missing_items: List[str]
        - extra_items: List[str]
    """
    # Get all output items
    output_items = []
    for category in debug_view.categories:
        for item in category.items:
            output_items.append(item.original_bill_text)
    
    # Find missing items (in input but not in output)
    missing_items = [
        item for item in input_items
        if item not in output_items
    ]
    
    # Find extra items (in output but not in input)
    extra_items = [
        item for item in output_items
        if item not in input_items
    ]
    
    all_items_present = len(missing_items) == 0 and len(extra_items) == 0
    
    result = {
        "all_items_present": all_items_present,
        "input_count": len(input_items),
        "output_count": len(output_items),
        "missing_items": missing_items,
        "extra_items": extra_items
    }
    
    if not all_items_present:
        logger.warning(
            f"⚠️ Completeness check FAILED! "
            f"Input: {len(input_items)}, Output: {len(output_items)}"
        )
        if missing_items:
            logger.warning(f"Missing items ({len(missing_items)}): {missing_items[:3]}...")
        if extra_items:
            logger.warning(f"Extra items ({len(extra_items)}): {extra_items[:3]}...")
    else:
        logger.info(f"✅ Completeness check PASSED - All {len(input_items)} items present")
    
    return result


# =============================================================================
# Financial Fields Validation
# =============================================================================


def validate_financial_fields(final_view: FinalView) -> Dict:
    """
    Validate financial fields according to Phase-7 rules.
    
    Rules:
    - GREEN: bill_amount ✓, allowed_amount ✓, extra_amount optional
    - RED: bill_amount ✓, allowed_amount ✓, extra_amount ✓
    - MISMATCH: bill_amount ✓, allowed_amount N/A, extra_amount N/A
    - ALLOWED_NOT_COMPARABLE: bill_amount ✓, others N/A
    
    Args:
        final_view: Final view to validate
        
    Returns:
        Validation result with:
        - valid: bool
        - issues: List[str]
    """
    issues = []
    
    for category in final_view.categories:
        for item in category.items:
            # Bill amount ALWAYS required (Phase-7 strict rule)
            if item.bill_amount <= 0:
                issues.append(
                    f"❌ Missing bill_amount for: {item.original_bill_text} "
                    f"(status: {item.final_status.value})"
                )
            
            # Status-specific validation
            if item.final_status == VerificationStatus.GREEN:
                if item.allowed_amount <= 0:
                    issues.append(
                        f"❌ GREEN item missing allowed_amount: {item.original_bill_text}"
                    )
            
            elif item.final_status == VerificationStatus.RED:
                if item.allowed_amount <= 0:
                    issues.append(
                        f"❌ RED item missing allowed_amount: {item.original_bill_text}"
                    )
                if item.extra_amount <= 0:
                    issues.append(
                        f"❌ RED item missing extra_amount: {item.original_bill_text}"
                    )
            
            elif item.final_status == VerificationStatus.MISMATCH:
                # MISMATCH should have N/A for allowed/extra
                # (allowed_amount = 0.0 is acceptable)
                pass
            
            elif item.final_status == VerificationStatus.ALLOWED_NOT_COMPARABLE:
                # Bill amount required, others optional
                pass
    
    valid = len(issues) == 0
    
    result = {
        "valid": valid,
        "issues": issues,
        "total_items_checked": sum(len(cat.items) for cat in final_view.categories)
    }
    
    if not valid:
        logger.warning(f"⚠️ Financial validation FAILED with {len(issues)} issues")
        for issue in issues[:5]:  # Show first 5
            logger.warning(f"  {issue}")
    else:
        logger.info(f"✅ Financial validation PASSED - All {result['total_items_checked']} items valid")
    
    return result


# =============================================================================
# Category Uniqueness Validation
# =============================================================================


def validate_category_uniqueness(final_view: FinalView) -> Dict:
    """
    Ensure each category appears exactly once in final view.
    
    Phase-7 Requirement: No repeated category blocks.
    
    Args:
        final_view: Final view to validate
        
    Returns:
        Validation result with:
        - unique: bool
        - duplicates: List[str]
        - category_count: int
        - unique_category_count: int
    """
    category_names = [cat.category for cat in final_view.categories]
    duplicates = [
        name for name in set(category_names)
        if category_names.count(name) > 1
    ]
    
    unique = len(duplicates) == 0
    
    result = {
        "unique": unique,
        "duplicates": duplicates,
        "category_count": len(category_names),
        "unique_category_count": len(set(category_names))
    }
    
    if not unique:
        logger.warning(
            f"⚠️ Category uniqueness FAILED! "
            f"Duplicate categories: {duplicates}"
        )
    else:
        logger.info(
            f"✅ Category uniqueness PASSED - "
            f"{result['unique_category_count']} unique categories"
        )
    
    return result


# =============================================================================
# Status Count Validation
# =============================================================================


def validate_status_counts(final_view: FinalView, input_item_count: int) -> Dict:
    """
    Validate that status counts sum to total input items.
    
    Phase-7 Requirement: GREEN + RED + MISMATCH + ALLOWED_NOT_COMPARABLE == input_count
    
    Args:
        final_view: Final view with status counts
        input_item_count: Total number of input items
        
    Returns:
        Validation result with:
        - match: bool
        - input_count: int
        - status_sum: int
        - breakdown: Dict[str, int]
        - difference: int
    """
    status_sum = (
        final_view.green_count +
        final_view.red_count +
        final_view.mismatch_count +
        final_view.allowed_not_comparable_count
    )
    
    match = status_sum == input_item_count
    difference = status_sum - input_item_count
    
    result = {
        "match": match,
        "input_count": input_item_count,
        "status_sum": status_sum,
        "difference": difference,
        "breakdown": {
            "GREEN": final_view.green_count,
            "RED": final_view.red_count,
            "MISMATCH": final_view.mismatch_count,
            "ALLOWED_NOT_COMPARABLE": final_view.allowed_not_comparable_count
        }
    }
    
    if not match:
        logger.warning(
            f"⚠️ Status count validation FAILED! "
            f"Input: {input_item_count}, Status sum: {status_sum}, "
            f"Difference: {difference:+d}"
        )
        logger.warning(f"  Breakdown: {result['breakdown']}")
    else:
        logger.info(
            f"✅ Status count validation PASSED - "
            f"All {input_item_count} items accounted for"
        )
    
    return result


# =============================================================================
# Comprehensive Phase-7 Validation
# =============================================================================


def validate_phase7_requirements(
    input_items: List[str],
    debug_view: DebugView,
    final_view: FinalView
) -> Dict:
    """
    Comprehensive Phase-7 validation.
    
    Runs all Phase-7 validation checks:
    1. Completeness - No items lost
    2. Financial fields - All required fields present
    3. Category uniqueness - No duplicate categories
    4. Status counts - Sum matches input count
    
    Args:
        input_items: Original bill item texts
        debug_view: Debug view
        final_view: Final view
        
    Returns:
        Comprehensive validation report with:
        - phase7_compliant: bool (overall pass/fail)
        - checks: Dict of individual check results
        - summary: Human-readable summary
    """
    logger.info("=" * 80)
    logger.info("Running Phase-7 Validation")
    logger.info("=" * 80)
    
    report = {
        "phase7_compliant": True,
        "checks": {},
        "summary": []
    }
    
    # Check 1: Completeness
    logger.info("Check 1: Completeness (no items lost)...")
    completeness = validate_completeness(input_items, debug_view)
    report["checks"]["completeness"] = completeness
    if not completeness["all_items_present"]:
        report["phase7_compliant"] = False
        report["summary"].append("❌ Completeness check failed - items were lost")
    else:
        report["summary"].append("✅ Completeness check passed")
    
    # Check 2: Financial fields
    logger.info("Check 2: Financial fields...")
    financial = validate_financial_fields(final_view)
    report["checks"]["financial"] = financial
    if not financial["valid"]:
        report["phase7_compliant"] = False
        report["summary"].append(f"❌ Financial validation failed - {len(financial['issues'])} issues")
    else:
        report["summary"].append("✅ Financial validation passed")
    
    # Check 3: Category uniqueness
    logger.info("Check 3: Category uniqueness...")
    categories = validate_category_uniqueness(final_view)
    report["checks"]["categories"] = categories
    if not categories["unique"]:
        report["phase7_compliant"] = False
        report["summary"].append(f"❌ Category uniqueness failed - duplicates: {categories['duplicates']}")
    else:
        report["summary"].append("✅ Category uniqueness passed")
    
    # Check 4: Status counts
    logger.info("Check 4: Status count reconciliation...")
    status_counts = validate_status_counts(final_view, len(input_items))
    report["checks"]["status_counts"] = status_counts
    if not status_counts["match"]:
        report["phase7_compliant"] = False
        report["summary"].append(
            f"❌ Status counts don't match - "
            f"difference: {status_counts['difference']:+d}"
        )
    else:
        report["summary"].append("✅ Status count reconciliation passed")
    
    # Final summary
    logger.info("=" * 80)
    if report["phase7_compliant"]:
        logger.info("✅ Phase-7 Validation: PASSED")
        logger.info("All requirements met - output is complete and correct")
    else:
        logger.warning("❌ Phase-7 Validation: FAILED")
        logger.warning("Some requirements not met - see details above")
    logger.info("=" * 80)
    
    return report


# =============================================================================
# Testing
# =============================================================================

if __name__ == "__main__":
    print("Phase-7 Validation Module")
    print("=" * 80)
    print("Provides comprehensive validation for:")
    print("  1. Completeness - No items lost")
    print("  2. Financial fields - All required fields present")
    print("  3. Category uniqueness - No duplicate categories")
    print("  4. Status counts - Sum matches input count")
    print("=" * 80)
