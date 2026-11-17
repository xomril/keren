"""Orchestration. Order matters: access -> advice gate -> (model) intent ->
deterministic tools -> retrieval -> render -> optional validated model prose."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import policy, render
from .access import AccessDenied, authorize
from .model import ModelUnavailable
from .retrieval import Chunk, load_kb, search
from .tools import (DataUnavailable, MissingPriceError, Store, compute_valuation, exposure_check,
                    get_portfolio, get_prices, quarterly_fee_estimate)

EXPECTED_DOC = {"exposure_policy": "KB-001", "fees": "KB-002", "market_review": "KB-004"}


@dataclass
class Answer:
    status: str  # ok | refused | denied | error
    text: str
    sources: List[str] = field(default_factory=list)
    facts: Dict = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)  # degradation, quarantine, validator events


def _refusal(kb: List[Chunk], lang: str, notes: List[str]) -> Answer:
    src = [c.id for c in kb if c.doc_id == "KB-003"]
    return Answer("refused", render.msg("refusal", lang), src, {}, notes)


def answer(operator: str, customer_id: str, question: str, model, store: Optional[Store] = None,
           kb: Optional[List[Chunk]] = None) -> Answer:
    store = store or Store()
    kb = kb if kb is not None else load_kb()
    lang = policy.detect_lang(question)
    notes: List[str] = []

    # 1. Access, BEFORE any data access. Customer IDs named in the question must be in scope too.
    try:
        auth = authorize(operator, customer_id)
        for cid in policy.mentioned_customers(question):
            authorize(operator, cid)
    except AccessDenied:
        return Answer("denied", render.msg("denied", lang))

    # 2. Rule-based advice gate: independent of the model, runs before any model call.
    if policy.is_advice_request(question):
        return _refusal(kb, lang, ["advice gate: rules"])

    # 3. Intent. Model failure degrades to the rule router; never to a guess.
    try:
        routed = model.classify(question)
        intent, model_flag = routed["intent"], routed["is_advice_request"]
    except (ModelUnavailable, KeyError):
        intent, model_flag = policy.rule_intent(question), False
        notes.append("degraded: model unavailable for routing, rule router used")
    if model_flag or intent == "advice":
        return _refusal(kb, lang, notes + ["advice gate: model"])
    if intent == "other":
        return Answer("ok", render.msg("unsupported", lang), [], {}, notes)

    # 4. Retrieval (all four docs searchable). Required source must be present and not quarantined.
    hits, quarantined = search(question, kb)
    if quarantined:
        notes.append("quarantined chunks: " + ", ".join(quarantined))
    expected = EXPECTED_DOC.get(intent)
    used = [c for c in hits if c.doc_id == expected] if expected else []
    if expected and not used:
        return Answer("error", render.msg("no_source", lang), [], {}, notes)

    # 5. Deterministic tools + rendering.
    facts: Dict = {}
    sources = [c.id for c in used]
    try:
        if intent == "market_review":
            text = render.market_text([c.text for c in used], lang)
            return Answer("ok", text, sources, {}, notes)
        pf = get_portfolio(store, auth)
        priced = get_prices(store, [h["asset"] for h in pf["holdings"]])
        val = compute_valuation(pf, priced)
    except MissingPriceError as exc:
        return Answer("error", render.msg("missing_price", lang, assets=", ".join(exc.assets)), [], {}, notes)
    except DataUnavailable:
        return Answer("error", render.msg("data_unavailable", lang), [], {}, notes)
    sources = ["tool:get_portfolio", "tool:get_prices"] + sources
    ph = {"total_usd": render.usd(val["totalUsd"]), "as_of": val["holdingsAsOf"]}  # display-formatted
    for p in val["positions"]:
        ph["value_%s_usd" % p["asset"].lower()] = render.usd(p["valueUsd"])
        ph["exposure_%s_pct" % p["asset"].lower()] = p["exposurePct"] + "%"

    if intent == "portfolio_value":
        facts, text = val, render.value_text(val, lang)
    elif intent == "exposure_policy":
        if pf["riskProfile"] != "medium":
            return Answer("error", render.msg("profile", lang), [], {}, notes)
        chk = exposure_check(val)
        facts, text = chk, render.exposure_text(chk, lang)
        ph.update(top_asset=chk["asset"], top_exposure_pct=chk["exposurePct"] + "%", limit_pct=chk["limitPct"] + "%")
    else:  # fees
        fee = quarterly_fee_estimate(val)
        facts, text = fee, render.fee_text(fee, val["totalUsd"], lang)
        ph.update(fee_usd=render.usd(fee["estimateUsd"]), annual_rate_pct="0.8%", periods_per_year="4")

    # 6. Optional model prose: kept only if it passes the validator. Facts above never depend on it.
    try:
        prose = model.compose(question, ph, [c.text for c in used], lang)
        if prose:
            checked = policy.validate_prose(prose, ph, sources)
            if checked:
                text += "\n" + checked
            else:
                notes.append("validator: model prose rejected, template answer only")
    except ModelUnavailable:
        notes.append("degraded: model unavailable for prose, template answer only")
    return Answer("ok", text, sources, facts, notes)
