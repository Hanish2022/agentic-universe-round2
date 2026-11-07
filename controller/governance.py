"""C9 — governance client, and C10 — honest impact / dry-run computation.

Every config change the controller makes goes through here: either the
approval path (POST /approvals -> poll -> POST apply) or a policy-permitted
auto-apply (PUT /config). Nothing else in the codebase touches config.

Lifecycle handled: pending -> approved -> applied; rejected; expired
(= a rejection, per Product: re-queue with fresh data, never resubmit stale);
approved -> lapsed (apply window missed); 409 stale_base_version at submit or
apply time (a supervisor edit moved the base) -> rebuild on the new base and
re-propose; 409 duplicate_proposal_id (we crashed after submitting) ->
reconcile from GET /approvals instead of double-submitting.
"""
import copy
import hashlib
import json

ALLOC_DIMS = ("welcome_message", "voice", "caller_id")


def tv_distance(p: dict, q: dict) -> float:
    keys = set(p) | set(q)
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in keys)


def changed_dims(cur: dict, new: dict):
    """Which governance dimensions differ between two configs."""
    dims = set()
    if cur.get("cohorts", []) != new.get("cohorts", []):
        dims.add("cohorts")
    if cur.get("prompt_version") != new.get("prompt_version"):
        dims.add("prompt_version")
    if cur.get("schedule", {}) != new.get("schedule", {}):
        dims.add("schedule")
    cur_a, new_a = cur.get("allocations", {}), new.get("allocations", {})
    for cohort in set(cur_a) | set(new_a):
        for dim in ALLOC_DIMS:
            if cur_a.get(cohort, {}).get(dim) != new_a.get(cohort, {}).get(dim):
                dims.add(dim)
    return dims


def auto_apply_permitted(wf: dict, cur: dict, new: dict):
    """(ok, reasons). Mirrors the contract in docs/SIMULATOR.md §4.2 exactly:
    policy enabled, every changed dim allowed, and no cohort distribution on
    an allocation dim moves by more than max_shift (total variation)."""
    pol = wf["governance"]["auto_apply"]
    if not pol["enabled"]:
        return False, ["auto_apply disabled by policy"]
    dims = changed_dims(cur, new)
    reasons = []
    not_allowed = dims - set(pol["allowed_dims"])
    if not_allowed:
        reasons.append(f"dims not auto-applyable: {sorted(not_allowed)}")
    for cohort in set(cur.get("allocations", {})) | set(new.get("allocations", {})):
        for dim in ALLOC_DIMS:
            p = cur.get("allocations", {}).get(cohort, {}).get(dim)
            q = new.get("allocations", {}).get(cohort, {}).get(dim)
            if p is not None and q is not None and tv_distance(p, q) > pol["max_shift"] + 1e-9:
                reasons.append(f"{cohort}.{dim} shift {tv_distance(p, q):.2f} > max {pol['max_shift']}")
    return (not reasons), reasons


def dry_run(rates: dict, proposed_mix: dict, current_mix: dict):
    """C10 dry run: replay the proposed allocation over measured per-variant
    rates (from this workflow's own historical/live cohort data). Returns the
    expected metric under the proposed mix vs the current mix. Honest by
    construction: it is exactly the weighted average of observed rates, and
    variants with no observations contribute their current-mix weight's rate
    of the control — flagged via `unmeasured`."""
    def expected(mix):
        tot_w, tot, unmeasured = 0.0, 0.0, 0.0
        for variant, w in mix.items():
            if w <= 0:
                continue
            tot_w += w
            if variant in rates:
                tot += w * rates[variant]
            else:
                unmeasured += w
        return (tot / tot_w if tot_w else None), unmeasured
    exp_new, unm_new = expected(proposed_mix)
    exp_cur, _ = expected(current_mix)
    return {"expected_rate_proposed": exp_new, "expected_rate_current": exp_cur,
            "unmeasured_weight": unm_new,
            "basis": "weighted average of this workflow's observed per-variant rates"}


def impact_score(expected_lift: float, affected_share: float) -> float:
    """[0,1]. A 10-point expected lift over the whole workflow scores ~1;
    small lifts on small cohorts score low. Deliberately ungenerous: the
    supervisor's queue is ranked by this number, so it has to mean something."""
    return round(max(0.0, min(1.0, (expected_lift / 0.10) * affected_share)), 3)


class Governance:
    def __init__(self, client, store):
        self.c = client
        self.s = store

    # -- config snapshots ----------------------------------------------------
    def snapshot(self, wid, version, actor, minute, config):
        self.s.db.execute(
            "INSERT OR IGNORE INTO config_versions VALUES (?,?,?,?,?)",
            (wid, version, actor, minute, json.dumps(config)))
        self.s.commit()

    def current(self, wid):
        r = self.c.config(wid)
        return r["version"], r["config"]

    # -- submission ----------------------------------------------------------
    def proposals_last_24h(self, wid, minute):
        row = self.s.db.execute(
            "SELECT COUNT(*) FROM proposals WHERE workflow_id=? AND created_minute>?",
            (wid, minute - 1440)).fetchone()
        return row[0]

    def submit(self, wf, base_version, new_config, kind, summary, diff,
               affected_leads, dry, impact, rationale, minute, ts, evidence=None):
        wid = wf["workflow_id"]
        # Batching discipline (C9): the approver rejects anything beyond
        # max_requests_per_24h anyway, so defer non-urgent kinds instead of
        # burning a request slot. Prompt fixes (incidents) always go through.
        if kind != "prompt_fix" and \
                self.proposals_last_24h(wid, minute) >= wf["governance"]["max_requests_per_24h"]:
            self.s.log_decision(minute, ts, wid, "proposal_deferred_cap",
                                f"{kind} deferred: 24h request cap reached", {})
            return {"status": "deferred_cap", "proposal_id": None}
        digest = hashlib.sha1(json.dumps(new_config, sort_keys=True).encode()).hexdigest()[:10]
        proposal_id = f"{wid}:{kind}:{base_version}:{digest}"
        existing = self.s.db.execute(
            "SELECT status FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
        if existing:
            return {"status": "duplicate_local", "proposal_id": proposal_id}
        body = {"proposal_id": proposal_id, "workflow_id": wid,
                "base_version": base_version, "proposed_config": new_config,
                "change_summary": summary, "diff": diff,
                "affected_leads": int(affected_leads), "dry_run": dry,
                "impact_score": impact, "rationale": rationale,
                "expires_in_hours": wf["governance"]["proposal_ttl_hours"]}
        if evidence:
            body["evidence"] = evidence
        r = self.c.submit_approval(body)
        if r.status_code == 200:
            aid = r.json()["approval_id"]
            self._record(proposal_id, wid, aid, base_version, kind, "pending",
                         new_config, summary, impact, affected_leads, minute)
            self.s.log_decision(minute, ts, wid, "proposal_submitted", summary,
                                {"proposal_id": proposal_id, "approval_id": aid,
                                 "kind": kind, "impact_score": impact})
            return {"status": "pending", "proposal_id": proposal_id, "approval_id": aid}
        if r.status_code == 409 and "duplicate_proposal_id" in r.text:
            # We submitted this before a crash and never recorded it. Reconcile.
            aid = self._find_approval_id(wid, proposal_id)
            if aid:
                self._record(proposal_id, wid, aid, base_version, kind, "pending",
                             new_config, summary, impact, affected_leads, minute)
                return {"status": "pending", "proposal_id": proposal_id, "approval_id": aid}
        self.s.log_decision(minute, ts, wid, "proposal_failed",
                            f"{summary} -> HTTP {r.status_code}",
                            {"proposal_id": proposal_id, "response": r.text[:300]})
        return {"status": "failed", "proposal_id": proposal_id,
                "http": r.status_code, "body": r.text[:300]}

    def _record(self, pid, wid, aid, base_version, kind, status, config,
                summary, impact, affected, minute):
        self.s.db.execute(
            "INSERT OR REPLACE INTO proposals (proposal_id, workflow_id, approval_id,"
            " base_version, kind, status, proposed_config, change_summary,"
            " impact_score, affected_leads, created_minute) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (pid, wid, aid, base_version, kind, status, json.dumps(config),
             summary, impact, affected, minute))
        self.s.commit()

    def _find_approval_id(self, wid, proposal_id):
        r = self.c.list_approvals(wid)
        if r.status_code != 200:
            return None
        for a in r.json():
            if a.get("proposal_id") == proposal_id:
                return a.get("approval_id") or a.get("id")
        return None

    # -- auto-apply ------------------------------------------------------------
    def auto_apply(self, wf, base_version, new_config, rationale, minute, ts):
        wid = wf["workflow_id"]
        digest = hashlib.sha1(json.dumps(new_config, sort_keys=True).encode()).hexdigest()[:10]
        body = {"proposal_id": f"{wid}:auto:{base_version}:{digest}",
                "base_version": base_version, "proposed_config": new_config,
                "rationale": rationale}
        r = self.c.put_config(wid, body)
        if r.status_code == 200:
            version = r.json().get("version", base_version + 1)
            self.snapshot(wid, version, "controller_auto", minute, new_config)
            self.s.log_decision(minute, ts, wid, "auto_applied", rationale,
                                {"version": version})
            return {"status": "applied", "version": version}
        self.s.log_decision(minute, ts, wid, "auto_apply_failed",
                            f"{rationale} -> HTTP {r.status_code}",
                            {"response": r.text[:300]})
        return {"status": "failed", "http": r.status_code, "body": r.text[:300]}

    # -- polling / applying ----------------------------------------------------
    def poll_open_proposals(self, wid, minute, ts):
        """Advance every non-terminal proposal for one workflow. Applies
        approved changes immediately (the apply window is short). Returns a
        list of (proposal_row, new_status) transitions."""
        rows = self.s.db.execute(
            "SELECT proposal_id, approval_id, status FROM proposals"
            " WHERE workflow_id=? AND status IN ('pending','approved')",
            (wid,)).fetchall()
        transitions = []
        for pid, aid, _st in rows:
            if not aid:
                continue
            r = self.c.get_approval(aid)
            if r.status_code != 200:
                continue
            status = r.json().get("status")
            if status == "approved":
                ar = self.c.apply_approval(wid, aid)
                if ar.status_code == 200:
                    version = ar.json().get("version")
                    cfg = json.loads(self.s.db.execute(
                        "SELECT proposed_config FROM proposals WHERE proposal_id=?",
                        (pid,)).fetchone()[0])
                    self.snapshot(wid, version, "controller_approved", minute, cfg)
                    self._set_status(pid, "applied", minute)
                    self.s.log_decision(minute, ts, wid, "change_applied",
                                        f"approved change applied (approval {aid})",
                                        {"proposal_id": pid, "version": version})
                    transitions.append((pid, "applied"))
                elif ar.status_code == 410:
                    self._set_status(pid, "lapsed", minute)
                    self.s.log_decision(minute, ts, wid, "proposal_lapsed",
                                        f"approval {aid} lapsed before apply",
                                        {"proposal_id": pid})
                    transitions.append((pid, "lapsed"))
                elif ar.status_code == 409:
                    self._set_status(pid, "stale", minute)
                    self.s.log_decision(minute, ts, wid, "proposal_stale_at_apply",
                                        f"base moved under approval {aid}; will re-propose",
                                        {"proposal_id": pid})
                    transitions.append((pid, "stale"))
            elif status in ("rejected", "expired"):
                self._set_status(pid, status, minute)
                self.s.log_decision(minute, ts, wid, f"proposal_{status}",
                                    f"approval {aid} {status}: {r.json().get('reasons')}",
                                    {"proposal_id": pid})
                transitions.append((pid, status))
        return transitions

    def _set_status(self, pid, status, minute):
        self.s.db.execute(
            "UPDATE proposals SET status=?, decided_minute=? WHERE proposal_id=?",
            (status, minute, pid))
        self.s.commit()

    def open_proposals(self, wid):
        rows = self.s.db.execute(
            "SELECT COUNT(*) FROM proposals WHERE workflow_id=? AND status IN ('pending','approved')",
            (wid,)).fetchone()
        return rows[0]

    def reconcile(self, wid, minute):
        """After a restart: pull the simulator's view of our proposals and
        repair local state (crash between submit and record, or between
        decision and our poll)."""
        r = self.c.list_approvals(wid)
        if r.status_code != 200:
            return
        for a in r.json():
            pid = a.get("proposal_id")
            if not pid:
                continue
            local = self.s.db.execute(
                "SELECT status FROM proposals WHERE proposal_id=?", (pid,)).fetchone()
            if local is None:
                self.s.db.execute(
                    "INSERT INTO proposals (proposal_id, workflow_id, approval_id,"
                    " base_version, kind, status, proposed_config, change_summary,"
                    " impact_score, affected_leads, created_minute)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (pid, wid, a.get("approval_id") or a.get("id"), a.get("base_version"),
                     "reconciled", a.get("status"), json.dumps(a.get("proposed_config", {})),
                     a.get("change_summary", ""), a.get("impact_score"),
                     a.get("affected_leads"), minute))
            elif local[0] in ("pending", "approved") and a.get("status") not in ("pending",):
                self._set_status(pid, a.get("status"), minute)
        self.s.commit()
