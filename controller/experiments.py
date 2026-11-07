"""C6 — variant experiments, C7 — promotion, decay detection, rollback.

Design (written to be defended, not to be clever):
- One round per workflow tests welcome_message and voice SIMULTANEOUSLY with a
  factorial split: the simulator samples the two dimensions independently, so
  each dimension's marginal effect is estimable from the same traffic.
- Decisions are two-stage. Stage 1 pools all cohorts per (workflow, dim):
  most traffic lives in few cells, and pooling is where the statistical power
  is. Stage 2 lets a LARGE cohort (>= 15% of leads) override the pooled answer
  only on its own significant evidence — cohort-specific truth exists (that is
  why cohorts are in the config), but a small cell may not veto the pool on
  noise. Winner selection is stats.decide_winner: deterministic z-tests,
  Bonferroni over the round's family, min sample, min practical effect.
- Winners are promoted batched: one proposal per (workflow, dim) covering
  every cohort. A decided winner is re-proposed until the config actually
  reflects it (approvals get rejected, bases go stale — the decision stands,
  the paperwork retries).
- A round that finds no winner reverts that dimension to the control at 100%:
  "no significant difference" is a result; split traffic forever hides it.
- After promotion the winner is watched daily against its experiment-era
  baseline; a significant decay rolls back to the previous champion. Decayed
  variants are not retested in the same run.
"""
import copy
import json

from . import stats
from .governance import changed_dims, auto_apply_permitted, dry_run, impact_score

DIMS = ("welcome_message", "voice")
ROUND_MAX_MINUTES = 3 * 1440   # a round gets at most 3 sim days to decide
BIG_COHORT_SHARE = 0.15        # stage-2 override needs a cohort this large


def _kpi_pair(primary: str, agg: dict):
    """(successes, trials) for the primary KPI from a variant_stats row."""
    if primary == "engagement_rate":
        return agg["engaged"], agg["connected"]
    return agg["connected"], agg["dials"]


def _guardrail_pair(primary: str, agg: dict):
    if primary == "engagement_rate":
        return agg["connected"], agg["dials"]
    return agg["engaged"], agg["connected"]


def _guardrail_limit(wf: dict) -> float:
    g = wf["objective"]["guardrail"]
    return g.get("pickup_rate_max_drop", g.get("engagement_rate_max_drop", 0.02))


def _arm_list(wf, vstats, control, arms):
    out = []
    for name in [control] + [x for x in arms if x != control]:
        agg = vstats.get(name, {"dials": 0, "connected": 0, "engaged": 0})
        k, n = _kpi_pair(wf["objective"]["primary"], agg)
        out.append({"name": name, "k": k, "n": n, "agg": agg})
    return out


class Experiments:
    def __init__(self, client, store, gov):
        self.c, self.s, self.g = client, store, gov

    # -- round setup ---------------------------------------------------------
    def start_round(self, wf, cohortset, minute, ts):
        wid = wf["workflow_id"]
        version, cur = self.g.current(wid)
        new = copy.deepcopy(cur)
        if not new.get("cohorts"):
            new["cohorts"] = cohortset.config_cohorts()
        cohort_ids = ["default"] + [c["id"] for c in new["cohorts"]]
        for dim in DIMS:
            split = {o: 1.0 for o in wf["options"][dim]}
            for cid in cohort_ids:
                new.setdefault("allocations", {}).setdefault(cid, {})[dim] = dict(split)
        summary = (f"Start welcome x voice experiment (equal split on"
                   f" {', '.join(wf['options']['welcome_message'])} x"
                   f" {', '.join(wf['options']['voice'])}, all cohorts)")
        res = self._change(wf, version, cur, new, "experiment_setup", summary,
                           {"allocations": "factorial equal split on welcome_message and voice"},
                           minute, ts)
        if res["status"] in ("pending", "applied"):
            started = minute if res["status"] == "applied" else None
            for cid in cohort_ids:
                for dim in DIMS:
                    control = (cur.get("allocations", {}).get(cid, {})
                               .get(dim) or cur["allocations"]["default"][dim])
                    control = max(control, key=control.get)
                    self.s.db.execute(
                        "INSERT INTO experiments (workflow_id, cohort_id, dim, control,"
                        " arms, status, started_minute, pre_config) VALUES (?,?,?,?,?,?,?,?)",
                        (wid, cid, dim, control, json.dumps(wf["options"][dim]),
                         "running" if started else "proposed", started,
                         json.dumps(cur)))
            self.s.commit()
            self.s.log_decision(minute, ts, wid, "experiment_started", summary,
                                {"cohorts": cohort_ids, "dims": list(DIMS)})
        return res

    def _change(self, wf, version, cur, new, kind, summary, diff, minute, ts,
                evidence=None, impact=None, dry=None):
        """Route one config change: auto-apply if policy permits, else approval.
        One open proposal per workflow at a time (except incident prompt
        fixes): parallel proposals stale each other's base at apply time."""
        wid = wf["workflow_id"]
        ok, _reasons = auto_apply_permitted(wf, cur, new)
        if ok:
            return self.g.auto_apply(wf, version, new, summary, minute, ts)
        if self.g.open_proposals(wid) > 0:
            return {"status": "deferred_open"}
        if impact is None:
            impact, dry = 0.3, {"note": "config change; see rationale"}
        affected = self.s.cohort_lead_count(wid, "default")
        return self.g.submit(wf, version, new, kind, summary, diff, affected,
                             dry, impact, summary, minute, ts, evidence=evidence)

    # -- per-tick work ---------------------------------------------------------
    def tick(self, wf, cohortset, minute, ts):
        wid = wf["workflow_id"]
        self._activate(wid, minute)
        rows = self.s.db.execute(
            "SELECT id, cohort_id, dim, control, arms, started_minute"
            " FROM experiments WHERE workflow_id=? AND status='running'", (wid,)).fetchall()
        if rows:
            started = min(r[5] for r in rows)
            family = sum(len(json.loads(r[4])) - 1 for r in rows)
            for dim in DIMS:
                dim_rows = [r for r in rows if r[2] == dim]
                if not dim_rows:
                    continue
                control = dim_rows[0][3]
                arms = json.loads(dim_rows[0][4])
                pooled = _arm_list(wf, self.s.variant_stats(wid, dim, since_minute=started),
                                   control, arms)
                winner = stats.decide_winner(pooled, family)
                if winner and self._guardrail_ok(wf, pooled, winner):
                    for r in dim_rows:
                        self._mark_won(wf, r, winner, pooled, minute, ts, pooled_win=True)
                else:
                    # stage 2: a big cohort may still carry its own winner
                    for r in dim_rows:
                        cid = r[1]
                        if self._cohort_share(wid, cid) < BIG_COHORT_SHARE:
                            continue
                        own = _arm_list(wf, self.s.variant_stats(
                            wid, dim, since_minute=r[5], cohort_id=cid), r[3],
                            json.loads(r[4]))
                        w2 = stats.decide_winner(own, family)
                        if w2 and self._guardrail_ok(wf, own, w2):
                            self._mark_won(wf, r, w2, own, minute, ts, pooled_win=False)
            # round expiry for anything still undecided
            for r in rows:
                if minute - r[5] >= ROUND_MAX_MINUTES:
                    cur_status = self.s.db.execute(
                        "SELECT status FROM experiments WHERE id=?", (r[0],)).fetchone()[0]
                    if cur_status == "running":
                        self._expire(wf, r, minute, ts)
        self._ensure_promoted(wf, minute, ts)
        self._decay_watch(wf, minute, ts)

    def _activate(self, wid, minute):
        pend = self.s.db.execute(
            "SELECT COUNT(*) FROM experiments WHERE workflow_id=? AND status='proposed'",
            (wid,)).fetchone()[0]
        if not pend:
            return
        applied = self.s.db.execute(
            "SELECT COUNT(*) FROM proposals WHERE workflow_id=? AND kind='experiment_setup'"
            " AND status='applied'", (wid,)).fetchone()[0]
        if applied:
            self.s.db.execute(
                "UPDATE experiments SET status='running', started_minute=?"
                " WHERE workflow_id=? AND status='proposed'", (minute, wid))
            self.s.commit()

    def _guardrail_ok(self, wf, arm_list, winner):
        control = arm_list[0]
        ck, cn = _guardrail_pair(wf["objective"]["primary"], control["agg"])
        wk, wn = _guardrail_pair(wf["objective"]["primary"], winner["agg"])
        if cn < stats.MIN_ARM_SAMPLE or wn < stats.MIN_ARM_SAMPLE:
            return False
        return (wk / wn) >= (ck / cn) - _guardrail_limit(wf)

    def _mark_won(self, wf, row, winner, arm_list, minute, ts, pooled_win):
        eid, cid, dim, control = row[0], row[1], row[2], row[3]
        base = {a["name"]: a for a in arm_list}
        bk, bn = _kpi_pair(wf["objective"]["primary"], base[control]["agg"])
        wk, wn = _kpi_pair(wf["objective"]["primary"], winner["agg"])
        note = {"baseline_k": wk, "baseline_n": wn, "rollback_to": control,
                "pooled": pooled_win, "control_rate": bk / bn if bn else None,
                "winner_rate": wk / wn if wn else None}
        self.s.db.execute(
            "UPDATE experiments SET status='won', winner=?, decided_minute=?, note=?"
            " WHERE id=?", (winner["name"], minute, json.dumps(note), eid))
        self.s.commit()
        self.s.log_decision(minute, ts, wf["workflow_id"], "experiment_winner",
                            f"{dim} cohort {cid}: {winner['name']} beats {control}"
                            f" ({note['winner_rate']:.3f} vs {note['control_rate']:.3f},"
                            f" {'pooled' if pooled_win else 'cohort'} evidence)",
                            {"experiment_id": eid})

    def _ensure_promoted(self, wf, minute, ts):
        """Re-propose decided winners until the live config reflects them."""
        wid = wf["workflow_id"]
        won = self.s.db.execute(
            "SELECT id, cohort_id, dim, winner FROM experiments WHERE workflow_id=?"
            " AND status='won'", (wid,)).fetchall()
        if not won:
            return
        version, cur = self.g.current(wid)
        new = copy.deepcopy(cur)
        summaries, notes = [], {}
        for eid, cid, dim, winner in won:
            cur_alloc = cur.get("allocations", {}).get(cid, {}).get(dim) or \
                cur["allocations"]["default"][dim]
            if set(cur_alloc) == {winner}:
                self._finalise_promotion(eid, minute)
                continue
            new.setdefault("allocations", {}).setdefault(cid, {})[dim] = {winner: 1.0}
            summaries.append(f"{dim}={winner} (cohort {cid})")
            notes[eid] = True
        if not summaries:
            return
        summary = "Promote experiment winners: " + "; ".join(summaries)
        res = self._change(wf, version, cur, new, "promotion", summary,
                           {"promotions": summaries}, minute, ts)
        if res["status"] == "applied":
            for eid in notes:
                self._finalise_promotion(eid, minute)

    def _finalise_promotion(self, eid, minute):
        row = self.s.db.execute(
            "SELECT note FROM experiments WHERE id=?", (eid,)).fetchone()
        note = json.loads(row[0] or "{}")
        note["promoted_minute"] = minute
        self.s.db.execute(
            "UPDATE experiments SET status='promoted', note=? WHERE id=?",
            (json.dumps(note), eid))
        self.s.commit()

    def _expire(self, wf, row, minute, ts):
        eid, cid, dim, control = row[0], row[1], row[2], row[3]
        wid = wf["workflow_id"]
        version, cur = self.g.current(wid)
        new = copy.deepcopy(cur)
        cur_alloc = new.get("allocations", {}).get(cid, {}).get(dim)
        if cur_alloc and set(cur_alloc) != {control}:
            new["allocations"][cid][dim] = {control: 1.0}
            self._change(wf, version, cur, new, "round_revert",
                         f"Experiment on {dim} (cohort {cid}) found no winner in"
                         f" {ROUND_MAX_MINUTES//1440} days; reverting to {control}",
                         {f"allocations.{cid}.{dim}": {control: 1.0}}, minute, ts)
        self.s.db.execute(
            "UPDATE experiments SET status='no_winner', decided_minute=? WHERE id=?",
            (minute, eid))
        self.s.commit()
        self.s.log_decision(minute, ts, wid, "experiment_no_winner",
                            f"{dim} cohort {cid}: no significant winner", {})

    # -- decay + rollback (C7) --------------------------------------------------
    def _decay_watch(self, wf, minute, ts):
        wid = wf["workflow_id"]
        rows = self.s.db.execute(
            "SELECT id, cohort_id, dim, winner, note FROM experiments"
            " WHERE workflow_id=? AND status='promoted'", (wid,)).fetchall()
        for eid, cid, dim, winner, note_json in rows:
            note = json.loads(note_json or "{}")
            if minute - note.get("promoted_minute", 0) < 1440:
                continue  # a promoted winner gets a day before decay judgement
            vstats = self.s.variant_stats(wid, dim, since_minute=minute - 1440,
                                          cohort_id=cid)
            agg = vstats.get(winner)
            if not agg:
                continue
            k, n = _kpi_pair(wf["objective"]["primary"], agg)
            if n < stats.MIN_ARM_SAMPLE:
                continue
            p, diff = stats.two_prop_ztest(k, n, note["baseline_k"], note["baseline_n"])
            if p < 0.05 and diff <= -stats.MIN_EFFECT:
                self._rollback(wf, eid, cid, dim, winner, note, minute, ts, diff)

    def _rollback(self, wf, eid, cid, dim, winner, note, minute, ts, diff):
        wid = wf["workflow_id"]
        version, cur = self.g.current(wid)
        new = copy.deepcopy(cur)
        back = note["rollback_to"]
        new.setdefault("allocations", {}).setdefault(cid, {})[dim] = {back: 1.0}
        summary = (f"Rollback {dim} for cohort {cid}: promoted {winner} decayed"
                   f" ({diff:+.3f} vs its experiment baseline, significant);"
                   f" restoring {back}")
        res = self._change(wf, version, cur, new, "rollback", summary,
                           {f"allocations.{cid}.{dim}": {back: 1.0}}, minute, ts)
        if res["status"] in ("pending", "applied"):
            self.s.db.execute(
                "UPDATE experiments SET status='rolled_back' WHERE id=?", (eid,))
            self.s.commit()
            self.s.log_decision(minute, ts, wid, "rollback", summary,
                                {"experiment_id": eid})

    def _cohort_share(self, wid, cid):
        total = self.s.cohort_lead_count(wid, cid)
        all_leads = self.s.db.execute(
            "SELECT COUNT(*) FROM leads WHERE workflow_id=?", (wid,)).fetchone()[0]
        return (total / all_leads) if all_leads else 0.0

    # -- supervisor edits --------------------------------------------------------
    def on_supervisor_edit(self, wf, minute, ts):
        """A supervisor edit touching a tested dimension invalidates that arm
        (Product: only what actually happened counts). We never overwrite
        their edit; a later round restarts from the new base."""
        wid = wf["workflow_id"]
        rows = self.s.db.execute(
            "SELECT id, cohort_id, dim FROM experiments WHERE workflow_id=?"
            " AND status IN ('running','proposed')", (wid,)).fetchall()
        for eid, cid, dim in rows:
            self.s.db.execute(
                "UPDATE experiments SET status='invalidated', note=?"
                " WHERE id=?", (json.dumps({"reason": "supervisor_edit"}), eid))
            self.s.log_decision(minute, ts, wid, "experiment_invalidated",
                                f"{dim} cohort {cid}: supervisor edited config"
                                " mid-experiment; arm invalidated, not overwritten", {})
        self.s.commit()
