"""Tiny lexical retrieval over the four supplied documents (no vector DB).

Character-trigram overlap handles Hebrew prefixes (ב/ה/ל...) without a stemmer.
Each doc has a `keywords` field: retrieval metadata only, never shown as source
text. Retrieved text is DATA: chunks that look like instructions are quarantined
before they can reach the model or the answer.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from .tools import DATA_DIR

_WORD = re.compile(r"[\w%]+", re.UNICODE)
_STOP = frozenset("the what does say about and for are was this that with how much will next can".split())
_INJECTION = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+|any\s+)?(previous|prior|above|earlier)|system\s*:|"
    r"new\s+instruction|you\s+must|override|reveal|"
    r"התעלם|תתעלם|הוראות\s+קודמות|הוראה\s+חדשה", re.IGNORECASE)


@dataclass(frozen=True)
class Chunk:
    id: str  # stable: KB-001#1 = document KB-001, sentence 1
    doc_id: str
    title: str
    text: str
    keywords: str


def load_kb(docs: Optional[List[Dict[str, str]]] = None) -> List[Chunk]:
    docs = docs if docs is not None else json.loads((DATA_DIR / "kb.json").read_text(encoding="utf-8"))
    chunks = []
    for d in docs:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", d["text"]) if s.strip()]
        for i, s in enumerate(sentences, 1):
            chunks.append(Chunk("%s#%d" % (d["id"], i), d["id"], d["title"], s, d.get("keywords", "")))
    return chunks


def is_suspicious(chunk: Chunk) -> bool:
    return bool(_INJECTION.search(chunk.text))


def _trigrams(text: str) -> Set[str]:
    out: Set[str] = set()
    for w in _WORD.findall(text.lower()):
        if w in _STOP or len(w) < 3:
            continue
        out.update(w[i:i + 3] for i in range(len(w) - 2))
    return out


def search(question: str, kb: List[Chunk], k: int = 2, min_score: float = 0.12
           ) -> Tuple[List[Chunk], List[str]]:
    """Returns (usable top-k chunks, quarantined chunk ids)."""
    q = _trigrams(question)
    scored, quarantined = [], []
    bad_docs = {c.doc_id for c in kb if is_suspicious(c)}  # one bad sentence taints the whole document
    for c in kb:
        if c.doc_id in bad_docs:
            quarantined.append(c.id)
            continue
        d = _trigrams(c.text + " " + c.keywords)
        if not q or not d:
            continue
        score = len(q & d) / len(q)
        if score >= min_score:
            scored.append((score, c))
    scored.sort(key=lambda t: (-t[0], t[1].id))
    return [c for _, c in scored[:k]], quarantined
