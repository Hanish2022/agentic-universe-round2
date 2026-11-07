"""Controller entry point.

    python -m controller.main --url http://127.0.0.1:8700 [--step 30]

Runs until the scenario finishes. All durable state is in one SQLite file
per scenario under controller_state/; killing and restarting this process
resumes from the store (C13): ingestion checkpoints, open proposals are
reconciled with the simulator, experiments continue from their rows.

Loop per iteration (sim time is free — nothing happens between advances):
  advance -> ingest new chunks -> poll/apply proposals -> incidents ->
  experiments -> call-time optimisation -> metrics line (C14).
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

from .client import SimClient
from .cohorts import CohortSet
from .experiments import Experiments
from .governance import Governance
from .incidents import Incidents
from .ingest import Ingestor
from .store import Store
from . import schedule_opt, view

ALL_DATA = -10 ** 9


def log(obj):
    print(json.dumps(obj), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--step", type=int, default=30, help="sim minutes per advance")
    ap.add_argument("--db", default=None)
    ap.add_argument("--state-dir", default="controller_state")
    ap.add_argument("--view-port", type=int, default=8799)
    a = ap.parse_args()

    client = SimClient(a.url)
    state = client.state()
    scenario = state["scenario"]
    epoch = datetime.fromisoformat(state["ts"]) - timedelta(minutes=state["sim_minute"])

    os.makedirs(a.state_dir, exist_ok=True)
    db_path = a.db or os.path.join(a.state_dir, f"{scenario}.db")
    store = Store(db_path)
    # New world under the same scenario name? Our checkpoint is ahead of the
    # simulator -> this DB belongs to a dead world. Archive and start fresh.
    prev_minute = int(store.get_meta("sim_minute", "-1"))
    if prev_minute > state["sim_minute"]:
        store.db.close()
        os.rename(db_path, f"{db_path}.bak-{int(time.time())}")
        store = Store(db_path)
        prev_minute = -1
    store.set_meta("sim_minute", state["sim_minute"])

    gov = Governance(client, store)
    exps = Experiments(client, store, gov)
    incs = Incidents(client, store, gov)

    workflows = {w["workflow_id"]: w for w in client.workflows()}

    # Supervisor edits (and any config change) arrive as events; snapshot and,
    # when they touch a dimension under test, invalidate that experiment arm.
    def on_config_changed(ev, minute):
        wid = ev["workflow_id"]
        version, cfg = gov.current(wid)
        gov.snapshot(wid, version, ev.get("actor", "?"), minute, cfg)
        if ev.get("actor") == "supervisor":
            store.log_decision(minute, ev["ts"], wid, "supervisor_edit",
                               f"supervisor changed {ev.get('changed_dims')}",
                               {"version": version})
            if set(ev.get("changed_dims") or []) & {"cohorts", "welcome_message", "voice"}:
                exps.on_supervisor_edit(workflows[wid], minute, ev["ts"])

    ing = Ingestor(client, store, epoch, on_config_changed=on_config_changed)

    # --- reconcile + snapshot current configs (crash safety, C13) ----------
    for wid, wf in workflows.items():
        gov.reconcile(wid, state["sim_minute"])
        version, cfg = gov.current(wid)
        gov.snapshot(wid, version, "observed", state["sim_minute"], cfg)

    # --- C3: bootstrap from pre-D0 history ----------------------------------
    hist_chunks = [ch["chunk"] for ch in client.chunk_list("history", after=-1)]
    if not store.get_meta("cohorts_built"):
        for n in hist_chunks:
            ing.ingest_chunk(n, "history", leads_only=True)
        cohortsets = {}
        for wid in workflows:
            cs = CohortSet(store.lead_cells(wid))
            cohortsets[wid] = cs
            for (ab, lang), cid in _cell_map(cs).items():
                store.db.execute(
                    "UPDATE leads SET cohort_id=? WHERE workflow_id=? AND age_band=?"
                    " AND lang=?", (cid, wid, ab, lang))
            store.log_decision(0, state["ts"], wid, "cohorts_built",
                               f"cohorts from history: {cs.ids}", {})
        store.commit()
        store.set_meta("cohort_defs",
                       json.dumps({wid: cs.config_cohorts() for wid, cs in cohortsets.items()}))
        store.set_meta("cohorts_built", "1")
    else:
        cohortsets = {}
        saved = json.loads(store.get_meta("cohort_defs", "{}"))
        for wid in workflows:
            cs = CohortSet(store.lead_cells(wid))
            cohortsets[wid] = cs  # deterministic rebuild == saved defs
    ing.cohortsets = cohortsets

    done_hist = int(store.get_meta("hist_calls_chunk", "-1"))
    for n in hist_chunks:
        if n > done_hist:
            ing.ingest_chunk(n, "history")
            store.set_meta("hist_calls_chunk", n)
    if not store.get_meta("bootstrapped"):
        for wid in workflows:
            k = store.kpi(wid, since_minute=ALL_DATA)
            store.log_decision(
                0, state["ts"], wid, "bootstrap",
                f"history baseline: {k['dials']} dials, pickup"
                f" {k['connected']/max(1,k['dials']):.3f}, engagement"
                f" {k['engaged']/max(1,k['connected']):.3f}", k)
        store.set_meta("bootstrapped", "1")

    if a.view_port:
        view.start_view(store, a.view_port)

    # --- start experiment rounds where none are active ----------------------
    minute = state["sim_minute"]
    ts = state["ts"]
    for wid, wf in workflows.items():
        _maybe_start_round(store, exps, wf, cohortsets[wid], minute, ts)

    # --- main loop -----------------------------------------------------------
    last_chunk = int(store.get_meta("last_event_chunk", "-1"))
    while True:
        r = client.advance(a.step)
        if r.status_code == 409:
            break
        st = r.json()
        minute, ts = st["sim_minute"], st["ts"]
        store.set_meta("sim_minute", minute)
        ingested = 0
        for ch in client.chunk_list("events", after=last_chunk):
            ingested += ing.ingest_chunk(ch["chunk"], "events")
            last_chunk = ch["chunk"]
            store.set_meta("last_event_chunk", last_chunk)
        for wid, wf in workflows.items():
            gov.poll_open_proposals(wid, minute, ts)
            _maybe_restart_round(store, exps, wf, cohortsets[wid], minute, ts)
            _maybe_start_round(store, exps, wf, cohortsets[wid], minute, ts)
            incs.tick(wf, minute, ts)
            exps.tick(wf, cohortsets[wid], minute, ts)
            schedule_opt.maybe_optimise(client, store, gov, wf, cohortsets[wid], minute, ts)
        credits = client.state().get("credits_remaining")
        n_dec = store.db.execute(
            "SELECT COUNT(*) FROM decisions WHERE sim_minute>=?", (minute - 60,)).fetchone()[0]
        store.db.execute(
            "INSERT INTO metrics VALUES (?,?,?,?,?,?)",
            (minute, datetime.now().isoformat(), ingested, None, credits, n_dec))
        store.commit()
        log({"sim_minute": minute, "ts": ts, "ingested": ingested,
             "credits_remaining": credits, "decisions_last_hour": n_dec})
        if st.get("finished"):
            break

    for wid in workflows:
        k = store.kpi(wid, since_minute=0)
        store.log_decision(minute, ts, wid, "run_complete",
                           f"live totals: {k['dials']} dials,"
                           f" pickup {k['connected']/max(1,k['dials']):.3f},"
                           f" engagement {k['engaged']/max(1,k['connected']):.3f}", k)
    log({"done": True, "scenario": scenario})
    return 0


def _cell_map(cs: CohortSet):
    return {(w["age_band"], w["lang"]): cid for cid, w in cs.defs}


def _maybe_start_round(store, exps, wf, cohortset, minute, ts):
    """Start a round when nothing is active and we haven't tried in the last
    6 sim-hours (a rejected setup gets retried on a fresh base, not lost)."""
    wid = wf["workflow_id"]
    active = store.db.execute(
        "SELECT COUNT(*) FROM experiments WHERE workflow_id=? AND status IN"
        " ('proposed','running','won','promoted')", (wid,)).fetchone()[0]
    if active:
        return
    last_try = store.db.execute(
        "SELECT MAX(sim_minute) FROM decisions WHERE workflow_id=? AND kind IN"
        " ('experiment_started','experiment_setup_failed')", (wid,)).fetchone()[0]
    if last_try is not None and minute - last_try < 360:
        return
    rounds = store.db.execute(
        "SELECT COUNT(*) FROM decisions WHERE workflow_id=? AND kind='experiment_started'",
        (wid,)).fetchone()[0]
    if rounds >= 2:
        return  # two rounds per workflow per scenario: re-testing the same
        # dimensions all week inflates false winners and churns approvers
    exps.start_round(wf, cohortset, minute, ts)


def _maybe_restart_round(store, exps, wf, cohortset, minute, ts):
    """A setup proposal that was rejected/expired/stale leaves experiment rows
    stuck at 'proposed'. Abandon them and start a fresh round on the new base
    (Product: an expired proposal is a rejection — re-queue with fresh data)."""
    wid = wf["workflow_id"]
    stuck = store.db.execute(
        "SELECT COUNT(*) FROM experiments WHERE workflow_id=? AND status='proposed'",
        (wid,)).fetchone()[0]
    if not stuck:
        return
    live = store.db.execute(
        "SELECT COUNT(*) FROM proposals WHERE workflow_id=? AND kind='experiment_setup'"
        " AND status IN ('pending','approved','applied')", (wid,)).fetchone()[0]
    if live:
        return
    store.db.execute(
        "UPDATE experiments SET status='abandoned' WHERE workflow_id=? AND status='proposed'",
        (wid,))
    store.commit()
    store.log_decision(minute, ts, wid, "experiment_setup_failed",
                       "setup proposal did not apply; restarting round on fresh base", {})
    exps.start_round(wf, cohortset, minute, ts)


if __name__ == "__main__":
    sys.exit(main())
