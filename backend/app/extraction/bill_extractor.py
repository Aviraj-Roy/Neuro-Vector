"""Medical Bill Extractor.

Converts *structured* OCR output into a *single*, bill-scoped document.

Non-negotiable business rules enforced:
- One PDF upload = one MongoDB document.
- Payments/receipts are NOT medical services and must be routed to `payments: []`.
- No hospital-specific logic. No LLM usage.

Architecture (Three-Stage Isolated Parsing):
- Stage 1: Header Parser - Extracts patient info, bill metadata (header zone only)
- Stage 2: Item Parser - Extracts line items with section tracking (item zone only)
- Stage 3: Payment Parser - Extracts receipts/payments (payment zone only)

Key protections:
- Zone boundary detection prevents header labels from leaking into items.
- Numeric guardrails reject phone numbers, MRNs, dates as amounts.
- Section tracker persists across pages for proper categorization.
- First-valid-wins header locking prevents multi-page overwrites.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Import new modules for isolated parsing
from app.extraction.numeric_guards import (
    MAX_LINE_ITEM_AMOUNT,
    has_valid_row_context,
    is_suspect_numeric,
    validate_amount,
    validate_grand_total,
)
from app.extraction.section_tracker import (
    SectionTracker,
    build_section_tracker,
    classify_item_by_description,
    detect_section_header,
    get_category_for_item,
    is_regulated_pricing_item,
)
from app.extraction.zone_detector import (
    detect_all_zones,
    get_line_zone,
    is_header_label,
    is_payment_zone,
    should_skip_as_header_label,
)
from app.extraction.regex_utils import (
    safe_group,
    try_extract_labeled_field,
    is_label_only,
    extract_from_next_line,
    clean_extracted_value,
)
from app.extraction.column_parser import (
    parse_item_columns,
    is_valid_item,
    is_non_billable_section,
    ParsedItem,
)


# =============================================================================
# Payment / receipt detection (generic)
# =============================================================================
PAYMENT_PATTERNS = [
    r"\bRCPO-[A-Z0-9]+\b",
    r"\bRCP[A-Z]*[-/:]?[A-Z0-9]+\b",  # RCP*, RCPT, etc.
    r"\bRCPT[-/:]?[A-Z0-9]+\b",
    r"\b(UTR|RRN|TXN|TRANSACTION)\b",
    r"\b(PAYMENT|PAID|RECEIPT)\b",
    r"\b(CASH|CARD|UPI|NET\s*BANKING)\b",
    r"\bbalance\s*(due|to\s*pay)\b",
    r"\btotal\s*(paid|received)\b",
    r"\bamount\s*(paid|received)\b",
    # New broader patterns
    r"\bpaid\s+by\b",
    r"\bpayment\s+(mode|method|type)\b",
    r"\b(advance|deposit)\s+received\b",
    r"\brefund\b",
    r"\bsettlement\b",
    r"\b(credit|debit)\s+card\b",
    r"\btransaction\s+id\b",
]


def is_paymentish(text: str) -> bool:
    """Check if text indicates a payment/receipt entry."""
    t = (text or "").upper()
    # Quick reject if looks like a medical item
    medical_indicators = [" TAB ", " CAP ", " INJ ", " SYR ", " MG ", " ML ", " TEST ", " SCAN "]
    if any(ind in f" {t} " for ind in medical_indicators):
        return False
    return any(re.search(p, t, re.IGNORECASE) for p in PAYMENT_PATTERNS)


# =============================================================================
# Discount detection (generic)
# =============================================================================
DISCOUNT_PATTERNS = [
    r"\bdiscount\b",
    r"\bdisc\.?\b",
    r"\bconcession\b",
    r"\brebate\b",
    r"\bwaiver\b",
    r"\bdeduction\b",
    r"\brelief\b",
]

# Patterns to classify discount beneficiary
PATIENT_DISCOUNT_PATTERNS = [
    r"discount\s*[-:]?\s*patient",
    r"patient\s*discount",
    r"patient\s*concession",
    r"self\s*discount",
]

SPONSOR_DISCOUNT_PATTERNS = [
    r"discount\s*[-:]?\s*sponsor",
    r"sponsor\s*discount",
    r"insurance\s*discount",
    r"tpa\s*discount",
    r"corporate\s*discount",
    r"company\s*discount",
]


def is_discount(text: str) -> bool:
    """Check if text indicates a discount line item.

    Args:
        text: Description text to check

    Returns:
        True if text appears to be a discount line
    """
    if not text:
        return False
    t = text.lower().strip()
    return any(re.search(p, t, re.IGNORECASE) for p in DISCOUNT_PATTERNS)


def classify_discount_type(text: str) -> str:
    """Classify discount as 'patient', 'sponsor', or 'general'.

    Args:
        text: Discount description text

    Returns:
        Discount type: 'patient', 'sponsor', or 'general'
    """
    if not text:
        return "general"
    t = text.lower().strip()

    # Check for patient discount
    for pattern in PATIENT_DISCOUNT_PATTERNS:
        if re.search(pattern, t, re.IGNORECASE):
            return "patient"

    # Check for sponsor discount
    for pattern in SPONSOR_DISCOUNT_PATTERNS:
        if re.search(pattern, t, re.IGNORECASE):
            return "sponsor"

    return "general"


def extract_discount_amount(text: str) -> Optional[float]:
    """Extract discount amount from text like 'Discount - Patient: 225.00'.

    Args:
        text: Discount description text

    Returns:
        Discount amount or None
    """
    if not text:
        return None

    # Look for amount patterns in the text
    # Pattern: "Discount - Patient: 225.00" or "Discount 225.00"
    patterns = [
        r"[:.]\s*([\d,]+\.\d{2})\s*$",  # : 225.00 at end
        r"\s([\d,]+\.\d{2})\s*$",        # 225.00 at end
        r"₹\s*([\d,]+\.?\d*)\b",         # ₹225.00
    ]

    for pat in patterns:
        m = re.search(pat, text.strip())
        if m:
            try:
                # Use safe_group to prevent None.replace() crashes
                amount_str = safe_group(m, 1, "")
                if not amount_str:
                    continue
                return float(amount_str.replace(",", ""))
            except (ValueError, AttributeError):
                continue

    return None


def extract_reference(text: str) -> Optional[str]:
    """Extract payment reference number from text."""
    if not text:
        return None
    u = text.upper()
    m = re.search(r"\bRCPO-[A-Z0-9]+\b", u)
    if m:
        ref = safe_group(m, 0, "")
        if ref:
            return ref
    m = re.search(r"\b(UTR|RRN|TXN)\s*[:#-]?\s*([A-Z0-9]{6,})\b", u)
    if m:
        type_part = safe_group(m, 1, "")
        ref_part = safe_group(m, 2, "")
        if type_part and ref_part:
            return f"{type_part}-{ref_part}"
    return None


def extract_payment_mode(text: str) -> Optional[str]:
    """Extract payment mode from text."""
    if not text:
        return None
    t = text.upper()
    modes = [("CASH", "cash"), ("CARD", "card"), ("UPI", "upi"),
             ("NEFT", "neft"), ("RTGS", "rtgs"), ("CHEQUE", "cheque")]
    for pattern, mode in modes:
        if pattern in t:
            return mode
    return None


# =============================================================================
# Amount extraction with guardrails
# =============================================================================
AMOUNT_PATTERNS = [
    r"₹?\s*([\d,]+\.\d{2})\s*$",
    r"₹?\s*([\d,]+)\s*$",
]


def extract_amount_from_text(text: str) -> Optional[float]:
    """Extract amount from text with basic validation."""
    if not text:
        return None

    # Quick rejection of suspect patterns
    if is_suspect_numeric(text.strip()):
        return None

    for pat in AMOUNT_PATTERNS:
        m = re.search(pat, text.strip())
        if not m:
            continue
        # Use safe_group to prevent None.replace() crashes
        s = safe_group(m, 1, "")
        if not s:
            continue
        try:
            val = float(s.replace(",", ""))
            # Apply sanity cap
            if val > MAX_LINE_ITEM_AMOUNT:
                return None
            return val
        except (ValueError, AttributeError):
            continue
    return None


# =============================================================================
# Header extraction with strict locking
# =============================================================================
VALUE_VALIDATORS = {
    "patient_name": {
        "min_len": 3,
        "max_len": 100,
        # Prevent bill numbers / MRN from landing in name
        "invalid_patterns": [r"^[A-Z]{2}\d{6,}", r"^\d{10,}$", r"^\d+$"],
        "valid_patterns": [r"[A-Za-z]{2,}"],
    },
    "patient_mrn": {
        "min_len": 5,
        "max_len": 20,
        "valid_patterns": [r"\d{5,}"],
    },
    "billing_date": {
        "min_len": 8,
        "max_len": 30,
        "valid_patterns": [r"\d{2}[-/]\d{2}[-/]\d{4}", r"\d{4}[-/]\d{2}[-/]\d{2}"],
    },
    "bill_number": {
        "min_len": 5,
        "max_len": 40,
        "valid_patterns": [r"[A-Z]{2,}\d+", r"\d+[A-Z]+\d+", r"[A-Z]+[-/]\d+"],
    },
}


def _validate(field: str, value: str) -> bool:
    """Validate a header field value against rules."""
    if not value or not value.strip():
        return False
    v = value.strip()
    rules = VALUE_VALIDATORS.get(field)
    if not rules:
        return True

    if len(v) < rules.get("min_len", 1) or len(v) > rules.get("max_len", 9999):
        return False

    for p in rules.get("invalid_patterns", []):
        if re.search(p, v, re.IGNORECASE):
            return False

    valids = rules.get("valid_patterns", [])
    if valids and not any(re.search(p, v, re.IGNORECASE) for p in valids):
        return False

    return True


@dataclass
class Candidate:
    """A candidate header field value."""
    field: str
    value: str
    score: float
    page: int


class HeaderAggregator:
    """Set-once header locking with strict first-valid-wins policy.

    Once a field has a valid value, it is LOCKED and cannot be overwritten,
    even if a later page has a "better" match. This prevents multi-page
    overwrite bugs.
    """

    def __init__(self):
        self.best: Dict[str, Candidate] = {}
        self._locked: set = set()

    def is_locked(self, field: str) -> bool:
        """Check if a field is locked (already has valid value)."""
        return field in self._locked

    def _is_garbage_value(self, field: str, value: str) -> bool:
        """Reject values that are just labels or artifacts."""
        v = (value or "").strip()
        if not v:
            return True
        v_upper = v.upper()
        # label-only or punctuation-only
        garbage_patterns = [
            r"^(MRN|UHID|NAME|PATIENT|DATE|BILL|NO|NUMBER|ID)\.?[:]?$",
            r"^[:.\-\s]+$",
        ]
        if any(re.match(p, v_upper) for p in garbage_patterns):
            return True
        # very short non-alphabetic
        if len(v) < 2 or not re.search(r"[A-Za-z]", v):
            return True
        return False

    def offer(self, cand: Candidate) -> bool:
        """Offer a candidate value. Returns True if accepted."""
        # New: quick garbage filter
        if self._is_garbage_value(cand.field, cand.value):
            return False
        if not _validate(cand.field, cand.value):
            return False

        # If already locked, reject
        if self.is_locked(cand.field):
            return False

        # Accept and lock
        self.best[cand.field] = cand
        self._locked.add(cand.field)
        return True

    def finalize(self) -> Dict[str, str]:
        """Return final header values."""
        return {k: v.value for k, v in self.best.items()}


LABEL_PATTERNS = {
    # hospital_name: REMOVED - no longer extracted from bills
    "patient_name": [
        r"patient\s*name\s*[:.]?",
        r"patient\s*[:.]?\s*(?=\w)",  # "Patient: Mr Mohak Nandy"
        r"^name\s*[:.]?",
        r"pt\.?\s*name\s*[:.]?",  # "Pt. Name:"
    ],
    "patient_mrn": [
        r"patient\s*mrn\s*[:.]?",
        r"mrn\s*[:.]?",
        r"uhid\s*[:.]?",
        r"patient\s*id\s*[:.]?",
        r"hospital\s*id\s*[:.]?",
        r"reg\.?\s*(no|number)?\s*[:.]?",
    ],
    "bill_number": [
        r"bill\s*no\s*[:.]?",
        r"bill\s*number\s*[:.]?",
        r"invoice\s*no\s*[:.]?",
        r"invoice\s*number\s*[:.]?",
    ],
    "billing_date": [
        r"billing\s*date\s*[:.]?",
        r"bill\s*date\s*[:.]?",
        r"invoice\s*date\s*[:.]?",
        r"date\s*[:.]?\s*(?=\d)",
    ],
}

# Fallback patterns for patient name when label-based extraction fails
# These match title-case human names with optional salutation
NAME_FALLBACK_PATTERNS = [
    # "Mr Mohak Nandy" or "Mrs. Priya Sharma" - salutation followed by title-case name
    r"\b(Mr\.?|Mrs\.?|Ms\.?|Miss|Dr\.?|Shri|Smt\.?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b",
    # "MOHAK NANDY" - all caps name (2-4 words)
    r"\b([A-Z]{2,}(?:\s+[A-Z]{2,}){1,3})\b",
]

# HOSPITAL_FALLBACK_PATTERNS: REMOVED - hospital name no longer extracted from bills


# =============================================================================
# Utility functions
# =============================================================================
def _normalize_ws(s: str) -> str:
    """Normalize whitespace in a string."""
    return re.sub(r"\s+", " ", (s or "").strip())


def _make_id(prefix: str, parts: List[str]) -> str:
    """Generate a stable ID from prefix and parts."""
    payload = "|".join([prefix, *parts])
    return hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()


def _get_y(line: Dict[str, Any]) -> float:
    """Extract Y coordinate from a line dict."""
    box = line.get("box")
    try:
        if isinstance(box, (list, tuple)) and box:
            return float(min(p[1] for p in box))
    except Exception:
        pass
    return 0.0


# =============================================================================
# Stage 1: Header Parser (Isolated)
# =============================================================================
class HeaderParser:
    """Stage 1: Extract headers from header zone.

    - Processes lines in header zone (before table starts)
    - Processes ALL pages with first-valid-wins locking
    - Uses strict first-valid-wins locking to prevent multi-page overwrites
    - Falls back to name-like patterns if label-based extraction fails
    """

    def __init__(self):
        self.aggregator = HeaderAggregator()
        self.bill_number_candidates: List[str] = []
        self._fallback_name_candidates: List[Tuple[str, int, float]] = []  # (name, page, confidence)
        # _fallback_hospital_candidates: REMOVED - hospital no longer extracted
        self._pending_label: Optional[Tuple[str, int, float]] = None  # (field, page, confidence) for multi-line extraction

    def parse(self, lines: List[Dict[str, Any]], page_zones: Dict) -> Dict[str, Any]:
        """Parse headers from lines.

        Args:
            lines: OCR lines sorted by (page, y)
            page_zones: Zone boundaries by page

        Returns:
            Dict with header and patient info
        """
        # First pass: label-based extraction from ALL pages with multi-line support
        for i, line in enumerate(lines):
            text = (line.get("text") or "").strip()
            if not text:
                continue

            page = int(line.get("page", 0) or 0)

            # Check if line is in header zone (allow all pages for header extraction)
            zone = get_line_zone(line, page_zones)
            if zone == "payment":
                # Skip payment zone lines for header extraction
                continue

            # Skip lines that look like items (have amounts at end)
            if re.search(r"[\d,]+\.\d{2}\s*$", text):
                continue

            # Get next line for multi-line extraction support
            next_line = lines[i + 1] if i + 1 < len(lines) else None
            self._extract_from_line(line, next_line)

        # Second pass: fallback name extraction if patient_name not found
        if not self.aggregator.is_locked("patient_name"):
            self._extract_fallback_names(lines, page_zones)
        
        # Third pass: REMOVED - hospital extraction no longer performed

        return self._finalize()

    def _extract_from_line(self, line: Dict[str, Any], next_line: Optional[Dict[str, Any]] = None) -> None:
        """Extract header candidates from a single line using label patterns.
        
        Args:
            line: Current OCR line
            next_line: Next OCR line (for multi-line extraction)
        """
        text = (line.get("text") or "").strip()
        page = int(line.get("page", 0) or 0)
        conf = float(line.get("confidence", 1.0) or 1.0)
        tl = text.lower()

        for field, patterns in LABEL_PATTERNS.items():
            if self.aggregator.is_locked(field):
                continue

            # Try to extract value using safe helpers
            extracted_value = self._try_extract_field(text, patterns, field, next_line)
            
            if extracted_value:
                # For patient_name, clean up the extracted value
                if field == "patient_name":
                    extracted_value = self._clean_patient_name(extracted_value)
                
                cand = Candidate(field=field, value=extracted_value, score=conf, page=page)
                if self.aggregator.offer(cand):
                    if field == "bill_number":
                        self.bill_number_candidates.append(extracted_value.strip())
                break  # Move to next field once extracted

    def _try_extract_field(self, text: str, patterns: List[str], field: str, 
                          next_line: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Try to extract a field value safely from current or next line.
        
        Args:
            text: Current line text
            patterns: Label patterns to try
            field: Field name being extracted
            next_line: Next line for multi-line extraction
            
        Returns:
            Extracted value or None
        """
        # First try: same-line extraction with safe pattern matching
        for pat in patterns:
            # Check if pattern matches the label
            if not re.search(pat, text, re.IGNORECASE):
                continue
            
            # Try to extract value with defensive regex
            # Use (.*)  instead of (.+) to allow empty groups
            full_pattern = pat + r"\s*(.*)"
            match = re.search(full_pattern, text, re.IGNORECASE)
            
            if not match:
                continue
            
            # Safely extract the value group
            raw_value = safe_group(match, 1, "")
            cleaned_value = clean_extracted_value(raw_value)
            
            # If we got a meaningful value, return it
            if len(cleaned_value) >= 2:  # Minimum 2 chars to be valid
                return cleaned_value
            
            # Second try: multi-line extraction if current line has label only
            if next_line and is_label_only(text, [pat]):
                next_text = (next_line.get("text") or "").strip()
                multi_line_value = extract_from_next_line(text, next_text, [pat])
                if multi_line_value:
                    return multi_line_value
            
            # Pattern matched but couldn't extract value - stop trying other patterns
            # to avoid false positives
            break
        
        return None

    def _clean_patient_name(self, name: str) -> str:
        """Clean up extracted patient name.

        Removes trailing metadata that might have been captured.
        """
        if not name:
            return name

        # Remove common trailing patterns
        # e.g., "Mr Mohak Nandy Age: 35" -> "Mr Mohak Nandy"
        name = re.sub(r"\s+(age|gender|sex|dob|mrn|uhid|id)\s*[:.].*$", "", name, flags=re.IGNORECASE)

        # Remove trailing numbers that might be MRN/ID
        name = re.sub(r"\s+\d{5,}\s*$", "", name)

        return name.strip()

    def _extract_fallback_names(self, lines: List[Dict[str, Any]], page_zones: Dict) -> None:
        """Extract patient name using fallback patterns (title-case names with salutation).

        Only called if label-based extraction failed.
        """
        for line in lines:
            text = (line.get("text") or "").strip()
            if not text or len(text) < 5:
                continue

            page = int(line.get("page", 0) or 0)
            conf = float(line.get("confidence", 1.0) or 1.0)

            # Only check header zone on first few pages
            if page > 1:
                continue

            zone = get_line_zone(line, page_zones)
            if zone == "payment":
                continue

            # Skip lines with amounts
            if re.search(r"[\d,]+\.\d{2}\s*$", text):
                continue

            # Try fallback patterns
            for pattern in NAME_FALLBACK_PATTERNS:
                m = re.search(pattern, text)
                if m:
                    # Extract the full match or named groups
                    if m.lastindex and m.lastindex >= 2:
                        # Pattern has groups: salutation + name
                        name = f"{m.group(1)} {m.group(2)}".strip()
                    else:
                        name = m.group(0).strip()

                    # Validate: must look like a real name
                    if self._is_valid_fallback_name(name):
                        self._fallback_name_candidates.append((name, page, conf))
                        break

        # Use best fallback candidate (prefer earlier page, higher confidence)
        if self._fallback_name_candidates:
            self._fallback_name_candidates.sort(key=lambda x: (x[1], -x[2]))
            best_name, best_page, best_conf = self._fallback_name_candidates[0]
            cand = Candidate(field="patient_name", value=best_name, score=best_conf, page=best_page)
            self.aggregator.offer(cand)

    def _is_valid_fallback_name(self, name: str) -> bool:
        """Check if fallback name looks like a valid patient name."""
        if not name or len(name) < 3:
            return False

        # Reject if looks like a bill number or ID
        if re.match(r"^[A-Z]{2,4}\d+", name):
            return False

        # Reject if all digits
        if re.match(r"^\d+$", name):
            return False

        # Reject common non-name words
        reject_words = [
            "hospital", "clinic", "medical", "centre", "center",
            "bill", "invoice", "receipt", "patient", "doctor",
            "date", "time", "total", "amount", "payment",
        ]
        name_lower = name.lower()
        if any(word in name_lower for word in reject_words):
            return False

        # Must have at least one letter
        if not re.search(r"[A-Za-z]", name):
            return False

        return True
    
    # _extract_fallback_hospitals: REMOVED - hospital extraction no longer performed
    # _is_valid_fallback_hospital: REMOVED - hospital extraction no longer performed

    def _finalize(self) -> Dict[str, Any]:
        """Finalize and return header data."""
        header_locked = self.aggregator.finalize()

        # Deduplicate bill numbers
        bill_numbers: List[str] = []
        seen = set()
        for bn in self.bill_number_candidates:
            bn2 = bn.strip()
            if bn2 and bn2 not in seen:
                seen.add(bn2)
                bill_numbers.append(bn2)

        primary_bill_number = header_locked.get("bill_number")
        if primary_bill_number and primary_bill_number not in seen:
            bill_numbers.insert(0, primary_bill_number)

        return {
            "header": {
                "primary_bill_number": primary_bill_number,
                "bill_numbers": bill_numbers,
                "billing_date": header_locked.get("billing_date"),
                # hospital_name: REMOVED - no longer extracted
            },
            "patient": {
                "name": header_locked.get("patient_name") or "UNKNOWN",
                "mrn": header_locked.get("patient_mrn"),
            },
        }


# =============================================================================
# Stage 2: Item Parser (Isolated)
# =============================================================================
class ItemParser:
    """Stage 2: Extract items from item zone only.

    - Only processes lines in item zone (after header, before payment)
    - Uses section tracker for categorization
    - Applies numeric guardrails to reject suspect values
    - Skips header labels that leak into item zone
    - Separates discounts from billable items (discounts are non-billable metadata)
    """

    CATEGORIES = [
        "medicines",
        # "regulated_pricing_drugs" removed - will flag on items
        "surgical_consumables",
        "implants_devices",
        "diagnostics_tests",
        "radiology",
        "consultation",
        "hospitalization",
        "packages",
        "administrative",
        "other",
    ]

    def __init__(self):
        self.categorized: Dict[str, List[Dict[str, Any]]] = {k: [] for k in self.CATEGORIES}
        self.section_tracker: Optional[SectionTracker] = None
        # Discounts are tracked separately and NOT included in billable items
        self.discounts: Dict[str, List[Dict[str, Any]]] = {
            "patient": [],
            "sponsor": [],
            "general": [],
        }

    def parse(
        self,
        lines: List[Dict[str, Any]],
        item_blocks: List[Dict[str, Any]],
        page_zones: Dict,
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, List[Dict[str, Any]]]]:
        """Parse items from lines or item_blocks.

        Args:
            lines: OCR lines sorted by (page, y)
            item_blocks: Pre-grouped item blocks from OCR
            page_zones: Zone boundaries by page

        Returns:
            Tuple of:
            - Dict mapping category to list of billable items (excludes discounts)
            - Dict mapping discount type to list of discount entries
        """
        # Build section tracker
        self.section_tracker = build_section_tracker(lines)

        if item_blocks:
            self._parse_blocks(item_blocks, page_zones)
        else:
            self._parse_lines(lines, page_zones)

        return self.categorized, self.discounts

    def _parse_blocks(self, item_blocks: List[Dict[str, Any]], page_zones: Dict) -> None:
        """Parse from pre-grouped item blocks with enhanced column parsing."""
        for block in item_blocks:
            text = _normalize_ws(block.get("text") or "")
            desc = _normalize_ws(block.get("description") or "") or text
            cols = block.get("columns") or []
            page = int(block.get("page", 0) or 0)
            y = float(block.get("y", 0.0) or 0.0)

            # Create fake line for zone detection
            fake_line = {"text": text, "page": page, "box": [[0, y], [0, y], [0, y], [0, y]]}

            # Skip payment zone
            zone = get_line_zone(fake_line, page_zones)
            if zone == "payment":
                continue

            # Skip if payment-like
            if is_paymentish(text) or is_paymentish(desc):
                continue

            # Skip header labels
            if should_skip_as_header_label(desc):
                continue

            # Skip non-billable sections (totals, payments, etc.)
            if is_non_billable_section(desc) or is_non_billable_section(text):
                continue

            # Check if this is a DISCOUNT line - route to discounts, not items
            if is_discount(desc) or is_discount(text):
                # Extract amount using fallback method
                amount = self._extract_validated_amount(cols, text, desc)
                if amount is not None:
                    discount_type = classify_discount_type(desc) or classify_discount_type(text)
                    embedded_amount = extract_discount_amount(desc)
                    discount_amount = embedded_amount if embedded_amount is not None else amount

                    discount_id = _make_id("discount", [discount_type, f"{discount_amount:.2f}", desc.lower(), str(page)])
                    self.discounts[discount_type].append({
                        "discount_id": discount_id,
                        "description": desc,
                        "amount": discount_amount,
                        "type": discount_type,
                        "page": page,
                    })
                continue  # Do NOT add to categorized items

            # Enhanced column parsing with semantic context
            parsed = parse_item_columns(desc, cols, full_text=text)
            if not parsed or not is_valid_item(parsed):
                continue

            # Get category from section tracker
            category = get_category_for_item(desc, page, y, self.section_tracker)

            item_id = _make_id("item", [category, f"{parsed.final_amount:.2f}", desc.lower(), str(page)])

            self.categorized[category].append({
                "item_id": item_id,
                "description": parsed.description,
                "qty": parsed.qty,
                "unit_rate": parsed.unit_rate,
                "pdf_amount": parsed.pdf_amount,
                "computed_amount": parsed.computed_amount,
                "final_amount": parsed.final_amount,
                "discrepancy": parsed.discrepancy,
                "category": category,
                "page": page,
                "section_raw": self.section_tracker.get_section_at(page, y),
                "is_regulated_pricing": is_regulated_pricing_item(desc) if category == "medicines" else False,
            })

    def _parse_lines(self, lines: List[Dict[str, Any]], page_zones: Dict) -> None:
        """Parse from individual lines (fallback) with consistent schema output."""
        for line in lines:
            text = _normalize_ws(line.get("text") or "")
            if not text:
                continue

            page = int(line.get("page", 0) or 0)
            y = _get_y(line)

            # Skip if section header
            if detect_section_header(text):
                continue

            # Skip payment zone
            zone = get_line_zone(line, page_zones)
            if zone == "payment":
                continue

            # Skip header zone
            if zone == "header":
                continue

            # Skip if payment-like
            if is_paymentish(text):
                continue

            # Skip header labels
            if should_skip_as_header_label(text):
                continue

            # Skip non-billable sections (totals, payments, etc.)
            if is_non_billable_section(text):
                continue

            # Check if this is a DISCOUNT line - handle separately
            if is_discount(text):
                amount = extract_amount_from_text(text)
                if amount is not None and amount > 0:
                    discount_type = classify_discount_type(text)
                    embedded_amount = extract_discount_amount(text)
                    discount_amount = embedded_amount if embedded_amount is not None else amount

                    discount_id = _make_id("discount", [discount_type, f"{discount_amount:.2f}", text.lower(), str(page)])
                    self.discounts[discount_type].append({
                        "discount_id": discount_id,
                        "description": text,
                        "amount": discount_amount,
                        "type": discount_type,
                        "page": page,
                    })
                continue  # Do NOT add to categorized items

            # Extract amount
            amount = extract_amount_from_text(text)
            if amount is None or amount <= 0:
                continue

            # Validate amount
            is_valid, _ = validate_amount(amount, row_has_description=True, source_text=text)
            if not is_valid:
                continue

            # Get category
            category = get_category_for_item(text, page, y, self.section_tracker)

            item_id = _make_id("item", [category, f"{amount:.2f}", text.lower(), str(page)])

            # Build item with consistent schema (line-based has qty=1, no explicit rate)
            self.categorized[category].append({
                "item_id": item_id,
                "description": text,
                "qty": 1.0,  # Default qty for line-based parsing
                "unit_rate": None,
                "pdf_amount": amount,
                "computed_amount": None,
                "final_amount": amount,
                "discrepancy": False,
                "category": category,
                "page": page,
                "section_raw": self.section_tracker.get_section_at(page, y),
                "is_regulated_pricing": is_regulated_pricing_item(text) if category == "medicines" else False,
            })

    def _extract_validated_amount(
        self,
        cols: List[str],
        text: str,
        desc: str,
    ) -> Optional[float]:
        """Extract and validate amount from columns or text."""
        amount: Optional[float] = None

        # Prefer numeric columns (from right)
        for c in reversed(cols):
            amount = extract_amount_from_text(c)
            if amount is not None:
                break

        # Fallback to text
        if amount is None:
            amount = extract_amount_from_text(text)

        if amount is None or amount <= 0:
            return None

        # Validate with row context
        has_context = has_valid_row_context(desc, cols, min_description_len=3, min_columns=1)
        is_valid, _ = validate_amount(amount, row_has_description=has_context, source_text="")

        if not is_valid:
            return None

        return amount

    def _extract_qty_rate(self, cols: List[str]) -> Tuple[Optional[float], Optional[float]]:
        """Extract quantity and unit rate from columns (best-effort)."""
        def to_float(x: str) -> Optional[float]:
            if not x:
                return None
            try:
                return float(re.sub(r"[₹$,\s]", "", x))
            except Exception:
                return None

        nums: List[float] = []
        for c in cols:
            v = to_float(c)
            if v is not None:
                nums.append(v)
        # Heuristic: if we have 3+ numbers, assume last is amount, previous two are qty, rate
        if len(nums) >= 3:
            return nums[-3], nums[-2]
        if len(nums) == 2:
            # Could be qty, amount OR rate, amount; can't know. Prefer qty.
            return nums[0], None
        return None, None


# =============================================================================
# Stage 3: Payment Parser (Isolated)
# =============================================================================
class PaymentParser:
    """Stage 3: Extract payments from payment zone only.

    - Only processes lines in payment zone or with payment keywords
    - Extracts reference numbers, payment modes
    - Never routes to medical items
    """

    def __init__(self):
        self.payments: List[Dict[str, Any]] = []

    def parse(
        self,
        lines: List[Dict[str, Any]],
        item_blocks: List[Dict[str, Any]],
        page_zones: Dict,
    ) -> List[Dict[str, Any]]:
        """Parse payments from lines or item_blocks.

        Args:
            lines: OCR lines sorted by (page, y)
            item_blocks: Pre-grouped item blocks from OCR
            page_zones: Zone boundaries by page

        Returns:
            List of payment entries
        """
        if item_blocks:
            self._parse_blocks(item_blocks, page_zones)
        else:
            self._parse_lines(lines, page_zones)

        return self.payments

    def _parse_blocks(self, item_blocks: List[Dict[str, Any]], page_zones: Dict) -> None:
        """Parse payments from item blocks."""
        for block in item_blocks:
            text = _normalize_ws(block.get("text") or "")
            desc = _normalize_ws(block.get("description") or "") or text
            page = int(block.get("page", 0) or 0)
            y = float(block.get("y", 0.0) or 0.0)

            # Create fake line for zone detection
            fake_line = {"text": text, "page": page, "box": [[0, y], [0, y], [0, y], [0, y]]}

            # Check if in payment zone or has payment keywords
            zone = get_line_zone(fake_line, page_zones)
            is_payment = zone == "payment" or is_paymentish(text) or is_paymentish(desc)

            if not is_payment:
                continue

            self._add_payment(text, desc, page)

    def _parse_lines(self, lines: List[Dict[str, Any]], page_zones: Dict) -> None:
        """Parse payments from lines."""
        for line in lines:
            text = _normalize_ws(line.get("text") or "")
            if not text:
                continue

            page = int(line.get("page", 0) or 0)

            # Check if in payment zone or has payment keywords
            zone = get_line_zone(line, page_zones)
            is_payment = zone == "payment" or is_paymentish(text)

            if not is_payment:
                continue

            self._add_payment(text, text, page)

    def _add_payment(self, text: str, desc: str, page: int) -> None:
        """Add a payment entry."""
        amount = extract_amount_from_text(text)
        ref = extract_reference(text)
        mode = extract_payment_mode(text)

        pid = _make_id("payment", [ref or "", f"{amount or ''}", desc.lower(), str(page)])

        self.payments.append({
            "payment_id": pid,
            "description": desc,
            "amount": amount,
            "reference": ref,
            "mode": mode,
            "page": page,
        })


# =============================================================================
# Main Bill Extractor (Orchestrator)
# =============================================================================
class BillExtractor:
    """Orchestrates three-stage extraction pipeline.

    Stage 1: Header Parser -> patient info, bill metadata
    Stage 2: Item Parser -> categorized line items + discounts (separate)
    Stage 3: Payment Parser -> receipts/payments (excluded from final doc per choice C)

    Business rules:
    - Discounts are stored in summary.discounts, NOT in items or totals
    - Payments (RCPO/RCP*) are completely excluded from final document
    - grand_total = sum of billable items only (excludes discounts & payments)
    """

    def __init__(self):
        self._warnings: List[Dict[str, Any]] = []

    def warn(self, code: str, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        self._warnings.append({
            "code": code,
            "message": message,
            "context": context or {},
            "ts": datetime.now().isoformat(),
        })

    def extract(self, ocr_result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract bill data from OCR result.

        Args:
            ocr_result: OCR output with raw_text, lines, item_blocks

        Returns:
            Structured bill document (payments excluded, discounts in summary)
        """
        raw_text = ocr_result.get("raw_text", "") or ""
        lines: List[Dict[str, Any]] = ocr_result.get("lines") or []
        item_blocks: List[Dict[str, Any]] = ocr_result.get("item_blocks") or []

        # Legacy fallback: if only raw_text exists
        if not lines and raw_text:
            lines = [
                {"text": t.strip(), "confidence": 1.0, "box": None, "page": 0}
                for t in raw_text.split("\n")
                if t.strip()
            ]

        # Sort lines by (page, y)
        lines_sorted = sorted(lines, key=lambda l: (int(l.get("page", 0) or 0), _get_y(l)))

        # Detect zone boundaries
        page_zones = detect_all_zones(lines_sorted)

        # Stage 1: Header parsing (all pages, first-valid-wins)
        header_parser = HeaderParser()
        header_data = header_parser.parse(lines_sorted, page_zones)

        # Stage 2: Item parsing (returns billable items AND discounts separately)
        item_parser = ItemParser()
        categorized, discounts = item_parser.parse(lines_sorted, item_blocks, page_zones)

        # Stage 3: Payment parsing
        # NOTE: Payments are parsed but NOT included in final document (choice C)
        # This ensures RCPO/RCP* entries don't pollute items or totals
        payment_parser = PaymentParser()
        _payments = payment_parser.parse(lines_sorted, item_blocks, page_zones)
        # _payments is intentionally discarded per requirement choice C

        # Post-processing validation
        self._validate_no_payment_leakage(categorized)

        # Calculate totals from BILLABLE items only (discounts excluded)
        # Use final_amount (B2 rule: pdf_amount takes precedence over computed)
        subtotals = {
            k: round(sum(i.get("final_amount", 0.0) or 0.0 for i in v), 2)
            for k, v in categorized.items()
        }
        # Remove zero subtotals for cleaner output
        subtotals = {k: v for k, v in subtotals.items() if v > 0}

        grand_total = round(sum(subtotals.values()), 2)
        
        # Track discrepancy count for warnings
        total_discrepancies = sum(
            sum(1 for i in v if i.get("discrepancy", False))
            for v in categorized.values()
        )
        if total_discrepancies > 0:
            self.warn("qty_rate_discrepancies", f"{total_discrepancies} items have qty×rate != pdf_amount")

        # Validate grand total
        is_valid, reason = validate_grand_total(grand_total)
        if not is_valid:
            # Log warning but don't fail - cap the total
            self.warn("grand_total_cap", f"Grand total capped: {grand_total}")
            grand_total = min(grand_total, 1e8)

        # Build discount summary
        discount_summary = self._build_discount_summary(discounts)
        
        # Add "Hospital - " category at the top with hospital name from header
        # This is required for verifier to match hospital tie-ups
        hospital_name = header_data["header"].get("hospital_name") or "UNKNOWN"
        hospital_category = {
            "Hospital - ": [
                {
                    "item_name": hospital_name,
                    "amount": 0,
                    "quantity": 1,
                    "final_amount": 0,
                }
            ]
        }
        # Merge hospital category at the top (before other categories)
        categorized_with_hospital = {**hospital_category, **categorized}

        result: Dict[str, Any] = {
            "extraction_date": datetime.now().isoformat(),
            "header": header_data["header"],
            "patient": header_data["patient"],
            "items": categorized_with_hospital,  # Use merged dict with hospital category
            # "payments" intentionally excluded per choice C
            "subtotals": subtotals,
            "grand_total": grand_total,
            "summary": {
                "discounts": discount_summary,
            },
            "extraction_warnings": self._warnings,
            "raw_ocr_text": raw_text[:5000] if raw_text else None,
        }

        return result

    def _build_discount_summary(self, discounts: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Build discount summary from parsed discounts.

        Args:
            discounts: Dict mapping discount type to list of discount entries

        Returns:
            Summary with totals by type
        """
        summary: Dict[str, Any] = {
            "patient": 0.0,
            "sponsor": 0.0,
            "general": 0.0,
            "total": 0.0,
            "details": [],
        }

        for discount_type, entries in discounts.items():
            type_total = sum(e.get("amount", 0.0) or 0.0 for e in entries)
            summary[discount_type] = round(type_total, 2)
            summary["total"] += type_total
            summary["details"].extend(entries)

        summary["total"] = round(summary["total"], 2)
        return summary

    def _validate_no_payment_leakage(self, categorized: Dict[str, List[Dict[str, Any]]]) -> None:
        """Ensure no payment-like items leaked into medical categories."""
        for cat, items in categorized.items():
            for it in items:
                d = (it.get("description") or "").upper()
                if "RCPO-" in d or "RCP" in d or is_paymentish(d):
                    raise AssertionError(
                        f"Payment-like reference leaked into medical items category={cat}: {d[:50]}"
                    )


def extract_bill_data(ocr_result: Dict[str, Any]) -> Dict[str, Any]:
    """Public entry point used by the rest of the codebase."""
    return BillExtractor().extract(ocr_result)
