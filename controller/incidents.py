"""C5 — caller-ID health, and C8 — hallucination incident response.

Both detectors work on populations with minimum samples and significance
tests (constraint 5): one bad call, or one flagged call, never triggers
anything. Both keep a human-auditable trail in the incidents + decisions
tables, and both route changes through governance like everything else.
"""
import copy
import json

from . import stats
from .governance import changed_dims

ALL_DATA = -10 ** 9           # history lives at negative sim-minutes (pre-D0)

# C5 constants
CID_WINDOW_MIN = 720          # judge a caller ID on its last 12 sim-hours
CID_MIN_DIALS = 200
CID_ABS_DROP = 0.05           # and at least 5 points below its own baseline
CID_REL_DROP = 0.30           # or a 30% relative collapse
CID_EXPLORE_SHARE = 0.10      # keep 10% on a suspect ID to detect recovery
CID_COOLDOWN_MIN = 720

# C8 constants
HALL_WINDOW_MIN = 480         # last 8 sim-hours of connected calls
HALL_MIN_CONNECTED = 200
HALL_MIN_RATE = 0.02          # ignore noise floors below 2%
CREDIT_RESERVE = 15           # never plan spend that takes us below this
VALIDATION_N = 500            # costs ceil(500/100) = 5 credits


class Incidents:
    def __init__(self, client, store, gov):
        self.c, self.s, self.g = client, store, gov

    def tick(self, wf, minute, ts):
        self._caller_id_health(wf, minute, ts)
        self._hallucination_watch(wf, minute, ts)

    # ------------------------------------------------------------------ C5
    def _caller_id_health(self, wf, minute, ts):
        wid = wf["workflow_id"]
        recent = self.s.variant_stats(wid, "caller_id", since_minute=minute - CID_WINDOW_MIN)
        baseline = self.s.variant_stats(wid, "caller_id", since_minute=ALL_DATA)
        open_inc = self._open_incident(wid, "caller_id")
        for cid, agg in recent.items():
            base_dials = baseline.get(cid, {}).get("dials", 0) - agg["dials"]
            base_conn = baseline.get(cid, {}).get("connected", 0) - agg["connected"]
            if base_dials < CID_MIN_DIALS:
                continue
            r_base = base_conn / base_dials
            if open_inc and open_inc["detail"].get("caller_id") == cid:
                # Recovery is judged ONLY on dials made after the rotation,
                # on the small explore share — never on pre-rotation data —
                # and it needs real evidence: >=300 post-rotation dials within
                # 2pp of baseline. (public_02 run: a 100-dial / 95% bar
                # restored an ID that was still toxic; grade -0.465 pickup.)
                # An ID rotated twice is never auto-restored again.
                post = self.s.variant_stats(
                    wid, "caller_id", since_minute=open_inc["detected_minute"]).get(cid)
                if post and not open_inc["detail"].get("permanent") and \
                        post["dials"] >= 300 and \
                        post["connected"] / post["dials"] >= r_base - 0.02:
                    self._restore_caller_id(wf, open_inc, minute, ts)
                continue
            if agg["dials"] < CID_MIN_DIALS:
                continue
            r_recent = agg["connected"] / agg["dials"]
            p, diff = stats.two_prop_ztest(agg["connected"], agg["dials"], base_conn, base_dials)
            # Confirmation: BOTH halves of the window must be down. A single
            # pooled dip across hundreds of checks is how false rotations
            # happen; a real flagged ID stays down for the whole window.
            halves_down = True
            for h0, h1 in ((minute - CID_WINDOW_MIN, minute - CID_WINDOW_MIN // 2),
                           (minute - CID_WINDOW_MIN // 2, minute)):
                half = self.s.variant_stats(wid, "caller_id", since_minute=h0,
                                            until_minute=h1).get(cid)
                if not half or half["dials"] < 75 or \
                        half["connected"] / half["dials"] > r_base - 0.03:
                    halves_down = False
                    break
            degraded = halves_down and p < 0.001 and diff <= -CID_ABS_DROP
            if degraded:
                self._rotate_caller_id(wf, cid, r_recent, r_base, minute, ts)

    def _rotate_caller_id(self, wf, bad_id, r_recent, r_base, minute, ts):
        wid = wf["workflow_id"]
        version, cur = self.g.current(wid)
        new = copy.deepcopy(cur)
        cohorts = ["default"] + [c["id"] for c in new.get("cohorts", [])]
        changed = False
        originals = {}
        for cohort in cohorts:
            alloc = new.get("allocations", {}).get(cohort, {}).get("caller_id")
            if not alloc or bad_id not in alloc or alloc[bad_id] <= CID_EXPLORE_SHARE:
                continue
            originals[cohort] = dict(alloc)
            keep = CID_EXPLORE_SHARE
            others = {k: v for k, v in alloc.items() if k != bad_id}
            rest = sum(others.values())
            if rest <= 0:
                continue
            new["allocations"][cohort]["caller_id"] = {
                **{k: v / rest * (1 - keep) for k, v in others.items()}, bad_id: keep}
            changed = True
        if not changed:
            return
        summary = (f"Caller ID {bad_id} degraded: pickup {r_recent:.3f} vs its own"
                   f" baseline {r_base:.3f} over the last {CID_WINDOW_MIN//60}h;"
                   f" rotating it down to {int(CID_EXPLORE_SHARE*100)}% to detect recovery")
        res = self._route(wf, version, cur, new, "caller_id_rotation", summary, minute, ts)
        if res["status"] in ("pending", "applied"):
            prior_recovered = self.s.db.execute(
                "SELECT COUNT(*) FROM incidents WHERE workflow_id=? AND kind='caller_id'"
                " AND status='recovered' AND json_extract(detail,'$.caller_id')=?",
                (wid, bad_id)).fetchone()[0]
            self.s.db.execute(
                "INSERT INTO incidents (workflow_id, kind, detected_minute, detail, status)"
                " VALUES (?,?,?,?, 'active')",
                (wid, "caller_id", minute,
                 json.dumps({"caller_id": bad_id, "originals": originals,
                             "pickup_recent": r_recent, "pickup_baseline": r_base,
                             "permanent": prior_recovered > 0})))
            self.s.commit()
            self.s.log_decision(minute, ts, wid, "caller_id_rotated", summary, {})

    def _restore_caller_id(self, wf, incident, minute, ts):
        wid = wf["workflow_id"]
        version, cur = self.g.current(wid)
        new = copy.deepcopy(cur)
        for cohort, orig in incident["detail"].get("originals", {}).items():
            if cohort in new.get("allocations", {}):
                new["allocations"][cohort]["caller_id"] = orig
        if changed_dims(cur, new):
            summary = (f"Caller ID {incident['detail']['caller_id']} back within"
                       " 2pp of its baseline pickup on >=300 post-rotation dials;"
                       " restoring original share")
            res = self._route(wf, version, cur, new, "caller_id_restore", summary, minute, ts)
            if res["status"] not in ("pending", "applied"):
                return
        self.s.db.execute("UPDATE incidents SET status='recovered', resolved_minute=?"
                            " WHERE id=?", (minute, incident["id"]))
        self.s.commit()
        self.s.log_decision(minute, ts, wid, "caller_id_recovered",
                            f"caller ID {incident['detail']['caller_id']} restored", {})

    # ------------------------------------------------------------------ C8
    def _hallucination_watch(self, wf, minute, ts):
        wid = wf["workflow_id"]
        recent = self.s.hallucination_stats(wid, since_minute=minute - HALL_WINDOW_MIN)
        if recent["connected"] < HALL_MIN_CONNECTED:
            return
        alltime = self.s.hallucination_stats(wid, since_minute=ALL_DATA)
        base_n = alltime["connected"] - recent["connected"]
        base_h = alltime["flagged"] - recent["flagged"]
        if base_n < HALL_MIN_CONNECTED:
            return
        r_recent = recent["flagged"] / recent["connected"]
        r_base = base_h / base_n
        open_inc = self._open_incident(wid, "hallucination")
        if open_inc:
            self._verify_hallucination_fix(wf, open_inc, r_recent, r_base, minute, ts)
            return
        threshold = max(2 * r_base, r_base + 0.03, HALL_MIN_RATE)
        if r_recent >= threshold:
            self._respond_hallucination(wf, r_recent, r_base, minute, ts)

    def _respond_hallucination(self, wf, r_recent, r_base, minute, ts):
        wid = wf["workflow_id"]
        cur_prompt = self.g.current(wid)[1]["prompt_version"]
        detail = {"rate_recent": r_recent, "rate_baseline": r_base, "prompt": cur_prompt}
        cur = self.s.db.execute(
            "INSERT INTO incidents (workflow_id, kind, detected_minute, detail, status)"
            " VALUES (?,?,?,?, 'responding')", (wid, "hallucination", minute, json.dumps(detail)))
        inc_id = cur.lastrowid
        self.s.commit()
        self.s.log_decision(minute, ts, wid, "hallucination_detected",
                            f"hallucination flags at {r_recent:.3f} of connected calls"
                            f" vs baseline {r_base:.3f} (population threshold crossed)", detail)
        credits = self.c.state().get("credits_remaining", 0)
        if credits - 3 - (VALIDATION_N // 100) < CREDIT_RESERVE:
            self.s.log_decision(minute, ts, wid, "hallucination_no_credits",
                                "credit reserve would be breached; not spending", detail)
            return
        r = self.c.post("/llm/suggest-fixes",
                        {"workflow_id": wid,
                         "problem": f"hallucination flags rose to {r_recent:.3f} of connected"
                                    f" calls (baseline {r_base:.3f}) on prompt {cur_prompt}"})
        if r.status_code != 200:
            self.s.log_decision(minute, ts, wid, "hallucination_suggest_failed",
                                f"suggest-fixes -> HTTP {r.status_code}", detail)
            return
        suggestions = r.json().get("suggestions") or r.json().get("fixes") or []
        best = None
        for sgt in suggestions:
            pv = sgt.get("prompt_version") if isinstance(sgt, dict) else sgt
            if not pv or pv == cur_prompt:
                continue
            credits = self.c.state().get("credits_remaining", 0)
            if credits - (VALIDATION_N // 100) < CREDIT_RESERVE:
                break
            vr = self.c.post("/validation/runs",
                             {"workflow_id": wid, "prompt_version": pv, "n": VALIDATION_N})
            if vr.status_code != 200:
                continue
            v = vr.json()
            self.s.log_decision(minute, ts, wid, "validation_run",
                                f"validation of {pv}: pass_rate {v.get('pass_rate')}",
                                {"run_id": v.get("run_id") or v.get("validation_run_id"),
                                 "prompt_version": pv})
            if best is None or v["pass_rate"] > best["pass_rate"]:
                best = {"prompt_version": pv, "pass_rate": v["pass_rate"],
                        "run_id": v.get("run_id") or v.get("validation_run_id")}
        gate = wf["governance"]["min_validation_pass_rate"]
        if best is None or best["pass_rate"] < gate:
            self.s.db.execute("UPDATE incidents SET status='no_valid_fix' WHERE id=?",
                              (inc_id,))
            self.s.commit()
            self.s.log_decision(minute, ts, wid, "hallucination_no_valid_fix",
                                f"no suggested prompt passed the validation gate"
                                f" ({gate}); not proposing a prompt change", detail)
            return
        version, cur_cfg = self.g.current(wid)
        new = copy.deepcopy(cur_cfg)
        new["prompt_version"] = best["prompt_version"]
        summary = (f"Prompt fix for hallucination spike: {cur_prompt} ->"
                   f" {best['prompt_version']} (validated pass_rate"
                   f" {best['pass_rate']:.3f} >= {gate}; flags at {r_recent:.3f}"
                   f" vs baseline {r_base:.3f})")
        res = self.g.submit(wf, version, new, "prompt_fix", summary,
                            {"prompt_version": [cur_prompt, best["prompt_version"]]},
                            self.s.cohort_lead_count(wid, "default"),
                            {"validation": best}, 0.9, summary, minute, ts,
                            evidence={"validation_run_id": best["run_id"]})
        detail["fix_prompt"] = best["prompt_version"]
        detail["proposal"] = res["status"]
        self.s.db.execute("UPDATE incidents SET detail=? WHERE id=?",
                          (json.dumps(detail), inc_id))
        self.s.commit()

    def _verify_hallucination_fix(self, wf, incident, r_recent, r_base, minute, ts):
        if incident["status"] != "responding":
            return
        detail = incident["detail"]
        # fixed when the recent rate is back near baseline
        if r_recent < max(1.5 * r_base, r_base + 0.015):
            self.s.db.execute(
                "UPDATE incidents SET status='resolved', resolved_minute=? WHERE id=?",
                (minute, incident["id"]))
            self.s.commit()
            self.s.log_decision(minute, ts, wf["workflow_id"], "hallucination_resolved",
                                f"flag rate back to {r_recent:.3f} (baseline {r_base:.3f});"
                                f" time-to-fix {minute - incident['detected_minute']} sim-min",
                                detail)

    # ------------------------------------------------------------------ util
    def _route(self, wf, version, cur, new, kind, summary, minute, ts):
        from .governance import auto_apply_permitted
        ok, _ = auto_apply_permitted(wf, cur, new)
        if ok:
            return self.g.auto_apply(wf, version, new, summary, minute, ts)
        return self.g.submit(wf, version, new, kind, summary,
                             {"change": summary}, self.s.cohort_lead_count(wf["workflow_id"], "default"),
                             {"note": "incident response"}, 0.8, summary, minute, ts)

    def _open_incident(self, wid, kind):
        row = self.s.db.execute(
            "SELECT id, detected_minute, detail, status FROM incidents WHERE workflow_id=?"
            " AND kind=? AND status IN ('active','responding') ORDER BY id DESC LIMIT 1",
            (wid, kind)).fetchone()
        if not row:
            return None
        return {"id": row[0], "detected_minute": row[1],
                "detail": json.loads(row[2]), "status": row[3]}
