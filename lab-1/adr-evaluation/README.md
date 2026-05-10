# DevOps Helper Bot — ADR Review

Review of the S&T DevOps Helper Bot architecture against ADR practice. Inputs were the high-level architecture HTML and the one-page component diagram. No formal ADR markdown, threat model, runbooks, deployment manifests, or evaluation results were supplied, so anything in those areas is treated as unspecified rather than absent.


## What was supplied vs. what an ADR needs

The HTML is a competent architecture description: ingestion flow, inference flow, integrations. The PDF file repeats the same topology.

What is missing is the ADR substance — decision drivers, alternatives considered, tradeoffs accepted, status, owner. Everything else either reinforces it or names a specific commitment the missing ADR set should make.

## What is working — preserve these

- Slack-native UX with no public ingress. Socket Mode is the right default for an internal tool.
- One Go binary with separated internal packages (`internal/{slack,rag,claude,knowledge,docs,embedding,vectordb,gitlab,argocd}`).
- Two knowledge collections (`solutions`, `docs`) with payload schemas that already carry the fields needed to operate: `import_id`, `source_url`, `saved_by`, `source_channel`, `created_at`.
- Read-only scopes on GitLab (`read_api`) and Argo CD. Keep them.
- Built-in `web_search` / `web_fetch` constrained by an allowed-domains allowlist and max-uses cap. The kind of guardrail that often gets cut under deadline pressure; it is already in place.

## Issues that should block ADR acceptance

### 1. Credentials and external API surface

Acceptable today, fragile at scale. The ADR should commit to:

- Slack token rotation enabled; app-level (`xapp`) and bot (`xoxb`) tokens tracked separately.
- GitLab access via project or group access tokens scoped `read_api`, not user-bound PATs. PATs leave when the user does.
- Argo CD tokens scoped to `role:readonly` with explicit expiry and a documented rotation cadence.
- Google Cloud auth via Workload Identity Federation or ADC-based impersonation in preference to long-lived SA-key-as-base64.

The current architecture allows SA key via base64. That should be recorded as a fallback with an exit criterion ("remove once WIF is available"), not as an equal option.

### 2. Per-request observability is missing

For every inference, log: query text, retrieved chunk IDs and scores from both collections, tool calls and arguments, model version, prompt-template hash, tool-iteration count, latency breakdown, final answer, whether the response used RAG / fallback / knowledge-capture.

Without this, none of the recommendations below are measurable. You cannot calibrate a threshold against retrievals you did not record. You cannot debug a regression you cannot replay.

## Issues to address but not block on

### 3. RAG threshold of 0.70 is uncalibrated

How was 0.70 selected? With which embedding model? Against what target precision/recall? If the honest answer is "we tried it and it seemed fine," the ADR cannot claim the threshold is a decision.

### 4. Single-pod / single-socket availability ceiling

Slack Socket Mode supports up to 10 concurrent connections per app, specifically so two replicas can run active-active. The single-pod choice is defensible for v1; it should be recorded with explicit exit criteria — for example, scale to two pods when monthly question volume crosses 200, or when on-call rotation begins to depend on the bot, whichever comes first.

Do not conflate Socket Mode (fine) with single-pod (a v1 tradeoff). The HTML diagram strip mixes them.

### 5. `/doc add` has no deduplication

Without `import_id` or a content hash, every `/doc add` produces a new point even if the text is identical to existing content. Over a year this collection drifts toward noise and tanks retrieval precision for the docs it was supposed to improve. Add a source hash on insert; collapse duplicates on conflict.

### 6. Compressor is a hidden Claude dependency in ingestion

`/save` invokes Claude to compress threads into JSON before embedding. A Claude outage therefore breaks not only answering but also knowledge capture. A change to the compressor prompt silently shifts what gets embedded into `solutions`. Version the compressor prompt, log inputs and outputs for spot-checking, and decide explicitly whether `/save` should fail closed or queue when Claude is unavailable.

### 7. Embedding model migration is not planned

`gemini-embedding-001` will be deprecated. Commit to the migration pattern now: two named vectors side-by-side in Qdrant, dual-write during cutover, validate on the eval set, drop the old vector. Ad-hoc reindexing under a deprecation deadline is how teams accept months of degraded retrieval.

### 8. No evaluation harness

A small golden-question set across the use cases the bot is built for: pipeline failures, deployment status, Argo app diagnosis, MR inspection, docs lookup, known-solution retrieval. Track retrieval hit rate, grounded-answer rate, unsupported-claim rate, tool-call success rate, fallback rate. Run on every prompt change and every embedding-model change.

Mix in adversarial cases: instructions injected inside fetched logs, Markdown, and web content. RAG does not eliminate prompt injection — retrieved content is untrusted input.

### 9. Cost and latency are unbounded

One question can produce a query embedding, two vector searches, up to five Claude tool iterations, plus optional `web_search` / `web_fetch`. No per-user, per-channel, or daily budget is documented. One chatty channel can move the cost line. Add a per-channel rate limit and a daily token-cost ceiling with a circuit breaker that degrades to "RAG-only, no tool loop" when exceeded.

## What an ADR should look like

A worked example for the runtime-topology decision. ~250 words; the other three follow the same shape.

```
ADR-001: Slack Socket Mode and single-pod runtime topology
Status: Proposed (2026-05-10)
Owner: <name>
Reviewer: <name>

Context
The bot runs inside our Slack workspace with no public ingress. Operations
team capacity is limited; we want one binary, not a service mesh. Target:
< 8s p95 latency from @mention to first response.

Decision
Single Go binary, Slack Socket Mode, deployed as one Kubernetes pod with
one Socket Mode connection. Restart on deploy.

Drivers
- No public HTTPS endpoint (security posture).
- Operational simplicity (team capacity).
- Slack-native UX (user adoption).

Alternatives considered
- Slack Events API over public HTTPS with a CDN front. Rejected: requires a
  public endpoint, request-signing infrastructure, and an inbound firewall
  exception for marginal latency benefit.
- Two-pod active-active, both holding Socket Mode connections (Slack
  supports up to 10 concurrent). Rejected for v1 only — see exit criteria.

Consequences
- Every deploy interrupts service for ~15s.
- Pod failure means bot down until Kubernetes reschedules.
- No canary releases possible.
- Slack-initiated reconnect is a planned-downtime event for the user.

Exit criteria — revisit when any of:
- SLO of < 1 user-visible outage / month is broken twice in a quarter.
- Question volume crosses 200 / month.
- On-call rotation begins to rely on the bot.
```

## Risks worth blocking on, ranked

| # | Risk | Why it ranks here |
|---|------|-------------------|
| 1 | Sensitive content (Slack threads, GitLab job logs, internal docs) leaving for external model APIs without redaction or classification | Highest blast radius; once embedded in a vector store, recovery is messy |
| 2 | Heading-only chunking truncates on documents most relevant to operations | High likelihood, hits the bot's primary use case, fix is cheap |
| 3 | Delete-then-rebuild docs ingestion can permanently lose knowledge on partial failure | First failed import will demonstrate this; alias-swap fix exists today |

Cost ceilings, observability, and the eval harness are urgent in the operational sense, but they do not justify blocking acceptance — they justify blocking *production rollout*.
