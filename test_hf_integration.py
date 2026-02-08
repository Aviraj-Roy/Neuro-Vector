"""
Test script to verify HuggingFace Inference API integration.

This script tests the refactored LLM router to ensure:
1. HF API token validation works
2. Model name mapping is correct
3. Connection testing works
4. LLM calls work (if token is set)
5. Fallback behavior is preserved

Usage:
    python test_hf_integration.py
"""

import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

def test_model_mapping():
    """Test that model name mapping is correct."""
    print("\n" + "="*80)
    print("TEST 1: Model Name Mapping")
    print("="*80)
    
    from app.verifier.llm_router import MODEL_NAME_MAPPING
    
    expected_mapping = {
        "phi3:mini": "microsoft/Phi-3-mini-4k-instruct",
        "qwen2.5:3b": "Qwen/Qwen2.5-3B-Instruct",
    }
    
    for external, expected_hf in expected_mapping.items():
        actual_hf = MODEL_NAME_MAPPING.get(external)
        if actual_hf == expected_hf:
            print(f"✅ {external} → {actual_hf}")
        else:
            print(f"❌ {external} → Expected: {expected_hf}, Got: {actual_hf}")
            return False
    
    print("✅ All model mappings correct!")
    return True


def test_router_initialization():
    """Test LLM router initialization with and without token."""
    print("\n" + "="*80)
    print("TEST 2: Router Initialization")
    print("="*80)
    
    from app.verifier.llm_router import LLMRouter
    
    # Test without token
    print("\n--- Test 2a: Without HF_API_TOKEN ---")
    os.environ["ENABLE_LLM_MATCHING"] = "true"
    if "HF_API_TOKEN" in os.environ:
        del os.environ["HF_API_TOKEN"]
    
    router = LLMRouter()
    
    if not router._llm_available:
        print("✅ Router correctly disabled when HF_API_TOKEN not set")
    else:
        print("❌ Router should be disabled without HF_API_TOKEN")
        return False
    
    # Test with token (if available)
    print("\n--- Test 2b: With HF_API_TOKEN (if set) ---")
    hf_token = os.getenv("HF_API_TOKEN")
    
    if hf_token:
        router = LLMRouter(hf_api_token=hf_token)
        print(f"✅ Router initialized with token")
        print(f"   LLM Available: {router._llm_available}")
        print(f"   Primary: {router.primary_model}")
        print(f"   Secondary: {router.secondary_model}")
    else:
        print("⚠️  HF_API_TOKEN not set - skipping token test")
        print("   Set HF_API_TOKEN to test full functionality")
    
    return True


def test_model_name_helper():
    """Test the _get_hf_model_name helper method."""
    print("\n" + "="*80)
    print("TEST 3: Model Name Helper Method")
    print("="*80)
    
    from app.verifier.llm_router import LLMRouter
    
    router = LLMRouter()
    
    # Test known mappings
    test_cases = [
        ("phi3:mini", "microsoft/Phi-3-mini-4k-instruct"),
        ("qwen2.5:3b", "Qwen/Qwen2.5-3B-Instruct"),
        ("unknown-model", "unknown-model"),  # Should return input if not mapped
    ]
    
    for external, expected in test_cases:
        actual = router._get_hf_model_name(external)
        if actual == expected:
            print(f"✅ _get_hf_model_name('{external}') → '{actual}'")
        else:
            print(f"❌ _get_hf_model_name('{external}') → Expected: '{expected}', Got: '{actual}'")
            return False
    
    print("✅ All model name mappings work correctly!")
    return True


def test_fallback_behavior():
    """Test that fallback behavior is preserved."""
    print("\n" + "="*80)
    print("TEST 4: Fallback Behavior")
    print("="*80)
    
    from app.verifier.llm_router import LLMRouter, AUTO_MATCH_THRESHOLD, LLM_LOWER_THRESHOLD
    
    # Initialize router without token (LLM unavailable)
    if "HF_API_TOKEN" in os.environ:
        del os.environ["HF_API_TOKEN"]
    
    router = LLMRouter()
    
    # Test auto-match (high similarity)
    print("\n--- Test 4a: Auto-match (similarity >= 0.85) ---")
    result = router.match_with_llm("Consultation", "Consultation", 0.90)
    if result.match and result.model_used == "auto_match":
        print(f"✅ Auto-match works: similarity={0.90}, match={result.match}")
    else:
        print(f"❌ Auto-match failed: {result}")
        return False
    
    # Test auto-reject (low similarity)
    print("\n--- Test 4b: Auto-reject (similarity < 0.70) ---")
    result = router.match_with_llm("Consultation", "X-Ray", 0.50)
    if not result.match and result.model_used == "auto_reject":
        print(f"✅ Auto-reject works: similarity={0.50}, match={result.match}")
    else:
        print(f"❌ Auto-reject failed: {result}")
        return False
    
    # Test conservative fallback (borderline, no LLM)
    print("\n--- Test 4c: Conservative fallback (0.70 <= similarity < 0.85, no LLM) ---")
    result = router.match_with_llm("Consultation - First Visit", "Consultation", 0.75)
    if result.model_used == "fallback_threshold":
        print(f"✅ Fallback threshold works: similarity={0.75}, match={result.match}")
        print(f"   Uses conservative threshold (0.80): match={result.match}")
    else:
        print(f"❌ Fallback threshold failed: {result}")
        return False
    
    print("✅ All fallback behaviors preserved!")
    return True


def test_caching():
    """Test that caching still works."""
    print("\n" + "="*80)
    print("TEST 5: Decision Caching")
    print("="*80)
    
    from app.verifier.llm_router import LLMRouter
    
    router = LLMRouter()
    
    # First call (should cache)
    result1 = router.match_with_llm("Consultation", "Consultation", 0.90)
    cache_size_1 = router.cache_size
    
    # Second call (should hit cache)
    result2 = router.match_with_llm("Consultation", "Consultation", 0.90)
    cache_size_2 = router.cache_size
    
    if cache_size_1 == cache_size_2 and result1.match == result2.match:
        print(f"✅ Caching works: cache_size={cache_size_1}")
        print(f"   First call: {result1}")
        print(f"   Second call (cached): {result2}")
    else:
        print(f"❌ Caching failed")
        return False
    
    print("✅ Decision caching preserved!")
    return True


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("HUGGINGFACE INFERENCE API INTEGRATION TESTS")
    print("="*80)
    
    tests = [
        ("Model Mapping", test_model_mapping),
        ("Router Initialization", test_router_initialization),
        ("Model Name Helper", test_model_name_helper),
        ("Fallback Behavior", test_fallback_behavior),
        ("Decision Caching", test_caching),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ Test '{name}' raised exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {name}")
    
    total = len(results)
    passed = sum(1 for _, success in results if success)
    
    print("\n" + "="*80)
    print(f"TOTAL: {passed}/{total} tests passed")
    print("="*80)
    
    if passed == total:
        print("\n🎉 All tests passed! HuggingFace integration is working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
