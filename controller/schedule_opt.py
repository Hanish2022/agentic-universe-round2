"""C4 (partial) — per-cohort call-time optimisation.

What we do: from observed pickup by hour (history + live, per cohort), set
schedule.hour_weights so the dialler prefers hours where a cohort actually
picks up. Weights are relative; every hour inside the dialling window gets a
weight (an omitted hour means weight 0 — the dialler would never call then),
floored so no hour is starved entirely.

What we deliberately do NOT do: schedule.lead_preferred_hour per person.
With ~200k people that is a giant lookup built on a handful of observations
per person — noise dressed as personalisation (see SUBMISSION §2). Per-cohort
schedules aggregate thousands of dials per cell, which is measurable.

Acts once per workflow, after at least a day of live data exists to confirm
the history pattern, and only if the hour effect is real (>= 3 points between
best and worst well-sampled hours).
"""
from .governance import auto_apply_permitted

MIN_CELL_DIALS = 100
MIN_TOTAL_DIALS = 2000
MIN_HOUR_EFFECT = 0.03


def maybe_optimise(client, store, gov, wf, cohortset, minute, ts):
    wid = wf["workflow_id"]
    if store.get_meta(f"sched_done:{wid}"):
        return
    if minute < 1440:
        return
    version, cur = gov.current(wid)
    new_schedule = {}
    changed = False
    lo, hi = wf["dialling_window"]
    # hour_weights keys must be cohorts DEFINED in the live config (plus the
    # residual "default") — the simulator rejects anything else.
    defined = {c["id"] for c in cur.get("cohorts", [])} | {"default"}
    for cid in [c for c in cohortset.ids if c in defined]:
        hours = store.hour_stats(wid, cohort_id=cid)
        total = sum(h["dials"] for h in hours.values())
        if total < MIN_TOTAL_DIALS:
            continue
        sampled = {h: v for h, v in hours.items()
                   if lo <= h < hi and v["dials"] >= MIN_CELL_DIALS}
        if len(sampled) < 3:
            continue
        rates = {h: v["connected"] / v["dials"] for h, v in sampled.items()}
        if max(rates.values()) - min(rates.values()) < MIN_HOUR_EFFECT:
            continue
        mean = sum(rates.values()) / len(rates)
        table = {}
        for h in range(lo, hi):
            r = rates.get(h, mean)
            table[str(h)] = round(max(0.3, r / mean), 2)  # floor: never starve an hour
        new_schedule[cid] = table
        changed = True
    if not changed:
        store.set_meta(f"sched_done:{wid}", "no_effect")
        return
    import copy
    new = copy.deepcopy(cur)
    new.setdefault("schedule", {})["hour_weights"] = new_schedule
    summary = ("Per-cohort call-time weights from observed pickup by hour"
               f" (cohorts: {', '.join(new_schedule)})")
    ok, _ = auto_apply_permitted(wf, cur, new)
    if ok:
        res = gov.auto_apply(wf, version, new, summary, minute, ts)
    else:
        res = gov.submit(wf, version, new, "schedule", summary,
                         {"schedule.hour_weights": new_schedule},
                         store.cohort_lead_count(wid, "default"),
                         {"basis": "observed pickup by hour per cohort"}, 0.4,
                         summary, minute, ts)
    # One attempt per workflow per run, whatever the outcome — a rejected or
    # deferred schedule change is not worth burning approver attention daily.
    store.set_meta(f"sched_done:{wid}", res["status"])
    if res["status"] in ("pending", "applied"):
        store.log_decision(minute, ts, wid, "schedule_optimised", summary,
                           {"cohorts": list(new_schedule)})
