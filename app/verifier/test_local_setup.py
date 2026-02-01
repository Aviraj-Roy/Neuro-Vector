#!/usr/bin/env python3
"""
Setup script for local LLM medical bill verifier.
Tests all components and verifies the system is ready.
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def check_imports():
    """Check if all required packages are installed."""
    print("=" * 60)
    print("CHECKING DEPENDENCIES")
    print("=" * 60)
    
    required = {
        "sentence_transformers": "sentence-transformers",
        "torch": "torch",
        "faiss": "faiss-cpu",
        "numpy": "numpy",
        "requests": "requests",
    }
    
    missing = []
    for module, package in required.items():
        try:
            __import__(module)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package} - NOT INSTALLED")
            missing.append(package)
    
    if missing:
        print(f"\n⚠️  Missing packages: {', '.join(missing)}")
        print(f"Install with: pip install {' '.join(missing)}")
        return False
    
    print("\n✅ All dependencies installed\n")
    return True


def test_embedding_service():
    """Test the local embedding service."""
    print("=" * 60)
    print("TESTING EMBEDDING SERVICE")
    print("=" * 60)
    
    try:
        from app.verifier.embedding_service import EmbeddingService
        
        print("Initializing embedding service...")
        service = EmbeddingService()
        
        print(f"Model: {service.model_name}")
        print(f"Device: {service.device}")
        print(f"Dimension: {service.dimension}")
        
        print("\nGenerating test embeddings...")
        test_texts = ["CT Scan", "MRI Scan", "X-Ray"]
        embeddings = service.get_embeddings(test_texts)
        
        print(f"✅ Generated embeddings: shape={embeddings.shape}")
        print(f"   Expected: ({len(test_texts)}, {service.dimension})")
        
        if embeddings.shape == (len(test_texts), service.dimension):
            print("✅ Embedding service working correctly\n")
            return True
        else:
            print("❌ Unexpected embedding shape\n")
            return False
            
    except Exception as e:
        print(f"❌ Embedding service failed: {e}\n")
        return False


def test_llm_router():
    """Test the LLM router."""
    print("=" * 60)
    print("TESTING LLM ROUTER")
    print("=" * 60)
    
    try:
        from app.verifier.llm_router import LLMRouter
        import requests
        
        print("Initializing LLM router...")
        router = LLMRouter()
        
        print(f"Primary model: {router.primary_model}")
        print(f"Secondary model: {router.secondary_model}")
        print(f"Runtime: {router.runtime}")
        print(f"Base URL: {router.base_url}")
        
        # Check if Ollama is running
        print("\nChecking Ollama service...")
        try:
            response = requests.get(f"{router.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                print("✅ Ollama service is running")
                
                # Check if models are available
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                
                print(f"\nAvailable models: {len(models)}")
                for name in model_names:
                    print(f"  - {name}")
                
                # Check for required models
                primary_available = any(router.primary_model in name for name in model_names)
                secondary_available = any(router.secondary_model in name for name in model_names)
                
                if primary_available:
                    print(f"✅ Primary model ({router.primary_model}) available")
                else:
                    print(f"⚠️  Primary model ({router.primary_model}) not found")
                    print(f"   Run: ollama pull {router.primary_model}")
                
                if secondary_available:
                    print(f"✅ Secondary model ({router.secondary_model}) available")
                else:
                    print(f"⚠️  Secondary model ({router.secondary_model}) not found")
                    print(f"   Run: ollama pull {router.secondary_model}")
                
                if primary_available or secondary_available:
                    print("\n✅ LLM router ready (at least one model available)\n")
                    return True
                else:
                    print("\n⚠️  No required models found. Pull models first.\n")
                    return False
            else:
                print(f"❌ Ollama returned status {response.status_code}\n")
                return False
                
        except requests.exceptions.ConnectionError:
            print("❌ Cannot connect to Ollama service")
            print("   Make sure Ollama is running: ollama serve")
            print("   Or check LLM_BASE_URL in .env\n")
            return False
        except Exception as e:
            print(f"❌ Error checking Ollama: {e}\n")
            return False
            
    except Exception as e:
        print(f"❌ LLM router initialization failed: {e}\n")
        return False


def test_integration():
    """Test the full integration."""
    print("=" * 60)
    print("TESTING FULL INTEGRATION")
    print("=" * 60)
    
    try:
        from app.verifier.matcher import SemanticMatcher
        from app.verifier.models import TieUpRateSheet, TieUpCategory, TieUpItem
        
        print("Creating test data...")
        
        # Create a simple test rate sheet
        test_item = TieUpItem(
            item_name="CT Scan Head",
            rate=5000.0,
            unit="per scan"
        )
        
        test_category = TieUpCategory(
            category_name="Radiology",
            items=[test_item]
        )
        
        test_rate_sheet = TieUpRateSheet(
            hospital_name="Test Hospital",
            categories=[test_category]
        )
        
        print("Initializing matcher...")
        matcher = SemanticMatcher()
        
        print("Indexing test rate sheet...")
        success = matcher.index_rate_sheets([test_rate_sheet])
        
        if not success:
            print(f"❌ Indexing failed: {matcher.indexing_error}\n")
            return False
        
        print("✅ Indexing successful")
        
        print("\nTesting hospital match...")
        hospital_match = matcher.match_hospital("Test Medical Center")
        print(f"  Match: {hospital_match.matched_text}")
        print(f"  Similarity: {hospital_match.similarity:.4f}")
        
        print("\nTesting category match...")
        category_match = matcher.match_category("Radiology Services", "Test Hospital")
        print(f"  Match: {category_match.matched_text}")
        print(f"  Similarity: {category_match.similarity:.4f}")
        
        print("\nTesting item match...")
        item_match = matcher.match_item("CT Brain", "Test Hospital", "Radiology")
        print(f"  Match: {item_match.matched_text}")
        print(f"  Similarity: {item_match.similarity:.4f}")
        print(f"  Is Match: {item_match.is_match}")
        
        print("\n✅ Full integration test passed")
        
        # Show statistics
        stats = matcher.stats
        print("\nMatcher Statistics:")
        print(f"  Total matches: {stats['total_matches']}")
        print(f"  LLM calls: {stats['llm_calls']}")
        print(f"  LLM usage: {stats['llm_usage_percentage']:.2f}%")
        
        print("\n✅ System is ready for production use!\n")
        return True
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("LOCAL LLM MEDICAL BILL VERIFIER - SETUP VERIFICATION")
    print("=" * 60 + "\n")
    
    results = {
        "Dependencies": check_imports(),
        "Embedding Service": test_embedding_service(),
        "LLM Router": test_llm_router(),
        "Integration": test_integration(),
    }
    
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    for component, status in results.items():
        status_str = "✅ PASS" if status else "❌ FAIL"
        print(f"{component:20s}: {status_str}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n🎉 All tests passed! System is ready.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
