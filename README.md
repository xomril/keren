# Keren: AI portfolio assistant (take-home prototype)

A small, testable prototype of an internal assistant for portfolio managers. It answers questions about one customer's digital-asset portfolio and about internal policy documents, and it refuses to give investment advice.

**The idea in one line:** code decides access and computes every number; the model only classifies the question and, optionally, writes one short sentence that code then checks.

| Deliverable | Where |
|---|---|
| Part A: architecture diagram and document | [docs/architecture.svg](docs/architecture.svg), [docs/architecture.md](docs/architecture.md) |
| Part B: prototype, eval | `keren/`, `evals/`, `tests/` |
| Part C: delivery and management answers | [docs/part-c.md](docs/part-c.md) |

## Setup

Python 3.9+. The offline mode needs no packages and no API key.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # only needed for --live (anthropic SDK)
```

## Run

Offline by default: a fake model, no network, no cost.

```bash
.venv/bin/python -m keren C-1042 "What is the current value of C-1042's portfolio?"
.venv/bin/python -m keren C-1042 "Should the client buy ETH now?"
.venv/bin/python -m keren C-1042 "מה נאמר בסקירת השוק האחרונה על ETH?"
.venv/bin/python -m keren C-1042 "How much management fee next quarter?" --json
```

Exit codes: `0` answered or refused, `3` access denied, `4` error (for example a missing price).

Optional local chat page (Hebrew, right-to-left; plain HTML served by the standard library on 127.0.0.1 only):

```bash
.venv/bin/python -m keren.web          # then open http://127.0.0.1:8000
```

### Live mode (paid, optional)

`--live` calls the Anthropic API (default model `claude-haiku-5-5`, override with `KEREN_MODEL`). It costs money, so it is never used by tests or the eval. Put the key in a local `.env` file (copy `.env.example`); `.env` is git-ignored and is never printed or committed.

```bash
.venv/bin/python -m keren C-1042 "What is the current value?" --live
.venv/bin/python -m keren.web --live   # capped at 50 questions per server run
```

## Tests and eval

```bash
.venv/bin/python -m unittest              # 34 unit tests, offline
.venv/bin/python evals/run_eval.py        # 13 eval cases, offline; exit code 1 if any case fails
```

The eval has the 7 mandatory questions (value, BTC exposure vs policy, next-quarter fee, "buy ETH now?", ETH market review, an unauthorized customer, prompt injection in the question), 2 original cases (a **missing price**, and a **prompt injection inside a retrieved document**) and 4 extras (Hebrew variants, another customer named in the text, model outage). Each case prints PASS/FAIL with the reason and the run ends with a score. Expected values come from the assignment text, not from the code. Checks are deterministic (status, exact numbers, required and forbidden text, cited sources, and counters proving no model call and no data read on refusals and denials). No LLM judge.

## What it does

Pipeline, in order (see `keren/app.py`):

1. **Access** before any data is touched. Customer IDs written inside the question are checked too. Unknown, unauthorized and malformed IDs get the same denial.
2. **Advice gate** (rules, before any model call). Buy/sell/personal-advice requests, including injected ones, get a fixed refusal citing the recommendation policy (KB-003) and a referral to a licensed adviser.
3. **Intent router**: the model returns JSON only and never sees or picks the customer ID. If it fails, a rule router takes over.
4. **Retrieval** over all four documents with source IDs (`KB-001#1`). A document containing instruction-like text is quarantined whole.
5. **Tools** `get_portfolio`, `get_prices`; value, exposure and fee are computed in code with `Decimal`.
6. **Templates** (Hebrew or English, following the question).
7. **Optional model sentence**, kept only if the validator passes it: placeholders only, every number is a tool value, every source ID was retrieved, no advice wording, at most 400 characters. Otherwise the template answer stands.

Reference results: total **$104,510.00** (BTC $53,550, ETH $35,960, USDC $15,000); BTC exposure **51.2391%** (limit 60%, no breach); quarterly fee **$209.02**.

## Key decisions

- **Numbers never come from the model.** The fee is shown only as an *estimate* (0.8% / 4 on a constant value). The billing convention is unspecified, so it is never presented as a guaranteed bill.
- **Fail closed.** A missing price returns an error naming the asset, not a partial total.
- **No tools handed to the model.** It cannot pick arguments, so injection cannot redirect a data read.
- **Offline fake model by default**, so tests are free and repeatable. The fake reuses the rule router, so it proves the gates and the numbers, not the real model's behaviour.
- **Model adapter kept thin**: configurable model, explicit timeout, limited retries, thinking disabled, truncated output treated as failure, key from the environment only.
- **Language: Python** (allowed by the assignment). The production design is .NET Core, as the environment requires.
- Facts used as stated: `avgCostUsd` is historical cost and is not used for value; holdings are dated 2026-09-30; the sample prices carry no timestamp, so answers say they are not live data.

## Implemented vs designed, offline vs live

| | Status |
|---|---|
| Access check, advice gate, router with fallback, retrieval with quarantine, tools, templates, validator, fake model, CLI, eval | **Implemented**, tested **offline** (34 unit tests, 13 eval cases) |
| Anthropic adapter (Haiku) and its prompts | **Implemented**; **live-tested only manually**, with a few small calls (router, short summary, UI check). **Not** covered by the automated eval |
| Local Hebrew chat page | **Implemented** for demonstration. It is plain HTML, not the React front end. The assignment brief did not ask for a UI |
| Cognito/OIDC, Aurora, Bedrock and Guardrails, OpenSearch/pgvector, S3 ingest, audit store, CloudWatch/X-Ray, CI gate | **Designed only** (Part A). Nothing deployed |

## Known gaps and what production needs

- **Auth is a demo.** Access grants are hardcoded (`demo-pm` → `C-1042`). Production: OIDC/JWT and a server-side entitlement table.
- **Retrieval is lexical** (character trigrams plus keywords) over four documents. Production: hybrid keyword and vector search with role filters in the query.
- **The advice detector is rule-based.** It is biased to refuse but can miss paraphrases and other languages. The model flag and the output validator are extra layers, not guarantees.
- **The validator is strict.** It rejects correct prose that rounds a number; the answer is then the plain template.
- **Data is static fixtures.** No price feed, no timestamps, no database.
- **No real observability, audit log, rate limiting or deployment.** The web page has basic local safeguards only (127.0.0.1, Host/Origin checks, size limit, live-call cap, no question logging).
- **The eval is small and offline.** Passing it does not prove production safety.

## How AI was used (honest disclosure)

- **Built with Claude Code** (Anthropic's coding assistant, run in the Claude desktop app). I used it to plan the work in milestones, write most of the code, tests, eval, diagram and documents, and to review its own output. I approved each milestone, chose the scope, and ran the tests and the demo.
- **At runtime** the optional live mode uses Claude Haiku via the Anthropic API for routing and one short sentence. The default offline mode uses no model.
- The Part C answers are written from positions I chose when asked; they are plans, not claims about past experience.
- The code and numbers were verified by running the tests and the eval, and by checking the reference values above. I have not independently audited every line.

## Time spent

> **TO FILL IN BY THE AUTHOR.** Actual time per part, as the assignment asks. Not estimated here on purpose.
>
> - Part A (architecture): ___
> - Part B (prototype and eval): ___
> - Part C (management answers): ___
> - Total: ___
>
> If the time limit was exceeded, say what was left undone.
