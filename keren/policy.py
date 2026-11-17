"""Application policy: deterministic gates that do not depend on the model.

Residual limitation: these are lexical rules. They are biased towards refusing
(false positives are acceptable) but paraphrases, other languages, or indirect
phrasing can slip through; the model's own is_advice_request flag is a second
layer, the output validator a third. None is a proof of safety.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, List, Optional, Set

ADVICE_IN = re.compile(
    r"\b(buy|sell|purchase|recommend\w*|should\s+(i|we|the\s+client|my\s+client)|advice|advise|"
    r"worth\s+(buying|selling)|invest(ing)?\s+in|rebalance)\b|"
    r"(לקנות|למכור|לרכוש|קנייה|קניה|מכירה|המלצ\w*|כדאי|להשקיע|מומלץ)", re.IGNORECASE)
ADVICE_OUT = re.compile(
    r"\b(you|client|they)\s+should\b|\bi\s+recommend\b|\b(consider|worth)\s+(buying|selling)\b|"
    r"\b(buy|sell)\s+(now|more|some|eth|btc)\b|מומלץ|כדאי|אני\s+ממליץ", re.IGNORECASE)

INTENTS = ("portfolio_value", "exposure_policy", "fees", "market_review", "advice", "other")
_HEB = re.compile(r"[֐-׿]")
_CUST = re.compile(r"\bC-\d{4}\b")
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_ID = re.compile(r"KB-\d+(?:#\d+)?|C-\d{4}")
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def is_advice_request(text: str) -> bool:
    return bool(ADVICE_IN.search(text))


def detect_lang(text: str) -> str:
    return "he" if _HEB.search(text) else "en"


def mentioned_customers(text: str) -> List[str]:
    return sorted(set(_CUST.findall(text)))


def rule_intent(question: str) -> str:
    """Deterministic fallback router (also used by the offline fake model)."""
    q = question.lower()
    if is_advice_request(question):
        return "advice"
    rules = [
        ("market_review", ("market review", "volatil", "סקיר", "תנודתיות")),
        ("fees", ("fee", "billing", "דמי ניהול", "עמלה")),
        ("exposure_policy", ("exposure", "policy", "limit", "concentration", "חשיפה", "חורג", "מדיניות")),
        ("portfolio_value", ("value", "worth", "portfolio", "total", "שווי", "תיק")),
    ]
    for intent, words in rules:
        if any(w in q for w in words):
            return intent
    return "other"


def _decimals(texts: Iterable[str]) -> Set[Decimal]:
    out: Set[Decimal] = set()
    for t in texts:
        for m in _NUM.findall(_ID.sub(" ", t)):
            try:
                out.add(Decimal(m.replace(",", "")))
            except InvalidOperation:
                pass
    return out


def validate_prose(text: str, placeholders: Dict[str, str], allowed_ids: Iterable[str]) -> Optional[str]:
    """Fill {placeholders}; return None if the model text must be rejected.

    Rejects: unknown placeholders, numbers not present in authoritative facts,
    source IDs that were not retrieved, advice-like phrasing.
    """
    unknown = [n for n in _PLACEHOLDER.findall(text) if n not in placeholders]
    if unknown:
        return None
    filled = _PLACEHOLDER.sub(lambda m: placeholders[m.group(1)], text)
    if len(filled) > 400:  # summaries are short by contract; long text is likely drift or leakage
        return None
    if ADVICE_OUT.search(filled):
        return None
    allowed = _decimals(placeholders.values())
    for n in _decimals([filled]):
        if n not in allowed:
            return None
    ok_ids = set(allowed_ids) | {i.split("#")[0] for i in allowed_ids}
    for ident in _ID.findall(filled):
        if ident not in ok_ids:
            return None
    return filled.strip()
