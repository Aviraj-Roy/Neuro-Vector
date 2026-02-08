"""
LLM Router for Medical Bill Verification - HUGGING FACE INFERENCE API.

This module handles LLM-based matching for borderline similarity cases.
Uses a two-tier fallback system:
1. Primary: Phi-3 Mini (fast, efficient)
2. Fallback: Qwen2.5-3B (if Phi-3 fails or low confidence)

Routing Logic:
- similarity >= 0.85: Auto-match (no LLM needed)
- 0.70 <= similarity < 0.85: Use LLM for verification
- similarity < 0.70: Auto-reject (mismatch)

Uses Hugging Face Inference API (no local models required).

Environment Variables:
    HF_API_TOKEN: Hugging Face API token (REQUIRED for LLM matching)
    PRIMARY_LLM: Primary model name (default: phi3:mini)
    SECONDARY_LLM: Fallback model name (default: qwen2.5:3b)
    ENABLE_LLM_MATCHING: Enable/disable LLM matching (default: false)
    LLM_TIMEOUT: Request timeout in seconds (default: 30)
    LLM_MIN_CONFIDENCE: Minimum confidence threshold (default: 0.7)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# LLM model names (external identifiers, kept for backward compatibility)
DEFAULT_PRIMARY_LLM = "phi3:mini"
DEFAULT_SECONDARY_LLM = "qwen2.5:3b"
DEFAULT_TIMEOUT = 30  # Reduced from 300 for HF API
DEFAULT_MIN_CONFIDENCE = 0.7

# Hugging Face Inference API configuration
HF_API_BASE_URL = "https://api-inference.huggingface.co/models"

# Internal model mapping: external name -> HuggingFace repo name
# This mapping is INTERNAL ONLY and not exposed to external config
MODEL_NAME_MAPPING = {
    "phi3:mini": "microsoft/Phi-3-mini-4k-instruct",
    "qwen2.5:3b": "Qwen/Qwen2.5-3B-Instruct",
}

# Similarity thresholds (unchanged)
AUTO_MATCH_THRESHOLD = 0.85
LLM_LOWER_THRESHOLD = 0.70


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class LLMMatchResult:
    """Result from LLM matching."""
    match: bool
    confidence: float
    normalized_name: str
    model_used: str
    error: Optional[str] = None
    
    @property
    def is_valid(self) -> bool:
        """Check if result is valid (no error)."""
        return self.error is None


# =============================================================================
# LLM Decision Cache
# =============================================================================

class LLMDecisionCache:
    """
    In-memory cache for LLM decisions.
    Caches (text_pair) -> LLMMatchResult to avoid redundant LLM calls.
    """
    
    def __init__(self):
        self._cache: Dict[Tuple[str, str], LLMMatchResult] = {}
        self._hits = 0
        self._misses = 0
    
    def get(self, term_a: str, term_b: str) -> Optional[LLMMatchResult]:
        """Get cached result for a text pair."""
        key = (term_a.lower(), term_b.lower())
        result = self._cache.get(key)
        if result is not None:
            self._hits += 1
            logger.debug(f"LLM cache hit: {term_a} <-> {term_b}")
        else:
            self._misses += 1
        return result
    
    def set(self, term_a: str, term_b: str, result: LLMMatchResult):
        """Cache a result for a text pair."""
        key = (term_a.lower(), term_b.lower())
        self._cache[key] = result
    
    def clear(self):
        """Clear the cache."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        logger.info("LLM decision cache cleared")
    
    @property
    def size(self) -> int:
        """Return cache size."""
        return len(self._cache)
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0


# =============================================================================
# LLM Router
# =============================================================================

class LLMRouter:
    """
    Routes medical term matching to Hugging Face Inference API.
    
    Features:
    - Two-tier fallback (Phi-3 -> Qwen2.5)
    - Decision caching to minimize LLM calls
    - Strict JSON-only prompts for deterministic output
    - Uses HuggingFace Inference API (no local models)
    """
    
    # Strict prompt template for medical term matching
    PROMPT_TEMPLATE = """You are a medical billing auditor.

Decide if these two terms refer to the same medical service.

Term A: "{bill_item}"
Term B: "{tieup_item}"

Answer ONLY in JSON:
{{
  "match": true|false,
  "confidence": 0.0-1.0,
  "normalized_name": ""
}}

No explanations. No extra text."""
    
    def __init__(
        self,
        primary_model: Optional[str] = None,
        secondary_model: Optional[str] = None,
        hf_api_token: Optional[str] = None,
        timeout: Optional[int] = None,
        min_confidence: Optional[float] = None,
    ):
        """
        Initialize the LLM router with Hugging Face Inference API.
        
        Args:
            primary_model: Primary LLM model name (default: phi3:mini)
            secondary_model: Fallback LLM model name (default: qwen2.5:3b)
            hf_api_token: Hugging Face API token (reads from HF_API_TOKEN env var if None)
            timeout: Request timeout in seconds (default: 30)
            min_confidence: Minimum confidence threshold (default: 0.7)
        """
        # Check if LLM matching is enabled
        enable_llm = os.getenv("ENABLE_LLM_MATCHING", "false").lower() in ("true", "1", "yes")
        
        # Get HF API token from parameter or environment
        self.hf_api_token = hf_api_token or os.getenv("HF_API_TOKEN")
        
        # Model configuration (external names)
        self.primary_model = primary_model or os.getenv("PRIMARY_LLM", DEFAULT_PRIMARY_LLM)
        self.secondary_model = secondary_model or os.getenv("SECONDARY_LLM", DEFAULT_SECONDARY_LLM)
        self.timeout = timeout or int(os.getenv("LLM_TIMEOUT", str(DEFAULT_TIMEOUT)))
        self.min_confidence = min_confidence or float(os.getenv("LLM_MIN_CONFIDENCE", str(DEFAULT_MIN_CONFIDENCE)))
        
        # Decision cache
        self._cache = LLMDecisionCache()
        
        # Statistics
        self._primary_calls = 0
        self._secondary_calls = 0
        self._cache_hits = 0
        
        # Check if LLM is available
        self._llm_available = False
        
        if not enable_llm:
            logger.info("⚠️  LLM Matching: DISABLED")
            logger.info("   Reason: ENABLE_LLM_MATCHING=false")
            logger.info("   Verification will use embedding similarity only")
            self._llm_available = False
        elif not self.hf_api_token:
            logger.warning("⚠️  LLM Matching: DISABLED")
            logger.warning("   Reason: HF_API_TOKEN not set")
            logger.warning("   Set HF_API_TOKEN environment variable to enable LLM matching")
            logger.info("   Verification will use embedding similarity only")
            self._llm_available = False
        else:
            # Test HF API connectivity
            self._llm_available = self._test_hf_connection()
            
            if self._llm_available:
                logger.info(
                    f"✅ LLMRouter initialized with Hugging Face Inference API"
                )
                logger.info(
                    f"   Primary: {self.primary_model} -> {self._get_hf_model_name(self.primary_model)}"
                )
                logger.info(
                    f"   Secondary: {self.secondary_model} -> {self._get_hf_model_name(self.secondary_model)}"
                )
            else:
                logger.warning(
                    f"⚠️  Hugging Face API not reachable or token invalid. "
                    f"LLM-based matching will be disabled. "
                    f"Verification will continue with embedding similarity only."
                )
    
    
    def _get_hf_model_name(self, external_name: str) -> str:
        """
        Map external model name to Hugging Face repo name.
        
        This is an INTERNAL mapping only. External config still uses
        the same model names (phi3:mini, qwen2.5:3b).
        
        Args:
            external_name: External model identifier (e.g., "phi3:mini")
            
        Returns:
            Hugging Face model repo name (e.g., "microsoft/Phi-3-mini-4k-instruct")
        """
        return MODEL_NAME_MAPPING.get(external_name, external_name)
    
    def _test_hf_connection(self) -> bool:
        """
        Test if Hugging Face Inference API is available and token is valid.
        
        Uses a minimal POST request to verify:
        1. Token is present
        2. Token is valid (not expired/revoked)
        3. Model is accessible via Inference API
        4. API is reachable
        
        Returns:
            True if HF API is reachable and token is valid, False otherwise
        """
        if not self.hf_api_token:
            logger.warning("❌ HF_API_TOKEN not set - LLM matching disabled")
            logger.warning("   Set HF_API_TOKEN environment variable to enable LLM matching")
            return False
        
        # Validate token format
        if not self.hf_api_token.startswith("hf_"):
            logger.error("❌ HF_API_TOKEN has invalid format (should start with 'hf_')")
            logger.error(f"   Current token starts with: {self.hf_api_token[:10]}...")
            return False
            
        try:
            # Test with primary model using a minimal inference request
            hf_model_name = self._get_hf_model_name(self.primary_model)
            url = f"{HF_API_BASE_URL}/{hf_model_name}"
            
            logger.info(f"🔍 Testing HuggingFace Inference API connection...")
            logger.info(f"   Model: {self.primary_model} -> {hf_model_name}")
            logger.info(f"   URL: {url}")
            logger.info(f"   Token: {self.hf_api_token[:10]}...{self.hf_api_token[-4:]}")
            
            headers = {
                "Authorization": f"Bearer {self.hf_api_token}",
                "Content-Type": "application/json",
            }
            
            # Minimal test payload (empty prompt to minimize processing)
            # HF Inference API requires POST, not GET
            test_payload = {
                "inputs": "test",
                "parameters": {
                    "max_new_tokens": 1,  # Minimal generation
                    "return_full_text": False,
                }
            }
            
            # Quick health check with short timeout
            logger.debug(f"   Sending POST request with test payload...")
            response = requests.post(url, headers=headers, json=test_payload, timeout=10)
            
            logger.debug(f"   Response status: {response.status_code}")
            
            # Handle different response codes
            if response.status_code == 200:
                logger.info("✅ HuggingFace API connection successful!")
                logger.info(f"   Model {hf_model_name} is ready")
                return True
                
            elif response.status_code == 503:
                # Model is loading - this is OK, token is valid
                try:
                    error_data = response.json()
                    estimated_time = error_data.get("estimated_time", "unknown")
                    logger.info(f"✅ HuggingFace API token is valid")
                    logger.info(f"⏳ Model {hf_model_name} is loading (estimated: {estimated_time}s)")
                    logger.info(f"   This is normal for first request - subsequent calls will be fast")
                    return True
                except:
                    logger.info(f"✅ HuggingFace API token is valid (model loading)")
                    return True
                    
            elif response.status_code == 401:
                logger.error("❌ HuggingFace API authentication failed")
                logger.error("   Token is invalid, expired, or revoked")
                logger.error("   Get a new token from: https://huggingface.co/settings/tokens")
                return False
                
            elif response.status_code == 403:
                logger.error("❌ HuggingFace API access forbidden")
                logger.error(f"   You may not have access to model: {hf_model_name}")
                logger.error("   Note: This model should be public - check HuggingFace status")
                return False
                
            elif response.status_code == 404:
                logger.error("❌ Model not found on HuggingFace")
                logger.error(f"   Model: {hf_model_name}")
                logger.error("   Check MODEL_NAME_MAPPING in llm_router.py")
                return False
                
            elif response.status_code == 429:
                logger.warning("⚠️  HuggingFace API rate limit exceeded")
                logger.warning("   Free tier: ~10 requests/minute")
                logger.warning("   LLM matching will be disabled temporarily")
                return False
                
            else:
                logger.error(f"❌ HuggingFace API returned unexpected status: {response.status_code}")
                try:
                    error_detail = response.json()
                    logger.error(f"   Error details: {error_detail}")
                except:
                    logger.error(f"   Response text: {response.text[:200]}")
                return False
            
        except requests.exceptions.Timeout:
            logger.error("❌ HuggingFace API connection timeout")
            logger.error("   Check your internet connection")
            logger.error("   HuggingFace API may be experiencing issues")
            return False
            
        except requests.exceptions.ConnectionError as e:
            logger.error("❌ Cannot connect to HuggingFace API")
            logger.error(f"   Error: {str(e)[:100]}")
            logger.error("   Check your internet connection")
            logger.error("   Check if https://api-inference.huggingface.co is accessible")
            return False
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ HuggingFace API request failed: {type(e).__name__}")
            logger.error(f"   Error: {str(e)[:200]}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Unexpected error during HuggingFace API health check")
            logger.error(f"   Error type: {type(e).__name__}")
            logger.error(f"   Error message: {str(e)[:200]}")
            import traceback
            logger.debug(f"   Traceback: {traceback.format_exc()}")
            return False
    
    def _call_huggingface(self, model: str, prompt: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Call Hugging Face Inference API.
        
        Args:
            model: External model name (e.g., "phi3:mini")
            prompt: Prompt text
            
        Returns:
            Tuple of (response text, error message)
        """
        # Map external model name to HF repo name
        hf_model_name = self._get_hf_model_name(model)
        url = f"{HF_API_BASE_URL}/{hf_model_name}"
        
        logger.debug(f"Calling HuggingFace API: {model} -> {hf_model_name}")
        
        headers = {
            "Authorization": f"Bearer {self.hf_api_token}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": 0.1,  # Low temperature for deterministic output
                "max_new_tokens": 150,  # Limit output length
                "return_full_text": False,  # Only return generated text
            }
        }
        
        try:
            logger.debug(f"Sending POST request to {url}")
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            
            logger.debug(f"Response status: {response.status_code}")
            
            # Handle authentication errors
            if response.status_code == 401:
                error_msg = f"Authentication failed for {model} - token may be invalid or expired"
                logger.error(f"❌ {error_msg}")
                return None, error_msg
            
            # Handle rate limiting
            if response.status_code == 429:
                error_msg = f"Rate limit exceeded for {model}"
                logger.warning(f"⚠️  {error_msg}")
                return None, error_msg
            
            # Handle model loading (HF API returns 503 when model is loading)
            if response.status_code == 503:
                try:
                    error_data = response.json()
                    estimated_time = error_data.get("estimated_time", "unknown")
                    error_msg = f"Model {model} is loading (estimated time: {estimated_time}s)"
                    logger.info(f"⏳ {error_msg}")
                    return None, error_msg
                except:
                    error_msg = f"Model {model} is loading"
                    logger.info(f"⏳ {error_msg}")
                    return None, error_msg
            
            # Handle other HTTP errors
            if response.status_code != 200:
                try:
                    error_detail = response.json()
                    error_msg = f"API error for {model}: {error_detail}"
                except:
                    error_msg = f"API error for {model}: HTTP {response.status_code}"
                logger.error(f"❌ {error_msg}")
                logger.debug(f"   Response: {response.text[:200]}")
                return None, error_msg
            
            # Parse successful response
            result = response.json()
            logger.debug(f"Response type: {type(result)}")
            
            # HF API returns a list of generated texts
            if isinstance(result, list) and len(result) > 0:
                generated_text = result[0].get("generated_text", "")
                logger.debug(f"Generated text length: {len(generated_text)}")
                return generated_text, None
            elif isinstance(result, dict) and "generated_text" in result:
                generated_text = result["generated_text"]
                logger.debug(f"Generated text length: {len(generated_text)}")
                return generated_text, None
            else:
                error_msg = f"Unexpected response format from {model}: {type(result)}"
                logger.error(f"❌ {error_msg}")
                logger.debug(f"   Response: {result}")
                return None, error_msg
            
        except requests.exceptions.Timeout:
            error_msg = f"Timeout calling {model} (>{self.timeout}s)"
            logger.error(f"❌ {error_msg}")
            return None, error_msg
            
        except requests.exceptions.ConnectionError as e:
            error_msg = f"Connection error calling {model}: {str(e)[:100]}"
            logger.error(f"❌ {error_msg}")
            return None, error_msg
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed for {model}: {type(e).__name__} - {str(e)[:100]}"
            logger.error(f"❌ {error_msg}")
            return None, error_msg
            
        except Exception as e:
            error_msg = f"Unexpected error calling {model}: {type(e).__name__} - {str(e)[:100]}"
            logger.error(f"❌ {error_msg}")
            import traceback
            logger.debug(f"   Traceback: {traceback.format_exc()}")
            return None, error_msg
    
    def _call_llm(self, model: str, prompt: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Call LLM via Hugging Face Inference API.
        
        Args:
            model: External model name (e.g., "phi3:mini")
            prompt: Prompt text
            
        Returns:
            Tuple of (response text, error message)
        """
        return self._call_huggingface(model, prompt)
    
    def _parse_llm_response(self, response_text: str, model: str) -> LLMMatchResult:
        """
        Parse LLM JSON response.
        
        Args:
            response_text: Raw response text
            model: Model name used
            
        Returns:
            LLMMatchResult
        """
        try:
            # Try to extract JSON from response
            # Some models may add extra text, so we look for JSON block
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}") + 1
            
            if start_idx == -1 or end_idx == 0:
                return LLMMatchResult(
                    match=False,
                    confidence=0.0,
                    normalized_name="",
                    model_used=model,
                    error="No JSON found in response"
                )
            
            json_text = response_text[start_idx:end_idx]
            data = json.loads(json_text)
            
            # Validate required fields
            if "match" not in data or "confidence" not in data:
                return LLMMatchResult(
                    match=False,
                    confidence=0.0,
                    normalized_name="",
                    model_used=model,
                    error="Missing required fields in JSON"
                )
            
            return LLMMatchResult(
                match=bool(data["match"]),
                confidence=float(data["confidence"]),
                normalized_name=str(data.get("normalized_name", "")),
                model_used=model,
            )
            
        except json.JSONDecodeError as e:
            return LLMMatchResult(
                match=False,
                confidence=0.0,
                normalized_name="",
                model_used=model,
                error=f"JSON parse error: {e}"
            )
        except Exception as e:
            return LLMMatchResult(
                match=False,
                confidence=0.0,
                normalized_name="",
                model_used=model,
                error=f"Parse error: {e}"
            )
    
    def match_with_llm(
        self,
        bill_item: str,
        tieup_item: str,
        similarity: float,
    ) -> LLMMatchResult:
        """
        Match two medical terms using LLM with fallback logic.
        
        Routing Logic:
        1. If similarity >= 0.85: Auto-match (no LLM)
        2. If similarity < 0.70: Auto-reject (no LLM)
        3. If 0.70 <= similarity < 0.85: Use LLM
           a. Try primary model (Phi-3)
           b. If fails or low confidence, try secondary (Qwen2.5)
        
        Args:
            bill_item: Item name from bill
            tieup_item: Item name from tie-up rate sheet
            similarity: Embedding similarity score
            
        Returns:
            LLMMatchResult
        """
        # Check cache first
        cached = self._cache.get(bill_item, tieup_item)
        if cached is not None:
            self._cache_hits += 1
            return cached
        
        # Auto-match for high similarity
        if similarity >= AUTO_MATCH_THRESHOLD:
            result = LLMMatchResult(
                match=True,
                confidence=similarity,
                normalized_name=tieup_item,
                model_used="auto_match",
            )
            self._cache.set(bill_item, tieup_item, result)
            return result
        
        # Auto-reject for low similarity
        if similarity < LLM_LOWER_THRESHOLD:
            result = LLMMatchResult(
                match=False,
                confidence=similarity,
                normalized_name="",
                model_used="auto_reject",
            )
            self._cache.set(bill_item, tieup_item, result)
            return result
        
        # Borderline case: Use LLM (if available)
        if not self._llm_available:
            # LLM not available, use conservative threshold
            logger.info(
                f"LLM not available for borderline match: '{bill_item}' <-> '{tieup_item}' (sim={similarity:.4f})"
            )
            logger.info("   Using conservative threshold (0.80) instead")
            
            # Use 0.80 as conservative threshold when LLM unavailable
            if similarity >= 0.80:
                result = LLMMatchResult(
                    match=True,
                    confidence=similarity,
                    normalized_name=tieup_item,
                    model_used="fallback_threshold",
                )
            else:
                result = LLMMatchResult(
                    match=False,
                    confidence=similarity,
                    normalized_name="",
                    model_used="fallback_threshold",
                )
            self._cache.set(bill_item, tieup_item, result)
            return result
        
        logger.info(
            f"LLM matching needed: '{bill_item}' <-> '{tieup_item}' (sim={similarity:.4f})"
        )
        
        # Build prompt
        prompt = self.PROMPT_TEMPLATE.format(
            bill_item=bill_item,
            tieup_item=tieup_item,
        )
        
        # Try primary model
        self._primary_calls += 1
        response_text, error = self._call_llm(self.primary_model, prompt)
        
        if error is None and response_text:
            result = self._parse_llm_response(response_text, self.primary_model)
            
            # Check if result is valid and has sufficient confidence
            if result.is_valid and result.confidence >= self.min_confidence:
                logger.info(
                    f"Primary LLM ({self.primary_model}): match={result.match}, "
                    f"confidence={result.confidence:.4f}"
                )
                self._cache.set(bill_item, tieup_item, result)
                return result
            
            logger.warning(
                f"Primary LLM low confidence or invalid: confidence={result.confidence:.4f}, "
                f"error={result.error}"
            )
        else:
            logger.warning(f"Primary LLM failed: {error}")
        
        # Fallback to secondary model
        logger.info(f"Falling back to secondary model: {self.secondary_model}")
        self._secondary_calls += 1
        
        response_text, error = self._call_llm(self.secondary_model, prompt)
        
        if error is None and response_text:
            result = self._parse_llm_response(response_text, self.secondary_model)
            logger.info(
                f"Secondary LLM ({self.secondary_model}): match={result.match}, "
                f"confidence={result.confidence:.4f}"
            )
        else:
            logger.error(f"Secondary LLM also failed: {error}")
            result = LLMMatchResult(
                match=False,
                confidence=0.0,
                normalized_name="",
                model_used=self.secondary_model,
                error=error,
            )
        
        # Cache result
        self._cache.set(bill_item, tieup_item, result)
        return result
    
    def clear_cache(self):
        """Clear the decision cache."""
        self._cache.clear()
    
    @property
    def cache_size(self) -> int:
        """Return cache size."""
        return self._cache.size
    
    @property
    def cache_hit_rate(self) -> float:
        """Return cache hit rate."""
        return self._cache.hit_rate
    
    @property
    def stats(self) -> Dict[str, int]:
        """Return usage statistics."""
        return {
            "primary_calls": self._primary_calls,
            "secondary_calls": self._secondary_calls,
            "cache_hits": self._cache_hits,
            "cache_size": self.cache_size,
        }


# =============================================================================
# Module-level singleton
# =============================================================================

_llm_router: Optional[LLMRouter] = None


def get_llm_router() -> LLMRouter:
    """Get or create the global LLM router instance."""
    global _llm_router
    if _llm_router is None:
        _llm_router = LLMRouter()
    return _llm_router


def reset_llm_router():
    """Reset the global LLM router instance (for testing)."""
    global _llm_router
    _llm_router = None
