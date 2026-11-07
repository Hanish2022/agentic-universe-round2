# Outcome-First Agent Loop — Submission

**Name:** Hanish Bansal · **Date:** 9 Nov 2026 · **Hours actually spent (be honest):** ~6 hours (Fri 6 Nov ~23:35 IST – Sat 7 Nov, build + runs + write-up) · **Language / storage:** Python 3.12 / SQLite (WAL mode), single file per scenario

---

## 0. TL;DR
The controller ingests all call events into its own SQLite store, forms one shared set of cohorts per workflow from pre-D0 history, and runs factorial welcome×voice experiments decided by pooled two-proportion z-tests — the LLM only ever proposes prompt text, statistics decide everything else. All changes go through the real governance path (proposals with honest impact scores and dry runs, auto-apply only where policy allows and only within the shift cap). On public_01 it captured 8% of the overall engagement headroom (23% on nw_renewal) with zero governance conflicts; on public_02 it cut hallucinated calls from 406 to 151 and recovered +0.383 pickup by rotating a flagged caller ID. Deliberately not built: per-person call timing (lead_preferred_hour), a UI, and multi-process scaling — the reasoning is in §2.

## 1. Assumptions
1. The simulator's HTTP API is the only source of truth. Scenario files, `runs/`, and the `sim` package were never read or imported — everything the controller knows (options, governance policy, approver hours, credit budget) comes from API responses at runtime.
2. "History" chunks (negative sim-minutes, pre-D0) are a legitimate baseline: they describe the same population and the same variant effects as the live period, so variant baselines are computed over all data with the measurement window excluded, not just over history.
3. Pickup, engagement and outcome rates are properties of (workflow, dimension, variant, cohort) and are stable enough over a 3-day experiment round for a pooled test to be meaningful; §5 describes the decay watch that exists precisely because this assumption can fail.
4. The approver is a scarce, fatigable resource (per the memos and the 24h caps in policy), so one well-evidenced proposal beats five speculative ones; batching winners into a single proposal per (workflow, dimension) follows from this.
5. A rejected proposal is information about approver judgement, not a bug: rejected setups are retried later on a fresh base version with fresh evidence, never resubmitted identically. An *expired* proposal, per the Product memo, is a rejection for planning purposes — it is re-queued as a new decision, not chased.
6. Credits are a hard budget (200 in the public scenarios). A reserve of 15 credits is never spent on experiments, so an incident response late in the run can always afford suggest-fixes (3) plus a validation run.
7. The hallucination flag is a noisy detector (docs say false positives and negatives exist), so it is only ever acted on as a population rate over hundreds of connected calls, never per call.
8. One controller process per scenario, one SQLite file per scenario (`controller_state/<scenario>.db`). Crash safety comes from the store, not from process supervision.
9. Supervisor edits are legitimate production changes, not attacks: they are observed via `config_changed` events, recorded, and never silently overwritten (§6).

## 2. Scope decisions
| # | Capability | Built / Partial / Cut | Why | What it would take to finish |
|---|---|---|---|---|
| C1 | Event ingestion | Built | Everything else depends on a complete, idempotent event store | — |
| C2 | Shared cohort object | Built | One `CohortSet` class is used by detection, experiments, scheduling and the status view, and is written into config verbatim | — |
| C3 | Bootstrap from pre-D0 history | Built | Baselines and cohorts exist before the first live dial; no cold start | — |
| C4 | Call-time optimisation | Partial: per-cohort `hour_weights` only | Cohort-level timing is supported by cohort-level data (≥2,000 dials, ≥3pp effect required). Per-lead `lead_preferred_hour` was cut: 200k-entry maps built from per-lead samples of a handful of dials each is exactly the "act on anecdotes" failure the README forbids | ~half a day: shrink per-lead hour estimates toward the cohort prior (empirical Bayes) and cap map size by confidence |
| C5 | Caller-ID health | Built | Detect (pooled z, p<0.001, ≥5pp drop, both window halves down), rotate to 10% explore share, restore only on ≥300 post-rotation dials within 2pp of baseline; second offence is permanent | — |
| C6 | Variant experiments (welcome × voice) | Built | Factorial equal-split rounds; pooled test first, per-cohort override only for cohorts ≥15% of leads with their own significant result; max 2 rounds per workflow per scenario | — |
| C7 | Promotion, decay, rollback | Built | Winners batched into one proposal per (workflow, dimension); trailing-24h decay watch rolls a promoted winner back to the previous champion | — |
| C8 | Hallucination incident response | Built | Population threshold → `suggest-fixes` → validation run → propose only if pass_rate ≥ the workflow's own `min_validation_pass_rate`; credit reserve enforced | — |
| C9 | Governance client | Built | Full lifecycle: pending → approved → applied, plus rejected, expired (= re-queue fresh), lapsed (410), stale base (409 → rebuild on fresh base), duplicate proposal (reconcile via GET); 24h-cap guard defers lower-priority kinds | — |
| C10 | Honest impact score & dry run | Built | `impact_score` = expected lift (capped) × affected-lead share; `dry_run` = the proposed allocation re-weighted over *observed* per-variant rates. No invented numbers | — |
| C11 | Operator view | Partial: JSON API, no UI | `GET /status` and `GET /why?workflow=&minute=` on a stdlib HTTP server answer the audit questions; a UI adds no decision quality in scope | 1–2 days for a small read-only web UI over the same endpoints |
| C12 | Audit store | Built | Every decision, proposal, config version and incident is a row; §10 shows the actual "why" query | — |
| C13 | Crash recovery | Built, tested | kill -9 mid-run with approvals in flight; restart resumes from the chunk checkpoint; duplicate audit all zero (§9) | — |
| C14 | Structured logs | Partial: JSON log lines + metrics rows | One JSON line per loop iteration (minute, ingested, credits, decisions/hour) plus a metrics table; no log shipping/alerting plumbing | ~1 day: ship lines to a collector and wire the §10 alerts |
| C15 | Multi-tenant / multi-process scale-out | Cut (noted) | The SRE memo forbids new stateful infrastructure and the scenario scale doesn't need it; §8 shows measured headroom and the partition design instead | See §8: shard by workflow, one writer per shard |

**The principle used to choose:** floor first — the loop must run end-to-end unaided and never break a non-negotiable — then depth on the paths the hidden scenarios most likely stress (governance edge cases, incidents, rollback), and only then breadth. Anything whose data requirements the simulator cannot actually support (per-lead timing) was cut rather than faked.

## 3. Stakeholders

### Memo 01 — CTO
- **Accepted:** the system contract (README + SIMULATOR.md) outranks every memo; where a memo and the live policy disagree, the policy returned by the API wins. This is implemented literally: governance behaviour is driven by the `policy` object fetched per workflow, never by constants copied from memos.
- **Pushed back on:** nothing material.
- **Wrong claims:** none found.
- **Reply:** "Building to the contract as you directed: every governance decision in the controller is driven by the live policy object from the API, not by anything written in the stakeholder memos. Where memos conflicted with policy (auto-apply scope, KYC approvals), policy won and the conflict is documented in my submission. The loop is auditable end-to-end from its own store, and the LLM proposes text only — statistics and the approval path decide what ships."

### Memo 02 — Compliance (Northwind)
- **Accepted:** named human approval for anything customer-facing on Northwind workflows; validation evidence attached to every prompt change (`evidence.validation_run_id` with pass_rate ≥ 0.97); approver hours respected (10:00–19:00, KYC 10:00–18:00) — proposals are only submitted when they can be decided inside the window.
- **Pushed back on:** nothing; the compliance asks and the sim policy agree.
- **Wrong claims:** none — but note the Sales memo (04) claims the opposite of this memo about Northwind KYC auto-apply; compliance is the one that matches policy (see below).
- **Reply:** "Northwind is handled exactly as you specified: no customer-facing change ships without a named human approval, every script change carries a validation run ID at or above the 0.97 pass-rate bar, and nothing is submitted outside approver hours. Auto-apply is disabled for nw_kyc in policy and the controller never attempts it there. Every approval, rejection and expiry is in the audit store with the approver's decision attached."

### Memo 03 — SRE
- **Accepted:** no new stateful infrastructure — the controller's only store is a SQLite file (Postgres/Redis already run at Formi, but the loop doesn't need them at this scale); kill/restart safety proven, not asserted (§9); performance measured on public_03 rather than estimated (§8).
- **Pushed back on:** nothing.
- **Wrong claims:** none found.
- **Reply:** "No new stateful infra: the controller keeps everything in one SQLite file per scenario and can be killed and restarted safely — I tested kill -9 mid-run with approvals in flight and the restart applied them with zero duplicates. Load numbers from public_03 are in the submission (ingest rate, decision lag, peak memory, wall-clock per sim day), all well inside your 10-minute-per-day bar on this hardware."

### Memo 04 — Sales
- **Accepted:** speed matters; where auto-apply is genuinely permitted, the controller uses it (schedule changes on nw_renewal/ks_cancel ship without approver latency).
- **Pushed back on:** the request to treat auto-apply as broadly available. It isn't, and pretending otherwise produces 403s and burned approver goodwill.
- **Wrong claims — two, both verified against live policy:** (1) "Kestrel auto-apply is on for everything" — false: ks_cancel's policy allows auto-apply for schedule/caller_id/welcome_message/voice only, **prompt_version is excluded**, and any per-cohort distribution shift above TV distance 0.2 is rejected. (2) "Northwind is fine with auto-apply on KYC" — false: nw_kyc has auto-apply **disabled entirely**; every change needs the approval path. The controller mirrors the policy's own TV-distance check before attempting any auto-apply, so it never sends a request the policy would reject.
- **Reply:** "I checked both claims against the live policy before building on them: Kestrel's auto-apply excludes prompt_version and caps any shift at 0.2 total variation, and Northwind KYC has auto-apply fully disabled — every KYC change needs a human approval. Where auto-apply is real, we use it and changes ship in minutes. Where it isn't, going around governance would get changes rejected and the account flagged; the approval path with batched, well-evidenced proposals is the fastest route that actually lands."

### Memo 05 — Supervisor (Kestrel)
- **Accepted:** max 2 requests/day to her team in spirit — the controller batches all winners for a (workflow, dimension) into a single proposal and self-limits to ≤2 experiment rounds per workflow; nothing is submitted before 11:00 for ks_cancel beyond the cap the policy itself enforces (3–4/24h); proposals carry summary, diff, dry run and rationale on one screen, as the API requires. Her edits are never undone silently: a supervisor `config_changed` event invalidates any in-flight experiment on the touched dimensions instead of overwriting her change.
- **Pushed back on:** nothing material — her constraints and good governance point the same way.
- **Wrong claims:** none found.
- **Reply:** "Your rules are wired in: Kestrel changes are batched into one proposal per decision, never a drip-feed; every proposal shows its summary, diff, dry-run result and rationale together; and if you edit a config directly, the controller treats your version as the new truth — it invalidates its own in-flight experiment on those settings rather than overwriting you. You'll see at most a couple of requests a day from the system, each with the evidence attached."

### Memo 06 — Product
- **Accepted:** cohorts are one shared object (a single `CohortSet` instance per workflow is the same object in detection, experiments, scheduling and the status view, and is written into config identically); an expired proposal counts as a rejection (it is re-queued as a fresh decision with fresh evidence, not treated as pending forever); only changes that actually ran count as evidence (all rates come from ingested call events, never from proposal metadata).
- **Pushed back on:** nothing.
- **Wrong claims:** none found.
- **Reply:** "All three points are implemented literally: one cohort definition object is shared by every part of the system and written into config as-is; expired proposals are treated as rejections and re-decided with fresh evidence rather than chased; and every number the controller acts on comes from call events it ingested itself — a change that was proposed but never applied contributes nothing to any decision."

## 4. Architecture
```
            ┌──────────────────────── Simulator (HTTP API only) ───────────────────────┐
            │  /events/chunks  /workflows  /approvals  /sim/advance  /llm  /validation │
            └──────▲───────────────▲────────────────▲──────────────────▲───────────────┘
                   │ NDJSON chunks │ config+policy  │ proposals/apply  │ suggest/validate
            ┌──────┴───────────────┴────────────────┴──────────────────┴───────────────┐
            │                          controller (one process)                        │
            │  ingest ──► SQLite store ──► cohorts ──► experiments ──► governance      │
            │     │            │  ▲            │             │               │         │
            │     │            │  └────────────┴── incidents ┴── schedule ───┘         │
            │     │            ▼                                                       │
            │     └────► metrics + JSON log lines        view: /status /why :8799      │
            └──────────────────────────────────────────────────────────────────────────┘
```
- **Components** (all under `controller/`): `client.py` (HTTP, retries only on network/5xx — a 4xx is an answer, not an error), `ingest.py` (two passes per chunk: leads first, then calls), `store.py` (SQLite schema + all queries), `cohorts.py` (the shared CohortSet), `experiments.py`, `governance.py`, `incidents.py`, `schedule_opt.py`, `stats.py`, `view.py`, `main.py` (the loop).
- **State** lives in exactly one place: `controller_state/<scenario>.db` (WAL). Tables: `meta` (chunk checkpoint, sim minute), `leads`, `calls` (event_id primary key), `decisions` (the audit trail), `proposals`, `experiments`, `config_versions`, `incidents`, `metrics`.
- **The loop** per iteration: advance sim 30 min → ingest new chunks → poll/apply proposals → incidents tick → experiments tick → schedule optimisation → metrics row + one JSON log line.
- **On restart** the process reads its checkpoint from `meta`, reconciles in-flight proposals against `GET /approvals` (the sim is the source of truth for approval state; the local row is a cache), and continues. If the stored sim minute is *ahead* of the sim's clock, the world was reset: the old DB is archived to `.bak-<ts>` and a fresh one is bootstrapped — never mixed.

## 5. The learning loop
- **Cohorts**: formed once from pre-D0 history leads as (age_band × language) cells; a cell becomes a named cohort only if it holds ≥5% of the workflow's leads, capped at 5 cohorts, largest first, deterministic tie-break. The 5% floor is the anti-fragmentation rule: below it, a cohort cannot reach the minimum arm sample inside a 3-day round anyway, so naming it would only split traffic and multiply comparisons. Everyone else is `default`. The identical CohortSet object feeds detection, experiments, scheduling and the view.
- **Experiment design**: one factorial round per workflow over welcome_message × voice with equal splits in every cohort. Because the sim samples each dimension independently per dial, the factorial design needs no interaction model to estimate main effects — each dimension's arms are balanced across the other dimension's variants by construction. Exploration is the equal split itself (no bandit): with 3-day rounds and a promotion gate, explore-then-commit is easier to audit than adaptive allocation, and the exploration cost is bounded and visible (see §11 on the nw_kyc setup row). Caller ID and schedule are *not* experimented on; they are handled by incident response (C5) and observational optimisation (C4) respectively, because their failure modes are operational, not preferential.
- **Deciding a winner**: two-proportion z-test, two stages. Stage 1 pools all cohorts for a (workflow, dimension): an arm must beat control with Bonferroni-corrected α=0.05 across the round's family of tests, a minimum effect of 2pp, and ≥300 dials per arm. Stage 2 allows a per-cohort override only for cohorts ≥15% of leads whose own test is independently significant — small cohorts inherit the pooled winner instead of inventing their own. Winners are promoted batched, one proposal per (workflow, dimension). Rounds are capped at 2 per workflow per scenario: run 2 of public_01 showed repeated re-testing inflating false winners and churning approvers (a sequence of ±0.8pp "promotions" that netted ~0). **False-winner rate, measured**: across the graded public_01/public_02 runs, 1 of ~21 promotions was graded harmful in each scenario — roughly 5%, in line with the corrected α plus the 2pp effect floor; §11 names both cases.
- **Decay and rollback**: after a promotion has been live ≥1 day, a trailing-24h z-test compares the winner's current rate against its experiment-period baseline; p<0.05 **and** a drop ≥2pp triggers a rollback proposal restoring the previous champion. This fired once in public_01 run 2 and twice in public_02 — it is the mechanism that bounds how long a false winner can hurt.
- **Call time and caller ID**: call time uses history only at cohort level (C4 partial, §2). Caller ID is treated as infrastructure health, not a preference: per-ID pickup vs its own all-data baseline, with the strict confirmation rules of C5.
- **Guardrail KPI**: pickup and engagement are never blended (separate columns, separate tests, per the non-negotiables). A winner on the primary KPI is only promoted if the guardrail metric for the same arms does not show a significant drop beyond the workflow's own `guardrail` threshold (e.g. pickup_rate_max_drop 0.02); a candidate that wins engagement while significantly damaging pickup is recorded as a decision with reason `guardrail_blocked` and not proposed. Schedule changes (the main pickup lever) are validated against engagement the same way before auto-apply.

## 6. Governance
- **Proposal lifecycle** (state machine in `governance.py`, mirrored in the `proposals` table):
  `draft → pending → approved → applied`, with terminal branches `rejected`, `expired`, `lapsed`, `stale`. Handling per branch: **rejected** — recorded with the approver's reason; the underlying decision may be re-proposed later only with new evidence and a fresh base. **expired** (TTL passed undecided) — treated as a rejection per the Product memo: re-queued fresh, never assumed. **lapsed** (410: approved but not applied inside `apply_window_hours`) — re-proposed as a new proposal; the approval is not treated as transferable. **stale** (409 `stale_base_version`, at submit or at apply) — the change is rebuilt on the current config version and re-proposed; this is also how supervisor edits are absorbed. **duplicate** (409 `duplicate_proposal_id`) — reconciled via `GET /approvals` instead of resubmitted; proposal IDs are deterministic hashes of (workflow, base_version, change), which is what makes crash-restart safe (§9).
- **Batching and timing**: all winners for a (workflow, dimension) ride in one proposal; across kinds, a 24h-cap guard counts the workflow's requests in the trailing 24h from the sim's own approval list and defers lower-priority kinds (experiment setups before promotions before schedule tweaks; prompt fixes for live incidents jump the queue). Submissions are timed so the approver's random latency (30–240 min) lands inside approver hours and the 2h apply window is polled every loop iteration (30 sim-min), so an approval is applied within one iteration of being granted.
- **Auto-apply — when used, when not**: used only when the workflow's policy explicitly lists every changed dimension in `allowed_dims` **and** the controller's own TV-distance computation of the per-cohort shift is ≤ `max_shift` — the same check the sim performs, mirrored so a doomed request is never sent (0 `auto_apply_rejected` across all graded runs). Voluntarily *not* used for: prompt_version anywhere (even where a memo claimed it was allowed), caller-ID restores during an open incident's first hours, and anything on nw_kyc, where policy disables it entirely.
- **Impact score, affected leads, dry run — and their honesty**: `affected_leads` is counted from the ingested lead store for the cohorts the change touches. `dry_run` re-weights the *proposed* allocation over the *observed* per-variant rates from the call store — it is the expected KPI if the observed rates hold, labelled as such. `impact_score` = min(1, expected_lift / 0.10) × affected_share, capped to [0,1]: a big lift on a tiny cohort scores lower than a moderate lift on everyone. These are estimates from the same data the decision used; they are never tuned to make a proposal look better, and when the sample behind a rate is thin the dry run says so in the rationale.
- **Supervisor edits mid-experiment**: `config_changed` events (actor `supervisor`) are logged as decisions. If the edit touches cohorts/welcome/voice, in-flight experiment rows on those dimensions are marked invalidated — the experiment stops claiming evidence from a configuration that no longer exists — and the controller's next change is rebuilt on the supervisor's version. Her config is never overwritten by a stale in-flight proposal: the 409 stale-base path is the backstop, and in public_02 the voice edit at minute 8100 was absorbed with zero conflicts (the run's single apply conflict came from two of the controller's own proposals racing, and the self-heal re-proposal resolved it).

## 7. Incidents
**Detection thresholds.** Caller ID (C5): trailing 12h window per ID; rotation requires ≥200 window dials, ≥200 baseline dials, pooled z-test p<0.001, a drop ≥5pp vs the ID's own baseline, **and** both halves of the window ≥3pp below baseline — the halves rule is what keeps the false-positive rate near zero across the hundreds of (ID × window) checks in a run: a one-window dip essentially never satisfies all five conditions by chance, while a genuinely flagged ID stays down for the whole window. Hallucination (C8): trailing 8h window, ≥200 connected calls, flag rate above max(2× baseline, baseline + 3pp, 2%) — population thresholds only, because the detector itself has false positives.
**Picking a fix.** Caller ID: rotate the suspect to a 10% explore share (enough to judge recovery, small enough to bound harm), others renormalised. Hallucination: `POST /llm/suggest-fixes` (3 credits) → validate *every* candidate at n=500 (5 credits each) → propose only a candidate whose pass_rate ≥ the workflow's `min_validation_pass_rate`, with `evidence.validation_run_id` attached. The LLM's ranking is ignored; the validation number decides.
**Credit spend.** Hard reserve of 15 credits is never touched by anything except incident response. public_02 spent 36 of 200: 2 suggest calls (6) + 6 validation runs (30).
**Verification after applying.** A hallucination incident closes only when the trailing-window flag rate returns to near baseline (observed: 0.045→0.029 and 0.048→0.024 vs baselines ≈0.015). A caller-ID restore now requires ≥300 post-rotation dials within 2pp of baseline (see the failure below).
**Timeline from public_02 (sim minutes, D0 = Mon 04 Jan 2027 00:00 IST):**
| minute | day/time | event |
|---|---|---|
| 2130 | D1 11:30 | Hallucination spike detected on ks_cancel (flags 4.5% of connected vs 1.5% baseline) |
| 2130 | D1 11:30 | suggest-fixes + validation: candidate P3 pass_rate 0.992 ≥ 0.97 → proposal submitted with evidence |
| 2220 | D1 13:00 | Approved and applied (P1 → P3); flag rate back to 2.9% by 2280 — incident resolved, time-to-fix 150 min |
| 3870 | D2 16:30 | Caller ID D2 on ks_cancel degraded (pickup 0.110 vs own baseline 0.249) → rotated to 10%. Grade credits this change **+0.383 pickup** |
| 5010 | D3 11:30 | Supervisor ships a new prompt (P2) on ks_cancel — observed, recorded, not overwritten |
| 5400 | D3 18:00 | Hallucination spike #2 (4.8% vs 1.5%) — the supervisor's prompt is hallucinating |
| 5400–5460 | D3 | suggest → validate (P5, 0.992) → approved → applied in 60 min; resolved by 5910 |
| 7110 | D4 22:30 | Caller ID D1 rotated on a real measured dip — **this one was wrong in hindsight**: it was restored on the old weak bar (100 dials, 95%) and the grade shows −0.465 pickup for the restore. Fix shipped: ≥300 dials within 2pp, second offence permanent (§13) |
| 8100 | D5 15:00 | Supervisor edits nw_renewal voice mid-run — absorbed, no conflict |
| 11550–12270 | D8 | nw_renewal caller ID D1 rotated, genuinely recovered, restored (+0.028, graded beneficial) |

Hallucinated calls, whole run: **151 vs 406 for the no-op baseline.**

## 8. Scale
Measured on public_03_load (12 workflows, 3 tenants) on a 4-vCPU / 7 GB box — the SRE's reference shape. The controller ran the full 5-day scenario unaided via `./run.sh`:

| metric | measured |
|---|---|
| events generated by the scenario | 9,737,015 |
| rows ingested & stored | 9,736,871 (7,432,871 calls + 2,304,000 leads) |
| total wall-clock | 2,725 s for 5 sim days |
| **wall-clock per simulated day** | **545 s ≈ 9.1 min** (SRE bar: <10 min) |
| end-to-end throughput | ≈3,570 events/s sustained (ingest + all decision work) |
| decision lag | one decision cycle per 30 sim-min iteration; mean iteration wall time 11.4 s, so an event influences a decision within ≤2 iterations |
| peak memory (RSS) | 1,009,736 KB ≈ 0.96 GiB of 7 GB |
| store size at end | 2.39 GB SQLite (single file) |
| controller output | 837 decisions, 90 proposals (74 applied, 6 rejected, 4 expired, 6 still pending at scenario end), 0 credits spent |

It also *worked* at that scale, not just survived it: the grade for this run (`reports/public_03.md`) shows 26–57% of the engagement headroom captured per workflow. Honest caveats: 9.1 min/day is inside the bar but without much margin, and the margin shrinks as the calls table grows, because several detection queries aggregate over all data each iteration.

**What breaks first at 10×:** the per-iteration aggregation scans (variant baselines over the full calls table) — cost grows linearly with total events while the sim-day budget doesn't. Fix, in order: (1) incremental rollup tables maintained at ingest time (per workflow/dimension/variant/cohort/hour counters), turning every detection query into a lookup; (2) shard by workflow — state is already partitioned by workflow inside the store and workflows never share decisions, so one process + one SQLite file per workflow (or per tenant) scales linearly and keeps the no-new-infra property per shard; (3) parallelise chunk fetch/parse across shards. The single-file-per-scenario design (C15 cut) is the deliberate constraint that makes (2) a deployment change rather than a rewrite.

## 9. Reliability
- **Crash-recovery test (actually run, evidence in `reports/crash_recovery.md`)**: on public_01 with the shipped build, the controller was killed with `kill -9` at sim-minute 5040 with **5 proposals applied and 2 approvals pending**. The simulator was left running. The controller was restarted with `./run.sh <url>` against the same SQLite store. Result: the run completed unaided; both pending approvals were picked up and applied (9 applied in total); a duplicate audit on the final store showed **0 duplicate proposal_ids, 0 duplicate (workflow, version) config applications, 0 duplicate call event_ids**; the restart log contained no errors. State lost: none — the worst case is re-fetching the single chunk that was mid-ingest when the kill landed, and ingestion is idempotent, so that costs a few seconds, not correctness.
- **Idempotency keys**: proposal IDs are deterministic hashes of (workflow, base_version, change content) — resubmitting after a crash returns the sim's `duplicate_proposal_id`, which the client reconciles via `GET /approvals` instead of treating as failure. Call ingestion uses `INSERT OR IGNORE` on the `event_id` primary key with the chunk number checkpointed in `meta` only after a chunk is fully processed. Applies are guarded by base_version equality on both sides.
- **4xx/5xx behaviour**: the HTTP client retries only network errors and 5xx (bounded, with backoff); every 4xx is returned to the caller as a meaningful answer — 409 stale → rebuild on fresh base, 409 duplicate → reconcile, 410 lapsed → re-propose, 402 out of credits → incident response degrades to "propose nothing, keep watching", 403 auto-apply → fall back to the approval path. No 4xx is ever retried blindly, and every one of them lands in the decisions table.

## 10. Audit & observability
The question *"why did workflow X change at time T, who approved it, and what happened after?"* is answered entirely from the store. Real query (run against the public_02 store):

```sql
SELECT d.sim_minute, d.kind, d.summary
FROM decisions d
WHERE d.workflow_id = 'ks_cancel' AND d.sim_minute BETWEEN 2100 AND 2300
ORDER BY d.sim_minute;
```
Output (abridged summaries):
```
2130  hallucination_detected   flags at 0.045 of connected vs baseline 0.015 (population threshold crossed)
2130  proposal_submitted       Prompt fix P1 -> P3 (validated pass_rate 0.992 >= 0.97; approval evidence attached)
2220  change_applied           approved change applied (approval apr_00006)
2280  hallucination_resolved   flag rate back to 0.029 (baseline 0.015); time-to-fix 150 sim-min
```
Joining `proposals` on the same window gives the approver, the impact score and the dry run that were submitted; joining `config_versions` gives the before/after config; the `metrics` table gives the KPI trajectory after the change. The same data is served live at `GET /why?workflow=ks_cancel&minute=2220` (C11).

**Would page on:** a proposal stuck in `pending` past its TTL without a terminal state; credits below the incident reserve; ingestion checkpoint not advancing while the sim clock advances; a rollback firing (a promoted winner decaying is always worth a human look); guardrail breach on any workflow. **Would not page on:** judgement rejections (normal governance), a single no-winner round, expired proposals that re-queue successfully, or hallucination flags moving within the population threshold (that's detector noise by design).

## 11. Results

### public_01 (final shipped build; this run is also the §9 crash-test run)
| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.346 | +1.2% | 0.242 | +1.0% | 0.502 | +0.4% | -1% | 53 (52) |
| nw_kyc | 0.359 | -4.6% | 0.240 | -1.0% | 0.590 | -3.7% | 0% | 14 (21) |
| nw_renewal | 0.422 | +0.5% | 0.260 | -0.7% | 0.558 | +2.0% | 23% | 51 (39) |
| ALL | 0.374 | -0.3% | 0.248 | -0.0% | 0.539 | +0.0% | 8% | 118 (112) |

11 applied — beneficial: 2, neutral: 8, harmful: 1. Governance: 11 requests, 9 approved / 2 rejected, **0 apply conflicts, 0 auto-apply rejections, 0 lapsed**, peak 2 requests/24h per workflow.

### public_02 (incidents)
| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.209 | -14.2% | 0.159 | -12.7% | 0.476 | +0.9% | 2% | 69 (310) |
| nw_kyc | 0.381 | -0.8% | 0.250 | +1.1% | 0.582 | -2.9% | -20% | 27 (38) |
| nw_renewal | 0.421 | -2.2% | 0.260 | -1.1% | 0.541 | -1.2% | -5% | 55 (58) |
| ALL | 0.316 | -5.8% | 0.212 | -5.0% | 0.528 | -0.4% | -4% | 151 (406) |

20 applied — beneficial: 7, harmful: 4, neutral: 9. Governance: 17 requests, all 17 approved, 1 apply conflict (self-healed), peak 3 requests/24h. Credits used: 36/200 (2 LLM fix calls, 6 validation runs).

### Interpretation — where I helped, where I was harmful
- **Helped, clearly:** nw_renewal engagement (+2.0%, 23% of the available gap) on public_01 across two independent runs; incident response on public_02 — hallucinated calls cut 63% vs baseline, both prompt fixes through the full validation gate, and the flagged caller-ID rotation worth +0.383 pickup on ks_cancel.
- **Harmful, named:** (1) public_01: the nw_renewal v6 welcome promotion (−0.040 engagement) — a measured winner that did not hold out of sample; the 2-round cap and the decay watch are the mitigations, and the decay watch did roll back a sibling case in the earlier run. (2) public_02: the ks_cancel caller-ID restore (−0.465 pickup) — the recovery bar was too weak (100 dials at 95% of baseline) and restored an ID that was still toxic; fixed to ≥300 dials within 2pp with second-offence permanence (§7). This single change is most of ks_cancel's −12.7% pickup. (3) public_02: the second prompt fix (P2→P5, −0.051 engagement) passed the safety gate — validation measures safety, not engagement, so a safe-but-duller prompt can ship; I accept the trade (the alternative was leaving a hallucinating prompt live) and flag it in §13. (4) nw_kyc's −4.6% conclusion on public_01 came with **zero** nw_kyc changes graded harmful — its only applied change was a neutral schedule tweak; the delta is inside this sim's run-to-run noise band (nw_kyc showed the same −4.5% in the public_02 run where even fewer levers moved), and I report it rather than explain it away.
- **Exploration cost is real:** the factorial setup configs themselves grade as changes (nw_kyc v2 on public_02: −0.019) — that is the price of equal-split evidence, bounded by the 3-day round expiry and the 2-round cap.
- **What I'd change first:** the caller-ID recovery rule (done, post-run); second, require a promoted winner's effect to clear a higher bar (3pp) on the *second* round for the same dimension, since repeat testing is where the false winners clustered.

## 12. Trade-offs & rejected alternatives
| Option | Why considered | Why rejected / what instead |
|---|---|---|
| Bandit / Thompson sampling for variants | Faster convergence than fixed equal splits | Rejected: adaptive allocation makes the audit story ("why this share?") and the multiple-comparison control much harder to defend, and promotion still needs a clean test. Equal split + z-test + promotion gate instead |
| LLM picks the winning variant from call summaries | Cheap, uses the suggest endpoint's framing | Rejected outright: violates the statistical/deterministic winner rule. The LLM only proposes prompt *text*; validation pass_rate and z-tests decide |
| Postgres instead of SQLite | Familiar, concurrent writers | Rejected: SRE memo says no new stateful infra; one writer process per scenario makes SQLite strictly simpler and the file *is* the audit artefact. WAL mode + idempotent writes give the needed crash behaviour |
| Per-lead preferred-hour map (C4 full) | The API supports 200k entries; could lift pickup | Cut: per-lead samples are a handful of dials — acting on them is the anecdote failure the README forbids. Cohort-level weights with a 2,000-dial floor instead; the Bayesian-shrinkage version is scoped in §2 |
| Re-propose rejected changes until they pass | Approver judgement is stochastic (base_reject 0.05–0.15) | Rejected: that's gaming the approver and burns the 24h cap. Rejection is recorded; re-proposal needs new evidence |
| Auto-apply everything policy allows, immediately | Lowest latency | Partially rejected: auto-apply is used only after mirroring the sim's own TV-shift check, and never for prompt_version; speed is worthless if the request 403s or ships an unvalidated script |
| One mega-proposal bundling all dimensions | Fewest approver requests | Rejected: a rejection would sink unrelated changes, and the diff stops being reviewable on one screen. One proposal per (workflow, dimension) instead |

## 13. Known weaknesses
1. **Caller-ID recovery was shipped weak and cost real pickup on public_02** (−0.465) before the fix. The stricter bar (≥300 dials, within 2pp, second offence permanent) is coded but, honestly, has only been exercised on the nw_renewal recovery since — it has not yet survived a full hidden-scenario run.
2. **False winners are reduced, not eliminated** (~1 per scenario run). The measured effect of a variant can be real for the experiment window's population mix and still not hold afterwards; decay + rollback bounds the damage to ~a day but does not prevent it.
3. **Prompt fixes optimise safety only.** Validation pass_rate says nothing about engagement; the P2→P5 fix cost 5.1pp engagement on ks_cancel. A post-apply engagement watch on prompt changes (using the C7 decay machinery) is the obvious next step and is not built.
4. **nw_kyc barely improves.** Its levers are the narrowest (2–3 options per dimension, no auto-apply, next-campaign-only changes), so most of its outcome delta is sim noise; the controller correctly refuses to force changes there, but "correctly doing little" and "doing nothing" look similar in its row of the table.
5. **Supervisor-edit invalidation is coarse**: an edit to one dimension invalidates experiment rows for that dimension even if the edit was cosmetic; a finer diff (per-cohort) would preserve more evidence.
6. **Single-process, single-file design** caps throughput at one writer; §8 gives the measured headroom and the sharding answer, but the sharded version is unbuilt (C15 cut).
7. **Schedule optimisation is one-shot per workflow per run** (guarded against the invalid-cohort-key failure of the first run); a conservative choice that leaves possible pickup gains unclaimed on long runs.

## 14. If this went to production at Formi next month
First two weeks, in order:
1. **Shadow mode (days 1–3):** run the controller against production traffic with proposals logged but never submitted; compare its would-be decisions against what human operators actually did.
2. **Wire the §10 alerts** into the real paging path and put `/status` + `/why` behind the team's existing auth; no UI yet.
3. **Credit and cost accounting (days 3–5):** map sim credits to real LLM/validation spend per tenant, set per-tenant reserves and a hard daily cap, and dashboard them.
4. **Approver UX pass (days 5–8):** sit with the actual approvers; the proposal payload (summary, diff, dry run, rationale, evidence) is the product surface they live in — tune it to their one-screen rule before scaling request volume.
5. **Prompt-change engagement watch (days 8–11):** extend the decay/rollback machinery to prompt_version so a safe-but-duller script is caught the same way a decaying variant is (weakness §13.3).
6. **Failure drills (days 11–14):** kill the controller mid-approval in staging, expire a proposal on purpose, and have a supervisor edit config mid-experiment; verify each lands in the audit store the way §6 describes.
7. **Gradual enablement:** one tenant, one workflow, approval-path only; auto-apply enabled per-dimension only after two clean weeks of mirrored TV-check agreement with the platform's own decisions.
