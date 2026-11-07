"""C11 (partial) — consolidated supervisor view as a small JSON API.

One place, not fifty alerts (stakeholders/04): current KPIs, what's being
tested, what's winning, what's pending approval, what changed, per workflow.
Stdlib http.server only — no new dependency to defend. No UI (cut, recorded
in SUBMISSION §2); the same JSON is what a UI would render.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs


def start_view(store, port: int):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj, indent=1).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/status":
                self._json(_status(store))
            elif u.path == "/why":
                q = parse_qs(u.query)
                self._json(_why(store, q.get("workflow", [""])[0],
                                int(q.get("minute", [0])[0])))
            else:
                self._json({"error": "use /status or /why?workflow=<id>&minute=<sim_minute>"}, 404)

    server = HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _status(store):
    out = {}
    for (wid,) in store.db.execute("SELECT DISTINCT workflow_id FROM leads").fetchall():
        kpi = store.kpi(wid, since_minute=0)
        exps = store.db.execute(
            "SELECT cohort_id, dim, status, winner FROM experiments WHERE workflow_id=?",
            (wid,)).fetchall()
        props = store.db.execute(
            "SELECT kind, status, change_summary FROM proposals WHERE workflow_id=?"
            " AND status IN ('pending','approved')", (wid,)).fetchall()
        incs = store.db.execute(
            "SELECT kind, status FROM incidents WHERE workflow_id=?"
            " AND status IN ('active','responding')", (wid,)).fetchall()
        out[wid] = {
            "kpis_live": {
                "dials": kpi["dials"],
                "pickup_rate": (kpi["connected"] / kpi["dials"]) if kpi["dials"] else None,
                "engagement_rate": (kpi["engaged"] / kpi["connected"]) if kpi["connected"] else None},
            "experiments": [{"cohort": c, "dim": d, "status": s, "winner": w}
                            for c, d, s, w in exps],
            "pending_proposals": [{"kind": k, "status": s, "summary": sm}
                                  for k, s, sm in props],
            "open_incidents": [{"kind": k, "status": s} for k, s in incs]}
    return out


def _why(store, wid, minute):
    """Answer 'why did workflow X change at time T, who approved it, and what
    happened after?' from the audit store alone."""
    lo, hi = minute - 720, minute + 1440
    decisions = store.db.execute(
        "SELECT sim_minute, ts, kind, summary FROM decisions WHERE workflow_id=?"
        " AND sim_minute BETWEEN ? AND ? ORDER BY sim_minute", (wid, lo, hi)).fetchall()
    proposals = store.db.execute(
        "SELECT proposal_id, approval_id, kind, status, change_summary, impact_score"
        " FROM proposals WHERE workflow_id=? AND created_minute BETWEEN ? AND ?",
        (wid, lo, hi)).fetchall()
    return {"workflow_id": wid, "around_minute": minute,
            "decisions": [{"minute": m, "ts": t, "kind": k, "summary": s}
                          for m, t, k, s in decisions],
            "proposals": [{"proposal_id": p, "approval_id": a, "kind": k, "status": st,
                           "summary": sm, "impact_score": im}
                          for p, a, k, st, sm, im in proposals]}
