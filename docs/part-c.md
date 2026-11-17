# Part C: Delivery and management

Draft written from the stances chosen by the author. Everything here is a plan or a position, not a claim about past experience. Edit the wording so it sounds like you; if you have real examples from your own work, add them.

## 1. The first 90 days

**Principle: safety and evaluation first.** The team is four .NET developers with no AI-product experience, so the first risk is not the model, it is that nobody can yet tell whether the system is right.

- **Days 1-30, foundations.** Shared vocabulary (RAG, guardrails, eval, prompt injection) through short working sessions on the prototype, not lectures. Agree with compliance on what "advice" means and who signs off. Build the golden set (the 13-case set is the seed) and the CI gate. Ship the deterministic parts first: entitlements, tools, number maths, templates.
- **Days 31-60, pilot in shadow.** Add retrieval and the model behind the validator. A few portfolio managers use it while a person checks every answer. Each miss becomes a test case. Add observability and the audit log.
- **Days 61-90, limited rollout.** Pilot with a small group of managers, internal only, with the composer switchable off. Review weekly. Run a red-team session with compliance.

**Day-90 success, stated up front:**
- The eval gate runs on every change and is green; numbers 100% correct on the set, zero advice leaks, zero cross-customer reads on denial cases.
- Managers use it for real questions and the thumbs-down rate is tracked and falling.
- At least two team members can explain and extend the pipeline without me.
- A written go/no-go for client-facing use exists, with thresholds agreed by compliance.

**What I would not promise:** a client-facing launch or free-form answers. **How the team knows:** a one-page weekly status with the eval results and the open risks, not a feeling.

## 2. Production failure: a manager sees a wrong portfolio value

**Contain first, then investigate.**

**First hour.** Switch the assistant to templates-only or off through a flag (the composer is already optional by design). Preserve the audit records. The model does not produce numbers, so a wrong one comes from the data or the code.

**Who saw it?** The assistant is internal-only in this phase, so the first question is whether the wrong value stayed with the manager or reached a **client**. Ask the manager directly, and use the audit log to see every answer served from the same data and time window. If a client may have received a wrong value, that is a different severity: inform the business owner and compliance the same day, and let them decide on contacting the client. Internal-only limits the damage; it does not remove the duty to check.

**First 24 hours.**
1. Reproduce with the exact customer, time and inputs. Check the price feed and portfolio data first (stale or missing price, wrong snapshot), then the code, then the validator.
2. Find every other answer produced under the same cause; correct them.
3. Fix, and add a regression case to the golden set before re-enabling.
4. Re-enable behind the flag for a small group; confirm.

**Communication.** A short factual message: what happened, what was affected, what we did, next update time.

**What changes afterwards.** A blameless post-mortem within a week: root cause, why it was not caught, and the control we add (for example: freshness check that fails closed, a data contract test with the price provider, a canary question in production, an alarm). The test case stays forever.

## 3. Sales pressure: clients within a month

**I would not say a flat no, and I would not ship below the bar.** I would offer a narrower path that gives the CEO something real.

**The conversation.** Start from what the CEO needs (a credible client story, a competitive date), not from my objection. Then show the risk in terms they care about: a wrong number or advice-like sentence shown to a client is a regulatory and reputational event for a financial firm, and the eval threshold exists to prevent exactly that. Use the numbers: current eval results, what is not yet tested, what has not been reviewed by compliance.

**What I would offer in a month** (each a decision for the CEO and compliance, not for me alone):
- A supervised demo with a manager present, on sample data, with the assistant answering only the deterministic questions (value, exposure, fee estimate) from templates. These are the parts we can verify fully.
- Free-text answers and document questions stay internal until the thresholds are met.
- A dated plan to reach the client-facing bar, with the measurable gates.

**Where I hold the line.** No client-facing release before the agreed go/no-go is met, and I would write that down. If management decides to override, I ask for the decision in writing from the accountable owner, and I record the residual risk rather than quietly accept it.

## 4. Code written with AI

AI-written code is welcome and treated like code from any new teammate: useful, fast, and not trusted by default. Rules, and why:

- **Human review on every change.** The author must be able to explain it line by line. Why: the person who merges owns the code, and the failure mode of generated code is plausible but wrong.
- **Tests before merge.** Tests are written or reviewed by a human, and the money, access and refusal paths need explicit tests. Why: a model will happily write a test that passes on its own bug.
- **Security scan and secrets hygiene.** Dependency and static scanning in CI; no secrets, customer data or real portfolio data in prompts or in the repo. Why: assistants add dependencies and copy patterns without checking them.
- **Disclose AI use in the PR.** Mark what was AI-assisted; high-risk areas (access checks, number maths, validator, guardrails) get a second reviewer. Why: reviewers should know where to look hardest, and it keeps us honest.

**Process.** The golden set and the CI gate protect against AI changes the same way as human ones. I would revisit the rules after a quarter based on defects found in review.
