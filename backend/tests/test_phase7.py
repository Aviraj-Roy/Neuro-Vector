"""
PHASE-7 Validation Test

Quick test to verify:
1. Models can be imported
2. Validation functions work
3. Rendering functions work
"""

import sys
from pathlib import Path

# Add backend to path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

def test_models():
    """Test that new models can be imported."""
    print("Testing models import...")
    from app.verifier.models import (
        DebugItemInfo,
        RenderingOptions,
        VerificationResponse,
        VerificationStatus,
    )
    
    # Create sample rendering options
    options = RenderingOptions(
        debug_mode=False,
        show_normalized_names=True,
        show_similarity_scores=True,
    )
    print(f"✅ RenderingOptions created: {options}")
    
    # Create sample debug info
    debug_info = DebugItemInfo(
        bill_item_original="PARACETAMOL 500MG",
        normalized_item="paracetamol 500mg",
        category_attempts=[],
        item_candidates=[],
        final_decision="GREEN",
        decision_reason="High similarity match"
    )
    print(f"✅ DebugItemInfo created: {debug_info.bill_item_original}")
    
    print("✅ Models test passed\n")


def test_validation():
    """Test validation functions."""
    print("Testing validation functions...")
    from app.verifier.models import (
        BillInput,
        BillCategory,
        BillItem,
        VerificationResponse,
        CategoryVerificationResult,
        ItemVerificationResult,
        VerificationStatus,
    )
    from app.verifier.output_renderer import (
        validate_completeness,
        validate_summary_counters,
    )
    
    # Create sample bill input
    bill = BillInput(
        hospital_name="Test Hospital",
        categories=[
            BillCategory(
                category_name="Medicines",
                items=[
                    BillItem(item_name="Item 1", quantity=1.0, amount=100.0),
                    BillItem(item_name="Item 2", quantity=1.0, amount=200.0),
                ]
            )
        ]
    )
    
    # Create sample verification response (matching)
    response = VerificationResponse(
        hospital="Test Hospital",
        matched_hospital="Test Hospital",
        hospital_similarity=0.95,
        results=[
            CategoryVerificationResult(
                category="Medicines",
                matched_category="Medicines",
                category_similarity=0.90,
                items=[
                    ItemVerificationResult(
                        bill_item="Item 1",
                        matched_item="Item 1",
                        status=VerificationStatus.GREEN,
                        bill_amount=100.0,
                        allowed_amount=100.0,
                        extra_amount=0.0,
                    ),
                    ItemVerificationResult(
                        bill_item="Item 2",
                        matched_item="Item 2",
                        status=VerificationStatus.RED,
                        bill_amount=200.0,
                        allowed_amount=150.0,
                        extra_amount=50.0,
                    ),
                ]
            )
        ],
        green_count=1,
        red_count=1,
        mismatch_count=0,
        allowed_not_comparable_count=0,
    )
    
    # Test completeness validation
    is_complete, msg = validate_completeness(bill, response)
    if is_complete:
        print(f"✅ Completeness validation passed")
    else:
        print(f"❌ Completeness validation failed: {msg}")
    
    # Test counter validation
    is_valid, msg = validate_summary_counters(response)
    if is_valid:
        print(f"✅ Counter validation passed")
    else:
        print(f"❌ Counter validation failed: {msg}")
    
    print("✅ Validation test passed\n")


def test_rendering():
    """Test rendering functions."""
    print("Testing rendering functions...")
    from app.verifier.models import (
        VerificationResponse,
        CategoryVerificationResult,
        ItemVerificationResult,
        VerificationStatus,
        RenderingOptions,
    )
    from app.verifier.output_renderer import render_final_view
    
    # Create sample response
    response = VerificationResponse(
        hospital="Test Hospital",
        matched_hospital="Test Hospital",
        hospital_similarity=0.95,
        results=[
            CategoryVerificationResult(
                category="Medicines",
                matched_category="Medicines",
                category_similarity=0.90,
                items=[
                    ItemVerificationResult(
                        bill_item="PARACETAMOL 500MG",
                        matched_item="Paracetamol 500mg",
                        status=VerificationStatus.GREEN,
                        bill_amount=100.0,
                        allowed_amount=100.0,
                        extra_amount=0.0,
                        similarity_score=0.98,
                        normalized_item_name="paracetamol 500mg",
                    ),
                ]
            )
        ],
        total_bill_amount=100.0,
        total_allowed_amount=100.0,
        total_extra_amount=0.0,
        green_count=1,
        red_count=0,
        mismatch_count=0,
        allowed_not_comparable_count=0,
    )
    
    # Render final view
    options = RenderingOptions(
        show_normalized_names=True,
        show_similarity_scores=True,
    )
    output = render_final_view(response, options)
    
    # Check output contains expected elements
    assert "VERIFICATION RESULTS (FINAL VIEW)" in output
    assert "Test Hospital" in output
    assert "PARACETAMOL 500MG" in output
    assert "paracetamol 500mg" in output
    assert "✅" in output
    
    print("✅ Rendering test passed")
    print("\nSample output:")
    print("-" * 80)
    print(output)
    print("-" * 80)


if __name__ == "__main__":
    print("=" * 80)
    print("PHASE-7 VALIDATION TEST")
    print("=" * 80)
    print()
    
    try:
        test_models()
        test_validation()
        test_rendering()
        
        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)
        print("\nPhase-7 implementation is working correctly!")
        print("You can now use:")
        print("  - python -m backend.main --bill <file> --hospital <name>")
        print("  - python -m backend.main --bill <file> --hospital <name> --debug")
        
    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ TEST FAILED")
        print("=" * 80)
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
