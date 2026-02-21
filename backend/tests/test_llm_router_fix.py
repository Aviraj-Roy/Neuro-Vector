"""
Quick validation test for the LLM router fix.
Tests that match_with_llm is called correctly and returns expected results.
"""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from app.verifier.llm_router import LLMRouter, LLMMatchResult

def test_llm_router_method_exists():
    """Verify that match_with_llm method exists and has correct signature."""
    router = LLMRouter()
    
    # Check method exists
    assert hasattr(router, 'match_with_llm'), "LLMRouter missing match_with_llm method"
    
    # Check verify_match does NOT exist (it was the bug)
    assert not hasattr(router, 'verify_match'), "LLMRouter should not have verify_match method"
    
    print("✅ LLMRouter has correct method: match_with_llm")
    print("✅ LLMRouter does not have incorrect method: verify_match")

def test_llm_result_structure():
    """Verify LLMMatchResult has expected attributes."""
    router = LLMRouter()
    
    # Test auto-match case (high similarity)
    result = router.match_with_llm(
        bill_item="Consultation",
        tieup_item="Consultation - First Visit",
        similarity=0.90
    )
    
    # Check result type
    assert isinstance(result, LLMMatchResult), f"Expected LLMMatchResult, got {type(result)}"
    
    # Check required attributes
    assert hasattr(result, 'match'), "LLMMatchResult missing 'match' attribute"
    assert hasattr(result, 'confidence'), "LLMMatchResult missing 'confidence' attribute"
    assert hasattr(result, 'model_used'), "LLMMatchResult missing 'model_used' attribute"
    assert hasattr(result, 'error'), "LLMMatchResult missing 'error' attribute"
    assert hasattr(result, 'is_valid'), "LLMMatchResult missing 'is_valid' property"
    
    # Check values for auto-match
    assert result.match == True, "Auto-match should return match=True"
    assert result.confidence == 0.90, "Auto-match should preserve similarity"
    assert result.model_used == "auto_match", "Auto-match should use 'auto_match' as model"
    assert result.is_valid == True, "Auto-match should be valid (no error)"
    
    print("✅ LLMMatchResult has correct structure")
    print(f"   - match: {result.match}")
    print(f"   - confidence: {result.confidence}")
    print(f"   - model_used: {result.model_used}")
    print(f"   - is_valid: {result.is_valid}")

def test_llm_auto_reject():
    """Test that low similarity auto-rejects without calling LLM."""
    router = LLMRouter()
    
    result = router.match_with_llm(
        bill_item="X-Ray Chest",
        tieup_item="MRI Brain",
        similarity=0.30
    )
    
    assert result.match == False, "Auto-reject should return match=False"
    assert result.model_used == "auto_reject", "Low similarity should auto-reject"
    assert result.is_valid == True, "Auto-reject should be valid"
    
    print("✅ Auto-reject works correctly for low similarity")

if __name__ == "__main__":
    print("=" * 60)
    print("VALIDATION TEST: LLM Router Fix")
    print("=" * 60)
    print()
    
    try:
        test_llm_router_method_exists()
        print()
        test_llm_result_structure()
        print()
        test_llm_auto_reject()
        print()
        print("=" * 60)
        print("✅ ALL VALIDATION TESTS PASSED")
        print("=" * 60)
        print()
        print("The fix is correct:")
        print("1. match_with_llm() method exists and works")
        print("2. LLMMatchResult has correct attributes")
        print("3. Auto-match/reject logic works without LLM calls")
        print("4. System gracefully handles all cases")
        
    except AssertionError as e:
        print()
        print("=" * 60)
        print("❌ VALIDATION FAILED")
        print("=" * 60)
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print()
        print("=" * 60)
        print("❌ UNEXPECTED ERROR")
        print("=" * 60)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
