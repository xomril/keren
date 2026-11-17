# Part A: Production architecture for the Keren portfolio assistant

Diagram: [architecture.svg](architecture.svg). This document is the **designed** system. Only the parts marked *(prototype)* exist as code in this repo, and they were tested offline unless stated otherwise.

**Context.** An internal "AI assistant" for portfolio managers of a digital-asset platform. It answers questions about a customer's portfolio, and about internal research and product policy. Environment: React front end, C#/.NET Core WebAPI, AWS. Team: four .NET developers, no prior AI-product experience.

**The one design rule.** The model never holds authority over data, numbers or access. Code decides who may see what, computes every number, and checks what the model says. The model only (a) classifies the question and (b) optionally writes a short sentence around numbers it is handed. If the model is removed, the system still answers every supported question from templates.

## 1. Components and request flow

React SPA → CloudFront + WAF → ALB / API Gateway (JWT check) → **.NET Core WebAPI on ECS Fargate**, which runs an 8-step pipeline (numbers match the diagram):

| # | Step | Where it runs | Notes |
|---|------|---------------|-------|
| 1 | AuthN/Z | .NET + Cognito/corporate OIDC | Manager identity from the JWT. A server-side entitlement table (Aurora) says which customers this manager may see. Checked **before any data is read**. Unknown, unauthorized and malformed IDs get the same denial. *(prototype: hardcoded grants)* |
| 2 | Input gate | .NET rules + Bedrock Guardrails | Detects purchase/sale/personal-advice requests and injection phrasing. Advice → fixed refusal template that refers to a licensed adviser. Models and tools are skipped. *(prototype: rules only)* |
| 3 | Intent router | Bedrock, small Claude model | Returns JSON `{intent, is_advice_request}`. Never sees or chooses `customerId`. Timeout, then fallback to a rule router. *(prototype)* |
| 4 | Deterministic tools | C# | `get_portfolio`, `get_prices`; value, exposure and fee computed with `decimal`. *(prototype, Python `Decimal`)* |
| 5 | Retrieval | OpenSearch or pgvector | ACL-filtered chunks with stable source IDs. *(prototype: lexical)* |
| 6 | Composer | Bedrock Claude, pinned version | Writes at most 2 sentences using **placeholders** for numbers. Documents are passed as data, not instructions. *(prototype, live-tested with Haiku)* |
| 7 | Output validator | .NET | Rejects the model text unless every number is a tool value, every source ID was retrieved, no advice phrasing, length OK. On rejection the template answer is returned. *(prototype)* |
| 8 | Audit + metrics | S3 Object Lock, CloudWatch, X-Ray/OTel | Who asked, which customer, tools called, source IDs, latency, validator outcome. Logs hold IDs and hashes, not raw question text by default. |

The front end only renders text, source tags and a status. It holds no secrets and no business logic.

## 2. RAG

- **Corpus.** Four documents today (exposure policy, fees, recommendation policy, market review); the design must still scale to hundreds.
- **Ingestion.** Documents land in S3 (versioned). An ingest job splits by section (so a rule and its exception stay together), assigns stable IDs such as `KB-001#2`, attaches metadata (version, owner, date, allowed roles), embeds with Bedrock and indexes. Re-ingest on change; old versions kept for audit.
- **Search.** Hybrid: keyword (BM25) plus vector, then a role filter applied **inside the query**, not after it. The prototype's lexical-only search is acceptable for four documents and is not a production answer.
- **Citations.** Every answer carries source IDs, and the validator rejects IDs that were not retrieved. A claim without a source is not shown.
- **Freshness.** Each chunk carries a date, the answer states it, and old market reviews are flagged.
- **Poisoned documents.** A retrieved document is untrusted text. A document containing instruction-like text is quarantined whole and not used. *(prototype, one of the two original eval cases)*

## 3. Tools and agent

**Tools exposed to the model: none directly.** The router returns an intent, and the .NET code calls `get_portfolio` and `get_prices` itself with the `customerId` it took from the authenticated request. The model cannot pass or change a customer ID, so a prompt injection cannot make it read another customer's data.

**Agent loop or fixed pipeline?** A fixed pipeline: the question types are few and known, so a free-running agent adds latency, cost and attack surface for no benefit. If later questions need dependent tool calls, add a bounded loop inside step 4 only.

**Should this go through MCP?** Not for the core path.
- *Against, now:* two in-process functions in one service owned by one team. MCP would add a network hop, a second auth layer and something new for a .NET team to operate, to solve a discovery problem we do not have.
- *For, later:* if several AI products need the same portfolio tools, wrap the same C# functions as an MCP server. MCP is only a transport; the server must still authorize with the caller's identity and never accept a customer ID from the model.

## 4. Guardrails and safety

| Risk | Control | Layer |
|------|---------|-------|
| Investment advice | Rule gate before any model call, model flag as second layer, fixed refusal text citing the recommendation policy, output validator rejects advice phrasing. Bedrock Guardrails as an additional managed filter. | 2, 3, 7 |
| Prompt injection in the question | Rule gate; the model has no tools and no customer ID to abuse. | 2, 3 |
| Prompt injection inside retrieved documents (indirect) | Documents passed as delimited data; quarantine of instruction-like documents; validator limits what text can contain; no tool access to hijack. | 5, 6, 7 |
| Wrong numbers | Numbers come only from code. Model text must use placeholders and is rejected if any number is not a tool value. | 4, 7 |
| Cross-customer leakage | Entitlement check before reads; ACL in the search query; one customer per request; no cross-request memory or cache keyed by question text. | 1, 5 |
| PII and logs | IDs and hashes in logs, not names or raw questions; restricted log access; Guardrails PII filter on output. | 8 |
| Model outage or timeout | Router falls back to rules; composer is skipped; template answer still returns correct numbers. | 3, 6 |

**Known limits.** The rule-based advice detector is lexical: biased to refuse, but it can miss paraphrases and other languages, hence the extra layers and an eval set that grows from real misses. The validator is strict and drops correct prose that rounds a number; the cost is a plainer answer, never a wrong one.

## 5. Evaluation and quality

- **Golden set** (versioned in the repo, run in CI): the prototype has 13 cases (7 mandatory questions, 2 original, 4 extra). Production grows it from real traffic: every thumbs-down, refusal dispute and validator rejection becomes a case.
- **What is measured, and how:**

| Measure | Method | Proposed go / no-go (to be agreed with compliance) |
|---------|--------|-----------------------------------------------------|
| Numbers correct | Exact match against independently computed values (deterministic) | 100%. Any miss blocks release |
| Advice leakage | Adversarial set (direct, paraphrased, Hebrew/English, injected) | 0 leaks on the set; new leaks become cases |
| Wrongful refusal | Normal questions that must not be refused | below an agreed rate (start at 2%) |
| Access control | Cases for other customers, malformed IDs, IDs in free text | 100%, with zero data reads on denial |
| Citation correctness | Cited IDs ⊆ retrieved, required source present | 100% |
| Router accuracy and prose quality | Labelled questions; human review of a sample (an LLM judge may assist, never decides a gate) | no regression; reviewed before launch, then sampled |

- **Before go-live:** golden set on the exact model and prompts, a red-team session with the compliance owner, a **shadow period** where a person checks answers, then a pilot with a few managers.
- **After go-live:** the set runs on every prompt, model-version or document change; weekly review of refusals, validator rejections and feedback. The model version is pinned, so nothing changes silently.
- **Not claimed:** passing the offline set does not prove production safety, and the fake model used offline proves the gates and numbers, not model behaviour.

## 6. Operations

- **Observability:** per-step latency, refusal rate, validator-rejection rate, router fallbacks, empty-retrieval rate, token counts and errors; end-to-end traces; alarms on spikes.
- **Latency.** Template answers well under a second; with the composer a few seconds (targets to confirm with users). Explicit timeouts on every model call; on timeout the answer degrades to the template instead of waiting.
- **Cost.** Dominated by model calls. Levers: small model for routing, 2-sentence composer output, no composer for refusals and market-review quotes, per-user rate limit, daily budget alarm.
  *Rough estimate, not measured:* a live question makes two small calls (router about 200 input / 30 output tokens; composer about 600 input / 100 output). At the Anthropic API list price for Haiku 5.5 ($0.10 / $0.50 per million input / output tokens) that is about $0.00015 per question, so roughly $7 a month for an assumed 44,000 questions (50 managers x 40 a day x 22 days). Refusals and access denials cost no model call. Bedrock pricing may differ, and latency has not been measured.
- **Fallback.** Model down → templated numeric answers. Search down → value, exposure and fee questions still work; document questions return "source unavailable".
- **Model replacement.** All model access sits behind one interface (`classify`, `compose`). A new model: pin the version, run the golden set, compare, shadow, switch by flag, keep the old one for rollback. The prototype's `FakeModel` / `AnthropicModel` split shows the seam.
- **Security basics.** Least-privilege IAM, private subnets, VPC endpoints for Bedrock and S3, KMS, Secrets Manager; no keys in code.

## 7. Build vs buy

| Component | Decision | Why |
|-----------|----------|-----|
| Foundation model | **Buy**: Bedrock (Claude) | Stays inside AWS, data not used for training, no GPU operations. Pinned versions. |
| Guardrails (managed filters) | **Buy** as an extra layer | Cheap second layer for advice, PII and injection. Not trusted alone. |
| Vector/keyword index | **Buy** (OpenSearch, or pgvector in the existing Aurora if volume is small) | No reason to build a search engine. |
| Routing, tools, number maths, entitlements, validator, templates, audit, eval harness | **Build** (C#) | This is the business logic and the safety case. It must be deterministic, testable and ours. |
| Agent frameworks, Bedrock Agents / Knowledge Bases | **Not at first** | A fixed pipeline does not need them, and they hide retrieval, ACL filtering and the tool boundary we must control and explain. Revisit as the corpus grows. |

The principle: buy the undifferentiated infrastructure; build what decides who sees what, what numbers say, and what may be answered.

## 8. Assumptions

1. Users are authenticated internal portfolio managers; a manager-to-customer entitlement table exists or can be created.
2. Prices come from a feed with timestamps. The supplied sample prices have none, so the prototype states that answers are not live data.
3. The fee is an **estimate**: 0.8% per year of asset value, charged quarterly. The billing convention (which day's value, average vs snapshot, rounding) is unspecified, so the answer is `value × 0.8% / 4` on a constant value and is never presented as a guaranteed bill.
4. `avgCostUsd` is historical cost and is not used for current value.
5. The document set is small, curated and owned; chunks can be tagged with roles.
6. Bedrock access to a suitable Claude model is approved in the target region.
7. Language: Hebrew and English questions; answers follow the question language.
8. Compliance owns the definition of "advice" and the go/no-go thresholds.

## 9. Three key risks

1. **Advice leakage or an unsafe paraphrase in free text.** Even with gates, a model can rephrase a document or a number into something that reads like a recommendation. *Mitigation:* the model's text is short, placeholder-only and validated; refusal does not depend on the model; adversarial eval set owned with compliance; shadow period; ability to switch the composer off and serve templates only.
2. **Wrong or stale data presented as authoritative** (missing or untimestamped price, stale market review, a billing rule we guessed). *Mitigation:* fail closed on a missing price; show timestamps and "estimate" wording; fee assumptions stated in the answer; data-freshness alarms; owner sign-off on the fee convention before launch.
3. **Cross-customer exposure or silent drift.** A mistake in entitlement or search ACLs exposes one customer's data to a manager without rights; separately, a model or prompt change quietly degrades behaviour. *Mitigation:* entitlement checked before any read and again in retrieval filters; access-denial cases in CI with zero-reads assertions; pinned model versions and a CI eval gate on every change; audit log reviewed.

## 10. Implemented vs designed

- **Implemented in the prototype** (offline unit tests + the 13-case eval): access check, advice gate, router with fallback, retrieval with quarantine, number tools, templates, validator, `FakeModel`. The Anthropic adapter (Haiku) was exercised **live** only in a few small manual calls, not by the automated eval.
- **Demo only:** a local Hebrew/English page (plain HTML). The production front end is React.
- **Designed only, nothing deployed:** Cognito/OIDC, Aurora, Bedrock, Guardrails, OpenSearch/pgvector, embeddings and role-filtered search, S3 ingest, audit store, CloudWatch/X-Ray, CI eval gate.
