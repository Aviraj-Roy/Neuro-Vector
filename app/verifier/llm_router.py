"""
LLM Router for Medical Bill Verification - LOCAL MODELS ONLY.

This module handles LLM-based matching for borderline similarity cases.
Uses a two-tier fallback system:
1. Primary: Phi-3 Mini (fast, efficient)
2. Fallback: Qwen2.5-3B (if Phi-3 fails or low confidence)

Routing Logic:
- similarity >= 0.85: Auto-match (no LLM needed)
- 0.70 <= similarity < 0.85: Use LLM for verification
- similarity < 0.70: Auto-reject (mismatch)

Supports both Ollama and vLLM runtimes.

Environment Variables:
    PRIMARY_LLM: Primary model name (default: phi3:mini)
    SECONDARY_LLM: Fallback model name (default: qwen2.5:3b)
    LLM_RUNTIME: Runtime to use (default: ollama)
    LLM_BASE_URL: Base URL for LLM service (default: http://localhost:11434)
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

# LLM model names
DEFAULT_PRIMARY_LLM = "phi3:mini"
DEFAULT_SECONDARY_LLM = "qwen2.5:3b"
DEFAULT_RUNTIME = "ollama"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_TIMEOUT = 30
DEFAULT_MIN_CONFIDENCE = 0.7

# Similarity thresholds
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
    Routes medical term matching to local LLM models.
    
    Features:
    - Two-tier fallback (Phi-3 -> Qwen2.5)
    - Decision caching to minimize LLM calls
    - Strict JSON-only prompts for deterministic output
    - Supports Ollama and vLLM runtimes
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
        runtime: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        min_confidence: Optional[float] = None,
    ):
        """
        Initialize the LLM router.
        
        Args:
            primary_model: Primary LLM model name
            secondary_model: Fallback LLM model name
            runtime: Runtime to use ('ollama' or 'vllm')
            base_url: Base URL for LLM service
            timeout: Request timeout in seconds
            min_confidence: Minimum confidence threshold
        """
        self.primary_model = primary_model or os.getenv("PRIMARY_LLM", DEFAULT_PRIMARY_LLM)
        self.secondary_model = secondary_model or os.getenv("SECONDARY_LLM", DEFAULT_SECONDARY_LLM)
        self.runtime = runtime or os.getenv("LLM_RUNTIME", DEFAULT_RUNTIME)
        self.base_url = base_url or os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL)
        self.timeout = timeout or int(os.getenv("LLM_TIMEOUT", str(DEFAULT_TIMEOUT)))
        self.min_confidence = min_confidence or float(os.getenv("LLM_MIN_CONFIDENCE", str(DEFAULT_MIN_CONFIDENCE)))
        
        # Decision cache
        self._cache = LLMDecisionCache()
        
        # Statistics
        self._primary_calls = 0
        self._secondary_calls = 0
        self._cache_hits = 0
        
        logger.info(
            f"LLMRouter initialized: primary={self.primary_model}, "
            f"secondary={self.secondary_model}, runtime={self.runtime}, "
            f"base_url={self.base_url}"
        )
    
    def _call_ollama(self, model: str, prompt: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Call Ollama API.
        
        Args:
            model: Model name
            prompt: Prompt text
            
        Returns:
            Tuple of (response text, error message)
        """
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temperature for deterministic output
                "num_predict": 150,  # Limit output length
            }
        }
        
        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            
            result = response.json()
            return result.get("response", ""), None
            
        except requests.exceptions.Timeout:
            return None, f"Timeout calling {model}"
        except requests.exceptions.RequestException as e:
            return None, f"Request failed for {model}: {e}"
        except Exception as e:
            return None, f"Unexpected error calling {model}: {e}"
    
    def _call_vllm(self, model: str, prompt: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Call vLLM API (OpenAI-compatible).
        
        Args:
            model: Model name
            prompt: Prompt text
            
        Returns:
            Tuple of (response text, error message)
        """
        url = f"{self.base_url}/v1/completions"
        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": 0.1,
            "max_tokens": 150,
        }
        
        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            
            result = response.json()
            choices = result.get("choices", [])
            if choices:
                return choices[0].get("text", ""), None
            return None, "No response from vLLM"
            
        except requests.exceptions.Timeout:
            return None, f"Timeout calling {model}"
        except requests.exceptions.RequestException as e:
            return None, f"Request failed for {model}: {e}"
        except Exception as e:
            return None, f"Unexpected error calling {model}: {e}"
    
    def _call_llm(self, model: str, prompt: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Call LLM based on configured runtime.
        
        Args:
            model: Model name
            prompt: Prompt text
            
        Returns:
            Tuple of (response text, error message)
        """
        if self.runtime == "ollama":
            return self._call_ollama(model, prompt)
        elif self.runtime == "vllm":
            return self._call_vllm(model, prompt)
        else:
            return None, f"Unsupported runtime: {self.runtime}"
    
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
        
        # Borderline case: Use LLM
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
